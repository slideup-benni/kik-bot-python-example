import configparser
import datetime
import json
import random
import sqlite3

from flask_babel import gettext as _
from kik.messages import Message, StartChattingMessage, TextMessage, SuggestedResponseKeyboard, TextResponse, PictureMessage
from modules.character_persistent_class import CharacterPersistentClass


class MessageController:

    methods = list()
    commands = list()

    def __init__(self, bot_username, config_file):
        self.config = self.read_config(config_file)
        self.bot_username = bot_username
        self.character_persistent_class = CharacterPersistentClass(self.config)
        pass

    @staticmethod
    def read_config(config_file):
        config = configparser.ConfigParser()
        config.read(config_file)
        return config['DEFAULT']

    def process_message(self, message: Message, user):

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
                body=_("Hi {user[first_name]}, mit mir kann man auch privat reden. Für eine Liste an Befehlen antworte einfach mit 'Hilfe'.").format(user=user.__dict__),
                # keyboards are a great way to provide a menu of options for a user to respond with!
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
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
                         "Für weitere Informationen tippe auf Antwort und dann auf Hilfe."
                    ).format(
                        user=user.__dict__,
                        kik_group_id=self.config.get("KikGroup", "somegroup")
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[
                        TextResponse("Hilfe"),
                        TextResponse("Regeln"),
                        TextResponse("Vorlage")
                    ])]
                )]

            #
            # Dynamische Befehle
            #
            if message_body == u"\U00002B05\U0000FE0F":
                status_obj = self.character_persistent_class.get_user_command_status(self.get_from_userid(message))
                if status_obj['status'] == CharacterPersistentClass.STATUS_DYN_MESSAGES:
                    message_body = status_obj['data']['left'].lower()
                    message_body_c = status_obj['data']['left']

            elif message_body == u"\U000027A1\U0000FE0F":
                status_obj = self.character_persistent_class.get_user_command_status(self.get_from_userid(message))
                if status_obj['status'] == CharacterPersistentClass.STATUS_DYN_MESSAGES:
                    message_body = status_obj['data']['right'].lower()
                    message_body_c = status_obj['data']['right']
            elif message_body == u"\U0001F504":
                status_obj = self.character_persistent_class.get_user_command_status(self.get_from_userid(message))
                if status_obj['status'] == CharacterPersistentClass.STATUS_DYN_MESSAGES:
                    message_body = status_obj['data']['redo'].lower()
                    message_body_c = status_obj['data']['redo']
            elif message_body.strip()[0] == "@":
                status_obj = self.character_persistent_class.get_user_command_status(self.get_from_userid(message))
                if status_obj['status'] == CharacterPersistentClass.STATUS_DYN_MESSAGES:
                    message_body = status_obj['data']['add_user_id'].lower().format(message_body.strip()[1:])
                    message_body_c = status_obj['data']['add_user_id'].format(message_body_c.strip()[1:])

            message_command = message_body.split(None,1)[0]
            if message_command != "":
                method = self.get_command_method(message_command)
                response_messages, user_command_status, user_command_status_data = method(
                    self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user
                )
            else:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Sorry {user[first_name]}, ich habe dich nicht verstanden.").format(user=user.__dict__),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                ))
        elif isinstance(message, PictureMessage):
            status_obj = self.character_persistent_class.get_user_command_status(self.get_from_userid(message))
            if status_obj is None or status_obj['status'] != CharacterPersistentClass.STATUS_SET_PICTURE:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=_("Sorry {user[first_name]}, mit diesem Bild kann ich leider nichts anfangen.").format(user=user.__dict__),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                ))

            else:
                success = self.character_persistent_class.set_char_pic(status_obj['data']['user_id'], self.get_from_userid(message), message.pic_url, status_obj['data']['char_id'])
                if success is True:
                    body = _("Alles klar! Das Bild wurde gesetzt.")
                    show_resp = self.generate_text_response("Anzeigen", status_obj['data']['user_id'], status_obj['data']['char_id'], message)
                else:
                    body = _("Beim hochladen ist ein Fehler aufgetreten. Bitte versuche es erneut.")
                    show_resp = self.generate_text_response("Bild-setzen", status_obj['data']['user_id'], status_obj['data']['char_id'], message)
                    user_command_status = status_obj['status']
                    user_command_status_data = status_obj['data']

                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=body,
                    keyboards=[SuggestedResponseKeyboard(responses=[
                        show_resp,
                        TextResponse("Liste")
                    ])]
                ))

        # If its not a text message, give them another chance to use the suggested responses
        else:

            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Sorry {user[first_name]}, ich habe dich nicht verstanden.").format(user=user.__dict__),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
            ))

        # We're sending a batch of messages. We can send up to 25 messages at a time (with a limit of
        # 5 messages per user).

        self.character_persistent_class.update_user_command_status(self.get_from_userid(message), user_command_status, user_command_status_data)
        self.character_persistent_class.commit()
        return response_messages


    @staticmethod
    def generate_text_response(command, user_id, char_id, message, force_username=False):
        return TextResponse(MessageController.generate_text(command, user_id, char_id, message, force_username=force_username))

    @staticmethod
    def generate_text(command, user_id, char_id, message, force_username=False):
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
    def check_auth(persistent_class, message, config, auth_command=False):
        if auth_command is False and message.chat_id == config.get("KikGroupChatId", ""):
            return True

        if persistent_class.is_auth_user(message) is False:
            return TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du bist nicht berechtigt diesen Befehl auszuführen!\n" +
                     "Bitte melde dich in der Gruppe #{kik_group_id} und erfrage eine Berechtigung.").format(kik_group_id=config.get("KikGroup", "somegroup")),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
            )
        return True

    @staticmethod
    def create_char_messages(character_persistent_class, char_data: sqlite3.Row, message, user_command_status, user_command_status_data):
        response_messages = []
        keyboard_responses = []
        body_char_appendix = ""
        dyn_message_data = {}

        if "prev_char_id" in char_data.keys() and char_data["prev_char_id"] is not None:
            dyn_message_data['left'] = MessageController.generate_text("Anzeigen", char_data["user_id"], char_data["prev_char_id"], message)
            keyboard_responses.append(TextResponse(u"\U00002B05\U0000FE0F"))

        if "next_char_id" in char_data.keys() and char_data["next_char_id"] is not None:
            dyn_message_data['right'] = MessageController.generate_text("Anzeigen", char_data["user_id"], char_data["next_char_id"], message)
            keyboard_responses.append(TextResponse(u"\U000027A1\U0000FE0F"))

        if dyn_message_data != {}:
            body_char_appendix = _("\n\n(Weitere Charaktere des Nutzers vorhanden: {icon_left} und {icon_right} zum navigieren)").format(
                icon_left=u"\U00002B05\U0000FE0F",
                icon_right=u"\U000027A1\U0000FE0F"
            )
            user_command_status = CharacterPersistentClass.STATUS_DYN_MESSAGES
            user_command_status_data = dyn_message_data

        if char_data["user_id"] == MessageController.get_from_userid(message):
            keyboard_responses.append(MessageController.generate_text_response("Bild-setzen", char_data["user_id"], char_data["char_id"], message))

        keyboard_responses.append(TextResponse("Liste"))

        pic_url = character_persistent_class.get_char_pic_url(char_data["user_id"], char_data["char_id"])

        if pic_url is not None:
            response_messages.append(PictureMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                pic_url=pic_url,
            ))

        body = _("{char[text]}\n\n---\nCharakter von {from_user}\nErstellt von {creator_user}\nErstellt am {created:%d.%m.%Y %H:%M}{appendix}").format(
            char=char_data,
            from_user=MessageController.get_name(char_data["user_id"], append_user_id=True),
            creator_user=MessageController.get_name(char_data['creator_id'], append_user_id=True),
            created=datetime.datetime.fromtimestamp(char_data['created']),
            appendix=body_char_appendix
        )

        body_split = body.split("\n")
        new_body = ""
        for b in body_split:
            if len(new_body) + len(b) + 2 < 1500:
                new_body += "\n" + b
            else:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=new_body,
                    keyboards=[SuggestedResponseKeyboard(responses=keyboard_responses)]
                ))
                new_body = b

        # bodys = textwrap.wrap(body, 1500, replace_whitespace=False)
        # for body in bodys:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=new_body,
            keyboards=[SuggestedResponseKeyboard(responses=keyboard_responses)]
        ))
        return (response_messages, user_command_status, user_command_status_data)

    @staticmethod
    def get_name(user_id, append_user_id=False):
        from bot import get_kik_api_cache
        kik_api_cache = get_kik_api_cache()

        user = kik_api_cache.get_user(user_id)
        if user is not None and append_user_id is True:
            return user.first_name + " " + user.last_name + " (@{})".format(user_id)
        elif user is not None:
            return user.first_name + " " + user.last_name
        else:
            return "@" + user_id

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
            if(langs is None):
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
    def get_command_text(command, lang):
        try:
            return MessageController.commands[MessageController.get_command_id(command)][lang]
        except KeyError:
            return str(command).strip()

    @staticmethod
    def add_method(commands):
        def add_method_decore(func):
            idx = len(MessageController.methods)
            MessageController.methods.append({
                "func": func,
                "cmds": commands
            })
            return func
        return add_method_decore



