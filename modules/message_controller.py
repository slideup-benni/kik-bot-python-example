import configparser
import datetime
import json
import random
import time
from typing import Union

import regex as re
import sqlite3

from flask_babel import gettext as _, get_locale
from kik.messages import Message, StartChattingMessage, TextMessage, SuggestedResponseKeyboard, PictureMessage
from werkzeug.exceptions import BadRequest

from modules.character_persistent_class import CharacterPersistentClass
from modules.kik_user import User, LazyKikUser, LazyRandomKikUser


class MessageParam:
    CONST_REGEX_ALPHA = r"[a-zäöüß]+"
    CONST_REGEX_ALPHANUM = r"[a-zäöüß0-9]+"
    CONST_REGEX_NUM = r"[0-9]+"
    CONST_REGEX_NUM_Z = r"[\-\+]?[0-9]+"
    CONST_REGEX_DIGIT = r"[0-9]"
    CONST_REGEX_USER_ID = r"@[a-z0-9\.\_]+"
    CONST_REGEX_COMMAND = r"\S+"
    CONST_REGEX_TEXT = r".+"

    def __init__(self, name, regex, required=False, validate_in_message=False, examples=None, get_value_callback=None, default_value=None):
        self.get_value_callback = get_value_callback
        self.validate_in_message = validate_in_message
        self.name = name.strip()
        self.default_value = default_value
        self.regex = regex
        self.required = required
        self.examples = examples if examples is not None else []

    def get_regex(self, is_first=False):
        if is_first is True:
            regex = r"(?P<{name}>{regex}){req}"
        else:
            regex = r"(\s+(?P<{name}>{regex})){req}"
        return regex.format(
            name=self.name,
            regex=self.regex,
            req="" if self.required is True and self.validate_in_message is False else "?"
        )

    def get_help_desc(self):
        if self.required is True:
            return "<" + self.name + ">"
        return "(<" + self.name + ">)"

    def get_name(self):
        return self.name

    def get_random_example(self, response):
        if callable(self.examples):
            return self.examples(response)

        return random.choice(self.examples)

    def is_required(self):
        return self.required

    def get_value(self, params):

        if callable(self.get_value_callback):
            value = self.get_value_callback(self.name, params)
            return value if value is not None else self.default_value

        return params[self.name] if params[self.name] is not None else self.default_value

    @staticmethod
    def init_multiple_selection(name, selection: list, required=False, validate_in_message=False, examples=None):
        regex = r"((?P<{name}_sel>{sel})(\s*,\s*(?P<{name}_sel_add>{sel}))*)".format(
            sel="|".join([re.escape(str(x).lower()) for x in selection]),
            name=name
        )

        def get_value_cb(name, param_values):
            items = []

            if name + "_sel" in param_values and param_values[name + "_sel"] is not None:
                items.append(param_values[name + "_sel"])

            if name + "_sel_add" in param_values and param_values[name + "_sel_add"] is not None and isinstance(param_values[name + "_sel_add"], list):
                items.extend(param_values[name + "_sel_add"])
            elif name + "_sel_add" in param_values and param_values[name + "_sel_add"] is not None: # singe item
                items.append(param_values[name + "_sel_add"])

            return items

        if examples is None:
            examples = list(selection)
            if len(selection) > 1:
                for i in range(0,len(selection)):
                    examples.append("{item1}, {item2}".format(
                        item1 = selection[i],
                        item2 = selection[(i+1)%len(selection)]
                    ))
            if len(selection) > 2:
                for i in range(0,len(selection)):
                    examples.append("{item1}, {item2}, {item3}".format(
                        item1 = selection[i],
                        item2 = selection[(i - 1) % len(selection)],
                        item3 = selection[(i + 2) % len(selection)]
                    ))
        return MessageParam(name, regex, required, validate_in_message, examples=examples, get_value_callback=get_value_cb)

    @staticmethod
    def init_selection(name, selection: list, required=False, validate_in_message=False, examples=None):
        return MessageParam(name, r"({})".format(
            "|".join([re.escape(str(x).lower()) for x in selection])
        ), required, validate_in_message, examples=selection if examples is None else examples)

    @staticmethod
    def init_user_id(name="user_id", required=False, validate_in_message=False, examples=None):
        return MessageParam(name, MessageParam.CONST_REGEX_USER_ID, required=required, validate_in_message=validate_in_message,
                            examples=MessageParam.random_user if examples is None else examples)

    @staticmethod
    def init_char_id(name="char_id", required=False, validate_in_message=False, examples=None):
        return MessageParam(name, MessageParam.CONST_REGEX_NUM, required=required, validate_in_message=validate_in_message,
                            examples=range(1, 4) if examples is None else examples)

    @staticmethod
    def init_duration_minutes(name="duration", required=False, validate_in_message=False, examples=None):

        name = name.strip()

        hour_unit = r"(\s*(h|std))"
        min_regex = r"(?P<{name}_mins_{cnt}>\d+)\s*(m|min)"
        min_dec = r"[\.,](?P<{name}_hours_dec>\d+){hour_unit}?"
        min_colon = r":(?P<{name}_mins_1>\d{{1,2}}){hour_unit}?"
        hours = r"(?P<{name}_hours>\d+)"

        data = {
            'name': name,
            'hour_unit': hour_unit
        }

        regex = r"(({hours}(({min_int_1})|({min_dec})|({hour_unit})|({hour_unit}?\s+{min_int_2}))?)|({min_int_3}))".format(
            hours=hours.format(**data),
            min_int_1=min_colon.format(**data),
            min_dec=min_dec.format(**data),
            min_int_2=min_regex.format(**{**data, 'cnt':2}),
            min_int_3=min_regex.format(**{**data, 'cnt':3}),
            hour_unit=hour_unit
        )

        examples = ["3:12", "14:22", "12:0", "0:22", "8:00", "3:12h", "14:22 h", "12:0h", "0:22h", "8:00h", "3h 25min", "3 25min", "3min", "3h 25min", "3h 25 min", "325min", "3",
                    "3h", "322h", "0", "0h", "0:0", "325h", "1,23", "2,2", "3,5", "1,33333", "1.23", "2.2", "3.5", "1.3333", "1,23h", "2,2h", "3,5h", "1,33333h", "1.23 h", "2.2h",
                    "3.5h", "1.3333 h"] if examples is None else examples

        def get_value_cb(name, param_values):
            minutes = 0
            none = True

            if name + "_mins_1" in param_values and param_values[name + "_mins_1"] is not None:
                minutes += int(param_values[name + "_mins_1"])
                none=False

            if name + "_mins_2" in param_values and param_values[name + "_mins_2"] is not None:
                minutes += int(param_values[name + "_mins_2"])
                none = False

            if name + "_mins_3" in param_values and param_values[name + "_mins_3"] is not None:
                minutes += int(param_values[name + "_mins_3"])
                none = False

            if name + "_hours_dec" in param_values and param_values[name + "_hours_dec"] is not None:
                minutes += round(float("0." + param_values[name + "_hours_dec"]) * 60)
                none = False

            if name + "_hours" in param_values and param_values[name + "_hours"] is not None:
                minutes += int(param_values[name + "_hours"]) * 60
                none = False

            return minutes if none is False else None

        return MessageParam(name, regex, required=required, validate_in_message=validate_in_message,
                            examples=examples, get_value_callback=get_value_cb)

    @staticmethod
    def random_user(response):
        """

        :type response: CommandMessageResponse
        """
        users = set(["@" + u.strip() for u in response.get_message_controller().get_config().get("Admins", "admin1").split(',')])
        users.add(response.get_user().id)
        return random.choice(list(users))


