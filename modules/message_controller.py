import configparser
import datetime
import json
import random
import re
import sqlite3

from flask_babel import gettext as _, get_locale
from kik.messages import Message, StartChattingMessage, TextMessage, SuggestedResponseKeyboard, PictureMessage
from werkzeug.exceptions import BadRequest

from modules.character_persistent_class import CharacterPersistentClass
from modules.kik_user import User, LazyKikUser, LazyRandomKikUser


class MessageParam:
    CONST_REGEX_ALPHA = r"[a-z]+"
    CONST_REGEX_ALPHANUM = r"[a-z0-9]+"
    CONST_REGEX_NUM = r"[0-9]+"
    CONST_REGEX_DIGIT = r"[0-9]"
    CONST_REGEX_USER_ID = r"@[a-z0-9\.\_]+"
    CONST_REGEX_COMMAND = r"\S+"
    CONST_REGEX_TEXT = r".+"

    def __init__(self, name, regex, required=False, validate_in_message=False, examples=None, get_value_callback=None):
        self.get_value_callback = get_value_callback
        self.validate_in_message = validate_in_message
        self.name = name.strip()
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
            return self.name
        return "(" + self.name + ")"

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
            return self.get_value_callback(self.name, params)

        return params[self.name]

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

    def __init__(self, params: list, command_de, command_en, command_alts=None, help_command="Hilfe", hidden=False):
        self.hidden = hidden
        self.help_command = help_command
        self.command = {
            'de': command_de,
            'en': command_en,
            '_alts': [] if command_alts is None else command_alts
        }

        all_commands = set(self.command["_alts"])
        all_commands.add(command_de)
        all_commands.add(command_en)

        self.params = [
            MessageParam("command", MessageParam.CONST_REGEX_COMMAND, required=True, examples=list(all_commands))
        ]
        self.params.extend(params)

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
            examples.add(self.get_random_example(response, fixed_params))
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

            message_response = CommandMessageResponse(**{**command_message_response_data, "params": match.groupdict()})
            response = func(message_response) # type: CommandMessageResponse
            response_messages = response.get_kik_response()
            user_command_status, user_command_status_data = response.get_user_command_status()
            return response_messages, user_command_status, user_command_status_data
        return method


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

    def add_response_message(self, message: str):
        self.response_messages.append(message)

    def add_response_messages(self, messages: list):
        for message in messages:
            self.add_response_message(message)

    def set_suggestions(self, suggestions: list):
        self.suggestions = suggestions

    def get_kik_response(self):
        kik_responses = []
        num_resp = len(self.response_messages)
        for r in range(0, num_resp):
            message_dict = {
                "to":  self.orig_message.from_user,
                "chat_id": self.orig_message.chat_id,
                "body": self.response_messages[r],
            }
            if r == num_resp-1 and len(self.suggestions) != 0:
                message_dict["keyboards"] = [SuggestedResponseKeyboard(responses=[MessageController.generate_text_response(keyboard) for keyboard in self.suggestions])]
            kik_responses.append(TextMessage(**message_dict))
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
        return self.get_values()[key]

    def get_command(self):
        return self.command