#
# Befehl hinzufügen
#
@MessageController.add_method({"de": "Hinzufügen", "en": "add"})
def msg_cmd_add(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
    if len(message_body.split(None,2)) == 3 and message_body.split(None,2)[1][0] == "@" and message_body.split(None,2)[2].strip() != "":
        selected_user = message_body.split(None,2)[1][1:]

        auth = self.check_auth(self.character_persistent_class, message, self.config)
        if selected_user != self.get_from_userid(message) and auth is not True:
            return [auth]

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
                self.generate_text_response("Anzeigen", selected_user, char_id, message),
                self.generate_text_response("Bild-setzen", selected_user, char_id, message),
                self.generate_text_response("Löschen", selected_user, char_id, message, force_username=True),
                TextResponse("Liste")
            ])]
        ))
    elif len(message_body.split(None,1)) == 2 and message_body.split(None,1)[1][0] != "@":
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
                self.generate_text_response("Anzeigen", self.get_from_userid(message), char_id, message),
                self.generate_text_response("Bild-setzen", self.get_from_userid(message), char_id, message),
                self.generate_text_response("Löschen", self.get_from_userid(message), char_id, message, force_username=True),
                TextResponse("Liste")
            ])]
        ))

        if body2 is not None:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=body2
            ))
    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body="Fehler beim Aufruf des Befehls. Siehe Hilfe.",
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
        ))
    return response_messages, user_command_status, user_command_status_data

