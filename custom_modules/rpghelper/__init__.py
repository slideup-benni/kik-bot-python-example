import datetime
import json
import math
import os
import random
import re
import sqlite3
import time
import copy

from flask import send_file
from bs4 import BeautifulSoup, NavigableString, Tag
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

def claws_time_adjust(minutes, claw_per_minute):
    percent_loose = 0.2
    claws_per_min_before = claw_per_minute
    claws_per_min_after = claws_per_min_before * percent_loose
    transition_start_min = 6 * 60
    transition_end_min = 10 * 60

    _transition_mid_min = (transition_start_min + transition_end_min) / 2

    claws_for_min_before = lambda min: min * claws_per_min_before
    claws_for_min_after = lambda min: claws_per_min_after * (min - _transition_mid_min) + claws_for_min_before(_transition_mid_min)
    claws_for_min_triangle = lambda min: ((claws_for_min_after(transition_end_min) - claws_for_min_before(transition_start_min)) / (
                transition_end_min - transition_start_min)) * min + (claws_for_min_after(transition_end_min) - (
                (claws_for_min_after(transition_end_min) - claws_for_min_before(transition_start_min)) / (transition_end_min - transition_start_min)) * transition_end_min)
    claws_for_min_trans = lambda min: claws_for_min_triangle(min) / 2 + (
                claws_for_min_after(min) * (min - transition_start_min) / (transition_end_min - transition_start_min) + claws_for_min_before(min) * (
                    1 - (min - transition_start_min) / (transition_end_min - transition_start_min))) / 2
    claws_for_min = lambda min: claws_for_min_before(min) if min < transition_start_min else claws_for_min_trans(min) if min < transition_end_min else claws_for_min_after(min)
    return claws_for_min(minutes)

def work(minutes, difficulty, stat_points):
    min_blocked = None
    if difficulty == 1:
        claw_per_minute = 0.125
        if minutes > 11*60:
            min_blocked = random.randint(0, math.ceil(minutes/60-11))*15
            if min_blocked >= 45:
                min_blocked = None
    elif difficulty == 2:
        # 1/288*(x + 1/2)² + 7/128
        claw_per_minute = 1 / 288 * pow(int(stat_points) + 1 / 2, 2) + 7 / 128
        if minutes > 8*60:
            min_blocked = random.randint(0, math.ceil(minutes/60-8))*30
    else:
        # 1/240*(x + 3)² - 1/240
        claw_per_minute = 1 / 240 * pow(int(stat_points) + 3, 2) - 1 / 240
        min_blocked = (math.ceil(minutes / 60) + random.randint(0, math.ceil(minutes / 60)))*60

    money_base = math.ceil(claws_time_adjust(minutes, claw_per_minute))
    money = money_base + random.randint(0, money_base)

    return money, min_blocked

