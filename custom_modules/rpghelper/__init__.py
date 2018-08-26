import csv
import datetime
import json
import math
import os
import random
import re
import sqlite3
import time

from modules.character_persistent_class import CharacterPersistentClass
from modules.message_controller import MessageController, MessageCommand, MessageParam, CommandMessageResponse
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


def work(minutes, difficulty, stat_points):
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

    form_hours = math.floor(minutes/60)
    form_minutes = minutes - math.floor(minutes / 60) * 60

    if form_hours != 0 and form_minutes != 0:
        time = "{hours}:{minutes:02d} Stunden".format(hours=form_hours, minutes=form_minutes)
    elif form_hours != 0:
        time = "{hours} Stunden".format(hours=form_hours)
    else:
        time = "{minutes} Minuten".format(minutes=form_minutes)

    claws_base = math.ceil(claw_per_minute * minutes)
    result = claws_base + random.randint(0, claws_base)

    # expl = "[{from_claws}~{to_claws}]".format(
    #     time=time,
    #     from_claws=claws_base,
    #     to_claws=(claws_base*2-1)
    # )

    return "*Du erhältst für deine {time} Arbeit {claws} Krallen{appendix}*".format(time=time, claws=result, appendix=appendix)


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

    def set_char_stat(self, user_id, stat_id, stat_points, char_id=None):
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
                0 if stat_id != 1 else int(stat_points),
                0 if stat_id != 2 else int(stat_points),
                0 if stat_id != 3 else int(stat_points),
                0 if stat_id != 4 else int(stat_points),
                0 if stat_id != 5 else int(stat_points),
                0 if stat_id != 6 else int(stat_points),
                0 if stat_id != 7 else int(stat_points),
            ])
        else:
            self.cursor.execute((
                "UPDATE character_stats "
                "SET {} = ? "
                "WHERE user_id LIKE ? AND char_id=? AND deleted IS NULL "
            ).format("stat_"+str(int(stat_id))), [stat_points, user_id, char_id])

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

    def get_quests(self):
        self.connect_database()
        self.cursor.execute((
            "SELECT * "
            "FROM quests "
            "WHERE enabled <> 0 "
            "  AND (SELECT COUNT(*) "
            "       FROM character_quests "
            "       where quest_id = quests.id "
            "         AND completed + quests.repeat_hours*60*60 > ?) < max_active_count; "
        ), [int(time.time())])

        return self.cursor.fetchall()

    def get_quest_by_caption(self, caption):
        self.connect_database()

        self.cursor.execute((
            "SELECT *, (SELECT GROUP_CONCAT(user_id) "
            "       FROM character_quests "
            "       where quest_id = quests.id "
            "         AND completed + quests.repeat_hours*60*60 > ? "
            "       group by quest_id) AS curr_active "
            "FROM quests "
            "WHERE enabled <> 0 AND caption = ?;"
        ), [int(time.time()), caption])

        return self.cursor.fetchone()

    def get_quest(self, quest_id):
        self.connect_database()

        self.cursor.execute((
            "SELECT *, (SELECT GROUP_CONCAT(user_id) "
            "       FROM character_quests "
            "       where quest_id = quests.id "
            "         AND completed + quests.repeat_hours*60*60 > ? "
            "       group by quest_id) AS curr_active "
            "FROM quests "
            "WHERE enabled <> 0 AND id = ?;"
        ), [int(time.time()), quest_id])

        return self.cursor.fetchone()

    def get_char_quests(self, user_id, char_id):
        self.connect_database()
        self.cursor.execute((
            "SELECT * "
            "FROM character_quests AS cq "
            "LEFT JOIN quests AS q ON q.id = cq.quest_id "
            "LEFT JOIN quest_parts AS qp ON qp.id = cq.part_id "
            "WHERE cq.user_id = ? "
            "  AND cq.char_id = ? "
            "  AND cq.completed > ?"
            "  AND cq.status = 'running'; "
        ), [user_id, char_id, int(time.time())])

        return self.cursor.fetchall()

    def get_char_quest(self, user_id, char_id, quest_id):
        self.connect_database()
        self.cursor.execute((
            "SELECT * "
            "FROM character_quests AS cq "
            "LEFT JOIN quests AS q ON q.id = cq.quest_id "
            "LEFT JOIN quest_parts AS qp ON qp.id = cq.part_id "
            "WHERE cq.user_id = ? "
            "  AND cq.char_id = ?"
            "  AND cq.quest_id = ? "
            "  AND cq.completed > ?"
            "  AND cq.status = 'running'; "
        ), [user_id, char_id, quest_id, int(time.time())])

        return self.cursor.fetchone()

    def accept_quest(self, user_id, char_id, quest_part, quest=None):
        self.connect_database()

        if quest is None:
            quest = self.get_quest(quest_part["quest_id"])

        self.cursor.execute((
            "INSERT INTO character_quests "
            "(user_id, char_id, quest_id, part_id, status, started, changed, completed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?,  ?);"
        ), [
            user_id,
            char_id,
            quest_part["quest_id"],
            quest_part["id"],
            "running",
            int(time.time()),
            int(time.time()),
            int(time.time()) + int(quest["max_duration"]) * 3600
        ])

        return True

    def set_char_quest_part(self, user_id, char_id, quest_part):
        self.connect_database()

        if int(quest_part["next_part_num"]) == -1:
            self.cursor.execute((
                "UPDATE character_quests "
                "SET part_id=?, changed=?, completed=?, status=? "
                "WHERE user_id = ? "
                "  AND char_id = ? "
                "  AND quest_id = ? "
            ), [
                int(quest_part["id"]),
                int(time.time()),
                int(time.time()),
                "succeed",
                user_id,
                int(char_id),
                int(quest_part["quest_id"])
            ])
        else:
            self.cursor.execute((
                "UPDATE character_quests "
                "SET part_id=?, changed=? "
                "WHERE user_id = ? "
                "  AND char_id = ? "
                "  AND quest_id = ?"
                "  AND status = 'running';"
            ), [
                int(quest_part["id"]),
                int(time.time()),
                user_id,
                int(char_id),
                int(quest_part["quest_id"])
            ])


        return True

    def get_quest_parts(self, quest_id, part_num):
        self.connect_database()
        self.cursor.execute((
            "SELECT * "
            "FROM quest_parts "
            "WHERE quest_id = ? "
            "  AND part_num = ? "
        ), [quest_id, part_num])

        return self.cursor.fetchall()

    def get_quest_parts_by_name(self, quest_id, part_name):
        self.connect_database()
        self.cursor.execute((
            "SELECT * "
            "FROM quest_parts "
            "WHERE quest_id = ? "
            "  AND part_name = ? "
        ), [quest_id, part_name])

        return self.cursor.fetchall()

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

        self.cursor.execute((
            "UPDATE character_quests "
            "SET user_id=?, char_id=? "
            "WHERE user_id LIKE ? AND char_id=?"
        ), data)

        return to_char_id

    def remove_char(self, user_id, deletor_id, char_id=None):
        self.connect_database()

        if char_id is None:
            char_id = self.get_min_char_id()

        CharacterPersistentClass.remove_char(self, user_id, deletor_id, char_id)

        data = (int(time.time()), user_id, char_id)
        self.cursor.execute((
            "UPDATE character_stats "
            "SET deleted=? "
            "WHERE user_id LIKE ? AND char_id=?"
        ), data)

        self.cursor.execute((
            "DELETE FROM character_quests "
            "WHERE user_id = ? "
            "  AND char_id = ?"
        ), [user_id, char_id])