#
# Befehl ändern
#
@MessageController.add_method({"de": "Ändern", "en": "change"})
def msg_cmd_change(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
    if len(message_body.split(None, 3)) == 4 and message_body.split(None, 3)[1][0] == "@" \
            and message_body.split(None, 3)[2].isdigit() and message_body.split(None, 3)[3].strip() != "":

        user_id = message_body.split(None, 3)[1][1:].strip()
        char_id = int(message_body.split(None, 3)[2])
        text = message_body_c.split(None, 3)[3].strip()

        auth = self.check_auth(self.character_persistent_class, message, self.config)
        if user_id != self.get_from_userid(message) and auth is not True:
            return [auth]

        self.character_persistent_class.change_char(user_id, self.get_from_userid(message), text, char_id)
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Alles klar! Der {char_id}. Charakter für @{user_id} wurde gespeichert.").format(char_id=char_id, user_id=user_id),
            keyboards=[SuggestedResponseKeyboard(responses=[
                self.generate_text_response("Anzeigen", user_id, char_id, message),
                self.generate_text_response("Bild-setzen", user_id, char_id, message),
                self.generate_text_response("Letzte-Löschen", user_id, char_id, message, force_username=True),
                TextResponse("Liste")
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
                self.generate_text_response("Anzeigen", self.get_from_userid(message), char_id, message),
                self.generate_text_response("Bild-setzen", self.get_from_userid(message), char_id, message),
                self.generate_text_response("Letzte-Löschen", self.get_from_userid(message), char_id, message, force_username=True),
                TextResponse("Liste")
            ])]
        ))
    elif len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" and message_body.split(None, 2)[2].strip() != "":
        user_id = message_body.split(None, 2)[1][1:].strip()

        auth = self.check_auth(self.character_persistent_class, message, self.config)
        if user_id != self.get_from_userid(message) and auth is not True:
            return [auth]

        self.character_persistent_class.change_char(message_body.split(None, 2)[1][1:].strip(), self.get_from_userid(message), message_body_c.split(None, 2)[2].strip())
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Alles klar! Der erste Charakter für @{user_id} wurde gespeichert.").format(user_id=user_id),
            keyboards=[SuggestedResponseKeyboard(responses=[
                self.generate_text_response("Anzeigen", user_id, None, message),
                self.generate_text_response("Bild-setzen", user_id, None, message),
                self.generate_text_response("Letzte-Löschen", user_id, None, message, force_username=True),
                TextResponse("Liste")
            ])]
        ))
    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] != "@":
        self.character_persistent_class.change_char(self.get_from_userid(message), self.get_from_userid(message), message_body_c.split(None, 1)[1].strip())
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Alles klar! Dein erster Charakter wurde gespeichert."),
            keyboards=[SuggestedResponseKeyboard(responses=[
                self.generate_text_response("Anzeigen", self.get_from_userid(message), None, message),
                self.generate_text_response("Bild-setzen", self.get_from_userid(message), None, message),
                self.generate_text_response("Letzte-Löschen", self.get_from_userid(message), None, message, force_username=True),
                TextResponse("Liste")
            ])]
        ))
    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Fehler beim Aufruf des Befehls. Siehe Hilfe."),
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
        ))
    return response_messages, user_command_status, user_command_status_data