class MessageController:
    methods = list()

    def __init__(self, bot_username, config_file):
        self.config = self.read_config(config_file)
        self.bot_username = bot_username
        self.character_persistent_class = CharacterPersistentClass(self.config, bot_username)

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

    @staticmethod
    def check_auth(user: User, message, config, auth_command=False):
        if auth_command is False and message.chat_id == config.get("KikGroupChatId", ""):
            return True


        if user.is_authed() is False and MessageController.is_admin(message, config) is False:
            return TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du bist nicht berechtigt diesen Befehl auszuführen!\n" +
                       "Bitte melde dich in der Gruppe #{kik_group_id} und erfrage eine Berechtigung.").format(kik_group_id=config.get("KikGroup", "somegroup")),
                keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Hilfe")])]
            )
        return True

    def create_char_messages(self, char_data: sqlite3.Row, message, user_command_status, user_command_status_data, user: User):
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

    @staticmethod
    def is_aliased(message):
        return len(message.from_user) == 52

    @staticmethod
    def get_from_userid(message):
        return message.from_user

    @staticmethod
    def is_admin(message: Message, config):
        if message.type == "public":
            return False
        return message.from_user.lower() in [x.strip().lower() for x in config.get("Admins", "admin1").split(',')]

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

        return MessageController.methods[command_id]['cmds']

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

            if isinstance(commands, MessageCommand):
                func = commands.get_method(func)

            MessageController.methods.append({
                "func": func,
                "cmds": commands
            })
            return func

        return add_method_decore

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
            return "@"+user.is_user_id, response

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

        return user_id, response

    def require_char_id(self, params, key, user_id, response: CommandMessageResponse, use_linked_char=True):
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

        if linked_char_id is None and len(chars) > 1 and params[key] is None:

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

        auth = self.check_auth(user, message, self.config)
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

        auth = self.check_auth(user, message, self.config)
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

        auth = self.check_auth(user, message, self.config)
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

        auth = self.check_auth(user, message, self.config)
        if user_id != self.get_from_userid(message) and auth is not True:
            return [auth], user_command_status, user_command_status_data

    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].isdigit():

        user_id = self.get_from_userid(message)
        char_id = int(message_body.split(None, 1)[1])

    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
        user_id = message_body.split(None, 1)[1][1:].strip()
        char_id = None

        auth = self.check_auth(user, message, self.config)
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
@MessageController.add_method({"de": "Anzeigen", "en": "show", "_alts": ["Steckbrief", "Stecki"]})
def msg_cmd_show(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    char_data = None
    chars = None
    char_name = None

    if len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" and message_body.split(None, 2)[2].isdigit():
        selected_user = message_body.split(None, 2)[1][1:].strip()
        char_id = int(message_body.split(None, 2)[2])
    elif len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" and message_body.split(None, 2)[2].strip() != "":
        selected_user = message_body.split(None, 2)[1][1:].strip()
        char_name = message_body.split(None, 2)[2].strip()
        chars = self.character_persistent_class.find_char(char_name, selected_user)
        if len(chars) == 1:
            char_id = chars[0]['char_id']
            char_data = chars[0]
        else:
            char_id = None
    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].isdigit():
        selected_user = self.get_from_userid(message)
        char_id = int(message_body.split(None, 1)[1])
    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
        selected_user = message_body.split(None, 1)[1][1:].strip()
        char_id = None
    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].strip() != "":
        char_name = message_body.split(None, 1)[1].strip()
        chars = self.character_persistent_class.find_char(char_name, self.get_from_userid(message))
        selected_user = self.get_from_userid(message)
        if len(chars) == 1:
            char_id = chars[0]['char_id']
            char_data = chars[0]
        else:
            char_id = None
    else:
        selected_user = self.get_from_userid(message)
        char_id = None

    if chars is None and char_data is None and selected_user is not None:
        char_data = self.character_persistent_class.get_char(selected_user, char_id)

    if chars is not None and len(chars) == 0 and char_name is not None:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Es wurde kein Charakter mit dem Namen {char_name} des Nutzers @{user_id} gefunden").format(char_name=char_name, user_id=selected_user),
            keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Liste")])]
        ))
    elif chars is not None and len(chars) > 1:
        resp = []

        for char in chars:
            resp.append(self.generate_text_response_user_char("Anzeigen", char['user_id'], char['char_id'], message))

        resp.append(MessageController.generate_text_response("Liste"))

        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Es wurden {cnt} Charaktere mit dem Namen {char_name} des Nutzers @{user_id} gefunden").format(
                cnt=len(chars),
                char_name=char_name,
                user_id=selected_user
            ),
            keyboards=[SuggestedResponseKeyboard(responses=resp)]
        ))
    elif char_data is None and char_id is not None:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Keine Daten zum {char_id}. Charakter des Nutzers @{user_id} gefunden").format(char_id=char_id, user_id=selected_user),
            keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Liste")])]
        ))
    elif char_data is None:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Keine Daten zum Nutzer @{user_id} gefunden").format(user_id=selected_user),
            keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Liste")])]
        ))
    else:
        (char_resp_msg, user_command_status, user_command_status_data) = self.create_char_messages(char_data, message, user_command_status, user_command_status_data, user)
        response_messages += char_resp_msg
    return response_messages, user_command_status, user_command_status_data


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

        elif self.is_admin(message, self.config):
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

        elif self.is_admin(message, self.config):
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

        elif self.is_admin(message, self.config):
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
@MessageController.add_method({"de": "Suche", "en": "search"})
def msg_cmd_search(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].strip() != "":
        query = message_body.split(None, 1)[1].strip()

        auth = self.check_auth(user, message, self.config)
        if auth is not True:
            return [auth], user_command_status, user_command_status_data

        chars = self.character_persistent_class.search_char(query)

        if len(chars) == 0:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Für die Suchanfrage wurden keine Charaktere gefunden."),
                keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Liste")])]
            ))

        elif len(chars) == 1:
            (char_resp_msg, user_command_status, user_command_status_data) = self.create_char_messages(chars[0], message, user_command_status, user_command_status_data, user)
            response_messages += char_resp_msg

        else:
            resp = []

            for char in chars:
                resp.append(self.generate_text_response_user_char("Anzeigen", char['user_id'], char['char_id'], message))

            resp.append(MessageController.generate_text_response("Liste"))
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Es wurden mehrere Charaktere gefunden, die deiner Suchanfrage entsprechen."),
                keyboards=[SuggestedResponseKeyboard(responses=resp)]
            ))



    else:
        response_messages.append(MessageController.get_error_response(message))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl Setze Befehl Tastaturen