class ModuleMessageController(MessageController):

    def __init__(self, bot_username, config_file):
        MessageController.__init__(self, bot_username, config_file)
        self.character_persistent_class = ModuleCharacterPersistentClass(self.config)

    @staticmethod
    def require_user_id(message_controller, params, key, response: CommandMessageResponse):
        message = response.get_orig_message()
        command = response.get_command()

        if params[key] is None and ModuleMessageController.is_aliased(message):
            response.add_response_message("Leider konnte ich deinen Nutzer nicht zuordnen. Bitte führe den Befehl erneut mit deiner Nutzer-Id aus:")
            response.add_response_message("@{bot_username} {command}".format(
                bot_username=message_controller.bot_username,
                command=command.get_example({**params, key: "@Deine_User_Id"})
            ))
            return None, response

        user_id = params[key]
        if params[key] is None:
            user_id = "@" + message.from_user

        return user_id, response

    @staticmethod
    def require_char_id(message_controller, params, key, user_id, response: CommandMessageResponse):
        command = response.get_command()
        chars = message_controller.character_persistent_class.get_all_user_chars(user_id)

        if len(chars) == 0:
            response.add_response_message("Der Nutzer @{user_id} hat derzeit noch keine Charaktere angelegt. Siehe 'Vorlage' um einen Charakter zu erstellen.".format(
                user_id=user_id
            ))
            response.set_suggestions(["Vorlage @{}".format(user_id)])
            return None, response

        if len(chars) > 1 and params[key] is None:

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

            big_body = "Für den Nutzer sind mehrere Charaktere vorhanden. Bitte wähle einen aus:\n\n" + chars_txt
            for body in ModuleMessageController.split_messages(big_body, "---"):
                response.add_response_message(body)
                response.set_suggestions([command.get_example({**params, "char_id": char["char_id"]}) for char in chars][:12])

            return None, response

        char_id = params[key]
        if len(chars) == 1 and params[key] is None:
            char_id = chars[0]["char_id"]

        found = False
        for char in chars:
            if int(char["char_id"]) == int(char_id):
                found = True
                break

        if found is False:
            response.add_response_message("Der Charakter mit der Id {} konnte nicht gefunden werden.".format(char_id))
            response.set_suggestions([command.get_example({**params, "char_id": char["char_id"]}) for char in chars][:12])
            return None, response
        return int(char_id), response

    def get_my_quest_part(self, parts, user_id, char_id):

        if len(parts) == 1:
            return parts[0]

        char_stats_db = self.character_persistent_class.get_char_stats(user_id, char_id)
        char_stats = CharacterStats(char_stats_db) if char_stats_db is not None else CharacterStats.init_empty(user_id, char_id)

        def stat_gt(stat_id, stat_points):
            return char_stats.get_stat_by_id(int(stat_id)) > int(stat_points)

        def time(from_hour, to_hour):
            now = datetime.datetime.now()

            if int(from_hour) < int(to_hour):
                return int(from_hour) <= now.hour < int(to_hour)
            return now.hour >= int(to_hour) or now.hour < int(from_hour)

        def process_condition(part):
            importance = 1
            if part["condition"] is None or part["condition"] == "":
                return importance

            conds = part["condition"].split("&")
            regex = re.compile(r"^(?P<func>[a-z_]+)\((?P<args>.*)\)$", re.IGNORECASE | re.MULTILINE)

            for cond in conds:
                match = regex.match(cond.strip())
                if match is None:
                    print("[{bot_username}] Quest: Syntax-Fehler in Condition '{cond}' im Quest {quest_id} Part {part_num}".format(
                        bot_username=self.bot_username,
                        cond=cond,
                        quest_id=part["quest_id"],
                        part_num=part["part_num"]
                    ))
                    return 0
                dict = match.groupdict()

                args = None if dict["args"] is None else dict["args"].split(",")
                if dict["func"] == "stat_gt" and args is not None and len(args) == 2:
                    if stat_gt(int(args[0]), int(args[1])) is True:
                        importance += int(args[1])+1
                    else:
                        return 0

                elif dict["func"] == "time" and args is not None and len(args) == 2:
                    if time(int(args[0]), int(args[1])) is True:
                        importance += 11
                    else:
                        return 0

            return importance

        curr_part = None
        curr_importance = 0
        for part in parts:
            part_importance = process_condition(part)
            if part_importance > 0 and part_importance >= curr_importance:
                curr_importance = part_importance
                curr_part = part

        return curr_part

    def get_quest_part_messages(self, quest_part, quest, body_before=""):
        messages = [body_before]
        suggestions = []

        if quest_part is not None and quest_part["text"] is not None and quest_part["text"] != "":
            messages[0] += "\n\n" + quest_part["text"]

        if quest_part is not None and quest_part["next_step_text"] is not None and quest_part["next_step_text"] != "":
            messages[0] += "\n\n( Nächste Schritte: " + quest_part["next_step_text"] + " )"

        if quest_part is not None and quest_part["next_part_num"] is not None and int(quest_part["next_part_num"]) != -1:
            next_parts = self.character_persistent_class.get_quest_parts(int(quest_part["quest_id"]), int(quest_part["next_part_num"]))
            if next_parts is not None:
                messages[0] += "\n( Mit dem folgenden Befehl kannst du dann die nächste Teilaufgabe des Quests aufrufen: )"
                next_command = "Quest-Aufgabe \"{quest[caption]}\" \"{part[part_name]}\"".format(
                    quest=quest,
                    part=next_parts[0]
                )
                messages.append("@{bot_username} ".format(
                    bot_username=self.bot_username,
                ) + next_command)
                suggestions = [next_command]

        return [small_message for big_message in messages for small_message in self.split_messages(big_message)], suggestions