class MessageCommand:


    def __init__(self, params: list, command_de, command_en, command_alts=None, help_command=None, hidden=False, require_admin=False, require_auth=False, require_group=False, require_self: Union[bool, str]=False):
        """

        :param params:
        :param command_de:
        :param command_en:
        :param command_alts:
        :param help_command:
        :param hidden:
        :param require_admin: The command can executed only when the message.user is admin or any other require condition is complied
        :param require_auth: The command can executed only when the message.user is authed, admin or message.chat_id is authed group or any other require condition is complied
        :param require_group: The command can executed only when the message.user is admin or message.chat_id is authed or any other require condition is complied
        :param require_self: The command can executed only when the message.user is admin or the given value of parameter is None or message.user or any other require condition is complied
        """
        self.hidden = hidden
        if help_command is not None:
            self.help_command = help_command
        elif require_admin is False:
            self.help_command = 'Hilfe'
        else:
            self.help_command = 'Admin-Hilfe'
        self.require_admin = require_admin
        self.require_auth = require_auth
        self.require_group = require_group
        self.require_self = require_self
        self.command = {
            'de': command_de,
            'en': command_en,
            '_alts': [] if command_alts is None else command_alts
        }

        self.params = [
            MessageParam("command", MessageParam.CONST_REGEX_COMMAND, required=True, examples=self.get_all_command_names())
        ]
        self.params.extend(params)

    def is_admin_only(self):
        return self.require_admin

    def is_auth_only(self):
        return self.require_auth

    def is_require_group(self):
        return self.require_group

    def is_require_self(self):
        return self.require_self is not False

    def is_hidden(self):
        return self.hidden

    def get_all_command_names(self):
        all_commands = set()
        all_commands.add(self.command["de"])
        all_commands.add(self.command["en"])
        all_commands = all_commands.union(set(self.command["_alts"]))
        return list(all_commands)

    def add_param(self, param: MessageParam):
        self.params.append(param)

    def get_regex(self):
        base_regex = ""
        for i in range(0,len(self.params)):
            base_regex += self.params[i].get_regex(base_regex == "")

        return r"^\s*{}\s*$".format(base_regex)

    def get_command(self, message_string):
        regex = re.compile(r"^\s*{}.*$".format(self.params[0].get_regex(True)), re.IGNORECASE | re.MULTILINE)
        match = regex.match(message_string.strip())
        if match is None:
            return ""
        return match.group("command")

    def get_help_desc(self):
        lang = get_locale().language
        help_desc = self.command[lang] if lang in self.command else self.command["de"]
        for x in self.params[1:]:
            help_desc += " " + x.get_help_desc()
        return help_desc

    def get_command_loc(self):
        lang = get_locale().language
        if lang in self.command:
            return self.command[lang]
        return self.command["de"]

    def get_example(self, params: dict):
        lang = get_locale().language
        example_str = params["command"] if "command" in params and params["command"] is not None else (self.command[lang] if lang in self.command else self.command["de"])
        for x in self.params[1:]:
            name = x.get_name()
            if name in params and params[name] is not None:
                example_str += " " + str(params[name])
        return example_str

    def get_random_example(self, response, fixed_params=None):
        """

        :type response: CommandMessageResponse
        :type fixed_params: dict
        """
        example_str = ""
        for param in self.params:
            if fixed_params is not None and param.get_name() in fixed_params and fixed_params[param.get_name()] is not None:
                example_str += " " + str(fixed_params[param.get_name()])
            elif param.is_required() or random.randint(0,1) == 0:
                example_str += " " + str(param.get_random_example(response))

        return example_str.strip()

    def get_random_example_text(self, count, response, fixed_params=None):

        examples = set()
        for i in range(0, count*10):
            examples.add(u"\U000027A1\U0000FE0F " + self.get_random_example(response, fixed_params))
            if len(examples) == count:
                break

        count = len(examples)

        cnt_str = {
            2: _("zwei"),
            3: _("drei"),
            4: _("vier"),
            5: _("fünf"),
            10: _("zehn"),
            11: _("elf"),
            12: _("zwölf")
        }

        if count == 1:
            string = _("ein zufälliges Beispiel")
        else:
            string = _("{count} zufällige Beispiele").format(
                count=count if count not in cnt_str else cnt_str[count]
            )

        return string + ":\n" + "\n".join(examples)

    def __getitem__(self, item):
        return self.command[item]

    def items(self):
        return self.command.items()

    def get_values(self, params):
        values = {}
        for param in self.params:
            values[param.get_name()] = param.get_value(params)
        return values

    def get_method(self, func):

        def method(controller, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):

            if self.require_admin is True and controller.is_admin(message) is False:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Fehler beim Aufruf des Befehls.\n\nNur Admins können diesen Befehl ausführen."),
                    keyboards=[SuggestedResponseKeyboard(responses=[
                        MessageController.generate_text_response(self.help_command),
                    ])]
                ))
                return response_messages, user_command_status, user_command_status_data

            if self.require_auth is True and \
                    message.chat_id != controller.config.get("KikGroupChatId", "") and \
                    user.is_authed() is False and \
                    controller.is_admin(message) is False:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Du bist nicht berechtigt diesen Befehl auszuführen!\n"
                           "Bitte melde dich in der Gruppe #{kik_group_id} und erfrage eine Berechtigung oder führe dort folgenden Befehl aus:\n\n"
                           "@{bot_username} auth @{user_id}").format(
                        kik_group_id=controller.config.get("KikGroup", "somegroup"),
                        bot_username=controller.bot_username,
                        user_id=user.get_user_id()
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Hilfe")])]
                ))
                return response_messages, user_command_status, user_command_status_data

            response_texts = []
            suggestions = []
            for response_message in response_messages:  # type: TextMessage
                response_texts.append(response_message.body)
                if len(response_message.keyboards) > 0:
                    suggestions = [keyboard.body for keyboard in response_message.keyboards[0].reponses]
                else:
                    suggestions = []

            command_message_response_data = {
                "message_controller":       controller,  # message_controller,
                "orig_message":             message,  # orig_message,
                "response_messages":        response_texts,  # response_messages,
                "user_command_status":      user_command_status,  # user_command_status,
                "user_command_status_data": user_command_status_data,  # user_command_status_data,
                "user":                     user,  # user,
                "params":                   [],  # params,
                "command":                  self,  # command,
                "suggestions":              suggestions,
                "forced_message":           message_body_c
            }

            regex = re.compile(self.get_regex(), re.IGNORECASE | re.MULTILINE)
            match = regex.match(message_body_c.strip())
            if match is None:
                params_ = {i: x for i, x in enumerate(self.params)}
                params_["command"] = self.get_command(message_body_c)
                command_message_response = CommandMessageResponse(**{**command_message_response_data, "params": params_})
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Fehler beim Aufruf des Befehls.\n\n"
                           "Die Struktur des Befehls sieht wie folgt aus:\n"
                           "{command_structure}\n\n"
                           "{examples_3}\n\n"
                           "Für weitere Beispiele siehe '{help_command}'.").format(
                        command_structure=self.get_help_desc(),
                        examples_3=self.get_random_example_text(3, command_message_response, params_),
                        help_command="{} {}".format(MessageController.get_command_text("Hilfe"), self.get_command_loc())
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[
                        MessageController.generate_text_response("{} {}".format("Hilfe", self.get_command_loc())),
                        MessageController.generate_text_response(self.help_command),
                    ])]
                ))
                return response_messages, user_command_status, user_command_status_data

            params = {}
            for key, value in match.capturesdict().items():
                if len(value) == 0:
                    params[key] = None
                elif len(value) == 1:
                    params[key] = value[0]
                else:
                    params[key] = value

            message_response = CommandMessageResponse(**{**command_message_response_data, "params": params})
            response = func(message_response) # type: CommandMessageResponse
            response_messages = response.get_kik_response()
            user_command_status, user_command_status_data = response.get_user_command_status()
            return response_messages, user_command_status, user_command_status_data
        return method


class MessageCommandDB(MessageCommand):

    def __init__(self, row: sqlite3.Row):
        self.db_row = row
        self.db_id = row["id"]
        super().__init__([], row["command"], row["command"],
                         command_alts=json.loads(row["alt_commands"]) if row["alt_commands"] is not None and row["alt_commands"] != "" else None,
                         help_command=None,
                         hidden=True,
                         require_admin=False,
                         require_auth=False
                         )

    def get_regex(self):
        if len(self.params) == 1:
            return r"^\s*{}\s*.*?$".format(self.params[0].get_regex(True))
        return super(MessageCommand).get_regex()

class AdditionalActions:

    def __init__(self, name: str):
        self.name = name
        self.actions = list()

    def add_action(self, title:str, action: str):
        self.actions.append({"title":title, "action":action})


class ResponseMessage:
    pass


class PictureResponseMessage(ResponseMessage):

    def __init__(self, pic_url):
        self.pic_url = pic_url


class MessageResponse:

    def __init__(self, message_controller, orig_message: TextMessage, response_messages: list, user_command_status, user_command_status_data, user: User, suggestions=None,
                 forced_message=None):
        self.suggestions = [] if suggestions is None else suggestions
        self.user = user  # type: User
        self.user_command_status_data = user_command_status_data
        self.user_command_status = user_command_status
        self.response_messages = response_messages
        self.orig_message = orig_message
        self.message_controller = message_controller  # type: MessageController
        self.forced_message = forced_message
        self.additional_actions = list()

    def get_user(self):
        return self.user  #type: User

    def get_user_command_status(self):
        return self.user_command_status, self.user_command_status_data

    def get_response_messages(self):
        return self.response_messages

    def get_orig_message(self):
        return self.orig_message

    def get_message_controller(self):
        return self.message_controller

    def get_message_body(self):
        return self.forced_message

    def add_response_message(self, message: Union[str, ResponseMessage]):
        self.response_messages.append(message)

    def add_response_messages(self, messages: list):
        for message in messages:
            self.add_response_message(message)

    def set_suggestions(self, suggestions: list):
        self.suggestions = suggestions

    def request_is_direct_bot(self):
        return self.orig_message.chat_type == "direct"

    def request_is_direct_user(self):
        return self.orig_message.chat_type == "private" and len(self.orig_message.participants) == 2

    def request_is_private_group(self):
        return self.orig_message.chat_type == "private" and len(self.orig_message.participants) != 2

    def request_is_public_group(self):
        return self.orig_message.chat_type == "public"

    def get_all_group_users(self):
        return self.orig_message.participants

    def add_additional_actions(self, actions: AdditionalActions):
        self.additional_actions.append(actions)

    def get_kik_response(self):
        kik_responses = []
        num_resp = len(self.response_messages)
        for r in range(0, num_resp):
            if isinstance(self.response_messages[r], str):
                message_dict = {
                    "to":  self.orig_message.from_user,
                    "chat_id": self.orig_message.chat_id,
                    "body": self.response_messages[r],
                }
                if r == num_resp-1 and len(self.suggestions) != 0:
                    message_dict["keyboards"] = [SuggestedResponseKeyboard(responses=[MessageController.generate_text_response(keyboard) for keyboard in self.suggestions])]
                kik_responses.append(TextMessage(**message_dict))

            elif isinstance(self.response_messages[r], PictureResponseMessage):
                kik_responses.append(PictureMessage(
                    to=self.orig_message.from_user,
                    chat_id=self.orig_message.chat_id,
                    pic_url=self.response_messages[r].pic_url,
                ))

        return kik_responses


class CommandMessageResponse(MessageResponse):

    def __init__(self, message_controller, orig_message: TextMessage, response_messages: list, user_command_status, user_command_status_data, user: User, params: dict,
                 command: MessageCommand, suggestions=None, forced_message=None):
        MessageResponse.__init__(self, message_controller, orig_message, response_messages, user_command_status, user_command_status_data, user, suggestions, forced_message)
        self.params = params
        self.values = None
        self.command = command

    def get_params(self):
        return self.params

    def get_param(self, key):
        return self.get_params()[key]

    def get_values(self):
        if self.values is None:
            self.values = self.get_command().get_values(self.get_params())
        return self.values

    def get_value(self, key):
        values = self.get_values()
        if key in values:
            return values[key]
        return None

    def get_command(self):
        return self.command


