import csv
import math
import os
import random
import re
import time


from kik.messages import TextMessage, SuggestedResponseKeyboard

from modules.character_persistent_class import CharacterPersistentClass
from modules.kik_user import User
from modules.message_controller import MessageController, MessageCommand, MessageParam
from datetime import timedelta

def parse_work_string(time_str, regex_str):
    regex = re.compile(regex_str)
    parts = regex.match(time_str.strip())
    if parts is None:
        return None, 0
    parts = parts.groupdict()
    time_params = {}
    stat_points = 0
    for (name, param) in parts.items():
        if param and name in ["hours", "minutes"]:
            time_params[name] = int(param)
        if param and name == "stat_points":
            stat_points = int(param)
    return timedelta(**time_params), stat_points


def work(timedelta: timedelta, difficulty, stat_points, response_messages, message):
    minutes = timedelta.total_seconds()/60
    appendix = ""
    if difficulty == 1:
        claw_per_minute = 0.125
    elif difficulty == 2:
        # 1/288*(x + 1/2)² + 7/128
        claw_per_minute = 1 / 288 * pow(int(stat_points) + 1 / 2, 2) + 7 / 128
    else:
        # 1/240*(x + 3)² - 1/240
        claw_per_minute = 1 / 240 * pow(int(stat_points) + 3, 2) - 1 / 240
        hours_bocked = math.ceil(minutes / 60) + random.randint(0, math.ceil(minutes / 60))
        appendix = " und bist für {} Stunde(n) erschöpft. Du kannst in der Zeit weder arbeiten noch kämpfen.".format(hours_bocked)

    result = math.ceil(claw_per_minute*minutes)+random.randint(0, math.ceil(claw_per_minute*minutes))
    response_messages.append(TextMessage(
        to=message.from_user,
        chat_id=message.chat_id,
        body="*Du erhältst für deine Arbeit {} Krallen{}*".format(result, appendix),
        keyboards=[]
    ))
    return response_messages


class CharacterStats:

    CONST_STATS = {
        1: {"de": "Stärke", "en": "strength"},
        2: {"de": "Wahrnehmung", "en": "perception"},
        3: {"de": "Ausdauer", "en": "endurance"},
        4: {"de": "Charisma", "en": "charisma"},
        5: {"de": "Wissen", "en": "knowledge"},
        6: {"de": "Magie", "en": "magic"},
        7: {"de": "Geschicklichkeit", "en": "agility"},
    }

    def __init__(self, db_stats):
        self.db_stats = db_stats

    def get_stat_by_id(self, stat_id):
        return int(self.db_stats["stat_"+str(int(stat_id))])

    def get_exp(self):
        return int(self.db_stats["exp"])/100

    def get_used_exp(self):

        used_exp = 0
        for stat_id in range(1,8):
            stat_points = self.get_stat_by_id(stat_id)
            used_exp += CharacterStats.needed_exp_for_stat_points(stat_points)
        return used_exp

    def get_available_exp(self):
        return self.get_exp() - self.get_used_exp()

    def gen_stat_message(self, lang):
        stat_names = self.get_stat_names(lang)
        message = ""
        
        ava_exp = math.floor(self.get_available_exp())
        if ava_exp != 0:
            message += "Erfahrungspunkte verfügbar: {}\n---\n\n".format(ava_exp)
        
        for stat_id, stat_name in stat_names.items():
            stat_points = self.get_stat_by_id(stat_id)
            message += "{stat_name}:\n|{stat_blocks_black}{stat_blocks_white}| {stat_points:2d}\n\n".format(
                stat_name=stat_name,
                stat_points=stat_points,
                stat_blocks_black="█" * stat_points,
                stat_blocks_white="░" * (10-stat_points)
            )
        return message

    @staticmethod
    def get_all_stat_names(lang):
        all_names = set()
        for stat_id, names in CharacterStats.CONST_STATS.items():
            all_names.add(names["de"].lower())
            all_names.add(names["en"].lower())
            if lang in names:
                all_names.add(names[lang].lower())

        return all_names

    @staticmethod
    def get_stat_names(lang):
        all_names = {}
        for stat_id, names in CharacterStats.CONST_STATS.items():
            if lang in names:
                all_names[stat_id] = names[lang]
            else:
                all_names[stat_id] = names["de"]
        return all_names

    @staticmethod
    def get_stat_text(stat_id, stat_points):
        if stat_points == 0:
            return None

        with open(os.path.dirname(os.path.realpath(__file__)) + '/rpghelper_stat_texts.csv', 'r') as csv_file:
            stat_texts = csv.DictReader(csv_file, delimiter=";", quotechar="\"")
            rows = []
            for row in stat_texts:
                rows.append(row)

            text = rows[stat_points-1][str(int(stat_id))]
            if rows[11][str(int(stat_id))] != "":
                text += "\n\n"+rows[11][str(int(stat_id))]

            return text

    @staticmethod
    def stat_id_from_name(name, lang):
        for stat_id, names in CharacterStats.CONST_STATS.items():
            if names["de"].lower() == name.lower() or names["en"].lower() == name.lower() or (lang in names and names[lang].lower() == name.lower()):
                return stat_id
        return None

    @staticmethod
    def needed_exp_for_stat_points(stat_points):
        if stat_points <= 8:
            return stat_points
        elif stat_points == 9:
            return stat_points + 1
        else:
            return stat_points + 2

    @staticmethod
    def init_empty(user_id, char_id):
        return CharacterStats({
            "user_id": user_id,
            "char_id": char_id,
            "stat_1": 0,
            "stat_2": 0,
            "stat_3": 0,
            "stat_4": 0,
            "stat_5": 0,
            "stat_6": 0,
            "stat_7": 0,
            "id": None,
            "deleted": None,
            "exp": 3000
        })