easy_msg_work_cmd = MessageCommand([
    MessageParam.init_duration_minutes("duration", required=True)
], "leichte-arbeit", "easy-work")
@ModuleMessageController.add_method(easy_msg_work_cmd)
def easy_msg_work(response: CommandMessageResponse):

    response.add_response_message(work(response.get_value("duration"), 1, 0))
    return response

med_msg_work_cmd = MessageCommand([
    MessageParam.init_duration_minutes("duration", required=True),
    MessageParam("stat_points", MessageParam.CONST_REGEX_NUM, required=True, validate_in_message=True, examples=range(1, 11))
], "mittlere-arbeit", "medium-work",["mittelschwere-arbeit"])
@ModuleMessageController.add_method(med_msg_work_cmd)
def med_msg_work(response: CommandMessageResponse):

    if response.get_value("stat_points") is None:

        response.add_response_message("Um eine mittelschwere Arbeit ausüben zu können, musst du für den Job geeignet sein.\n"
                                      "Bitte gib als zweiten Wert deine Stat-Punkte an, die am ehesten zu deiner Tätigkeit passen.\n"
                                      "Beispielsweise\n"
                                      "- Charisma-Punkte als Kellner oder Verkäufer,\n"
                                      "- Stärke-Punkte als Schmied oder Wache, oder\n"
                                      "- Wissens-Punkte als Lehrer.\n\n" +
                                      response.get_command().get_random_example_text(4, response, response.get_params()))
        response.set_suggestions([response.get_command().get_example({**response.get_params(), "stat_points": stat_point}) for stat_point in range(1, 11)])
        return response

    response.add_response_message(work(response.get_value("duration"), 2, int(response.get_value("stat_points"))))
    return response