#
# Befehl Bild setzen
#
@MessageController.add_method({"de": "Bild-setzen", "en": "set-picture", "_alts": ["set-pic", "Setze-Bild"]})
def msg_cmd_set_pic(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):

    response = None

    if len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" \
            and message_body.split(None, 2)[2].isdigit():

        user_id = message_body.split(None, 2)[1][1:].strip()
        char_id = int(message_body.split(None, 2)[2])

        auth = self.check_auth(self.character_persistent_class, message, self.config)
        if user_id != self.get_from_userid(message) and auth is not True:
            return [auth]

    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].isdigit():

        user_id = self.get_from_userid(message)
        char_id = int(message_body.split(None, 1)[1])

    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
        user_id = message_body.split(None, 1)[1][1:].strip()
        char_id = None

        auth = self.check_auth(self.character_persistent_class, message, self.config)
        if user_id != self.get_from_userid(message) and auth is not True:
            return [auth]

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
def msg_cmd_show(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
    char_data = None
    chars = None
    char_name = None

    if len(message_body.split(None,2)) == 3 and message_body.split(None,2)[1][0] == "@" and message_body.split(None,2)[2].isdigit():
        selected_user = message_body.split(None,2)[1][1:].strip()
        char_id = int(message_body.split(None,2)[2])
    elif len(message_body.split(None,2)) == 3 and message_body.split(None,2)[1][0] == "@" and message_body.split(None,2)[2].strip() != "":
        selected_user = message_body.split(None,2)[1][1:].strip()
        char_name = message_body.split(None, 2)[2].strip()
        chars = self.character_persistent_class.find_char(char_name, selected_user)
        if len(chars) == 1:
            char_id = chars[0]['char_id']
            char_data = chars[0]
        else:
            char_id = None
    elif len(message_body.split(None,1)) == 2 and message_body.split(None,1)[1].isdigit():
        selected_user = self.get_from_userid(message)
        char_id = int(message_body.split(None,1)[1])
    elif len(message_body.split(None,1)) == 2 and message_body.split(None,1)[1][0] == "@":
        selected_user = message_body.split(None,1)[1][1:].strip()
        char_id = None
    elif len(message_body.split(None,1)) == 2 and message_body.split(None,1)[1].strip() != "":
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
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
        ))
    elif chars is not None and len(chars) > 1:
        resp = []

        for char in chars:
            resp.append(self.generate_text_response("Anzeigen", char['user_id'], char['char_id'], message))

        resp.append(TextResponse("Liste"))

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
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
        ))
    elif char_data is None:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Keine Daten zum Nutzer @{user_id} gefunden").format(user_id=selected_user),
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
        ))
    else:
        (char_resp_msg, user_command_status, user_command_status_data) = self.create_char_messages(self.character_persistent_class,
                                                       char_data, message, user_command_status, user_command_status_data)
        response_messages += char_resp_msg
    return response_messages, user_command_status, user_command_status_data