class ModuleCharacterPersistentClass(CharacterPersistentClass):
    
    def set_char_stat(self, user_id, stat_id, stat_num, char_id=None):
        self.connect_database()

        if char_id is None:
            char_id = self.get_first_char_id(user_id)

        char = self.get_char(user_id, char_id)
        if char is None:
            return None

        stats = self.get_char_stats(user_id, char_id)
        if stats is None:
            self.cursor.execute((
                "INSERT INTO character_stats "
                "(user_id, char_id, stat_1, stat_2, stat_3, stat_4, stat_5, stat_6, stat_7) "
                "VALUES (?, ?, ?, ? , ?, ?, ?, ?, ?) "
            ), [
                user_id,
                int(char_id),
                0 if stat_id != 1 else int(stat_num),
                0 if stat_id != 2 else int(stat_num),
                0 if stat_id != 3 else int(stat_num),
                0 if stat_id != 4 else int(stat_num),
                0 if stat_id != 5 else int(stat_num),
                0 if stat_id != 6 else int(stat_num),
                0 if stat_id != 7 else int(stat_num),
            ])
        else:
            self.cursor.execute((
                "UPDATE character_stats "
                "SET {} = ? "
                "WHERE user_id LIKE ? AND char_id=? AND deleted IS NULL "
            ).format("stat_"+str(int(stat_id))), [stat_num, user_id, char_id])

        return self.get_char_stats(user_id, char_id)

    def get_char_stats(self, user_id, char_id=None):
        self.connect_database()

        if char_id is None:
            char_id = self.get_first_char_id(user_id)

        self.cursor.execute((
            "SELECT * "
            "FROM character_stats "
            "WHERE user_id LIKE ? AND char_id=? AND deleted IS NULL "
            "LIMIT 1"
        ), [user_id, char_id])

        return self.cursor.fetchone()

    def move_char(self, from_user_id, to_user_id, from_char_id=None):
        self.connect_database()

        if from_char_id is None:
            from_char_id = self.get_min_char_id()

        to_char_id = CharacterPersistentClass.move_char(self, from_user_id, to_user_id, from_char_id)

        data = (to_user_id, to_char_id, from_user_id, from_char_id)
        self.cursor.execute((
            "UPDATE character_stats "
            "SET user_id=?, char_id=? "
            "WHERE user_id LIKE ? AND char_id=?"
        ), data)

        return to_char_id

    def remove_char(self, user_id, deletor_id, char_id=None):
        self.connect_database()

        if char_id is None:
            char_id = self.get_min_char_id()

            CharacterPersistentClass.remove_char(user_id, deletor_id, char_id)

        data = (int(time.time()), user_id, char_id)
        self.cursor.execute((
            "UPDATE character_stats "
            "SET deleted=? "
            "WHERE user_id LIKE ? AND char_id=?"
        ), data)


class ModuleMessageController(MessageController):

    def __init__(self, bot_username, config_file):
        MessageController.__init__(self, bot_username, config_file)
        self.character_persistent_class = ModuleCharacterPersistentClass(self.config)


@ModuleMessageController.add_method({"de": "leichte-arbeit", "en": "easy-work", "_alts": []})
def easy_msg_work(self, message: TextMessage, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 1)) != 2:
        response_messages.append(ModuleMessageController.get_error_response(message))
        return response_messages, user_command_status, user_command_status_data

    timedelta, stat_points = parse_work_string(message_body.split(None, 1)[1], r'^((?P<hours>\d+?)\s*?(h|Stunden|Std))?\s*?((?P<minutes>\d+?)\s*?(m|min|Minuten)?)?$')
    if timedelta is None or timedelta.total_seconds() == 0:
        response_messages.append(ModuleMessageController.get_error_response(message))
        return response_messages, user_command_status, user_command_status_data

    return work(timedelta, 1, 0, response_messages, message), user_command_status, user_command_status_data