hard_msg_work_cmd = MessageCommand([
    MessageParam.init_duration_minutes("duration", required=True),
    MessageParam("stat_points", MessageParam.CONST_REGEX_NUM, required=True, validate_in_message=True, examples=range(1, 11))
], "schwere-arbeit", "hard-work")
@ModuleMessageController.add_method(hard_msg_work_cmd)
def hard_msg_work(response: CommandMessageResponse):

    if response.get_value("stat_points") is None:

        response.add_response_message("Um eine schwere Arbeit ausüben zu können, musst du für den Job geeignet sein.\n"
                                      "Bitte gib als zweiten Wert deine Stat-Punkte an, die am ehesten zu deiner Tätigkeit passen.\n"
                                      "Beispielsweise\n"
                                      "- Charisma-Punkte als Kellner oder Verkäufer,\n"
                                      "- Stärke-Punkte als Schmied oder Wache, oder\n"
                                      "- Wissens-Punkte als Lehrer.\n\n" +
                                      response.get_command().get_random_example_text(4, response, response.get_params()))
        response.set_suggestions([response.get_command().get_example({**response.get_params(), "stat_points": stat_point}) for stat_point in range(1, 11)])
        return response

    response.add_response_message(work(response.get_value("duration"), 3, int(response.get_value("stat_points"))))
    return response