def work_text(worked_minutes, money, min_blocked, appendix=None):
    form_hours = math.floor(worked_minutes / 60)
    form_minutes = worked_minutes - math.floor(worked_minutes / 60) * 60

    if form_hours != 0 and form_minutes != 0:
        worked_time = "{hours}:{minutes:02d} Stunden".format(hours=form_hours, minutes=form_minutes)
    elif form_hours != 0:
        worked_time = "{hours} Stunden".format(hours=form_hours)
    else:
        worked_time = "{minutes} Minuten".format(minutes=form_minutes)

    blocked_text = ""
    if min_blocked is not None and min_blocked != 0:
        blocked_text = " und bist für {hours}:{minutes:02d} Stunden erschöpft. Du kannst in der Zeit weder arbeiten noch kämpfen".format(
            hours=math.floor(min_blocked / 60),
            minutes=min_blocked - math.floor(min_blocked / 60) * 60
        )

    # expl = "[{from_claws}~{to_claws}]".format(
    #     time=time,
    #     from_claws=money_base,
    #     to_claws=(money_base*2-1)
    # )

    return "*Du erhältst für deine {time} Arbeit {claws} Krallen{blocked_text}.{appendix}*".format(
        time=worked_time,
        claws=money,
        blocked_text=blocked_text,
        appendix="" if appendix is None or appendix == "" else " " + appendix
    )


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

    bs = None

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
    def get_stat_text(stat_id, stat_points, add_text=True, reload_bs=False, compare_with_point=None):
        if stat_points == 0:
            return None

        if CharacterStats.bs is None or reload_bs is True:
            CharacterStats.bs = BeautifulSoup(open(os.path.dirname(os.path.realpath(__file__)) + '/rpghelper_stat_texts.html', 'r'), "html.parser")

        base_results = CharacterStats.bs.find_all(attrs={'data-stat-name': CharacterStats.get_stat_names('en')[stat_id], 'data-stat-level': stat_points})
        cmp_result = None
        if compare_with_point is not None:
            cmp_results = CharacterStats.bs.find_all(attrs={'data-stat-name': CharacterStats.get_stat_names('en')[stat_id], 'data-stat-level': compare_with_point})
            if len(cmp_results) >= 1:
                cmp_result = cmp_results[0]
            else:
                return None

        if len(base_results) < 1:
            return None


        def filter_text(result, compare_result=None):
            result = copy.copy(result)  # type: Tag
            for tag in result.find_all('li'):
                if compare_result is None:
                    tag.insert(0, NavigableString("- "))
                else:
                    cmp_talent = compare_result.find(attrs={'data-talent': tag.attrs["data-talent"]})
                    if cmp_talent is None or cmp_talent.getText() != tag.getText():
                        btn = u"\U00002197\U0000FE0F" if compare_with_point < stat_points else u"\U00002198\U0000FE0F"
                    else:
                        btn = u"\U000027A1\U0000FE0F"
                    tag.insert(0, NavigableString(btn + " "))

            for tag in result.find_all('ul'):
                tag.append(NavigableString("\n"))

            for tag in result.find_all('h3'):
                tag.insert(0, NavigableString("*"))
                tag.append(NavigableString(":*"))

            text = result.getText()
            text = text.strip()
            text = re.sub(' +', ' ', text)
            text = re.sub('\n *\n', '\n', text)
            text = re.sub('\n *', '\n', text)
            return text

        if add_text is True:
            add_results = CharacterStats.bs.find_all(attrs={'data-stat-name': CharacterStats.get_stat_names('en')[stat_id], 'data-stat-add-text': True})
            if len(add_results) >= 1 and add_results[0].getText() != '':
                return filter_text(base_results[0], cmp_result) + "\n\n" + filter_text(add_results[0])

        return filter_text(base_results[0], cmp_result)

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

    def add_job(self, name, stat_ids):
        self.connect_database()

        self.cursor.execute((
            "INSERT INTO jobs "
            "(name, stat_ids, created) "
            "VALUES (?, ?, ?);"
        ), [
            name,
            json.dumps(stat_ids),
            int(time.time())
        ])

    def get_all_jobs(self):
        self.connect_database()

        self.cursor.execute((
            "SELECT * "
            "FROM jobs "
            "WHERE deleted IS NULL"
        ))

        columns = [column[0] for column in self.cursor.description]
        results = []

        for row in self.cursor:
            dict_row = dict(zip(columns, row))
            dict_row["stat_ids"] = json.loads(row["stat_ids"])
            results.append(dict_row)

        return results

    def get_job_by_name(self, name):
        self.connect_database()

        self.cursor.execute((
            "SELECT * "
            "FROM jobs "
            "WHERE deleted IS NULL "
            "    AND name LIKE ? "
            "ORDER BY created DESC "
            "LIMIT 1"
        ), [name])

        row = self.cursor.fetchone()

        if row is None:
            return None

        dict_row = dict(row)
        dict_row["stat_ids"] = json.loads(row["stat_ids"])

        return dict_row

    def get_job_by_id(self, job_id):
        self.connect_database()

        self.cursor.execute((
            "SELECT * "
            "FROM jobs "
            "WHERE id = ? "
            "LIMIT 1"
        ), [job_id])

        row = self.cursor.fetchone()

        if row is None:
            return None

        dict_row = dict(row)
        dict_row["stat_ids"] = json.loads(row["stat_ids"])

        return dict_row

    def start_work(self, user_id, char_id, job_id, difficulty):
        self.connect_database()

        self.cursor.execute((
            "UPDATE character_work "
            "SET completed = created "
            "WHERE completed IS NULL "
            "    AND deleted IS NULL "
            "    AND user_id = ? "
            "    AND char_id = ?"
        ), [user_id, char_id])

        self.cursor.execute((
            "INSERT INTO character_work "
            "(user_id, char_id, job_id, difficulty, created) "
            "VALUES (?,?,?,?,?)"
        ), [user_id, char_id, job_id, difficulty, int(time.time())])

    def current_work(self, user_id, char_id):
        self.connect_database()

        self.cursor.execute((
            "SELECT * "
            "FROM character_work "
            "WHERE user_id = ? "
            "    AND char_id = ? "
            "    AND completed IS NULL "
            "    AND deleted IS NULL "
            "ORDER BY created DESC "
            "LIMIT 1"
        ), [user_id, char_id])

        return self.cursor.fetchone()

    def complete_work(self, work_row):
        self.connect_database()

        completed = int(time.time())

        self.cursor.execute((
            "UPDATE character_work "
            "SET completed = ? "
            "WHERE id = ?"
        ), [completed, work_row["id"]])

        self.cursor.execute((
            "SELECT * "
            "FROM character_work "
            "WHERE id = ? "
            "LIMIT 1"
        ), [work_row["id"]])

        return self.cursor.fetchone()


    def receive_money(self, user_id, char_id, money, money_type=None, description=None):
        self.connect_database()

        self.cursor.execute((
            "INSERT INTO character_money_transactions "
            "(user_id, char_id, money, type, description, created) "
            "VALUES (?, ?, ?, ? , ?, ?) "
        ), [
            user_id,
            int(char_id),
            money,
            money_type,
            description,
            int(time.time())
        ])

    def send_money(self, user_id, char_id, money, money_type=None, description=None):
        return self.receive_money(user_id, char_id, money*-1, money_type, description)

    def get_balance(self, user_id, char_id):
        self.connect_database()

        self.cursor.execute((
            "SELECT SUM(money) AS balance "
            "FROM character_money_transactions "
            "WHERE user_id = ? "
            "    AND char_id = ? "
            "    AND deleted IS NULL"
        ), [user_id, int(char_id)])

        row = self.cursor.fetchone()
        if row is None or row["balance"] is None:
            return 0
        return row["balance"]

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

        self.cursor.execute((
            "UPDATE character_money_transactions "
            "SET user_id=?, char_id=? "
            "WHERE user_id LIKE ? AND char_id=?"
        ), data)

        self.cursor.execute((
            "UPDATE character_work "
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
            "UPDATE character_money_transactions "
            "SET deleted=? "
            "WHERE user_id LIKE ? AND char_id=?"
        ), data)

        self.cursor.execute((
            "UPDATE character_work "
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
        self.character_persistent_class = ModuleCharacterPersistentClass(self.config, bot_username)

    def is_static_file(self, path):
        if path == "stats.html":
            return True

        return MessageController.is_static_file(self, path)

    def send_file(self, path):
        if path == "stats.html":
            return send_file(os.path.dirname(os.path.realpath(__file__)) + '/rpghelper_stat_texts.html')

        return MessageController.send_file(self, path)

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
], "leichte-arbeit", "easy-work", hidden=True)
@ModuleMessageController.add_method(easy_msg_work_cmd)
def easy_msg_work(response: CommandMessageResponse):

    minutes = int(response.get_value("duration"))
    money, min_blocked = work(minutes, 1, 0)
    response.add_response_message(work_text(minutes, money, min_blocked))
    return response