#
# Befehl Verschieben
#
@MessageController.add_method({"de": "Verschieben", "en": "move"})
def msg_cmd_move(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
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
                    self.generate_text_response("Anzeigen", selected_to_user, char_id, message),
                    self.generate_text_response("Bild-setzen", selected_to_user, char_id, message),
                    self.generate_text_response("Löschen", selected_to_user, char_id, message, force_username=True),
                    TextResponse("Liste")
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
                    self.generate_text_response("Anzeigen", selected_to_user, to_char_id, message),
                    TextResponse("Liste")
                ])]
            ))

        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du kannst keine Charaktere von anderen Nutzern verschieben."),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
            ))

    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Fehler beim Aufruf des Befehls. Siehe Hilfe."),
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
        ))
    return response_messages, user_command_status, user_command_status_data

#
# Befehl Löschen
#
@MessageController.add_method({"de": "Löschen", "en": "delete", "_alts": ["del"]})
def msg_cmd_delete(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
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
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
            ))

        elif self.is_admin(message, self.config):
            self.character_persistent_class.remove_char(selected_user,self.get_from_userid(message), char_id)

            if char_id is not None:
                body = _("Du hast erfolgreich den {char_id}. Charakter von @{user_id} gelöscht.").format(char_id=char_id, user_id=selected_user)
            else:
                body = _("Du hast erfolgreich den ersten Charakter von @{user_id} gelöscht.").format(user_id=selected_user)

            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=body,
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
            ))

        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du kannst keine Charaktere von anderen Nutzern löschen."),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
            ))

    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Fehler beim Aufruf des Befehls. Siehe Hilfe."),
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
        ))
    return response_messages, user_command_status, user_command_status_data

#
# Befehl Löschen (letzte)
#
@MessageController.add_method({"de": "Letzte-Löschen", "en": "delete-last", "_alts": ["del-last"]})
def msg_cmd_delete_last(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
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
                    TextResponse("Liste"),
                    self.generate_text_response("Anzeigen", selected_user, char_id, message)
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
                    TextResponse("Liste"),
                    self.generate_text_response("Anzeigen", selected_user, char_id, message)
                ])]
            ))

        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du kannst keine Charaktere von anderen Nutzern löschen."),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
            ))

    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Fehler beim Aufruf des Befehls. Siehe Hilfe."),
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
        ))
    return response_messages, user_command_status, user_command_status_data

#
# Befehl Suche
#
@MessageController.add_method({"de": "Suche", "en": "search"})
def msg_cmd_search(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
    if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].strip() != "":
        query = message_body.split(None, 1)[1].strip()

        auth = self.check_auth(self.character_persistent_class, message, self.config)
        if auth is not True:
            return [auth]

        chars = self.character_persistent_class.search_char(query)

        if len(chars) == 0:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Für die Suchanfrage wurden keine Charaktere gefunden."),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
            ))

        elif len(chars) == 1:
            (char_resp_msg, user_command_status, user_command_status_data) = self.create_char_messages(self.character_persistent_class,
                                                           chars[0], message, user_command_status, user_command_status_data)
            response_messages += char_resp_msg

        else:
            resp = []

            for char in chars:
                resp.append(self.generate_text_response("Anzeigen", char['user_id'], char['char_id'], message))

            resp.append(TextResponse("Liste"))
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Es wurden mehrere Charaktere gefunden, die deiner Suchanfrage entsprechen."),
                keyboards=[SuggestedResponseKeyboard(responses=resp)]
            ))



    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Fehler beim Aufruf des Befehls. Siehe Hilfe."),
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
        ))
    return response_messages, user_command_status, user_command_status_data