class MessageController:
    methods = list()
    static_method = None

    def __init__(self, bot_username, config_file):
        self.config = self.read_config(config_file)
        self.bot_username = bot_username
        self.character_persistent_class = CharacterPersistentClass(self.config, bot_username)
        self.update_static_commands()

    @staticmethod
    def read_config(config_file):
        config = configparser.ConfigParser()
        config.read(config_file)
        return config['DEFAULT']

    def get_config(self):
        return self.config

    def is_static_file(self, path):
        return False

    def send_file(self, path):
        return BadRequest()

    def process_message(self, message: Message, user: User):

        log_requests = self.config.get("LogRequests", "False")
        if log_requests is True or str(log_requests).lower() == "true":
            print(message.__dict__)

        response_messages = []
        user_command_status = CharacterPersistentClass.STATUS_NONE
        user_command_status_data = None
        # Check if its the user's first message. Start Chatting messages are sent only once.
        if isinstance(message, StartChattingMessage):

            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Hi {user[first_name]}, mit mir kann man auch direkt schreiben. "
                       "Wenn du möchtest, kannst du hier auch @{bot_username} vor allen Befehlen weg lassen. "
                       "Probier es aus: Antworte mir einfach mit '{help_command}' und du bekommst eine Liste aller Befehle").format(
                    user=user,
                    help_command=MessageController.get_command_text('Hilfe'),
                    bot_username=self.bot_username
                ),
                # keyboards are a great way to provide a menu of options for a user to respond with!
                keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Hilfe")])]
            ))

        # Check if the user has sent a text message.
        elif isinstance(message, TextMessage):
            message_body = message.body.lower()
            message_body_c = message.body

            if message_body == "":
                return [TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Hi {user[first_name]}, ich bin der Steckbrief-Bot der Gruppe #{kik_group_id}\n" +
                           "Für weitere Informationen tippe auf Antwort und dann auf '{help_command}'."
                           ).format(
                        user=user,
                        kik_group_id=self.config.get("KikGroup", "somegroup"),
                        help_command=MessageController.get_command_text('Hilfe')
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[
                        MessageController.generate_text_response("Hilfe"),
                        MessageController.generate_text_response("Regeln"),
                        MessageController.generate_text_response("Vorlage")
                    ])]
                )]

            #
            # Dynamische Befehle
            #
            if message_body == u"\U00002B05\U0000FE0F":
                status_obj = user.get_status_obj()
                if status_obj['status'] == CharacterPersistentClass.STATUS_DYN_MESSAGES and 'left' in status_obj['data']:
                    message_body = status_obj['data']['left'].lower()
                    message_body_c = status_obj['data']['left']

            elif message_body == u"\U000027A1\U0000FE0F":
                status_obj = user.get_status_obj()
                if status_obj['status'] == CharacterPersistentClass.STATUS_DYN_MESSAGES and 'right' in status_obj['data']:
                    message_body = status_obj['data']['right'].lower()
                    message_body_c = status_obj['data']['right']
            elif message_body == u"\U0001F504":
                status_obj = user.get_status_obj()
                if status_obj['status'] == CharacterPersistentClass.STATUS_DYN_MESSAGES and 'redo' in status_obj['data']:
                    message_body = status_obj['data']['redo'].lower()
                    message_body_c = status_obj['data']['redo']
            elif message_body.strip()[0] == "@":
                status_obj = user.get_status_obj()
                if status_obj['status'] == CharacterPersistentClass.STATUS_DYN_MESSAGES and 'add_user_id' in status_obj['data']:
                    message_body = status_obj['data']['add_user_id'].lower().format(message_body.strip()[1:])
                    message_body_c = status_obj['data']['add_user_id'].format(message_body_c.strip()[1:])

            message_command = message_body.split(None, 1)[0]
            if message_command != "":
                method = self.get_command_method(message_command)
                response_messages, user_command_status, user_command_status_data = method(
                    self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user
                )
            else:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Sorry {user[first_name]}, ich habe dich nicht verstanden.").format(user=user),
                    keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Hilfe")])]
                ))
        elif isinstance(message, PictureMessage):
            status_obj = user.get_status_obj()
            if status_obj is None or status_obj['status'] != CharacterPersistentClass.STATUS_SET_PICTURE:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Sorry {user[first_name]}, mit diesem Bild kann ich leider nichts anfangen.").format(user=user),
                    keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Hilfe")])]
                ))

            else:
                success = self.character_persistent_class.set_char_pic(status_obj['data']['user_id'], self.get_from_userid(message), message.pic_url, status_obj['data']['char_id'])
                if success is True:
                    body = _("Alles klar! Das Bild wurde gesetzt. Bitte melde dich bei @{} damit das Bild bestätigt werden kann. "
                             "Dies ist notwendig, da Kik eine Zero-Tolerance-Policy gegenüber evtl. anstößigen Bildern hat.".format(
                        self.config.get("Admins", "admin1").split(',')[0].strip()
                    ))
                    show_resp = self.generate_text_response_user_char("Anzeigen", status_obj['data']['user_id'], status_obj['data']['char_id'], message)
                else:
                    body = _("Beim hochladen ist ein Fehler aufgetreten. Bitte versuche es erneut.")
                    show_resp = self.generate_text_response_user_char("Bild-setzen", status_obj['data']['user_id'], status_obj['data']['char_id'], message)
                    user_command_status = status_obj['status']
                    user_command_status_data = status_obj['data']

                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=body,
                    keyboards=[SuggestedResponseKeyboard(responses=[
                        show_resp,
                        MessageController.generate_text_response("Liste")
                    ])]
                ))

        # If its not a text message, give them another chance to use the suggested responses
        else:

            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Sorry {user[first_name]}, ich habe dich nicht verstanden.").format(user=user),
                keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Hilfe")])]
            ))

        # We're sending a batch of messages. We can send up to 25 messages at a time (with a limit of
        # 5 messages per user).

        user.update_status(user_command_status, user_command_status_data)
        self.character_persistent_class.update_user(user)
        self.character_persistent_class.commit()
        return response_messages

    @staticmethod
    def generate_text_response_user_char(command, user_id, char_id, message, force_username=False):
        return MessageController.generate_text_response(MessageController.generate_text_user_char(command, user_id, char_id, message, force_username=force_username))

    @staticmethod
    def generate_text_user_char(command, user_id, char_id, message, force_username=False):
        show_user = MessageController.get_from_userid(message) != user_id or force_username is True
        show_char_id = char_id is not None and char_id > CharacterPersistentClass.get_min_char_id()

        if show_user and show_char_id:
            return "{} @{} {}".format(command, user_id, char_id)
        if show_user:
            return "{} @{}".format(command, user_id)
        if show_char_id:
            return "{} {}".format(command, char_id)
        return command

    @staticmethod
    def generate_text_response(body, force_command=False):
        from kik.messages import TextResponse

        if force_command is True:
            return TextResponse(body)
        split = body.split(None, 1)
        split[0] = MessageController.get_command_text(split[0])
        return TextResponse(" ".join(split))

    def check_auth(self, user: User, message, auth_command=False):
        if auth_command is False and message.chat_id == self.config.get("KikGroupChatId", ""):
            return True


        if user.is_authed() is False and self.is_admin(message) is False:
            return TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du bist nicht berechtigt diesen Befehl auszuführen!\n" +
                       "Bitte melde dich in der Gruppe #{kik_group_id} und erfrage eine Berechtigung.").format(kik_group_id=self.config.get("KikGroup", "somegroup")),
                keyboards=[SuggestedResponseKeyboard(responses=[self.generate_text_response("Hilfe")])]
            )
        return True

    # depricated when search refactored
    def create_char_messages_old(self, char_data: sqlite3.Row, message, user_command_status, user_command_status_data, user: User):
        response_messages = []
        keyboard_responses = []
        body_char_appendix = ""
        dyn_message_data = {}

        if "prev_char_id" in char_data.keys() and char_data["prev_char_id"] is not None:
            dyn_message_data['left'] = MessageController.generate_text_user_char("Anzeigen", char_data["user_id"], char_data["prev_char_id"], message)
            keyboard_responses.append(MessageController.generate_text_response(u"\U00002B05\U0000FE0F"))

        if "next_char_id" in char_data.keys() and char_data["next_char_id"] is not None:
            dyn_message_data['right'] = MessageController.generate_text_user_char("Anzeigen", char_data["user_id"], char_data["next_char_id"], message)
            keyboard_responses.append(MessageController.generate_text_response(u"\U000027A1\U0000FE0F"))

        if dyn_message_data != {}:
            body_char_appendix = _("\n\n(Weitere Charaktere des Nutzers vorhanden: {icon_left} und {icon_right} zum navigieren)").format(
                icon_left=u"\U00002B05\U0000FE0F",
                icon_right=u"\U000027A1\U0000FE0F"
            )
            user_command_status = CharacterPersistentClass.STATUS_DYN_MESSAGES
            user_command_status_data = dyn_message_data

        if char_data["user_id"] == MessageController.get_from_userid(message):
            keyboard_responses.append(MessageController.generate_text_response_user_char("Bild-setzen", char_data["user_id"], char_data["char_id"], message))

        keyboard_responses.append(MessageController.generate_text_response("Liste"))

        pic_url = self.character_persistent_class.get_char_pic_url(char_data["user_id"], char_data["char_id"])

        if pic_url is False:
            body_char_appendix += _("\n\nCharakter-Bilder müssen vor dem Anzeigen bestätigt werden.")
        elif pic_url is not None:
            response_messages.append(PictureMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                pic_url=pic_url,
            ))

        body = _("{char_text}\n\n---\nCharakter von {from_user}\nErstellt von {creator_user}\nErstellt am {created:%d.%m.%Y %H:%M}{appendix}").format(
            char_text=str(char_data["text"]).format(
                user=user
            ),
            from_user=self.get_name(char_data["user_id"], append_user_id=True),
            creator_user=self.get_name(char_data['creator_id'], append_user_id=True),
            created=datetime.datetime.fromtimestamp(char_data['created']),
            appendix=body_char_appendix,
        )

        messages = MessageController.split_messages(body)

        for m in messages:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=m,
                keyboards=[SuggestedResponseKeyboard(responses=keyboard_responses)]
            ))

        return (response_messages, user_command_status, user_command_status_data)

    def create_char_messages(self, char_data: sqlite3.Row, response: CommandMessageResponse):
        suggestions = []
        body_char_appendix = ""
        dyn_message_data = {}

        if "prev_char_id" in char_data.keys() and char_data["prev_char_id"] is not None:
            dyn_message_data['left'] = MessageController.generate_text_user_char("Anzeigen", char_data["user_id"], char_data["prev_char_id"], response.get_orig_message())
            suggestions.append(u"\U00002B05\U0000FE0F")

        if "next_char_id" in char_data.keys() and char_data["next_char_id"] is not None:
            dyn_message_data['right'] = MessageController.generate_text_user_char("Anzeigen", char_data["user_id"], char_data["next_char_id"], response.get_orig_message())
            suggestions.append(u"\U000027A1\U0000FE0F")

        if dyn_message_data != {}:
            body_char_appendix = _("\n\n(Weitere Charaktere des Nutzers vorhanden: {icon_left} und {icon_right} zum navigieren)").format(
                icon_left=u"\U00002B05\U0000FE0F",
                icon_right=u"\U000027A1\U0000FE0F"
            )
            response.user_command_status = CharacterPersistentClass.STATUS_DYN_MESSAGES
            response.user_command_status_data = dyn_message_data

        if char_data["user_id"] == MessageController.get_from_userid(response.get_orig_message()):
            suggestions.append(MessageController.generate_text_user_char("Bild-setzen", char_data["user_id"], char_data["char_id"], response.get_orig_message()))


        suggestions.append("Liste")

        pic_url = self.character_persistent_class.get_char_pic_url(char_data["user_id"], char_data["char_id"])

        if pic_url is False:
            body_char_appendix += _("\n\nCharakter-Bilder müssen vor dem Anzeigen bestätigt werden.")
        elif pic_url is not None:
            response.add_response_message(PictureResponseMessage(pic_url))

        body = _("{char_text}\n\n---\nCharakter von {from_user}\nErstellt von {creator_user}\nErstellt am {created:%d.%m.%Y %H:%M}{appendix}").format(
            char_text=str(char_data["text"]).format(
                user=response.get_user()
            ),
            from_user=self.get_name(char_data["user_id"], append_user_id=True),
            creator_user=self.get_name(char_data['creator_id'], append_user_id=True),
            created=datetime.datetime.fromtimestamp(char_data['created']),
            appendix=body_char_appendix,
        )

        response.add_response_messages(MessageController.split_messages(body))
        response.set_suggestions(suggestions)

        return response

    @staticmethod
    def split_messages(message_body, split_char="\n", max_chars=1500):
        if split_char == "":
            return [message_body[i:i + max_chars] for i in range(0, len(message_body), max_chars)]

        body_split = message_body.split(split_char)
        splitted_messages = []
        new_body = ""
        for b in body_split:
            if len(new_body) + len(b) + len(split_char) < max_chars:
                if new_body != "":
                    new_body += split_char
                new_body += b
            elif len(b) + len(split_char) >= max_chars:
                new_message_to_split = new_body + split_char + b if len(new_body) != 0 else b
                new_split_char = "" if split_char == "\n" else "\n"
                splitted_messages += MessageController.split_messages(new_message_to_split, split_char=new_split_char)
                new_body = ""
            elif len(new_body) > 0:
                splitted_messages.append(new_body)
                new_body = b
            else:
                new_body = b

        if len(new_body) > 0:
            splitted_messages.append(new_body)
        return splitted_messages

    def get_name(self, user_id, append_user_id=False):
        user_db = self.character_persistent_class.get_user(user_id)
        user = LazyKikUser.init(user_db) if user_db is not None else LazyKikUser.init_new_user(user_id, self.bot_username)
        if append_user_id is True:
            return user["name_and_id"]
        else:
            return user["name_or_id"]

    def update_static_commands(self):
        all_static_methods = self.character_persistent_class.get_all_static_messages()
        current_static_methods = {obj["cmds"].db_id: (cmd_id, obj) for cmd_id, obj in enumerate(MessageController.methods) if isinstance(obj["cmds"], MessageCommandDB)}

        for db_row in all_static_methods:
            # update
            if db_row["id"] in current_static_methods:
                (cmd_id, obj) = current_static_methods[db_row["id"]]
                if obj["cmds"].db_row != db_row:
                    commands = MessageCommandDB(db_row)
                    obj["func"] = commands.get_method(MessageController.static_method)
                    obj["cmds"] = commands
                    MessageController.methods[cmd_id] = obj
                current_static_methods.pop(db_row["id"], None)

            # insert
            else:
                commands = MessageCommandDB(db_row)
                MessageController.methods.append({
                "func": commands.get_method(MessageController.static_method),
                "cmds": commands
            })

        # delete
        for csm in current_static_methods:
            MessageController.methods.remove(csm)


    @staticmethod
    def is_aliased(message):
        return MessageController.is_aliased_user(message.from_user)

    @staticmethod
    def is_aliased_user(user_id):
        return len(user_id) == 52

    @staticmethod
    def get_from_userid(message):
        return message.from_user

    def is_admin(self, message: Message):
        user_db = self.character_persistent_class.get_user(message.from_user.lower())
        if int(user_db["is_admin"]) == 1:
            return True
        return message.from_user.lower() in [x.strip().lower() for x in self.config.get("Admins", "admin1").split(',')]

    @staticmethod
    def get_command_id(command):
        cmd = str(command).strip().lower()
        for cmd_id, obj in enumerate(MessageController.methods):
            langs = obj["cmds"]
            if langs is None:
                continue

            for lang_id, cmd_text in langs.items():
                if lang_id != "_alts":
                    if cmd_text.lower() == cmd:
                        return cmd_id
                else:
                    for cmd_alt_text in cmd_text:
                        if cmd_alt_text.lower() == cmd:
                            return cmd_id

        return None

    @staticmethod
    def get_command_method(command):
        cmd = str(command).strip().lower()
        none_func = None
        for cmd_id, obj in enumerate(MessageController.methods):
            langs = obj["cmds"]
            if (langs is None):
                none_func = obj["func"]
                continue

            for lang_id, cmd_text in langs.items():
                if lang_id != "_alts":
                    if cmd_text.lower() == cmd:
                        return obj["func"]
                else:
                    for cmd_alt_text in cmd_text:
                        if cmd_alt_text.lower() == cmd:
                            return obj["func"]

        return none_func

    @staticmethod
    def get_command(command):
        command_id = MessageController.get_command_id(command)
        if command_id is None:
            return None

        return MessageController.methods[command_id]['cmds'] # type: Union[dict, MessageCommand]

    @staticmethod
    def get_command_text(command_str):
        lang = get_locale().language
        command = MessageController.get_command(command_str)
        if command is None:
            return str(command_str).strip()

        try:
            return command[lang]
        except KeyError:
            return command["de"]

    @staticmethod
    def add_method(commands):
        def add_method_decore(func):

            MessageController.methods.append({
                "func": func if isinstance(commands, MessageCommand) is False else commands.get_method(func),
                "cmds": commands
            })
            return func

        return add_method_decore

    @staticmethod
    def set_static_method(func):
        MessageController.static_method = func
        return func

    @staticmethod
    def get_error_response(message, command="Hilfe"):
        return TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Fehler beim Aufruf des Befehls. Siehe '{help_command}'.").format(
                help_command=MessageController.get_command_text(command)
            ),
            keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response(command)])]
        )

    def require_user_id(self, params, key, response: CommandMessageResponse, use_linked_char=True):
        message = response.get_orig_message()
        command = response.get_command()
        user = response.get_user()

        if params[key] is None and use_linked_char is True and user.is_user_id is not None:
            return "@"+user.is_user_id.lower(), response

        if params[key] is None and MessageController.is_aliased(message):
            response.add_response_message(_("Leider konnte ich deinen Nutzer nicht zuordnen. Bitte führe den Befehl erneut mit deiner Nutzer-Id aus:"))
            response.add_response_message("@{bot_username} {command}".format(
                bot_username=self.bot_username,
                command=command.get_example({**params, key: _("@Deine_User_Id")})
            ))
            if use_linked_char is True:
                response.add_response_message(_("Wenn du zukünfig alle Befehle mit deinem Charakter verknüpfen möchtest, kannst du dir deinen Standard-Charakter setzen:"))
                response.add_response_message("@{bot_username} {command}".format(
                    bot_username=self.bot_username,
                    command=MessageController.get_command("Ich-Bin").get_example({"command": None, "user_id": _("@Deine_User_Id"), "char_id": _("@Deine_Char_Id")})
                ))
            return None, response

        user_id = params[key]
        if params[key] is None:
            user_id = "@" + message.from_user

        return user_id.lower(), response

    def require_char_id(self, params, key, user_id, response: CommandMessageResponse, use_linked_char=True, use_first=False):
        command = response.get_command()
        chars = self.character_persistent_class.get_all_user_chars(user_id)
        user = response.get_user()
        linked_char_id = None
        if params[key] is None and use_linked_char is True and user.is_user_id == user_id:
            linked_char_id = user.is_char_id

        if linked_char_id is None and len(chars) == 0:
            response.add_response_message(_("Der Nutzer @{user_id} hat derzeit noch keine Charaktere angelegt. Siehe 'Vorlage' um einen Charakter zu erstellen.").format(
                user_id=user_id
            ))
            response.set_suggestions(["Vorlage @{}".format(user_id)])
            return None, response

        if linked_char_id is None and len(chars) > 1 and params[key] is None and use_first is False:

            chars_txt = ""
            for char in chars:
                if chars_txt != "":
                    chars_txt += "\n---\n\n"
                char_names = "\n".join(re.findall(r".*?name.*?:.*?\S+?.*", char["text"]))
                if char_names == "":
                    char_names = _("Im Steckbrief wurden keine Namen gefunden")
                chars_txt += _("*Charakter {char_id}*\n{char_names}").format(
                    char_id=char["char_id"],
                    char_names=char_names
                )

            big_body = _("Für den Nutzer sind mehrere Charaktere vorhanden. Bitte wähle einen aus:\n\n") + chars_txt
            for body in MessageController.split_messages(big_body, "---"):
                response.add_response_message(body)
                response.set_suggestions([command.get_example({**params, "char_id": char["char_id"]}) for char in chars][:12])

            return None, response

        char_id = params[key] if linked_char_id is None else linked_char_id
        if len(chars) == 1 and params[key] is None:
            char_id = chars[0]["char_id"]
        if char_id is None and use_first and params[key] is None:
            char_id = chars[0]["char_id"]

        found = False
        for char in chars:
            if int(char["char_id"]) == int(char_id):
                found = True
                break

        if found is False:
            response.add_response_message(_("Der Charakter mit der Id {} konnte nicht gefunden werden.").format(char_id))
            response.set_suggestions([command.get_example({**params, "char_id": char["char_id"]}) for char in chars][:12])
            return None, response

        return int(char_id), response