#
@MessageController.add_method({"de": "Setze-Befehl-Tastaturen", "en": "set-command-keyboards", "_alts": ["set-cmd-keyboards"]})
def msg_cmd_set_cmd_keyboards(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if self.is_admin(message, self.config):
        if len(message_body.split(None, 2)) == 3:
            keyboards = message_body_c.split(None, 2)[2].strip()
            static_command = message_body.split(None, 2)[1].strip()
            static_message = self.character_persistent_class.get_static_message(static_command)

            if static_message is None:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Der Befehl '{command}' existiert nicht.").format(command=static_message['command']),
                    keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Admin-Hilfe")])]
                ))

            else:
                static_command = static_message["command"]
                static_message = self.character_persistent_class.set_static_message_keyboard(static_command, [x.strip() for x in keyboards.split(',')])

                example_alt_commands = "Alt-Befehl1, Alt-Befehl2, etc."
                if static_message["alt_commands"] is not None:
                    example_alt_commands = ", ".join(json.loads(static_message["alt_commands"]))

                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Du hast erfolgreich die Tastaturen für den statischen Befehl '{command}' aktualisiert.\n" +
                           "Du kannst auch alternative Befehle (wie z.B. 'h' für Hilfe oder 'rules' für Regeln) hinzufügen. Dies geht mit dem Befehl:\n\n" +
                           "@{bot_username} {set_cmd_alt_cmd_command} {command} {curr_alt_cmd}").format(
                        command=static_message["command"],
                        bot_username=self.bot_username,
                        curr_alt_cmd=example_alt_commands,
                        set_cmd_alt_cmd_command=MessageController.get_command_text("Setze-Befehl-Alternative-Befehle")
                    ),
                    keyboards=[SuggestedResponseKeyboard(
                        responses=[MessageController.generate_text_response(static_message['command']), MessageController.generate_text_response("Admin-Hilfe")])]
                ))
        else:
            response_messages.append(MessageController.get_error_response(message, "Admin-Hilfe"))
    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body="Du kannst keine statischen Antworten setzen."
        ))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl Setze Befehl Alternative Befehle