med_msg_work_cmd = MessageCommand([
    MessageParam.init_duration_minutes("duration", required=True),
    MessageParam("stat_points", MessageParam.CONST_REGEX_NUM, required=True, validate_in_message=True, examples=range(1, 11))
], "mittlere-arbeit", "medium-work",["mittelschwere-arbeit"], hidden=True)
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

    minutes = int(response.get_value("duration"))
    money, min_blocked = work(minutes, 2, int(response.get_value("stat_points")))
    response.add_response_message(work_text(minutes, money, min_blocked))
    return response


hard_msg_work_cmd = MessageCommand([
    MessageParam.init_duration_minutes("duration", required=True),
    MessageParam("stat_points", MessageParam.CONST_REGEX_NUM, required=True, validate_in_message=True, examples=range(1, 11))
], "schwere-arbeit", "hard-work", hidden=True)
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

    minutes = int(response.get_value("duration"))
    money, min_blocked = work(minutes, 3, int(response.get_value("stat_points")))
    response.add_response_message(work_text(minutes, money, min_blocked))
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

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response)
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
            if curr_stat_points != 0 and curr_stat_points != 10:
                body += "\n\n\nFür Stufe {next_stat_point} erwarten dich folgende Eigenschaften:\n\n{stat_text}".format(
                    next_stat_point=curr_stat_points+1,
                    stat_text=CharacterStats.get_stat_text(curr_stat_id, curr_stat_points+1, reload_bs=True, compare_with_point=curr_stat_points)
                )
        else:
            body = "Du kannst keine Punkte auf {stat_name} verteilen.".format(
                stat_name=params["stat_name"]
            )

        response.add_response_message(body)
        response.set_suggestions([command.get_example({**params, "stat_points": stat_point}) for stat_point in possible_points])
        return response

    char_stats_db = character_persistent_class.get_char_stats(plain_user_id, char_id)
    stats_before = CharacterStats(char_stats_db) if char_stats_db is not None else CharacterStats.init_empty(plain_user_id, char_id)
    stats = CharacterStats(character_persistent_class.set_char_stat(plain_user_id, curr_stat_id, params["stat_points"], char_id=char_id))

    keyboards = []
    for stat_id, stat_name in stat_names.items():
        if stats.get_stat_by_id(stat_id) == 0 and stat_id != curr_stat_id:
            keyboards.append(command.get_example({**params, "stat_points": None, "stat_name": stat_name}))
    for stat_id, stat_name in stat_names.items():
        if stats.get_stat_by_id(stat_id) != 0 and stat_id != curr_stat_id:
            keyboards.append(command.get_example({**params, "stat_points": None, "stat_name": stat_name}))
    keyboards.append(MessageController.get_command("Stats-Info").get_example({**params, "command": None}))
    if stats_before.get_stat_by_id(curr_stat_id) != 0:
        keyboards.append(command.get_example({**params, "stat_points": stats_before.get_stat_by_id(curr_stat_id), "stat_name": params["stat_name"]}))


    response.add_response_message(stats.gen_stat_message("de"))
    response.add_response_message("{stat_name} {stat_points} verleiht dir folgende Eigenschaften:\n\n{stat_text}".format(
        stat_points=params["stat_points"],
        stat_name=params["stat_name"],
        stat_text=CharacterStats.get_stat_text(
            curr_stat_id,
            int(params["stat_points"]),
            reload_bs=True,
            compare_with_point=None if stats_before.get_stat_by_id(curr_stat_id) == 0 else stats_before.get_stat_by_id(curr_stat_id)
        )
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

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    char_stats_db = character_persistent_class.get_char_stats(plain_user_id, char_id)
    stats = CharacterStats(char_stats_db) if char_stats_db is not None else CharacterStats.init_empty(plain_user_id, char_id)

    response.add_response_message(stats.gen_stat_message("de"))
    response.set_suggestions([message_controller.generate_text_user_char("Anzeigen", plain_user_id, char_id, response.get_orig_message())])
    return response


add_job_command = MessageCommand([
    MessageParam("job_name", MessageParam.CONST_REGEX_ALPHA, examples=["Kellner", "Gärtner"], required=True),
    MessageParam.init_multiple_selection("stat_names", list(CharacterStats.get_all_stat_names("de")), required=True),
], "Job-hinzufügen", "add-job", admin_only=True)
@ModuleMessageController.add_method(add_job_command)
def start_work(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    params = response.get_params()

    stat_ids = set()
    for stat_name in response.get_value("stat_names"):
        stat_ids.add(CharacterStats.stat_id_from_name(stat_name, "de"))

    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass

    character_persistent_class.add_job(response.get_value("job_name"), list(stat_ids))

    response.add_response_message("Der Job {job_name} wurde hinzugefügt.".format(job_name=params["job_name"]))
    return response

work_difficulty = {
    1: ["easy", "leicht", "einfach"],
    2: ["mittel", "normal", "medium"],
    3: ["hart", "schwer", "hard"]
}

start_work_command = MessageCommand([
    MessageParam.init_user_id(),
    MessageParam.init_char_id(),
    MessageParam("job_name", MessageParam.CONST_REGEX_ALPHA, examples=["Kellner", "Gärtner", "Heiler"], required=True),
    MessageParam.init_selection("difficulty", sum(list(work_difficulty.values()), []))
], "starte-Arbeit", "start-work", ["work-start", "Arbeit-starten"])
@ModuleMessageController.add_method(start_work_command)
def start_work(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    params = response.get_params()

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass

    job_row = character_persistent_class.get_job_by_name(response.get_value("job_name"))
    if job_row is None:
        response.add_response_message("Der Job \"{}\" existiert noch nicht.".format(response.get_value("job_name")))
        return response

    char_stats_db = character_persistent_class.get_char_stats(plain_user_id, char_id)
    stats = CharacterStats(char_stats_db) if char_stats_db is not None else CharacterStats.init_empty(plain_user_id, char_id)

    difficulty_text = response.get_value("difficulty")
    difficulty_id = None
    if difficulty_text is not None:
        for diff_id, diff_names in work_difficulty.items():
            if difficulty_text in diff_names:
                difficulty_id = diff_id
                break

    char_has_stats = True
    for i in range(1, 8):
        if stats.get_stat_by_id(i) is None or stats.get_stat_by_id(i) == 0:
            char_has_stats = False
            break

    used_difficulty = 1 if char_has_stats is False else 2 if difficulty_id is None else difficulty_id
    character_persistent_class.start_work(plain_user_id, char_id, job_row["id"], used_difficulty)

    response.add_response_message("*Du beginnst deine {diff_text} Arbeit als {job_name}*".format(
        diff_text={1:"einfache", 2:"normale", 3:"harte"}[used_difficulty],
        job_name=job_row["name"]
    ))

    return response


finish_work_command = MessageCommand([
    MessageParam.init_user_id(),
    MessageParam.init_char_id(),
], "beende-Arbeit", "finish-work", ["work-end", "Arbeit-beenden", "Feierabend"])
@ModuleMessageController.add_method(finish_work_command)
def finish_work(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    params = response.get_params()

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass

    work_row = character_persistent_class.current_work(plain_user_id, char_id)
    if work_row is None:
        response.add_response_message("(Du arbeitest derzeit nicht.)")
        return response

    work_row = character_persistent_class.complete_work(work_row)
    job_row = character_persistent_class.get_job_by_id(work_row["job_id"])
    char_stats_db = character_persistent_class.get_char_stats(plain_user_id, char_id)
    stats = CharacterStats(char_stats_db) if char_stats_db is not None else CharacterStats.init_empty(plain_user_id, char_id)

    minutes = math.ceil((int(work_row["completed"]) - int(work_row["created"])) / 60)
    money, min_blocked = work(
        minutes,
        int(work_row["difficulty"]),
        max([stats.get_stat_by_id(stat_id) for stat_id in job_row["stat_ids"]])
    )

    character_persistent_class.receive_money(plain_user_id, char_id, money, "working", "gearbeitet für {hours}:{minutes:02d}h als {job_name}".format(
        hours=math.floor(minutes / 60),
        minutes=int(minutes - math.floor(minutes / 60) * 60),
        job_name=job_row["name"]
    ))

    response.add_response_message(work_text(
        minutes,
        money,
        min_blocked,
        "\n\nDu legst die Krallen in deinen Geldbeutel. Dort befinden sich jetzt {money} Krallen.".format(
            money=character_persistent_class.get_balance(plain_user_id, char_id)
        )
    ))

    return response


purse_command = MessageCommand([
    MessageParam.init_user_id(),
    MessageParam.init_char_id(),
    MessageParam("money",       MessageParam.CONST_REGEX_NUM_Z, examples=["+100", "-100", "234"]),
    MessageParam("description", MessageParam.CONST_REGEX_TEXT, examples=["Rüstung gekauft", "verschenkt"]),
], "Geldbeutel", "purse", ["pocket"])
@ModuleMessageController.add_method(purse_command)
def purse(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    params = response.get_params()

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass

    money_value = response.get_value("money")

    if money_value is None:
        response.add_response_message("*In deinem Geldbeutel befinden sich {balance} Krallen.*".format(
            balance=character_persistent_class.get_balance(plain_user_id, char_id)
        ))
        return response

    money = int(money_value)

    if money >= 0:
        character_persistent_class.receive_money(plain_user_id,char_id, money, "manual", response.get_value("description"))
        response.add_response_message("*Du legst {money} Krallen in den Geldbeutel. Du hast nun {balance} Krallen.*".format(
            money=money,
            balance=character_persistent_class.get_balance(plain_user_id, char_id)
        ))
    else:
        balance = character_persistent_class.get_balance(plain_user_id, char_id)
        if balance < money*-1:
            response.add_response_message("(Du kannst keine {money} Krallen aus deinem Geldbeutel nehmen. Du hast derzeit nur {balance} Krallen)".format(
                money=money*-1,
                balance=balance
            ))
            return response

        character_persistent_class.send_money(plain_user_id, char_id, money*-1, "manual", response.get_value("description"))
        response.add_response_message("*Du nimmst {money} Krallen aus dem Geldbeutel. Du hast nun {balance} Krallen.*".format(
            money=money*-1,
            balance=character_persistent_class.get_balance(plain_user_id, char_id)
        ))

    return response


negotiate_command = MessageCommand([
    MessageParam.init_user_id(),
    MessageParam.init_char_id(),
    MessageParam("money",       MessageParam.CONST_REGEX_NUM_Z, examples=["+100", "-100", "234"], required=True),
    MessageParam("description", MessageParam.CONST_REGEX_TEXT, examples=["Rüstung gekauft", "verschenkt"]),
], "verhandeln", "negotiate", [])
@ModuleMessageController.add_method(negotiate_command)
def neogate(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    params = response.get_params()

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass

    char_stats_db = character_persistent_class.get_char_stats(plain_user_id, char_id)
    stats = CharacterStats(char_stats_db) if char_stats_db is not None else CharacterStats.init_empty(plain_user_id, char_id)

    money = int(response.get_value("money"))

    charisma_modificator = {
        0:  lambda x: x,
        1:  lambda x: x * 1.25,
        2:  lambda x: x * 1.1,
        3:  lambda x: x,
        4:  lambda x: x * (1.00 - random.randint(1, 10)/100),
        5:  lambda x: x * (1.00 - random.randint(1, 25)/100),
        6:  lambda x: x * (0.90 - random.randint(1, 15)/100),
        7:  lambda x: x * (0.85 - random.randint(1, 35)/100),
        8:  lambda x: x * (0.80 - random.randint(1, 30)/100),
        9:  lambda x: x * (0.70 - random.randint(1, 20)/100),
        10: lambda x: x * (0.65 - random.randint(1, 35)/100),
    }

    description = response.get_value("description")
    if description is None:
        description = ""
        description_appx = "verhandelt von {money} Krallen"
    else:
        description_appx = " (verhandelt von {money} Krallen)"

    if money >= 0:
        negotiated_money = 2 * money - round(charisma_modificator[stats.get_stat_by_id(4)](money))

        character_persistent_class.receive_money(plain_user_id, char_id, negotiated_money, "negotiate", description + description_appx.format(money=money))
        response.add_response_message("*Du verhandelst den Preis auf {negotiated_money} Krallen und legst die Krallen in den Geldbeutel. Du hast nun {balance} Krallen.*".format(
            negotiated_money=negotiated_money,
            balance=character_persistent_class.get_balance(plain_user_id, char_id)
        ))
    else:
        negotiated_money = round(charisma_modificator[stats.get_stat_by_id(4)](money))

        balance = character_persistent_class.get_balance(plain_user_id, char_id)
        if balance < negotiated_money*-1:
            response.add_response_message("(Du verhandelst den Preis auf {negotiated_money} Krallen, aber du kannst diese nicht bezahlen. Du hast derzeit nur {balance} Krallen)".format(
                negotiated_money=negotiated_money*-1,
                balance=balance
            ))
            return response

        character_persistent_class.send_money(plain_user_id, char_id, negotiated_money * -1, "negotiate", description + description_appx.format(money=money*-1))
        response.add_response_message("*Du verhandelst den Preis auf {negotiated_money} Krallen und nimmst diese aus dem Geldbeutel. Du hast nun {balance} Krallen.*".format(
            negotiated_money=negotiated_money*-1,
            balance=character_persistent_class.get_balance(plain_user_id, char_id)
        ))

    return response


stats_info_command = MessageCommand([
    MessageParam("user_id", MessageParam.CONST_REGEX_USER_ID, examples=MessageParam.random_user),
    MessageParam("char_id", MessageParam.CONST_REGEX_NUM, examples=range(1,4)),
], "Statuswerte-Informationen", "stats-info", ["Stats-informationen", "Statuswerte-info", "show-stats-info"])
@ModuleMessageController.add_method(stats_info_command)
def stats_info(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    params = response.get_params()

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    char_stats_db = character_persistent_class.get_char_stats(plain_user_id, char_id)
    stats = CharacterStats(char_stats_db) if char_stats_db is not None else CharacterStats.init_empty(plain_user_id, char_id)

    message = ""

    stat_names = CharacterStats.get_stat_names("de")
    CharacterStats.bs = None
    for stat_id, stat_name in stat_names.items():
        stat_points = stats.get_stat_by_id(stat_id)
        if message != "":
            message += "\n\n----\n\n"
        message += "{stat_name} {stat_points:2d}:\n\n{stat_text}".format(
            stat_name=stat_name,
            stat_points=stat_points,
            stat_text=CharacterStats.get_stat_text(stat_id, stat_points, add_text=False)
        )

    response.add_response_messages(message_controller.split_messages(message, "----"))

    response.set_suggestions([message_controller.generate_text_user_char("Anzeigen", plain_user_id, char_id, response.get_orig_message())])
    return response

quest_command = MessageCommand([
    MessageParam("page", MessageParam.CONST_REGEX_NUM, examples=[2,3]),
], "Quests", "quests", ["schwarzes-Brett", "bulletin-board"], admin_only=True)
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
], "Quest-Info", "quest-info", ["Quest-Informationen", "quest-information"], admin_only=True)
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
], "Quest-annehmen", "quest-accept", ["quest-take", "quest-assume"], admin_only=True)
@ModuleMessageController.add_method(quest_accept_command)
def quest_accept(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: ModuleMessageController
    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    params = response.get_params()

    MAX_QUESTS = 1

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response)
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
], "Quest-Aufgabe", "quest-task", ["quest-take", "quest-assume"], admin_only=True)
@ModuleMessageController.add_method(quest_task_command)
def quest_task(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: ModuleMessageController
    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    params = response.get_params()

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response)
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
], "Quest-Status", "quest-status", ["my-quests", "meine-quests", "Questbuch", "questbook"], admin_only=True)
@ModuleMessageController.add_method(quest_status_command)
def quest_status(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: ModuleMessageController
    character_persistent_class = message_controller.character_persistent_class  # type: ModuleCharacterPersistentClass
    params = response.get_params()

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response)
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