#
# Befehl hinzufügen
#
@MessageController.add_method({"de": "Hinzufügen", "en": "add"})
def msg_cmd_add(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" and message_body.split(None, 2)[2].strip() != "":
        selected_user = message_body.split(None, 2)[1][1:]

        auth = self.check_auth(user, message)
        if selected_user != self.get_from_userid(message) and auth is not True:
            return [auth], user_command_status, user_command_status_data

        char_id = self.character_persistent_class.add_char(message_body.split(None, 2)[1][1:].strip(), self.get_from_userid(message), message_body_c.split(None, 2)[2].strip())

        if char_id == CharacterPersistentClass.get_min_char_id():
            body = _("Alles klar! Der erste Charakter für @{user_id} wurde hinzugefügt.").format(user_id=selected_user)
        else:
            body = _("Alles klar! Der {char_id}. Charakter für @{user_id} wurde hinzugefügt.").format(char_id=char_id, user_id=selected_user)

        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=body,
            keyboards=[SuggestedResponseKeyboard(responses=[
                self.generate_text_response_user_char("Anzeigen", selected_user, char_id, message),
                self.generate_text_response_user_char("Bild-setzen", selected_user, char_id, message),
                self.generate_text_response_user_char("Löschen", selected_user, char_id, message, force_username=True),
                MessageController.generate_text_response("Liste")
            ])]
        ))
    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] != "@":
        char_id = self.character_persistent_class.add_char(self.get_from_userid(message), self.get_from_userid(message), message_body_c.split(None, 1)[1].strip())
        body2 = None

        if self.is_aliased(message) is False and char_id == CharacterPersistentClass.get_min_char_id():
            body = _("Alles klar! Dein erster Charakter wurde hinzugefügt.")
        elif self.is_aliased(message) is False:
            body = _("Alles klar! Dein {char_id}. Charakter wurde hinzugefügt.").format(char_id=char_id)
        else:
            body = _("Alles klar! Dein Charakter wurde hinzugefügt. \n" +
                     "Der Charakter wurde temporär dem Alias-User @{alias_user_id} zugeordnet.\n\n" +
                     "Aufgrund der letzten Änderung von Kik, konnte ich dir den Charakter nicht direkt zuordnen.\n" +
                     "Damit der Charakter auch wirklich dir zugeordnet wird, sende bitte jetzt den folgenden Befehl " +
                     "(Bitte kopieren und deine Nutzer_Id ersetzen):").format(alias_user_id=self.get_from_userid(message))
            body2 = _("@{user_id} @Deine_Nutzer_Id").format(user_id=self.bot_username)
            user_command_status = CharacterPersistentClass.STATUS_DYN_MESSAGES
            user_command_status_data = {
                'add_user_id': "Verschieben @{} @{} {}".format(self.get_from_userid(message), "{}", char_id)
            }

        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=body,
            keyboards=[SuggestedResponseKeyboard(responses=[
                self.generate_text_response_user_char("Anzeigen", self.get_from_userid(message), char_id, message),
                self.generate_text_response_user_char("Bild-setzen", self.get_from_userid(message), char_id, message),
                self.generate_text_response_user_char("Löschen", self.get_from_userid(message), char_id, message, force_username=True),
                MessageController.generate_text_response("Liste")
            ])]
        ))

        if body2 is not None:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=body2
            ))
    else:
        response_messages.append(MessageController.get_error_response(message))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl ändern