#
# Befehl Setze Befehl Tastaturen
#
@MessageController.add_method({"de": "Setze-Befehl-Tastaturen", "en": "set-command-keyboards", "_alts": ["set-cmd-keyboards"]})
def msg_cmd_set_cmd_keyboards(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
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
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Admin-Hilfe")])]
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
                    "@{bot_username} Setze-Befehl-Alternative-Befehle {command} {curr_alt_cmd}").format(
                        command=static_message["command"],
                        bot_username=self.bot_username,
                        curr_alt_cmd=example_alt_commands
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse(static_message['command']), TextResponse("Admin-Hilfe")])]
                ))
        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Fehler beim Aufruf des Befehls. Siehe Admin-Hilfe."),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Admin-Hilfe")])]
            ))
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
def msg_cmd_set_cmd_alt_cmd(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
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
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Admin-Hilfe")])]
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
                    "@{bot_username} Setze-Befehl-Tastaturen {command} {curr_keyboards}").format(
                        command=static_message["command"],
                        bot_username=self.bot_username,
                        curr_keyboards=example_keyboards
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse(static_message['command']), TextResponse("Admin-Hilfe")])]
                ))
        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Fehler beim Aufruf des Befehls. Siehe Admin-Hilfe."),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Admin-Hilfe")])]
            ))
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
def msg_cmd_set_command(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
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
                    "@{bot_username} Setze-Befehl-Tastaturen {command} {curr_keyboards}\n\n\n" +
                    "Du kannst auch alternative Befehle (wie z.B. 'h' für Hilfe oder 'rules' für Regeln) hinzufügen. Dies geht mit dem Befehl:\n\n" +
                    "@{bot_username} Setze-Befehl-Alternative-Befehle {command} {curr_alt_cmd}"
                ).format(
                    command=static_message["command"],
                    bot_username=self.bot_username,
                    curr_keyboards=example_keyboards,
                    curr_alt_cmd=example_alt_commands
                ),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse(static_message["command"]), TextResponse("Admin-Hilfe")])]
            ))
        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Fehler beim Aufruf des Befehls. Siehe Admin-Hilfe."),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Admin-Hilfe")])]
            ))
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
def msg_cmd_auth(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
    if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
        selected_user = message_body.split(None, 1)[1][1:].strip()
        result = self.character_persistent_class.auth_user(selected_user, message)

        if result is True:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du hast erfolgreich den Nutzer @{user_id} berechtigt.").format(user_id=selected_user)
            ))

        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Der Nutzer @{user_id} konnte nicht berechtigt werden.\n\n" +
                    "Dies kann folgende Ursachen haben:\n" +
                    "1. Der Nutzer ist bereits berechtigt.\n" +
                    "2. Du bist nicht berechtigt, diesen Nutzer zu berechtigen.").format(user_id=selected_user)
            ))

    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Fehler beim Aufruf des Befehls. Siehe Hilfe."),
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
        ))
    return response_messages, user_command_status, user_command_status_data

#
# Befehl UnAuth
#
@MessageController.add_method({"de": "Entmachten", "en": "unauth", "_alts": ["unauthorize", "unauthorise"]})
def msg_cmd_unauth(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
    if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
        selected_user = message_body.split(None, 1)[1][1:].strip()
        result = self.character_persistent_class.unauth_user(selected_user, self.get_from_userid(message))

        if result is True:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Du hast erfolgreich den Nutzer @{user_id} entmächtigt.").format(user_id=selected_user)
            ))

        else:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Der Nutzer @{user_id} konnte nicht entmächtigt werden.\n\n" +
                     "Dies kann folgende Ursachen haben:\n" +
                     "Du bist nicht berechtigt, diesen Nutzer zu entmächtigen.").format(user_id=selected_user)
            ))

    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Fehler beim Aufruf des Befehls. Siehe Hilfe."),
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
        ))
    return response_messages, user_command_status, user_command_status_data