#
@MessageController.add_method({"de": "Setze-Befehl-alternative-Befehle", "en": "set-command-alternative-commands", "_alts": ["set-cmd-alt-cmd"]})
def msg_cmd_set_cmd_alt_cmd(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if self.is_admin(message, self.config):
        if len(message_body.split(None, 2)) == 3:
            alt_commands = message_body_c.split(None, 2)[2].strip()
            static_command = message_body.split(None, 2)[1].strip()
            static_message = self.character_persistent_class.get_static_message(static_command)

            if static_message is None:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Der Befehl '{command}' existiert nicht.").format(command=static_message['command']),
                    keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Admin-Hilfe")])]
                ))

            else:
                static_command = static_message["command"]
                static_message = self.character_persistent_class.set_static_message_alt_commands(static_command, [x.strip() for x in alt_commands.split(',')])

                example_keyboards = "Hilfe, Liste"
                if static_message["response_keyboards"] is not None:
                    example_keyboards = ", ".join(json.loads(static_message["response_keyboards"]))

                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Du hast erfolgreich die alternativen Befehle für den Befehl '{command}' aktualisiert.\n" +
                           "Du kannst jetzt noch mit dem folgenden Befehl die Antwort-Tastaturen setzen (Komma-getrennt):\n\n" +
                           "@{bot_username} {set_cmd_keyboards_command} {command} {curr_keyboards}").format(
                        command=static_message["command"],
                        bot_username=self.bot_username,
                        curr_keyboards=example_keyboards,
                        set_cmd_keyboards_command=MessageController.get_command_text("Setze-Befehl-Tastaturen"),
                    ),
                    keyboards=[SuggestedResponseKeyboard(
                        responses=[MessageController.generate_text_response(static_message['command']), MessageController.generate_text_response("Admin-Hilfe")])]
                ))
        else:
            response_messages.append(MessageController.get_error_response(message, "Admin-Hilfe"))
    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Du kannst keine statischen Antworten setzen.")
        ))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl Setze Antwort
#
@MessageController.add_method({"de": "Setze-Befehl", "en": "set-command", "_alts": ["set-cmd"]})
def msg_cmd_set_command(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if self.is_admin(message, self.config):
        if len(message_body.split(None, 2)) == 3:
            text = message_body_c.split(None, 2)[2].strip()
            static_command = message_body.split(None, 2)[1].strip()
            static_message = self.character_persistent_class.get_static_message(static_command)

            if static_message is not None:
                static_command = static_message["command"]

            static_message = self.character_persistent_class.set_static_message(static_command, text)

            example_keyboards = "Hilfe, Liste"
            if static_message["response_keyboards"] is not None:
                example_keyboards = ", ".join(json.loads(static_message["response_keyboards"]))

            example_alt_commands = "Alt-Befehl1, Alt-Befehl2, etc."
            if static_message["alt_commands"] is not None:
                example_alt_commands = ", ".join(json.loads(static_message["alt_commands"]))

            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du hast erfolgreich die statische Antwort auf den Befehl '{command}' aktualisiert.\n" +
                       "Du kannst jetzt noch mit dem folgenden Befehl die Antwort-Tastaturen setzen (Komma-getrennt):\n\n" +
                       "@{bot_username} {set_cmd_keyboards_command} {command} {curr_keyboards}\n\n\n" +
                       "Du kannst auch alternative Befehle (wie z.B. 'h' für Hilfe oder 'rules' für Regeln) hinzufügen. Dies geht mit dem Befehl:\n\n" +
                       "@{bot_username} {set_cmd_alt_cmd_command} {command} {curr_alt_cmd}"
                       ).format(
                    command=static_message["command"],
                    bot_username=self.bot_username,
                    curr_keyboards=example_keyboards,
                    curr_alt_cmd=example_alt_commands,
                    set_cmd_keyboards_command=MessageController.get_command_text("Setze-Befehl-Tastaturen"),
                    set_cmd_alt_cmd_command=MessageController.get_command_text("Setze-Befehl-Alternative-Befehle")
                ),
                keyboards=[SuggestedResponseKeyboard(
                    responses=[MessageController.generate_text_response(static_message["command"]), MessageController.generate_text_response("Admin-Hilfe")])]
            ))
        else:
            response_messages.append(MessageController.get_error_response(message, "Admin-Hilfe"))
    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Du kannst keine statischen Antworten setzen.")
        ))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl Auth