#
@MessageController.add_method({"de": "Ändern", "en": "change"})
def msg_cmd_change(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 3)) == 4 and message_body.split(None, 3)[1][0] == "@" \
            and message_body.split(None, 3)[2].isdigit() and message_body.split(None, 3)[3].strip() != "":

        user_id = message_body.split(None, 3)[1][1:].strip()
        char_id = int(message_body.split(None, 3)[2])
        text = message_body_c.split(None, 3)[3].strip()

        auth = self.check_auth(user, message)
        if user_id != self.get_from_userid(message) and auth is not True:
            return [auth], user_command_status, user_command_status_data

        self.character_persistent_class.change_char(user_id, self.get_from_userid(message), text, char_id)
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Alles klar! Der {char_id}. Charakter für @{user_id} wurde gespeichert.").format(char_id=char_id, user_id=user_id),
            keyboards=[SuggestedResponseKeyboard(responses=[
                self.generate_text_response_user_char("Anzeigen", user_id, char_id, message),
                self.generate_text_response_user_char("Bild-setzen", user_id, char_id, message),
                self.generate_text_response_user_char("Letzte-Löschen", user_id, char_id, message, force_username=True),
                MessageController.generate_text_response("Liste")
            ])]
        ))
    elif len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1].isdigit() and message_body.split(None, 2)[2].strip() != "":

        char_id = int(message_body.split(None, 2)[1])
        text = message_body_c.split(None, 2)[2].strip()

        self.character_persistent_class.change_char(self.get_from_userid(message), self.get_from_userid(message), text, char_id)
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Alles klar! Dein {char_id}. Charakter wurde gespeichert.").format(char_id=char_id),
            keyboards=[SuggestedResponseKeyboard(responses=[
                self.generate_text_response_user_char("Anzeigen", self.get_from_userid(message), char_id, message),
                self.generate_text_response_user_char("Bild-setzen", self.get_from_userid(message), char_id, message),
                self.generate_text_response_user_char("Letzte-Löschen", self.get_from_userid(message), char_id, message, force_username=True),
                MessageController.generate_text_response("Liste")
            ])]
        ))
    elif len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" and message_body.split(None, 2)[2].strip() != "":
        user_id = message_body.split(None, 2)[1][1:].strip()

        auth = self.check_auth(user, message)
        if user_id != self.get_from_userid(message) and auth is not True:
            return [auth], user_command_status, user_command_status_data

        self.character_persistent_class.change_char(message_body.split(None, 2)[1][1:].strip(), self.get_from_userid(message), message_body_c.split(None, 2)[2].strip())
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Alles klar! Der erste Charakter für @{user_id} wurde gespeichert.").format(user_id=user_id),
            keyboards=[SuggestedResponseKeyboard(responses=[
                self.generate_text_response_user_char("Anzeigen", user_id, None, message),
                self.generate_text_response_user_char("Bild-setzen", user_id, None, message),
                self.generate_text_response_user_char("Letzte-Löschen", user_id, None, message, force_username=True),
                MessageController.generate_text_response("Liste")
            ])]
        ))
    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] != "@":
        self.character_persistent_class.change_char(self.get_from_userid(message), self.get_from_userid(message), message_body_c.split(None, 1)[1].strip())
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Alles klar! Dein erster Charakter wurde gespeichert."),
            keyboards=[SuggestedResponseKeyboard(responses=[
                self.generate_text_response_user_char("Anzeigen", self.get_from_userid(message), None, message),
                self.generate_text_response_user_char("Bild-setzen", self.get_from_userid(message), None, message),
                self.generate_text_response_user_char("Letzte-Löschen", self.get_from_userid(message), None, message, force_username=True),
                MessageController.generate_text_response("Liste")
            ])]
        ))
    else:
        response_messages.append(MessageController.get_error_response(message))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl Bild setzen
#
@MessageController.add_method({"de": "Bild-setzen", "en": "set-picture", "_alts": ["set-pic", "Setze-Bild"]})
def msg_cmd_set_pic(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    response = None

    if len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" \
            and message_body.split(None, 2)[2].isdigit():

        user_id = message_body.split(None, 2)[1][1:].strip()
        char_id = int(message_body.split(None, 2)[2])

        auth = self.check_auth(user, message)
        if user_id != self.get_from_userid(message) and auth is not True:
            return [auth], user_command_status, user_command_status_data

    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].isdigit():

        user_id = self.get_from_userid(message)
        char_id = int(message_body.split(None, 1)[1])

    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
        user_id = message_body.split(None, 1)[1][1:].strip()
        char_id = None

        auth = self.check_auth(user, message)
        if user_id != self.get_from_userid(message) and auth is not True:
            return [auth], user_command_status, user_command_status_data

    else:
        user_id = self.get_from_userid(message)
        char_id = None

    user_command_status = CharacterPersistentClass.STATUS_SET_PICTURE
    user_command_status_data = {
        'user_id': user_id,
        'char_id': char_id
    }

    response_messages.append(TextMessage(
        to=message.from_user,
        chat_id=message.chat_id,
        body=_("Alles Klar! Bitte schicke jetzt das Bild direkt an @{bot_username}").format(bot_username=self.bot_username)
    ))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl Anzeigen
#
msg_cmd_show_command = MessageCommand([
    MessageParam.init_user_id(),
    MessageParam.init_char_id(required=False)
], "Anzeigen", "show", ["Steckbrief", "Stecki"])
@MessageController.add_method(msg_cmd_show_command)
def msg_cmd_show(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    params = response.get_params()

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response, use_first=True)
    if char_id is None:
        return response

    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass
    char_data = character_persistent_class.get_char(plain_user_id, char_id)

    chars = character_persistent_class.get_all_user_chars(plain_user_id)
    if len(chars) > 1:
        add_ac = AdditionalActions(_("Weitere Charaktere"))
        for char in chars:
            if int(char["char_id"]) != int(char_data["char_id"]):
                add_ac.add_action(char["char_id"], message_controller.generate_text_user_char("Anzeigen", plain_user_id, int(char["char_id"]), response.get_orig_message()))

        response.add_additional_actions(add_ac)

    response = message_controller.create_char_messages(char_data, response)
    return response

#
# Befehl Verschieben
#
@MessageController.add_method({"de": "Verschieben", "en": "move"})
def msg_cmd_move(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" and message_body.split(None, 2)[2][0] == "@":
        if len(message_body.split(None, 3)) == 4 and message_body.split(None, 3)[3].isdigit():
            char_id = int(message_body.split(None, 3)[3])
            selected_from_user = message_body.split(None, 3)[1][1:].strip()
            selected_to_user = message_body.split(None, 3)[2][1:].strip()
        else:
            char_id = None
            selected_from_user = message_body.split(None, 2)[1][1:].strip()
            selected_to_user = message_body.split(None, 2)[2][1:].strip()

        if selected_from_user == self.get_from_userid(message):
            to_char_id = self.character_persistent_class.move_char(selected_from_user, selected_to_user, char_id)

            if char_id is not None and char_id != CharacterPersistentClass.get_min_char_id():
                body = _("Du hast erfolgreich deinen {from_char_id}. Charakter auf @{to_user_id} ({to_char_id}.) verschoben.").format(
                    from_char_id=char_id,
                    to_user_id=selected_to_user,
                    to_char_id=to_char_id
                )
            else:
                body = _("Du hast erfolgreich deinen Charakter auf @{to_user_id} ({to_char_id}.) verschoben.").format(
                    to_user_id=selected_to_user,
                    to_char_id=to_char_id
                )

            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=body,
                keyboards=[SuggestedResponseKeyboard(responses=[
                    self.generate_text_response_user_char("Anzeigen", selected_to_user, char_id, message),
                    self.generate_text_response_user_char("Bild-setzen", selected_to_user, char_id, message),
                    self.generate_text_response_user_char("Löschen", selected_to_user, char_id, message, force_username=True),
                    MessageController.generate_text_response("Liste")
                ])]
            ))

        elif self.is_admin(message):
            to_char_id = self.character_persistent_class.move_char(selected_from_user, selected_to_user, char_id)

            if char_id is not None and char_id != CharacterPersistentClass.get_min_char_id():
                body = _("Du hast erfolgreich den {from_char_id}. Charakter von @{from_user_id} auf @{to_user_id} ({to_char_id}.) verschoben.").format(
                    from_char_id=char_id,
                    from_user_id=selected_from_user,
                    to_user_id=selected_to_user,
                    to_char_id=to_char_id
                )
            else:
                body = _("Du hast erfolgreich den ersten Charakter von @{from_user_id} auf @{to_user_id} ({to_char_id}.) verschoben.").format(
                    from_user_id=selected_from_user,
                    to_user_id=selected_to_user,
                    to_char_id=to_char_id
                )

            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=body,
                keyboards=[SuggestedResponseKeyboard(responses=[
                    self.generate_text_response_user_char("Anzeigen", selected_to_user, to_char_id, message),
                    MessageController.generate_text_response("Liste")
                ])]
            ))

        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du kannst keine Charaktere von anderen Nutzern verschieben."),
                keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Liste")])]
            ))

    else:
        response_messages.append(MessageController.get_error_response(message))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl Löschen
#
@MessageController.add_method({"de": "Löschen", "en": "delete", "_alts": ["del"]})
def msg_cmd_delete(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
        if len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[2].isdigit():
            char_id = int(message_body.split(None, 2)[2])
            selected_user = message_body.split(None, 2)[1][1:].strip()
        else:
            char_id = None
            selected_user = message_body.split(None, 1)[1][1:].strip()

        if selected_user == self.get_from_userid(message):
            self.character_persistent_class.remove_char(selected_user, self.get_from_userid(message), char_id)

            if char_id is not None:
                body = _("Du hast erfolgreich deinen {char_id}. Charakter gelöscht").format(char_id=char_id)
            else:
                body = _("Du hast erfolgreich deinen Charakter gelöscht.")

            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=body,
                keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Liste")])]
            ))

        elif self.is_admin(message):
            self.character_persistent_class.remove_char(selected_user, self.get_from_userid(message), char_id)

            if char_id is not None:
                body = _("Du hast erfolgreich den {char_id}. Charakter von @{user_id} gelöscht.").format(char_id=char_id, user_id=selected_user)
            else:
                body = _("Du hast erfolgreich den ersten Charakter von @{user_id} gelöscht.").format(user_id=selected_user)

            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=body,
                keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Liste")])]
            ))

        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du kannst keine Charaktere von anderen Nutzern löschen."),
                keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Liste")])]
            ))

    else:
        response_messages.append(MessageController.get_error_response(message))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl Löschen (letzte)
#
@MessageController.add_method({"de": "Letzte-Löschen", "en": "delete-last", "_alts": ["del-last"]})
def msg_cmd_delete_last(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
        if len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[2].isdigit():
            char_id = int(message_body.split(None, 2)[2])
            selected_user = message_body.split(None, 2)[1][1:].strip()
        else:
            char_id = None
            selected_user = message_body.split(None, 1)[1][1:].strip()

        if selected_user == self.get_from_userid(message):
            self.character_persistent_class.remove_last_char_change(selected_user, self.get_from_userid(message))

            if char_id is not None:
                body = _("Du hast erfolgreich die letzte Änderung am Charakter {char_id} gelöscht.").format(char_id=char_id)
            else:
                body = _("Du hast erfolgreich die letzte Änderung gelöscht.")

            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=body,
                keyboards=[SuggestedResponseKeyboard(responses=[
                    MessageController.generate_text_response("Liste"),
                    self.generate_text_response_user_char("Anzeigen", selected_user, char_id, message)
                ])]
            ))

        elif self.is_admin(message):
            self.character_persistent_class.remove_last_char_change(selected_user, self.get_from_userid(message))

            if char_id is not None:
                body = _("Du hast erfolgreich die letzte Änderung des Charakters {char_id} von @{user_id} gelöscht.").format(char_id=char_id, user_id=selected_user)
            else:
                body = _("Du hast erfolgreich die letzte Änderung des Charakters von @{user_id} gelöscht.").format(user_id=selected_user)

            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=body,
                keyboards=[SuggestedResponseKeyboard(responses=[
                    MessageController.generate_text_response("Liste"),
                    self.generate_text_response_user_char("Anzeigen", selected_user, char_id, message)
                ])]
            ))

        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du kannst keine Charaktere von anderen Nutzern löschen."),
                keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Liste")])]
            ))

    else:
        response_messages.append(MessageController.get_error_response(message))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl Suche