set_stats_command = MessageCommand([
    MessageParam.init_user_id(),
    MessageParam.init_char_id(),
    MessageParam.init_selection("stat_name", list(CharacterStats.get_all_stat_names("de")), required=True, validate_in_message=True),
    MessageParam("stat_points", MessageParam.CONST_REGEX_NUM, required=True, validate_in_message=True, examples=range(1,11))
], "Statuswerte-setzen", "set-stats", ["Stats-setzen", "Stat-setzen", "Statuswert-setzen"])
@ModuleMessageController.add_method(set_stats_command)
def set_stats(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    params = response.get_params()
    command = response.get_command()

    user_id, response = ModuleMessageController.require_user_id(message_controller, params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = ModuleMessageController.require_char_id(message_controller, params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    stat_names = CharacterStats.get_stat_names("de")
    if params["stat_name"] is None:
        response.add_response_message("Du hast keinen Statuswert angegeben. Mögliche Werte sind:\n\n{stat_names}".format(
            stat_names="\n".join([stat_name for stat_id, stat_name in stat_names.items()])
        ))
        response.set_suggestions([command.get_example({**params, "stat_name": stat_name}) for stat_id, stat_name in stat_names.items()])
        return response

    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    curr_stat_id = CharacterStats.stat_id_from_name(params["stat_name"], "de")

    if params["stat_points"] is None:
        char_stats_db = character_persistent_class.get_char_stats(plain_user_id, char_id)
        stats = CharacterStats(char_stats_db) if char_stats_db is not None else CharacterStats.init_empty(plain_user_id, char_id)
        curr_stat_points = stats.get_stat_by_id(curr_stat_id)
        ava_exp = stats.get_available_exp()
        possible_points = []
        for i in range(curr_stat_points+1, 11):
            if ava_exp >= CharacterStats.needed_exp_for_stat_points(i) - CharacterStats.needed_exp_for_stat_points(curr_stat_points):
                possible_points.append(i)

        if len(possible_points) != 0:
            body = "Du kannst auf {stat_name} bis zu {max_stat_points} Punkte setzen.\n\n" \
                   "Für 1-8 wird jeweils ein, für 9 zwei und für 10 drei Erfahrungspunkte benötigt.".format(
                stat_name=params["stat_name"],
                max_stat_points=possible_points[len(possible_points) - 1]
            )
        else:
            body = "Du kannst keine Punkte auf {stat_name} verteilen.".format(
                stat_name=params["stat_name"]
            )

        response.add_response_message(body)
        response.set_suggestions([command.get_example({**params, "stat_points": stat_point}) for stat_point in possible_points])
        return response

    stats = CharacterStats(character_persistent_class.set_char_stat(plain_user_id, curr_stat_id, params["stat_points"], char_id=char_id))

    keyboards = []
    for stat_id, stat_name in stat_names.items():
        if stats.get_stat_by_id(stat_id) == 0 and stat_id != curr_stat_id:
            keyboards.append(command.get_example({**params, "stat_points": None, "stat_name": stat_name}))
    for stat_id, stat_name in stat_names.items():
        if stats.get_stat_by_id(stat_id) != 0 and stat_id != curr_stat_id:
            keyboards.append(command.get_example({**params, "stat_points": None, "stat_name": stat_name}))

    response.add_response_message(stats.gen_stat_message("de"))
    response.add_response_message("{stat_name} {stat_points} verleiht dir folgende Eigenschaften:\n\n{stat_text}".format(
        stat_points=params["stat_points"],
        stat_name=params["stat_name"],
        stat_text=CharacterStats.get_stat_text(curr_stat_id, int(params["stat_points"]))
    ))
    response.set_suggestions(keyboards)

    return response


stats_command = MessageCommand([
    MessageParam("user_id", MessageParam.CONST_REGEX_USER_ID, examples=MessageParam.random_user),
    MessageParam("char_id", MessageParam.CONST_REGEX_NUM, examples=range(1,4)),
], "Statuswerte", "stats", ["Stats-anzeigen", "Statuswerte-anzeigen", "show-stats"])
@ModuleMessageController.add_method(stats_command)
def stats(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    params = response.get_params()

    user_id, response = ModuleMessageController.require_user_id(message_controller, params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = ModuleMessageController.require_char_id(message_controller, params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    char_stats_db = character_persistent_class.get_char_stats(plain_user_id, char_id)
    stats = CharacterStats(char_stats_db) if char_stats_db is not None else CharacterStats.init_empty(plain_user_id, char_id)

    response.add_response_message(stats.gen_stat_message("de"))
    response.set_suggestions([message_controller.generate_text_user_char("Anzeigen", plain_user_id, char_id, response.get_orig_message())])
    return response

quest_command = MessageCommand([
    MessageParam("page", MessageParam.CONST_REGEX_NUM, examples=[2,3]),
], "Quests", "quests", ["schwarzes-Brett", "bulletin-board"])
@ModuleMessageController.add_method(quest_command)
def quests(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    quests = character_persistent_class.get_quests()

    if quests is None or len(quests) == 0:
        response.add_response_message("Leider sind derzeit keine Quests verfügbar.")
        return response

    body = "***\nDu schaust auf das schwarze Brett in der Stadtmitte. {vis_quests_text}:\n".format(
        vis_quests_text= "Hierauf sind {len_quests} Pergamente angepinnt".format(len_quests=len(quests)) if len(quests) > 1 else "Hierauf ist ein Pergament angepinnt"
    )
    for quest in quests:
        body += "\n- \"{quest[caption]}\"".format(quest=quest)

    body += "\n***"

    response.add_response_messages(message_controller.split_messages(body, "\n\n\n"))
    response.set_suggestions([MessageController.get_command("Quest-Info").get_example({"caption": "\"" + quest["caption"] + "\""}) for quest in quests])

    return response

quest_info_command = MessageCommand([
    MessageParam("caption", r"\".*?\"", examples=["\"Heilkräuter für den Schmied\"", "\"Lotte\"", "\"Quest-Überschrift\""], required=True),
], "Quest-Info", "quest-info", ["Quest-Informationen", "quest-information"])
@ModuleMessageController.add_method(quest_info_command)
def quest_info(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    quest = character_persistent_class.get_quest_by_caption(response.get_value("caption")[1:-1].strip())  # type: sqlite3.Row
    params = response.get_params()

    if quest is None:
        response.add_response_message("Der angegebene Quest konnte nicht gefunden werden. Rufe 'quests' auf, um dir alle verfügbaren Quests anzuzeigen.")
        response.set_suggestions(["quests"])
        return response

    rewards = []
    requirements = []
    active_users = []
    if quest["reward_money"] is not None and int(quest["reward_money"]) != 0:
        rewards.append("Krallen")
    if quest["reward_exp"] is not None and int(quest["reward_exp"]) != 0:
        rewards.append("{exp} mEP".format(exp=int(quest["reward_exp"])))

    if quest["min_group_size"] is not None and int(quest["min_group_size"]) > 2:
        requirements.append("{cnt}-Gruppe benötigt".format(cnt=int(quest["min_group_size"])))
    if quest["min_stats"] is not None and quest["min_stats"] != "":
        min_stats = json.loads(quest["min_stats"])
        for stat in min_stats:
            requirements.append("min. {stat_points} {stat_name}".format(
                stat_points=stat["points"],
                stat_name=CharacterStats.get_stat_names("de")[stat["id"]]
            ))

    if quest["curr_active"] is not None and quest["curr_active"] != "":
        active_users = ["@"+user_id for user_id in quest["curr_active"].split(",")]

    body = "***\nDu schaust dir ein Pergament am schwarzen Brett genauer an:\n\n" \
           "{quest[description]}\n\n\n" \
           "Belohnung(en): {rewards}\n" \
           "besondere Voraussetzung(en): {requirements}\n" \
           "zu erledigen bis: {max_time:%d.%m %H:%M}\n" \
           "aktuell angenommen von: {curr_active} (max. {max_active})\n" \
           "***".format(
                quest=quest,
                rewards=", ".join(rewards) if len(rewards) != 0 else "-keine-",
                requirements=", ".join(requirements) if len(requirements) != 0 else "-keine-",
                max_time=(datetime.datetime.now() + datetime.timedelta(hours=int(quest["max_duration"]))),
                curr_active=", ".join(active_users) if len(active_users) != 0 else "-keinem-",
                max_active=int(quest["max_active_count"])
            )

    response.add_response_messages(message_controller.split_messages(body))

    if int(quest["max_active_count"]) > len(active_users):
        response.set_suggestions(["Quests",
                                  MessageController.get_command("Quest-annehmen").get_example({**params, "command": None})
                                  ])
    else:
        response.set_suggestions(["Quests"])

    return response

quest_accept_command = MessageCommand([
    MessageParam.init_user_id(),
    MessageParam.init_char_id(),
    MessageParam("caption", r"\".*?\"", examples=["\"Heilkräuter für den Schmied\"", "\"Lotte\"", "\"Quest-Überschrift\""], required=True),
], "Quest-annehmen", "quest-accept", ["quest-take", "quest-assume"])
@ModuleMessageController.add_method(quest_accept_command)
def quest_accept(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: ModuleMessageController
    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    params = response.get_params()

    MAX_QUESTS = 1

    user_id, response = ModuleMessageController.require_user_id(message_controller, params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = ModuleMessageController.require_char_id(message_controller, params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    quest = character_persistent_class.get_quest_by_caption(response.get_value("caption")[1:-1].strip())  # type: sqlite3.Row

    if quest is None:
        response.add_response_message("Der angegebene Quest konnte nicht gefunden werden. Rufe 'quests' auf, um dir alle verfügbaren Quests anzuzeigen.")
        response.set_suggestions(["quests"])
        return response

    user_quests = character_persistent_class.get_char_quests(plain_user_id, char_id)

    if quest["curr_active"] is not None and quest["curr_active"] != "" and len(quest["curr_active"].split(",")) >= int(quest["max_active_count"]):
        response.add_response_message("Der Quest kann nicht angenommen werden, da er bereits von {cnt} Spieler(n) angenommen wurde. Bitte versuche es später erneut.".format(
            cnt=len(quest["curr_active"].split(","))
        ))
        response.set_suggestions(["quests"])
        return response

    if user_quests is not None and len(user_quests) >= MAX_QUESTS:
        response.add_response_message("Du hast bereits einen Quest angenommen und kannst keinen weiteren annehmen. Bitte beende zunächst deinen aktiven Quest.")
        response.set_suggestions([MessageController.get_command("Quest-Status").get_example({**params, "command": None})])
        return response

    quest_parts = character_persistent_class.get_quest_parts(quest["id"], 0)
    quest_part = message_controller.get_my_quest_part(quest_parts, plain_user_id, char_id)
    character_persistent_class.accept_quest(plain_user_id, char_id, quest_part, quest)

    body = "*Du reißt das Pergament mit der Quest vom schwarzen Brett und steckst es ein. Du hast nun {hours} Stunden Zeit die Quest zu erledigen.*".format(
                hours=int(quest["max_duration"])
            )

    messages, suggestions = message_controller.get_quest_part_messages(quest_part, quest, body)

    response.add_response_messages(messages)
    response.set_suggestions(suggestions)

    return response

quest_task_command = MessageCommand([
    MessageParam.init_user_id(),
    MessageParam.init_char_id(),
    MessageParam("caption", r"\".*?\"", examples=["\"Heilkräuter für den Schmied\"", "\"Lotte\"", "\"Quest-Überschrift\""], required=True),
    MessageParam("part_name", r"\".*?\"", examples=["\"Beginn\"", "\"Beim Schmied\"", "\"Bei der Stinky's Cove\"", "\"Bei Myrrul's Haus\"", "\"Kiste abgestellt und im Haus\"",
                                                    "\"Bei der Stinky's Cove (Rückweg)\"", "\"Zurück beim Schmied\""], required=True),
], "Quest-Aufgabe", "quest-task", ["quest-take", "quest-assume"])
@ModuleMessageController.add_method(quest_task_command)
def quest_task(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: ModuleMessageController
    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    params = response.get_params()

    user_id, response = ModuleMessageController.require_user_id(message_controller, params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = ModuleMessageController.require_char_id(message_controller, params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    quest = character_persistent_class.get_quest_by_caption(response.get_value("caption")[1:-1].strip())  # type: sqlite3.Row

    if quest is None:
        response.add_response_message("Der angegebene Quest konnte nicht gefunden werden. Rufe 'quests' auf, um dir alle verfügbaren Quests anzuzeigen.")
        response.set_suggestions(["quests"])
        return response

    user_quest = character_persistent_class.get_char_quest(plain_user_id, char_id, int(quest["id"]))

    if user_quest is None:
        response.add_response_message("Der ausgewählte Quest wurde noch nicht angenommen.")
        response.set_suggestions([MessageController.get_command("Quest-annehmen").get_example({**params, "command": None})])
        return response

    quest_next_parts = character_persistent_class.get_quest_parts_by_name(quest["id"], response.get_value("part_name")[1:-1].strip())

    if quest_next_parts is None or len(quest_next_parts) == 0:
        response.add_response_message("Die angegebene Teilaufgabe des Quests exisiert nicht. Schaue im Questbuch nach um die weiteren Schritte zu sehen.")
        response.set_suggestions([MessageController.get_command("Quest-Status").get_example({**params, "command": None})])
        return response

    user_quest_next_part = message_controller.get_my_quest_part(quest_next_parts, plain_user_id, char_id)

    if user_quest_next_part["part_num"] != user_quest["next_part_num"]:
        response.add_response_message("Du kannst keine Aufgaben überspringen. Schaue im Questbuch nach um die weiteren Schritte zu sehen.")
        response.set_suggestions([MessageController.get_command("Quest-Status").get_example({**params, "command": None})])
        return response

    character_persistent_class.set_char_quest_part(plain_user_id, char_id, user_quest_next_part)

    messages, suggestions = message_controller.get_quest_part_messages(user_quest_next_part, quest)

    response.add_response_messages(messages)
    response.set_suggestions(suggestions)

    return response


quest_status_command = MessageCommand([
    MessageParam.init_user_id(),
    MessageParam.init_char_id()
], "Quest-Status", "quest-status", ["my-quests", "meine-quests", "Questbuch", "questbook"])
@ModuleMessageController.add_method(quest_status_command)
def quest_status(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: ModuleMessageController
    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    params = response.get_params()

    user_id, response = ModuleMessageController.require_user_id(message_controller, params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = ModuleMessageController.require_char_id(message_controller, params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    quests = character_persistent_class.get_char_quests(plain_user_id, char_id)

    if quests is None or len(quests) == 0:
        response.add_response_message("Du hast derzeit keine Quests angenommen. Begib dich zum schwarzen Brett in der Stadtmitte um verfügbare Quests zu sehen.")
        response.set_suggestions(["Quests"])
        return response

    body = "*Du schaust in dein Questbuch und dort findest du {quests}, die du noch abschließen musst*\n".format(
        quests="eine Quest" if len(quests) == 1 else "{} Quests".format(len(quests))
    )

    suggestions = []
    for quest in quests:
        body += "\n---\n" \
                "Quest \"{quest[caption]}\"\n\n" \
                "Zu erledigen bis: {completed:%d.%m. %H:%M}\n" \
                "Aktuelle Aufgabe: {quest[part_name]}\n" \
                "Nächste Schritte: {quest[next_step_text]}".format(quest=quest, completed=datetime.datetime.fromtimestamp(quest["completed"]))

        if int(quest["next_part_num"]) == -1:
            continue

        next_parts = character_persistent_class.get_quest_parts(quest["quest_id"], quest["next_part_num"])
        if next_parts is None or len(next_parts) == 0:
            continue

        suggestions.append(MessageController.get_command("Quest-Aufgabe").get_example({
            **params,
            "command": None,
            "caption": "\"" + quest["caption"] + "\"",
            "part_name": "\"" + next_parts[0]["part_name"] + "\""
        }))

    body += "\n---"

    response.add_response_messages(message_controller.split_messages(body, "---"))
    response.set_suggestions(suggestions)
    return response