@ModuleMessageController.add_method({"de": "mittlere-arbeit", "en": "medium-work", "_alts": ["mittelschwere-arbeit"]})
def med_msg_work(self, message: TextMessage, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 1)) != 2:
        response_messages.append(ModuleMessageController.get_error_response(message))
        return response_messages, user_command_status, user_command_status_data

    timedelta, stat_points = parse_work_string(message_body.split(None, 1)[1], r'^((?P<hours>\d+?)\s*?(h|Stunden|Std))?\s*?((?P<minutes>\d+?)\s*?(m|min|Minuten)?)?\s*(?P<stat_points>\d)$')
    if timedelta is None or timedelta.total_seconds() == 0:
        response_messages.append(ModuleMessageController.get_error_response(message))
        return response_messages, user_command_status, user_command_status_data

    return work(timedelta, 2, stat_points, response_messages, message), user_command_status, user_command_status_data


@ModuleMessageController.add_method({"de": "schwere-arbeit", "en": "hard-work", "_alts": []})
def hard_msg_work(self, message: TextMessage, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 1)) != 2:
        response_messages.append(ModuleMessageController.get_error_response(message))
        return response_messages, user_command_status, user_command_status_data

    timedelta, stat_points = parse_work_string(message_body.split(None, 1)[1], r'^((?P<hours>\d+?)\s*?(h|Stunden|Std))?\s*?((?P<minutes>\d+?)\s*?(m|min|Minuten)?)?\s*(?P<stat_points>\d)$')
    if timedelta is None or timedelta.total_seconds() == 0:
        response_messages.append(ModuleMessageController.get_error_response(message))
        return response_messages, user_command_status, user_command_status_data

    return work(timedelta, 3, stat_points, response_messages, message), user_command_status, user_command_status_data