#
msg_cmd_search_command = MessageCommand([
    MessageParam.init_user_id(required=False),
    MessageParam("name", MessageParam.CONST_REGEX_TEXT, examples=["Jan", "Mafu", "Aiden"], required=True),
], "Suche", "search", require_auth=True)
@MessageController.add_method(msg_cmd_search_command)
def msg_cmd_search(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass
    user_id = response.get_value("user_id")
    plain_user_id = user_id[1:].lower() if user_id is not None else None

    chars = character_persistent_class.search_char(response.get_value("name"), user_id=plain_user_id)

    if len(chars) == 0:
        response.add_response_message(_("Für die Suchanfrage wurden keine Charaktere gefunden."))
        response.set_suggestions(["Liste"])
        return response

    if len(chars) == 1:
        response = message_controller.create_char_messages(chars[0], response)
        return response

    suggestions = []
    for char in chars:
        suggestions.append(message_controller.generate_text_user_char("Anzeigen", char['user_id'], char['char_id'], response.get_orig_message()))
    suggestions.append("Liste")

    response.add_response_message(_("Es wurden mehrere Charaktere gefunden, die deiner Suchanfrage entsprechen."))
    response.set_suggestions(suggestions)
    return response

#
# Befehl Setze Befehl Tastaturen
#
msg_cmd_set_cmd_keyboards_command = MessageCommand([
    MessageParam("command_name", MessageParam.CONST_REGEX_COMMAND, required=True, examples=["Hilfe", "Neuer-Command", "Lol"]),
    MessageParam("actions", MessageParam.CONST_REGEX_TEXT, required=True, examples=["Hilfe, Liste", "Hilfe", "Hilfe, Wer-Bin-Ich"])
], "Setze-Befehl-Tastaturen", "set-command-keyboards", ["set-cmd-keyboards"], require_admin=True)
@MessageController.add_method(msg_cmd_set_cmd_keyboards_command)
def msg_cmd_set_cmd_keyboards(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: MessageController
    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass

    actions = response.get_value("actions")
    static_command = response.get_value("command_name")
    static_message = character_persistent_class.get_static_message(static_command)

    if static_message is None:
        response.add_response_message(_("Der Befehl '{command}' existiert nicht.").format(command=static_command))
        response.set_suggestions(["Admin-Hilfe"])
        return response

    static_message = character_persistent_class.set_static_message_keyboard(static_message["command"], [x.strip() for x in actions.split(',')])
    message_controller.update_static_commands()

    example_alt_commands = "Alt-Befehl1, Alt-Befehl2, etc."
    if static_message["alt_commands"] is not None:
        example_alt_commands = ", ".join(json.loads(static_message["alt_commands"]))

    response.add_response_message(_("Du hast erfolgreich die Tastaturen für den statischen Befehl '{command}' aktualisiert.\n" +
               "Du kannst auch alternative Befehle (wie z.B. 'h' für Hilfe oder 'rules' für Regeln) hinzufügen. Dies geht mit dem Befehl:\n\n" +
               "@{bot_username} {set_cmd_alt_cmd_command} {command} {curr_alt_cmd}").format(
            command=static_message["command"],
            bot_username=message_controller.bot_username,
            curr_alt_cmd=example_alt_commands,
            set_cmd_alt_cmd_command=MessageController.get_command_text("Setze-Befehl-Alternative-Befehle")
    ))

    response.set_suggestions([static_message["command"], "Admin-Hilfe"])
    return response



#
# Befehl Setze Befehl Alternative Befehle
#
msg_cmd_set_cmd_alt_cmd_command = MessageCommand([
    MessageParam("command_name", MessageParam.CONST_REGEX_COMMAND, required=True, examples=["Hilfe", "Neuer-Command", "Lol"]),
    MessageParam("alt_commands", MessageParam.CONST_REGEX_TEXT, required=True, examples=["Hilfe, Liste", "Hilfe", "Hilfe, Wer-Bin-Ich"])
], "Setze-Befehl-alternative-Befehle", "set-command-alternative-commands", ["set-cmd-alt-cmd"], require_admin=True)
@MessageController.add_method(msg_cmd_set_cmd_alt_cmd_command)
def msg_cmd_set_cmd_alt_cmd(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: MessageController
    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass

    alt_commands = response.get_value("alt_commands")
    static_command = response.get_value("command_name")
    static_message = character_persistent_class.get_static_message(static_command)

    if static_message is None:
        response.add_response_message(_("Der Befehl '{command}' existiert nicht.").format(command=static_command))
        response.set_suggestions(["Admin-Hilfe"])
        return response

    static_message = character_persistent_class.set_static_message_alt_commands(static_message["command"], [x.strip() for x in alt_commands.split(',')])
    message_controller.update_static_commands()

    example_keyboards = "Hilfe, Liste"
    if static_message["response_keyboards"] is not None:
        example_keyboards = ", ".join(json.loads(static_message["response_keyboards"]))

    response.add_response_message(_("Du hast erfolgreich die alternativen Befehle für den Befehl '{command}' aktualisiert.\n" +
               "Du kannst jetzt noch mit dem folgenden Befehl die Antwort-Tastaturen setzen (Komma-getrennt):\n\n" +
               "@{bot_username} {set_cmd_keyboards_command} {command} {curr_keyboards}").format(
            command=static_message["command"],
            bot_username=message_controller.bot_username,
            curr_keyboards=example_keyboards,
            set_cmd_keyboards_command=MessageController.get_command_text("Setze-Befehl-Tastaturen"),
    ))

    response.set_suggestions([static_message["command"], "Admin-Hilfe"])
    return response


#
# Befehl Setze Antwort
#
msg_cmd_set_command_command = MessageCommand([
    MessageParam("command_name", MessageParam.CONST_REGEX_COMMAND, required=True, examples=["Hilfe", "Neuer-Command", "Lol"]),
    MessageParam("text", MessageParam.CONST_REGEX_TEXT, required=True, examples=["Antworttext"])
], "Setze-Befehl", "set-command", ["set-cmd"], require_admin=True)
@MessageController.add_method(msg_cmd_set_command_command)
def msg_cmd_set_command(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: MessageController
    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass

    text = response.get_value("text")
    static_command = response.get_value("command_name")
    static_message = character_persistent_class.get_static_message(static_command)

    if static_message is not None:
        static_command = static_message["command"]

    static_message = character_persistent_class.set_static_message(static_command, text)
    message_controller.update_static_commands()

    example_keyboards = "Hilfe, Liste"
    if static_message["response_keyboards"] is not None:
        example_keyboards = ", ".join(json.loads(static_message["response_keyboards"]))

    example_alt_commands = "Alt-Befehl1, Alt-Befehl2, etc."
    if static_message["alt_commands"] is not None:
        example_alt_commands = ", ".join(json.loads(static_message["alt_commands"]))

    response.add_response_message(_("Du hast erfolgreich die statische Antwort auf den Befehl '{command}' aktualisiert.\n" +
               "Du kannst jetzt noch mit dem folgenden Befehl die Antwort-Tastaturen setzen (Komma-getrennt):\n\n" +
               "@{bot_username} {set_cmd_keyboards_command} {command} {curr_keyboards}\n\n\n" +
               "Du kannst auch alternative Befehle (wie z.B. 'h' für Hilfe oder 'rules' für Regeln) hinzufügen. Dies geht mit dem Befehl:\n\n" +
               "@{bot_username} {set_cmd_alt_cmd_command} {command} {curr_alt_cmd}"
               ).format(
            command=static_message["command"],
            bot_username=message_controller.bot_username,
            curr_keyboards=example_keyboards,
            curr_alt_cmd=example_alt_commands,
            set_cmd_keyboards_command=MessageController.get_command_text("Setze-Befehl-Tastaturen"),
            set_cmd_alt_cmd_command=MessageController.get_command_text("Setze-Befehl-Alternative-Befehle")
    ))

    response.set_suggestions([static_message["command"], "Admin-Hilfe"])
    return response


#
# Befehl Auth
#
msg_cmd_auth_command = MessageCommand([
    MessageParam.init_user_id(required=True),
], "Berechtigen", "auth", ["authorize", "authorise"], require_auth=True)
@MessageController.add_method(msg_cmd_auth_command)
def msg_cmd_auth(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: MessageController
    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass
    plain_user_id = response.get_value("user_id")[1:]

    to_auth_user_db = character_persistent_class.get_user(plain_user_id)
    to_auth_user = User.init(to_auth_user_db) if to_auth_user_db is not None else User.init_new_user(plain_user_id, message_controller.bot_username)
    to_auth_user.auth(response.get_user())
    character_persistent_class.update_user(to_auth_user, as_request=False)

    response.add_response_message(_("Du hast erfolgreich den Nutzer @{user_id} berechtigt.").format(user_id=plain_user_id))
    return response


#
# Befehl UnAuth
#
msg_cmd_unauth_command = MessageCommand([
    MessageParam.init_user_id(required=True),
], "Entmachten", "unauth", ["unauthorize", "unauthorise"], require_admin=True)
@MessageController.add_method(msg_cmd_unauth_command)
def msg_cmd_unauth(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: MessageController
    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass
    plain_user_id = response.get_value("user_id")[1:]

    to_auth_user_db = character_persistent_class.get_user(plain_user_id)
    to_auth_user = User.init(to_auth_user_db) if to_auth_user_db is not None else User.init_new_user(plain_user_id, message_controller.bot_username)
    to_auth_user.unauth()
    character_persistent_class.update_user(to_auth_user, as_request=False)

    response.add_response_message(_("Du hast erfolgreich den Nutzer @{user_id} entmächtigt.").format(user_id=plain_user_id))
    return response


#
# Befehl Admin-Auth
#
msg_cmd_auth_admin_command = MessageCommand([
    MessageParam.init_user_id(required=True),
], "Admin-geben", "auth-admin", ["authorize-admin", "authorise-admin"], require_admin=True)
@MessageController.add_method(msg_cmd_auth_admin_command)
def msg_cmd_auth_admin(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: MessageController
    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass
    plain_user_id = response.get_value("user_id")[1:]

    to_auth_user_db = character_persistent_class.get_user(plain_user_id)
    to_auth_user = User.init(to_auth_user_db) if to_auth_user_db is not None else User.init_new_user(plain_user_id, message_controller.bot_username)
    to_auth_user.set_admin(True)
    character_persistent_class.update_user(to_auth_user, as_request=False)

    response.add_response_message(_("Der Nutzer @{user_id} hat nun Admin-Berechtigungen.").format(user_id=plain_user_id))
    return response


#
# Befehl UnAuth
#
msg_cmd_unauth_admin_command = MessageCommand([
    MessageParam.init_user_id(required=True),
], "Admin-nehmen", "unauth-admin", ["unauthorize-admin", "unauthorise-admin"], require_admin=True)
@MessageController.add_method(msg_cmd_unauth_admin_command)
def msg_admin_cmd_unauth(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: MessageController
    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass
    plain_user_id = response.get_value("user_id")[1:]

    to_auth_user_db = character_persistent_class.get_user(plain_user_id)
    to_auth_user = User.init(to_auth_user_db) if to_auth_user_db is not None else User.init_new_user(plain_user_id, message_controller.bot_username)
    to_auth_user.set_admin(False)
    character_persistent_class.update_user(to_auth_user, as_request=False)

    response.add_response_message(_("Der Nutzer @{user_id} kann keine Admin-Befehle mehr ausführen.").format(user_id=plain_user_id))
    return response


#
# Befehl scan-active
#
scan_active_command = MessageCommand([
], "Scanne-Active", "scan-active", [], require_admin=True)
@MessageController.add_method(scan_active_command)
def scan_active(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: MessageController

    if response.request_is_private_group() is False:
        response.add_response_message(_("Dieser Befehl kann nur in einer privaten Gruppe ausgeführt werden!"))
        return response

    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass
    users_with_chars_row = character_persistent_class.list_all_users_with_chars(list_all=True)
    group_users = set(response.get_all_group_users())
    users_with_chars_in_group = set() # werden (wieder) aktiviert
    users_with_chars_not_in_group = set() # werden deaktiviert, wenn nicht neu
    aliased_chars = set()

    for user_row in users_with_chars_row:
        if user_row["user_id"] in group_users or (user_row["created"] + 3*60*60*24 >= int(time.time()) and message_controller.is_aliased_user(user_row["user_id"])):
            users_with_chars_in_group.add(user_row["user_id"])
        elif message_controller.is_aliased_user(user_row["user_id"]):
            aliased_chars.add(user_row["user_id"])
        else:
            users_with_chars_not_in_group.add(user_row["user_id"])

    users_without_chars_in_group = group_users - users_with_chars_in_group

    response.add_response_message(_(
        "Steckbriefe wurden gescannt:\n\n"
        "{cnt_users_deactivate} mit Steckbriefen sind nicht mehr in der Gruppe und können deaktiviert werden.\n"
        "{cnt_users_aliased} Personen haben dem Steckbrief nicht ihre Benutzer-Id hinterlegt.\n"
        "Folgende Nutzer sind in der Gruppe, aber haben noch keinen Steckbrief:\n"
        "{users_without_chars_list}"
    ).format(
        cnt_users_deactivate=len(users_with_chars_not_in_group),
        cnt_users_aliased=len(aliased_chars),
        users_without_chars_list="\n".join(["@"+user_id for user_id in users_without_chars_in_group])
    ))

    return response


#
# Befehl i-am
#
iam_command = MessageCommand([
    MessageParam.init_user_id(),
    MessageParam.init_char_id(),
], "Ich-Bin", "i-am", ["iam"])
@MessageController.add_method(iam_command)
def i_am(response: CommandMessageResponse):
    message_controller = response.get_message_controller()  # type: MessageController
    params = response.get_params()
    user = response.get_user() # type: User

    user_id, response = message_controller.require_user_id(params, "user_id", response)
    if user_id is None:
        return response

    plain_user_id = user_id[1:]

    char_id, response = message_controller.require_char_id(params, "char_id", plain_user_id, response)
    if char_id is None:
        return response

    user.set_linked_chars(plain_user_id, char_id)

    response.add_response_message(_("Alles klar!\n"
                                    "Alle charakter-spezifischen Befehle sind ab jetzt für dich standardmäßig auf @{user_id} mit der Charakter-Id {char_id} gesetzt.\n\n"
                                    "Bitte beachte: Möglicherweise musst du den Befehl erneut ausführen, wenn du deinen Namen oder Profilbild änderst.\n"
                                    "Durch die Änderung wird dir durch Kik neue ID zugewiesen.").format(
        user_id=plain_user_id,
        char_id=char_id
    ))
    response.set_suggestions(["Anzeigen", "Wer-bin-ich"])
    return response

#
# Befehl Wer bin ich
#
iam_command = MessageCommand([
], "Wer-bin-ich", "who-am-i", ["wer-bin-ich?", "whoami", "who-am-i?"])
@MessageController.add_method(iam_command)
def who_am_i(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    user = response.get_user() # type: User

    if user["is_user_id"] is None:
        response.add_response_message(_(
            "Du führst derzeit alle Befehle als du selbst aus. Kik hat dir für diese Gruppe folgende Benutzer-ID zugewiesen:\n\n"
            "@{user_id}\n\n"
            "Wenn du Befehle mit einer anderen Benutzer-ID und std. Charakter ausführen möchtest, dann führe hier folgenden Befehl aus:"
        ).format(
            user_id=user.get_user_id()
        ))
        response.add_response_message(_("@{bot_username} {iam_command}").format(
            bot_username=message_controller.bot_username,
            iam_command=message_controller.get_command("i-am").get_example({"user_id": _("@deine.id"), "char_id": "1", "command": None})
        ))
        return response

    response.add_response_message(_("Alle Befehle sind für dich standardmäßig auf @{user_id} mit der Charakter-Id {char_id} gesetzt.").format(
        user_id=user["is_user_id"],
        char_id=user["is_char_id"]
    ))
    response.set_suggestions(["Anzeigen"])
    return response


#
# Befehl Befehle
#
commands_command = MessageCommand([
], "Befehle", "commands")
@MessageController.add_method(commands_command)
def commands(response: CommandMessageResponse):
    message_controller = response.get_message_controller()

    show_commands = []
    suggestions = []
    for cmd_id, obj in enumerate(message_controller.methods):
        cmds = obj["cmds"] # type: MessageCommand
        if isinstance(cmds, MessageCommand) and cmds.is_admin_only() is False and cmds.is_hidden() is False:
            show_commands.append(cmds)
            suggestions.append(MessageController.get_command("Befehl").get_example({"command_name":cmds.get_command_loc(), "command": None}))

    symbols = {
        (False, False): u"\U000027A1\U0000FE0F",
        (True, False): u"\U0001F512",
        (False, True): u"\U0001F232",
        (True, True): u"\U0001F232"
    }
    response.add_response_message(_("Folgende weitere Befehle sind möglich:\n\n"
                                    "{more_commands}\n\n"
                                    "Für weitere Informationen zu einem Befehl schreibe").format(
        more_commands="\n".join([u"{symbol} {help_desc}".format(
            symbol=symbols[(cmd.is_auth_only(), cmd.is_admin_only())],
            help_desc=cmd.get_help_desc()
        ) for cmd in show_commands])
    ))
    response.set_suggestions(suggestions)
    return response

#
# Befehl Admin Befehle
#
admin_commands_command = MessageCommand([
], "Admin-Befehle", "admin-commands", require_admin=True)
@MessageController.add_method(admin_commands_command)
def admin_commands(response: CommandMessageResponse):
    message_controller = response.get_message_controller()

    show_commands = []
    suggestions = []
    for cmd_id, obj in enumerate(message_controller.methods):
        cmds = obj["cmds"] # type: MessageCommand
        if isinstance(cmds, MessageCommand) and cmds.is_admin_only() is True and cmds.is_hidden() is False:
            show_commands.append(cmds)
            suggestions.append(MessageController.get_command("Befehl").get_example({"command_name": cmds.get_command_loc(), "command": None}))

    symbols = {
        (False, False): u"\U000027A1\U0000FE0F",
        (True, False): u"\U0001F512",
        (False, True): u"\U0001F232",
        (True, True): u"\U0001F232"
    }
    response.add_response_message(_("Folgende weitere Admin Befehle sind möglich:\n\n"
                                    "{more_commands}\n\n"
                                    "Für weitere Informationen zu einem Befehl schreibe").format(
        more_commands="\n".join([u"{symbol} {help_desc}".format(
            symbol=symbols[(cmd.is_auth_only(), cmd.is_admin_only())],
            help_desc=cmd.get_help_desc()
        ) for cmd in show_commands])
    ))
    response.set_suggestions(suggestions)
    return response


#
# Befehl Befehl-Info
#
command_info_command = MessageCommand([
    MessageParam("command_name", MessageParam.CONST_REGEX_COMMAND, required=True, examples=["Ich-Bin", "Vorlage", "Befehle"])
], "Befehl", "command", ["Befehl-Info", "command-info"])
@MessageController.add_method(command_info_command)
def command_info(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    desc_command = message_controller.get_command(response.get_value("command_name")) # type: MessageCommand

    if desc_command is None:
        response.add_response_message(_("Der Befehl \"{command}\" existiert nicht.").format(
            command=response.get_value("command_name")
        ))
        response.set_suggestions(["Hilfe", "Befehle"])
        return response

    if isinstance(desc_command, MessageCommand) is False:
        response.add_response_message(_("Der Befehl \"{command}\" wurde noch nicht migriert und besitzt keine Hilfe.").format(
            command=response.get_value("command_name")
        ))
        response.set_suggestions(["Hilfe", "Befehle"])
        return response

    if desc_command.is_admin_only() is True and message_controller.is_admin(response.get_orig_message()) is False:
        # ist ein Admin Befehl
        response.add_response_message(_("Der Befehl \"{command}\" existiert nicht.").format(
            command=response.get_value("command_name")
        ))
        response.set_suggestions(["Hilfe", "Befehle"])
        return response

    response.add_response_message(_("Die Struktur des Befehls sieht wie folgt aus:\n"
                                    "{command_structure}\n\n\n"
                                    "{examples_5}\n\n\n"
                                    "alternative Namen für diesen Befehl (Aliasse):\n"
                                    "{aliasses}").format(
        command_structure=desc_command.get_help_desc(),
        examples_5=desc_command.get_random_example_text(5, response, {"command": desc_command.get_command_loc()}),
        aliasses="\n".join(u"\U000027A1\U0000FE0F " + name for name in desc_command.get_all_command_names())
    ))

    return response


#
# Befehl Liste
#
msg_cmd_list_command = MessageCommand([
    MessageParam("page", MessageParam.CONST_REGEX_NUM, examples=range(1,4), default_value=1)
], "Liste", "list", require_auth=True)
@MessageController.add_method(msg_cmd_list_command)
def msg_cmd_list(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass
    page = int(response.get_value("page"))
    limit = 15

    chars = character_persistent_class.list_all_users_with_chars(page)
    user_ids = [item['user_id'] for item in chars[:limit]]

    bodys = [_("Liste aller Nutzer mit Charakteren:\n--- Seite {page} ---\n").format(page=page)]
    number = (page - 1) * limit + 1
    for char in chars[:limit]:
        bodys.append(_("{consecutive_number}.: {user_name}\n" +
              "Nutzername: @{user_id}\n" +
              "Anz. Charaktere: {chars_cnt}\n" +
              "letzte Änderung: {last_change:%d.%m.%Y}"
              ).format(
            consecutive_number=number,
            user_name=message_controller.get_name(char['user_id']),
            user_id=char['user_id'],
            chars_cnt=char['chars_cnt'],
            last_change=datetime.datetime.fromtimestamp(char['created'])
        ))

        number += 1

    suggestions = list()
    dyn_message_data = {}
    if page != 1:
        dyn_message_data['left'] = "Liste {}".format(page - 1)
        suggestions.append(u"\U00002B05\U0000FE0F")
    if len(chars) > limit:
        dyn_message_data['right'] = "Liste {}".format(page + 1)
        suggestions.append(u"\U000027A1\U0000FE0F")

    if dyn_message_data != {}:
        response.user_command_status = CharacterPersistentClass.STATUS_DYN_MESSAGES
        response.user_command_status_data = dyn_message_data
        bodys.append(("\n\n(Weitere Seiten: {icon_left} und {icon_right} zum navigieren)").format(
            icon_left=u"\U00002B05\U0000FE0F",
            icon_right=u"\U000027A1\U0000FE0F"
        ))


    suggestions += [MessageController.generate_text_user_char("Anzeigen", user_id, None, response.get_orig_message(), force_username=True) for user_id in user_ids]
    response.set_suggestions(suggestions)
    response.add_response_messages(MessageController.split_messages("\n\n".join(bodys), split_char="\n\n"))

    return response


#
# Befehl Vorlage
#
template_command = MessageCommand([
    MessageParam.init_user_id(),
], "Vorlage", "template", ["Charaktervorlage", "boilerplate", "draft", "Steckbriefvorlage", "Stecki"])
@MessageController.add_method(template_command)
def msg_cmd_template(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    params = response.get_params()

    response.add_response_message(_(
        "Die folgende Charaktervorlage kann genutzt werden um einen neuen Charakter im RPG zu erstellen.\n"
        "Dies ist eine notwendige Voraussetung um am RPG teilnehmen zu können.\n"
        "Bitte poste diese Vorlage ausgefüllt im Gruppenchannel #{kik_group_id}\n"
        "Wichtig: Bitte lasse die Schlüsselwörter (Vorname:, Nachname:, etc.) stehen.\n"
        "Möchtest du die Vorlage nicht über den Bot speichern, dann entferne bitte die erste Zeile.\n"
        "Hast du bereits einen Charakter und möchtest diesen aktualisieren, dann schreibe in der ersten Zeile '{change_command}' anstatt '{add_command}'"
    ).format(
        kik_group_id=message_controller.config.get("KikGroup", "somegroup"),
        add_command=MessageController.get_command_text("Hinzufügen"),
        change_command=MessageController.get_command_text("Ändern"),
    ))

    template_message = message_controller.character_persistent_class.get_static_message('nur-vorlage')

    response.add_response_message(
        "@{bot_username} {add_command} {user_id_wa}\n".format(
            bot_username=message_controller.bot_username,
            add_command=MessageController.get_command_text("Hinzufügen"),
            user_id_wa=params["user_id"] if params["user_id"] is not None else ""
        ) + template_message["response"]
    )
    response.set_suggestions(["Hilfe", "Weitere-Beispiele"])
    return response


#
# Befehl Weitere Beispiele
#
msg_cmd_more_examples_command = MessageCommand([
], "Weitere-Beispiele", "more-examples")
@MessageController.add_method(msg_cmd_more_examples_command)
def msg_cmd_more_examples(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    response.add_response_message(_(
            "Weitere Beispiele\n"
            "Alle Beispiele sind in einzelnen Abschnitten mittels ----- getrennt.\n\n"
            "------\n"
            "@{bot_username} {add_command} @{user_id}\n"
            "Hier kann der Text zum Charakter stehen\n"
            "Zeilenumbrüche sind erlaubt\n"
            "In diesem Beispiel wurde der Nickname angegeben\n"
            "------\n"
            "@{bot_username} {change_command}\n"
            "Hier kann der Text zum Charakter stehen\n"
            "Die Befehle Ändern und Hinzufügen bewirken das gleiche\n"
            "Wird kein Benutzername angegeben so betrifft die Änderung bzw. das Hinzufügen einen selbst\n"
            "------\n"
            "@{bot_username} {show_command} @{admin_user}\n"
            "------\n"
            "@{bot_username} {show_command}\n"
            "------\n"
            "@{bot_username} {delete_command} @{user_id}\n"
            "------\n"
            "@{bot_username} {list_command}\n"
            "------\n"
            "@{bot_username} {help_command}\n"
            "------\n"
            "@{bot_username} {dice_command} 8\n"
            "------\n"
            "@{bot_username} {dice_command} Rot, Grün, Blau, Schwarz, Weiß\n"
            "------\n"
            "Bitte beachten, dass alle Befehle an den Bot mit @{bot_username} beginnen müssen. Die Nachricht darf"
            " mit keinem Leerzeichen oder sonstigen Zeichen beginnen, da ansonsten die Nachricht nicht an den Bot weitergeleitet wird.\n"
            "Wenn du bei dieser Nachricht auf Antworten tippst, werden dir unten {number} der oben gezeigten Beispiele als Vorauswahl angeboten"
        ).format(
            bot_username=message_controller.bot_username,
            user_id=response.get_user().get_user_id(),
            show_command=message_controller.get_command_text("Anzeigen"),
            delete_command=message_controller.get_command_text("Löschen"),
            list_command=message_controller.get_command_text("Liste"),
            help_command=message_controller.get_command_text("Hilfe"),
            dice_command=message_controller.get_command_text("Würfeln"),
            add_command=message_controller.get_command_text("Hinzufügen"),
            change_command=message_controller.get_command_text("Ändern"),
            number=7,
            admin_user=message_controller.config.get("Admins", "admin1").split(',')[0].strip()
    ))
    response.set_suggestions([
        "Hilfe",
        #TODO: entkommentieren message_controller.get_command("Hinzufügen").get_example({"command": None, "text": _("Neuer Charakter")}),
        message_controller.generate_text_user_char("Anzeigen", message_controller.config.get("Admins", "admin1").split(',')[0].strip(), None, response.get_orig_message()),
        "Anzeigen",
        "Liste",
        message_controller.get_command("Würfeln").get_example({"command": None, "term": "8"}),
        message_controller.get_command("Würfeln").get_example({"command": None, "term": _("Rot, Grün, Blau, Schwarz, Weiß")}),
    ])
    return response


#
# Befehl Würfeln
#
dice_command = MessageCommand([
    MessageParam("term", MessageParam.CONST_REGEX_TEXT, examples=["3", "4", "12", "24", "Rot, Grün, Blau", "10D6", "20D12", "20D12 + 10D8", "100D6"])
], "Würfeln", "dice", ["Würfel", u"\U0001F3B2", "roll"])
coin_command = MessageCommand([], "Münze", "coin")
@MessageController.add_method(dice_command)
@MessageController.add_method(coin_command)
def msg_cmd_roll(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    message_command = response.get_command()

    body = ""

    if message_command["en"] == message_controller.get_command("coin")["en"]:
        possibilities = [_("Kopf"), _("Zahl")]
        result = possibilities[random.randint(0, len(possibilities) - 1)]
        thing = _("Die Münze zeigt")
        body = "{}: {}".format(thing, result)
    else:
        term = response.get_value("term")
        if term is None or term == "":
            result = str(random.randint(1, 6))
            thing = _("Der Würfel zeigt")
            body = "{}: {}".format(thing, result)
        elif term.isdigit():
            count = int(term)
            result = str(random.randint(1, count))
            thing = _("Der Würfel zeigt")
            body = "{}: {}".format(thing, result)
        elif re.search(r"^(([0-9]+\s*([×x\*]\s*)?)?D\s*)?[0-9]+(\s*\+\s*(([0-9]+\s*([×x\*]\s*)?)?D\s*)?[0-9]+)*$", term,
                       re.MULTILINE + re.IGNORECASE) is not None:
            dices = str(term).split("+")
            results = list()
            result_int = 0
            for dice in dices:
                match = re.search(r"^((([0-9]+)\s*([×x\*]\s*)?)?D\s*)?([0-9]+)$", dice.strip(), re.MULTILINE + re.IGNORECASE)
                if match.group(1) is None:
                    res = int(match.group(5))
                    result_int += res
                    text = str(res)
                    results.append(text)
                elif match.group(3) is None or int(match.group(3)) <= 1:
                    res = random.randint(1, int(match.group(5)))
                    result_int += res
                    text = "D{}: {}".format(int(match.group(5)), res)
                    results.append(text)
                else:
                    res_text = ""

                    if int(match.group(3)) <= 20:
                        loops = int(match.group(3))
                        while loops > 0:
                            res = random.randint(1, int(match.group(5)))
                            result_int += res
                            if res_text != "":
                                res_text += ", "
                            res_text += str(res)
                            loops -= 1
                    else:
                        dice_results = [0] * int(match.group(3))
                        loops = int(match.group(3))
                        while loops > 0:
                            res = random.randint(1, int(match.group(5)))
                            result_int += res
                            dice_results[res-1] += 1
                            loops -= 1

                        e = 0
                        while e < int(match.group(3)):
                            e += 1
                            if dice_results[e-1] == 0:
                                continue

                            if res_text != "":
                                res_text += ", "

                            res_text += "{}×{}".format(dice_results[e-1],e)

                    text = "{}×D{}: ({})".format(int(match.group(3)), int(match.group(5)), res_text)
                    results.append(text)

                if len(results) >= 4:
                    body = "{}:\n\n{}\n".format(_("Die Würfel zeigen"), " + \n".join(results))
                else:
                    body = "{}: {}".format(_("Die Würfel zeigen"), " + ".join(results))
                body += "\n{}: {}".format(_("Ergebnis"), str(result_int))
        else:
            possibilities = [x.strip() for x in term.split(',')]

            if len(possibilities) == 1:
                response.add_response_message(_("Bitte gib mehr als nur eine Auswahlmöglichkeit an. z.B.: {}, Zweite, Dritte, ...".format(term)))
                response.set_suggestions([
                    message_command.get_example({"command": None, "term": "{}, Zweite, Dritte, ...".format(term)}),
                    message_controller.get_command("Befehl").get_example({"command": None, "command_name": message_command}),
                    u"\U0001F504",
                    "Hilfe"
                ])
                return response

            result = possibilities[random.randint(0, len(possibilities) - 1)]
            thing = _("Ich wähle")
            body = "{}: {}".format(thing, result)

    response.user_command_status = CharacterPersistentClass.STATUS_DYN_MESSAGES
    response.user_command_status_data = {
        'redo': response.get_message_body()
    }

    response.add_response_message(body)
    response.set_suggestions([u"\U0001F504", "Hilfe"])
    return response


debug_url_cmd = MessageCommand([], "Debug-URL", "debug-url", hidden=True, require_admin=True)
@MessageController.add_method(debug_url_cmd)
def quest_status(response: CommandMessageResponse):

    message_controller = response.get_message_controller()

    log_requests = message_controller.get_config().get("LogRequests", "False")
    if log_requests is not True and str(log_requests).lower() != "true":
        response.add_response_message("Der Bot läuft derzeit nicht im Log-Request Modus. Debug URL deaktiviert.")
    else:
        response.add_response_message("Debug URL: {host}:{port}/debug".format(
            bot_username=message_controller.bot_username,
            host=message_controller.get_config().get("RemoteHostIP", "www.example.com"),
            port=message_controller.get_config().get("RemotePort", "8080")
        ))

    return response

#
# Befehl statische Antwort / keine Antwort
#
@MessageController.add_method(MessageCommand([], "Hilfe", "help", ["?", "h", "hilfe!", "rpg-help"]))
@MessageController.add_method(MessageCommand([], "Regeln", "rules"))
@MessageController.add_method(MessageCommand([], "nur-Vorlage", "template-only", hidden=True))
@MessageController.add_method(MessageCommand([], "Kurzbefehle", "help2", ["Hilfe2"]))
@MessageController.add_method(MessageCommand([], "Admin-Hilfe", "admin-help", require_admin=True))
@MessageController.add_method(MessageCommand([], "Quellcode", "sourcecode", ["source", "lizenz", "licence"]))
@MessageController.set_static_method
def msg_cmd_other(response: CommandMessageResponse):
    message_controller = response.get_message_controller()
    character_persistent_class = message_controller.character_persistent_class  # type: CharacterPersistentClass
    message_command = response.get_command().get_command_loc()
    static_message = character_persistent_class.get_static_message(message_command)

    if static_message is None:
        response.set_suggestions(["Hilfe", "Befehle"])
        response.add_response_messages(_("Sorry {user[first_name]}, den Befehl '{command}' kenne ich nicht.").format(
            user=response.get_command(),
            command=message_command)
        )
        return response

    if static_message["response_keyboards"] is None:
        suggestions = ["Hilfe"]
    else:
        suggestions = json.loads(static_message["response_keyboards"])

    messages = MessageController.split_messages(static_message["response"].format(
        bot_username=message_controller.bot_username,
        user=response.get_user(),
        command=message_command,
        kik_group_id=message_controller.config.get("KikGroup", "somegroup"),
        user_id=response.get_user().get_user_id(),
        message=response.get_orig_message(),
        ruser=LazyRandomKikUser(
            response.get_orig_message().participants,
            response.get_user(),
            message_controller.config.get("Admins", "admin1").split(',')[0].strip(),
            character_persistent_class
        ),
        args=[v.strip() for v in response.get_params().values()]
    ))

    response.set_suggestions(suggestions)
    response.add_response_messages(messages)
    return response