#
# Befehl Liste
#
@MessageController.add_method({"de": "Liste", "en": "list"})
def msg_cmd_list(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
    if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].isdigit():
        page = int(message_body.split(None, 1)[1])
    else:
        page = 1

    auth = self.check_auth(self.character_persistent_class, message, self.config)
    if auth is not True:
        return [auth]

    limit = 15
    chars = self.character_persistent_class.list_all_users_with_chars(page)
    user_ids = [item['user_id'] for item in chars[:limit]]

    body = _("Liste aller Nutzer mit Charakteren:\n--- Seite {page} ---\n").format(page=page)
    number = (page-1)*limit+1
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
        dyn_message_data['left'] = "Liste {}".format(page-1)
        responses.append(TextResponse(u"\U00002B05\U0000FE0F"))
    if len(chars) > limit:
        dyn_message_data['right'] = "Liste {}".format(page+1)
        responses.append(TextResponse(u"\U000027A1\U0000FE0F"))

    if dyn_message_data != {}:
        user_command_status = CharacterPersistentClass.STATUS_DYN_MESSAGES
        user_command_status_data = dyn_message_data
        body += _("\n\n(Weitere Seiten: {icon_left} und {icon_right} zum navigieren)").format(
            icon_left=u"\U00002B05\U0000FE0F",
            icon_right=u"\U000027A1\U0000FE0F"
        )

    responses += [TextResponse("Anzeigen @{}".format(x)) for x in user_ids]

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
@MessageController.add_method({"de": "Vorlage", "en": "template", "_alts": ["Charaktervorlage", "boilerplate", "draft", "Steckbriefvorlage", "Stecki"]})
def msg_cmd_template(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
    response_messages.append(TextMessage(
        to=message.from_user,
        chat_id=message.chat_id,
        body=_(
            "Die folgende Charaktervorlage kann genutzt werden um einen neuen Charakter im RPG zu erstellen.\n"
            "Dies ist eine notwendige Voraussetung um am RPG teilnehmen zu können.\n"
            "Bitte poste diese Vorlage ausgefüllt im Gruppenchannel #{kik_group_id}\n"
            "Wichtig: Bitte lasse die Schlüsselwörter (Vorname:, Nachname:, etc.) stehen.\n"
            "Möchtest du die Vorlage nicht über den Bot speichern, dann entferne bitte die erste Zeile.\n"
            "Hast du bereits einen Charakter und möchtest diesen aktualisieren, dann schreibe in der ersten Zeile 'ändern' anstatt 'hinzufügen'"
        ).format(kik_group_id=self.config.get("KikGroup", "somegroup")),
        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe"), TextResponse("Weitere-Beispiele")])]
    ))

    template_message = self.character_persistent_class.get_static_message('nur-vorlage')

    response_messages.append(TextMessage(
        to=message.from_user,
        chat_id=message.chat_id,
        body=(
            _("@{bot_username} hinzufügen \n").format(bot_username=self.bot_username) + template_message["response"]
        ),
        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe"), TextResponse("Weitere-Beispiele")])]
    ))
    return response_messages, user_command_status, user_command_status_data

#
# Befehl Weitere Beispiele
#
@MessageController.add_method({"de": "Weitere-Beispiele", "en": "more-examples"})
def msg_cmd_more_examples(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
    response_messages.append(TextMessage(
        to=message.from_user,
        chat_id=message.chat_id,
        body=_(
            "Weitere Beispiele\n"
            "Alle Beispiele sind in einzelnen Abschnitten mittels ----- getrennt.\n\n"
            "------\n"
            "@{bot_username} Hinzufügen @{user_id}\n"
            "Hier kann der Text zum Charakter stehen\n"
            "Zeilenumbrüche sind erlaubt\n"
            "In diesem Beispiel wurde der Nickname angegeben\n"
            "------\n"
            "@{bot_username} Ändern\n"
            "Hier kann der Text zum Charakter stehen\n"
            "Die Befehle Ändern und Hinzufügen bewirken das gleiche\n"
            "Wird kein Benutzername angegeben so betrifft die Änderung bzw. das Hinzufügen einen selbst\n"
            "------\n"
            "@{bot_username} Anzeigen @ismil1110\n"
            "------\n"
            "@{bot_username} Anzeigen\n"
            "------\n"
            "@{bot_username} Löschen @{user_id}\n"
            "------\n"
            "@{bot_username} Liste\n"
            "------\n"
            "@{bot_username} Hilfe\n"
            "------\n"
            "@{bot_username} Würfeln 8\n"
            "------\n"
            "@{bot_username} Würfeln Rot, Grün, Blau, Schwarz, Weiß\n"
            "------\n"
            "Bitte beachten, dass alle Befehle an den Bot mit @{bot_username} beginnen müssen. Die Nachricht darf"
            " mit keinem Leerzeichen oder sonstigen Zeichen beginnen, da ansonsten die Nachricht nicht an den Bot weitergeleitet wird.\n"
            "Wenn du bei dieser Nachricht auf Antworten tippst, werden dir unten 4 der oben gezeigten Beispiele als Vorauswahl angeboten"
        ).format(
            bot_username=self.bot_username,
            user_id=self.get_from_userid(message),
        ),
        keyboards=[SuggestedResponseKeyboard(responses=[
            TextResponse("Hilfe"),
            TextResponse((
                "Hinzufügen".format(self.bot_username, self.get_from_userid(message)) +
                "Neuer Charakter"
            )),
            TextResponse("Anzeigen @ismil1110".format(self.bot_username)),
            TextResponse("Anzeigen".format(self.bot_username)),
            TextResponse("Liste".format(self.bot_username)),
            TextResponse("Hilfe".format(self.bot_username)),
            TextResponse("Würfeln 8".format(self.bot_username)),
            TextResponse("Würfeln Rot, Grün, Blau, Schwarz, Weiß".format(self.bot_username))
        ])]
    ))
    return response_messages, user_command_status, user_command_status_data

#
# Befehl Würfeln
#
@MessageController.add_method({"de": "Würfeln", "en": "dice", "_alts": ["Würfel", u"\U0001F3B2"]})
@MessageController.add_method({"de": "Münze", "en": "coin"})
def msg_cmd_roll(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
    message_command = message_body.split(None, 1)[0]

    if message_command in ["münze", "coin"]:
        possibilities = [_("Kopf"), _("Zahl")]
        thing = _("Die Münze zeigt")
    elif len(message_body.split(None, 1)) == 1 or message_body.split(None, 1)[1].strip() == "":
        possibilities = list(range(1,7))
        thing = _("Der Würfel zeigt")
    elif message_body.split(None, 1)[1].isdigit():
        count = int(message_body.split(None, 1)[1])

        if count > 65535 or count < 1:
            response_messages.append(TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Ein Würfel mit der angegebenen Augenanzahl konnte nicht gewürfelt werden. Die Anzahl der Augen muss zwischen 1 und 65535 liegen."),
                keyboards=[SuggestedResponseKeyboard(responses=[
                    TextResponse("{} 65535".format(message_body_c.split(None, 1)[0])),
                    TextResponse("Hilfe")])
                ]
            ))
            return response_messages, user_command_status, user_command_status_data

        possibilities = list(range(1,count+1)) if count > 0 else [1]
        thing = _("Der Würfel zeigt")
    else:
        possibilities = [x.strip() for x in message_body_c.split(None, 1)[1].split(',')]
        thing = _("Ich wähle")

    user_command_status = CharacterPersistentClass.STATUS_DYN_MESSAGES
    user_command_status_data = {
        'redo': message_body_c
    }

    response_messages.append(TextMessage(
        to=message.from_user,
        chat_id=message.chat_id,
        body="{}: {}".format(thing, possibilities[random.randint(0, len(possibilities)-1)]),
        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse(u"\U0001F504"), TextResponse("Hilfe")])]
    ))
    return response_messages, user_command_status, user_command_status_data


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
def msg_cmd_other(self, message, message_body, message_body_c, response_messages, user_command_status, user_command_status_data, user):
    message_command = message_body.split(None, 1)[0]
    static_message = self.character_persistent_class.get_static_message(message_command)

    if static_message is not None:
        if static_message["response_keyboards"] is None:
            keyboards = ["Hilfe"]
        else:
            keyboards = json.loads(static_message["response_keyboards"])

        keyboard_responses = list(map(TextResponse, keyboards))

        body_split = static_message["response"].format(
            bot_username=self.bot_username,
            user=user.__dict__,
            command=message_command,
            kik_group_id=self.config.get("KikGroup", "somegroup"),
            user_id=self.get_from_userid(message),
            message=message
        ).split("\n")
        new_body = ""
        for b in body_split:
            if len(new_body) + len(b) + 2 < 1500:
                new_body += "\n" + b
            else:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=new_body,
                    keyboards=[SuggestedResponseKeyboard(responses=keyboard_responses)]
                ))
                new_body = b

        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=new_body,
            keyboards=[SuggestedResponseKeyboard(responses=keyboard_responses)]
        ))

    else:
        response_messages.append(TextMessage(
            to=message.from_user,
            chat_id=message.chat_id,
            body=_("Sorry {user[first_name]}, den Befehl '{command}' kenne ich nicht.").format(user=user.__dict__, command=message_command),
            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
        ))
    return response_messages, user_command_status, user_command_status_data