set_stats_command = MessageCommand([
    MessageParam("user_id", MessageParam.CONST_REGEX_USER_ID),
    MessageParam("char_id", MessageParam.CONST_REGEX_NUM),
    MessageParam.init_selection("stat_name", list(CharacterStats.get_all_stat_names("de"))),
    MessageParam("stat_num", MessageParam.CONST_REGEX_NUM)
], "Statuswerte-setzen", "set-stats")
@ModuleMessageController.add_method(set_stats_command)
def set_stats(self: ModuleMessageController, message: TextMessage, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User, params: dict, command: MessageCommand):
    orig_params = params.copy()

    if params["user_id"] is None and ModuleMessageController.is_aliased(message):
        params["user_id"] = "@Deine_User_Id"
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body="Leider konnte ich deinen Nutzer nicht zuordnen. Bitte führe den Befehl erneut mit deiner Nutzer-Id aus:"
        ))
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body="@{bot_username} {command}".format(
                bot_username=self.bot_username,
                command=command.get_example(params, "de")
            )
        ))
        return response_messages, user_command_status, user_command_status_data
    elif params["user_id"] is None:
        params["user_id"] = "@" + message.from_user

    chars = self.character_persistent_class.get_all_user_chars(params["user_id"][1:])

    if len(chars) == 0:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body="Der Nutzer {user_id_wa} hat derzeit noch keine Charaktere angelegt. Siehe 'Vorlage' um einen Charakter zu erstellen.".format(
                user_id_wa=params["user_id"]
            ),
            keyboards=[SuggestedResponseKeyboard(responses=[
                ModuleMessageController.generate_text_response("Vorlage {}".format(params["user_id"]))
            ])]
        ))
        return response_messages, user_command_status, user_command_status_data

    if len(chars) > 1 and params["char_id"] is None:

        chars_txt = ""
        for char in chars:
            if chars_txt != "":
                chars_txt += "\n---\n\n"
            char_names = "\n".join(re.findall(r".*?name.*?:.*?\S+?.*", char["text"]))
            if char_names == "":
                char_names = "Im Steckbrief wurden keine Namen gefunden"
            chars_txt += "*Charakter {char_id}*\n{char_names}".format(
                char_id=char["char_id"],
                char_names=char_names
            )

        big_body = "Für den Nutzer sind mehrere Charaktere vorhanden. Bitte wähle einen aus:\n\n"+chars_txt
        for body in ModuleMessageController.split_messages(big_body, "---"):
            keyboards = [ModuleMessageController.generate_text_response(command.get_example({**orig_params, "char_id": char["char_id"]}, "de")) for char in chars][:12]
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=body,
                keyboards=([SuggestedResponseKeyboard(responses=keyboards)]) if len(keyboards) != 0 else []
            ))
        return response_messages, user_command_status, user_command_status_data
    elif len(chars) == 1 and params["char_id"] is None:
        params["char_id"] = chars[0]["char_id"]
        
    found = False
    for char in chars:
        if int(char["char_id"]) == int(params["char_id"]):
            found = True
            break

    if found is False:
        keyboards = [ModuleMessageController.generate_text_response(command.get_example({**orig_params, "char_id": char["char_id"]}, "de")) for char in chars][:12]
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body="Der Charakter mit der Id {} konnte nicht gefunden werden.".format(params["char_id"]),
            keyboards=([SuggestedResponseKeyboard(responses=keyboards)]) if len(keyboards) != 0 else []
        ))
        return response_messages, user_command_status, user_command_status_data

    stat_names = CharacterStats.get_stat_names("de")
    if params["stat_name"] is None:
        keyboards = [ModuleMessageController.generate_text_response(command.get_example({**orig_params, "stat_name": stat_name}, "de")) for stat_id, stat_name in stat_names.items()]
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body="Du hast keinen Statuswert angegeben. Mögliche Werte sind:\n\n{stat_names}".format(
                stat_names="\n".join([stat_name for stat_id, stat_name in stat_names.items()])
            ),
            keyboards=([SuggestedResponseKeyboard(responses=keyboards)]) if len(keyboards) != 0 else []

        ))
        return response_messages, user_command_status, user_command_status_data

    character_persistent_class = self.character_persistent_class  # type: ModuleCharacterPersistentClass
    curr_stat_id = CharacterStats.stat_id_from_name(params["stat_name"], "de")


    if params["stat_num"] is None:
        char_stats_db = character_persistent_class.get_char_stats(params["user_id"][1:], int(params["char_id"]))
        stats = CharacterStats(char_stats_db) if char_stats_db is not None else CharacterStats.init_empty(params["user_id"][1:], int(params["char_id"]))
        curr_stat_points = stats.get_stat_by_id(curr_stat_id)
        ava_exp = stats.get_available_exp()
        possible_points = []
        for i in range(curr_stat_points+1, 11):
            if ava_exp >= CharacterStats.needed_exp_for_stat_points(i) - CharacterStats.needed_exp_for_stat_points(curr_stat_points):
                possible_points.append(i)

        if len(possible_points) != 0:
            body = "Du kannst auf {stat_name} bis zu {max_stat_points} Punkte setzen.".format(
                stat_name=params["stat_name"],
                max_stat_points=possible_points[len(possible_points) - 1]
            )
        else:
            body = "Du kannst keine Punkte auf {stat_name} verteilen.".format(
                stat_name=params["stat_name"]
            )

        keyboards = [ModuleMessageController.generate_text_response(command.get_example({**orig_params, "stat_num": stat_point}, "de")) for stat_point in possible_points]
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=body,
            keyboards=([SuggestedResponseKeyboard(responses=keyboards)]) if len(keyboards) != 0 else []

        ))
        return response_messages, user_command_status, user_command_status_data

    stats = CharacterStats(character_persistent_class.set_char_stat(params["user_id"][1:], curr_stat_id, params["stat_num"], char_id=int(params["char_id"])))

    keyboards = []
    for stat_id, stat_name in stat_names.items():
        if stats.get_stat_by_id(stat_id) == 0 and stat_id != curr_stat_id:
            keyboards.append(ModuleMessageController.generate_text_response(command.get_example({**orig_params, "stat_num": None, "stat_name": stat_name}, "de")))
    for stat_id, stat_name in stat_names.items():
        if stats.get_stat_by_id(stat_id) != 0 and stat_id != curr_stat_id:
            keyboards.append(ModuleMessageController.generate_text_response(command.get_example({**orig_params, "stat_num": None, "stat_name": stat_name}, "de")))

    response_messages.append(TextMessage(
        to=message.from_user,
        chat_id=message.chat_id,
        body=stats.gen_stat_message("de"),
        keyboards=[SuggestedResponseKeyboard(responses=keyboards)]
    ))

    response_messages.append(TextMessage(
        to=message.from_user,
        chat_id=message.chat_id,
        body="{stat_name} {stat_points} verleiht dir folgende Eigenschaften:\n\n{stat_text}".format(
            stat_points=params["stat_num"],
            stat_name=params["stat_name"],
            stat_text=CharacterStats.get_stat_text(curr_stat_id, int(params["stat_num"]))
        ),
        keyboards=[SuggestedResponseKeyboard(responses=keyboards)]
    ))


    return response_messages, user_command_status, user_command_status_data