#
@MessageController.add_method({"de": "Berechtigen", "en": "auth", "_alts": ["authorize", "authorise"]})
def msg_cmd_auth(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
        selected_user = message_body.split(None, 1)[1][1:].strip()
        auth = self.check_auth(user, message, self.config)
        if auth is not True:
            return [auth], user_command_status, user_command_status_data

        to_auth_user_db = self.character_persistent_class.get_user(selected_user)
        to_auth_user = User.init(to_auth_user_db) if to_auth_user_db is not None else User.init_new_user(selected_user, self.bot_username)
        to_auth_user.auth(user)
        self.character_persistent_class.update_user(to_auth_user, as_request=False)

        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Du hast erfolgreich den Nutzer @{user_id} berechtigt.").format(user_id=selected_user)
        ))

    else:
        response_messages.append(MessageController.get_error_response(message))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl UnAuth
#
@MessageController.add_method({"de": "Entmachten", "en": "unauth", "_alts": ["unauthorize", "unauthorise"]})
def msg_cmd_unauth(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
        selected_user = message_body.split(None, 1)[1][1:].strip()

        if MessageController.is_admin(message, self.config) is False:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du bist nicht berechtigt diesen Befehl auszuführen!\nNur Admins können Nutzern Rechte entziehen.")
            ))
            return response_messages, user_command_status, user_command_status_data


        to_auth_user_db = self.character_persistent_class.get_user(selected_user)
        to_auth_user = User.init(to_auth_user_db) if to_auth_user_db is not None else User.init_new_user(selected_user, self.bot_username)
        to_auth_user.unauth()
        self.character_persistent_class.update_user(to_auth_user, as_request=False)

        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Du hast erfolgreich den Nutzer @{user_id} entmächtigt.").format(user_id=selected_user)
        ))

    else:
        response_messages.append(MessageController.get_error_response(message))
    return response_messages, user_command_status, user_command_status_data

#
# Befehl i-am
#
iam_command = MessageCommand([
    MessageParam.init_user_id(),
    MessageParam.init_char_id(),
], "Ich-Bin", "i-am", ["iam"])
@MessageController.add_method(iam_command)
def quest_accept(response: CommandMessageResponse):
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

    response.add_response_message(_("Alles klar! "
                                    "Alle charakter-spezifischen Befehle sind ab jetzt für dich standardmäßig auf @{user_id} mit der Charakter-Id {char_id} gesetzt.").format(
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
def quest_accept(response: CommandMessageResponse):
    user = response.get_user() # type: User

    if user["is_user_id"] is None:
        response.add_response_message(_("Du hast derzeit keinen Benutzernamen und Charakter-Id für charakter-spezifischen Befehle gesetzt."))
        return response

    response.add_response_message(_("Alle charakter-spezifischen Befehle sind für standardmäßig auf @{user_id} mit der Charakter-Id {char_id} gesetzt.").format(
        user_id=user["is_user_id"],
        char_id=user["is_char_id"]
    ))
    response.set_suggestions(["Anzeigen"])
    return response


#
# Befehl Liste
#
@MessageController.add_method({"de": "Liste", "en": "list"})
def msg_cmd_list(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].isdigit():
        page = int(message_body.split(None, 1)[1])
    else:
        page = 1

    auth = self.check_auth(user, message, self.config)
    if auth is not True:
        return [auth], user_command_status, user_command_status_data

    limit = 15
    chars = self.character_persistent_class.list_all_users_with_chars(page)
    user_ids = [item['user_id'] for item in chars[:limit]]

    body = _("Liste aller Nutzer mit Charakteren:\n--- Seite {page} ---\n").format(page=page)
    number = (page - 1) * limit + 1
    for char in chars[:limit]:
        b = _("{consecutive_number}.: {user_name}\n" +
              "Nutzername: @{user_id}\n" +
              "Anz. Charaktere: {chars_cnt}\n" +
              "letzte Änderung: {last_change:%d.%m.%Y}"
              ).format(
            consecutive_number=number,
            user_name=self.get_name(char['user_id']),
            user_id=char['user_id'],
            chars_cnt=char['chars_cnt'],
            last_change=datetime.datetime.fromtimestamp(char['created'])
        )

        number += 1

        if len(body) + len(b) + 4 < 1500:
            body += "\n\n" + b
        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=body
            ))
            body = b

    responses = list()
    dyn_message_data = {}
    if page != 1:
        dyn_message_data['left'] = "Liste {}".format(page - 1)
        responses.append(MessageController.generate_text_response(u"\U00002B05\U0000FE0F"))
    if len(chars) > limit:
        dyn_message_data['right'] = "Liste {}".format(page + 1)
        responses.append(MessageController.generate_text_response(u"\U000027A1\U0000FE0F"))

    if dyn_message_data != {}:
        user_command_status = CharacterPersistentClass.STATUS_DYN_MESSAGES
        user_command_status_data = dyn_message_data
        body += _("\n\n(Weitere Seiten: {icon_left} und {icon_right} zum navigieren)").format(
            icon_left=u"\U00002B05\U0000FE0F",
            icon_right=u"\U000027A1\U0000FE0F"
        )

    responses += [MessageController.generate_text_response("Anzeigen @{}".format(x)) for x in user_ids]

    response_messages.append(TextMessage(
        to=message.from_user,
        chat_id=message.chat_id,
        body=body,
        keyboards=[SuggestedResponseKeyboard(responses=responses)]
    ))
    return response_messages, user_command_status, user_command_status_data


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
@MessageController.add_method({"de": "Weitere-Beispiele", "en": "more-examples"})
def msg_cmd_more_examples(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    response_messages.append(TextMessage(
        to=message.from_user,
        chat_id=message.chat_id,
        body=_(
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
            bot_username=self.bot_username,
            user_id=self.get_from_userid(message),
            show_command=MessageController.get_command_text("Anzeigen"),
            delete_command=MessageController.get_command_text("Löschen"),
            list_command=MessageController.get_command_text("Liste"),
            help_command=MessageController.get_command_text("Hilfe"),
            dice_command=MessageController.get_command_text("Würfeln"),
            add_command=MessageController.get_command_text("Hinzufügen"),
            change_command=MessageController.get_command_text("Ändern"),
            number=7,
            admin_user=self.config.get("Admins", "admin1").split(',')[0].strip()
        ),
        keyboards=[SuggestedResponseKeyboard(responses=[
            MessageController.generate_text_response("Hilfe"),
            MessageController.generate_text_response("Hinzufügen {}".format(_("Neuer Charakter"))),
            MessageController.generate_text_response("Anzeigen @{}".format(self.config.get("Admins", "admin1").split(',')[0].strip())),
            MessageController.generate_text_response("Anzeigen"),
            MessageController.generate_text_response("Liste"),
            MessageController.generate_text_response("Hilfe"),
            MessageController.generate_text_response("Würfeln 8"),
            MessageController.generate_text_response("Würfeln {}".format(_("Rot, Grün, Blau, Schwarz, Weiß")))
        ])]
    ))
    return response_messages, user_command_status, user_command_status_data


#
# Befehl Würfeln
#
@MessageController.add_method({"de": "Würfeln", "en": "dice", "_alts": ["Würfel", u"\U0001F3B2"]})
@MessageController.add_method({"de": "Münze", "en": "coin"})
def msg_cmd_roll(self, message: TextMessage, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    bracket = None
    accepted_brackets = {
        'open': ["(", "[", "*"],
        'close': [")", "]", "*"],
    }
    if message_body[-1:] in accepted_brackets['close']:
        bracket = accepted_brackets['close'].index(message_body[-1:])
        message_body = message_body[:-1].strip()
        message_body_c = message_body_c[:-1].strip()

    message_command = message_body.split(None, 1)[0]
    body = ""

    if message_command in ["münze", "coin"]:
        possibilities = [_("Kopf"), _("Zahl")]
        result = possibilities[random.randint(0, len(possibilities) - 1)]
        thing = _("Die Münze zeigt")
        body = "{}: {}".format(thing, result)
    elif len(message_body.split(None, 1)) == 1 or message_body.split(None, 1)[1].strip() == "":
        result = str(random.randint(1, 6))
        thing = _("Der Würfel zeigt")
        body = "{}: {}".format(thing, result)
    elif message_body.split(None, 1)[1].isdigit():
        count = int(message_body.split(None, 1)[1])
        result = str(random.randint(1, count))
        thing = _("Der Würfel zeigt")
        body = "{}: {}".format(thing, result)
    elif re.search(r"^(([0-9]+\s*([×x\*]\s*)?)?D\s*)?[0-9]+(\s*\+\s*(([0-9]+\s*([×x\*]\s*)?)?D\s*)?[0-9]+)*$", message_body.split(None, 1)[1],
                   re.MULTILINE + re.IGNORECASE) is not None:
        dices = str(message_body_c.split(None, 1)[1]).split("+")
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
                    while loops >= 0:
                        res = random.randint(1, int(match.group(5)))
                        result_int += res
                        if res_text != "":
                            res_text += ", "
                        res_text += str(res)
                        loops -= 1
                else:
                    dice_results = [0] * int(match.group(3))
                    loops = int(match.group(3))
                    while loops >= 0:
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
        possibilities = [x.strip() for x in message_body_c.split(None, 1)[1].split(',')]

        if len(possibilities) == 1:
            response_messages.append(MessageController.get_error_response(message))
            return response_messages, user_command_status, user_command_status_data

        result = possibilities[random.randint(0, len(possibilities) - 1)]
        thing = _("Ich wähle")
        body = "{}: {}".format(thing, result)

    user_command_status = CharacterPersistentClass.STATUS_DYN_MESSAGES
    user_command_status_data = {
        'redo': message.body
    }

    if bracket is not None:
        body = "{} {} {}".format(
            accepted_brackets['open'][bracket],
            body,
            accepted_brackets['close'][bracket]
        )

    response_messages.append(TextMessage(
        to=message.from_user,
        chat_id=message.chat_id,
        body=body,
        keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response(u"\U0001F504"), MessageController.generate_text_response("Hilfe")])]
    ))
    return response_messages, user_command_status, user_command_status_data


debug_url_cmd = MessageCommand([], "Debug-URL", "debug-url", hidden=True)
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
@MessageController.add_method({"de": "Hilfe", "en": "help", "_alts": ["?", "h", "hilfe!", "rpg-help"]})
@MessageController.add_method({"de": "Regeln", "en": "rules"})
@MessageController.add_method({"de": "nur-Vorlage", "en": "template-only"})
@MessageController.add_method({"de": "Kurzbefehle", "en": "help2", "_alts": ["Hilfe2"]})
@MessageController.add_method({"de": "Admin-Hilfe", "en": "admin-help"})
@MessageController.add_method({"de": "Quellcode", "en": "sourcecode", "_alts": ["source", "lizenz", "licence"]})
@MessageController.add_method(None)
def msg_cmd_other(self, message: TextMessage, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user: User):
    message_command = message_body.split(None, 1)[0]
    static_message = self.character_persistent_class.get_static_message(message_command)

    if static_message is not None:
        if static_message["response_keyboards"] is None:
            keyboards = ["Hilfe"]
        else:
            keyboards = json.loads(static_message["response_keyboards"])

        keyboard_responses = list(map(MessageController.generate_text_response, keyboards))

        messages = MessageController.split_messages(static_message["response"].format(
            bot_username=self.bot_username,
            user=user,
            command=message_command,
            kik_group_id=self.config.get("KikGroup", "somegroup"),
            user_id=self.get_from_userid(message),
            message=message,
            ruser=LazyRandomKikUser(message.participants, user, self.config.get("Admins", "admin1").split(',')[0].strip(), self.character_persistent_class),
            args=[x.strip() for x in message_body_c.split()[1:]]
        ))

        if len(keyboard_responses) > 0:
            kb = [SuggestedResponseKeyboard(responses=keyboard_responses)]
        else:
            kb = []

        for m in messages:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=m,
                keyboards=kb
            ))

    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Sorry {user[first_name]}, den Befehl '{command}' kenne ich nicht.").format(user=user, command=message_command),
            keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Hilfe")])]
        ))
    return response_messages, user_command_status, user_command_status_data
