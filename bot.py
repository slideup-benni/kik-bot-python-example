#!/usr/local/bin/python3.6
# -*- coding: utf-8 -*-
"""An example Kik bot implemented in Python.

It's designed to greet the user, send a suggested response and replies to them with their profile picture.
Remember to replace the BOT_USERNAME_HERE, BOT_API_KEY_HERE and WEBHOOK_HERE fields with your own.

See https://github.com/kikinteractive/kik-python for Kik's Python API documentation.

Apache 2.0 License

(c) 2016 Kik Interactive Inc.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the
License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific
language governing permissions and limitations under the License.

"""
import configparser
import datetime
import hashlib
import json
import os
import random
import re
import sqlite3
import time
import traceback

import requests
from configparser import SectionProxy
from mimetypes import guess_extension
from pathlib import Path
from flask import Flask, request, Response, send_from_directory
from kik import User, KikApi, Configuration, KikError
from kik.messages import messages_from_json, TextMessage, PictureMessage, \
    SuggestedResponseKeyboard, TextResponse, StartChattingMessage, Message, FriendPickerResponse

app = Flask(__name__)


@app.route("/picture/<path:path>", methods=["GET"])
def picture(path):
    picture_path = default_config.get("PicturePath", "{home}/pictures").format(home=str(Path.home()))
    return send_from_directory(picture_path, path)


@app.route("/incoming", methods=["POST"])
def incoming():
    global kik_api
    """Handle incoming messages to the bot. All requests are authenticated using the signature in
    the 'X-Kik-Signature' header, which is built using the bot's api key (set in main() below).
    :return: Response
    """
    # verify that this is a valid request
    if not kik_api.verify_signature(
            request.headers.get("X-Kik-Signature"), request.get_data()):
        return Response(status=403)

    messages = messages_from_json(request.json["messages"])

    response_messages = []
    message_controller = MessageController()

    for message in messages:
        try:
            user = kik_api.get_user(message.from_user) # type: User
            response_messages += message_controller.process_message(message, user)
        except:
            error_id = hashlib.md5((str(int(time.time())) + message.from_user).encode('utf-8')).hexdigest()
            print("Error: " + error_id + " --- " + traceback.format_exc())

            response_messages += [TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body="Leider ist ein Fehler aufgetreten. Bitte versuche es erneut.\n\n" +
                     "Sollte der Fehler weiterhin auftreten, mach bitte einen Screenshot und sprich @ismil1110 per PM an.\n\n" +
                     "Fehler-Informationen: {}".format(error_id),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
            )]

        kik_api.send_messages(response_messages)

    return Response(status=200)


class MessageController:

    def __init__(self):
        self.reload_config()
        self.character_persistent_class = CharacterPersistentClass()
        pass

    @staticmethod
    def reload_config():
        global config
        global default_config
        config.read(configFile)
        default_config = config['DEFAULT']  # type: SectionProxy

    def process_message(self, message: Message, user):

        log_requests = default_config.get("LogRequests", "False")
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
                body="Hi {}, mit mir kann man auch privat reden. Für eine Liste an Befehlen antworte einfach mit 'Hilfe'.".format(user.first_name),
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
                    body="Hi {}, ich bin der Steckbrief-Bot der Gruppe #{}\n".format(user.first_name, default_config.get("KikGroup", "somegroup")) +
                         "Für weitere Informationen tippe auf Antwort und dann auf Hilfe.",
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

            #
            # Befehl hinzufügen
            #
            if message_command in ["hinzufügen", "add"]:
                if len(message_body.split(None,2)) == 3 and message_body.split(None,2)[1][0] == "@" and message_body.split(None,2)[2].strip() != "":
                    selected_user = message_body.split(None,2)[1][1:]

                    auth = self.check_auth(self.character_persistent_class, message)
                    if selected_user != self.get_from_userid(message) and auth is not True:
                        return [auth]

                    char_id = self.character_persistent_class.add_char(message_body.split(None, 2)[1][1:].strip(), self.get_from_userid(message), message_body_c.split(None, 2)[2].strip())

                    if char_id == CharacterPersistentClass.get_min_char_id():
                        body = "Alles klar! Der erste Charakter für @{} wurde hinzugefügt.".format(selected_user)
                    else:
                        body = "Alles klar! Der {}. Charakter für @{} wurde hinzugefügt.".format(char_id, selected_user)

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
                        body = "Alles klar! Dein erster Charakter wurde hinzugefügt."
                    elif self.is_aliased(message) is False:
                        body = "Alles klar! Dein {}. Charakter wurde hinzugefügt.".format(char_id)
                    else:
                        body = "Alles klar! Dein Charakter wurde hinzugefügt. \n" + \
                            "Der Charakter wurde temporär dem Alias-User @{} zugeordnet.\n\n".format(self.get_from_userid(message)) + \
                            "Aufgrund der letzten Änderung von Kik, konnte ich dir den Charakter nicht direkt zuordnen.\n" + \
                            "Damit der Charakter auch wirklich dir zugeordnet wird, sende bitte jetzt den folgenden Befehl (Bitte kopieren und deine Nutzer_Id ersetzen):"
                        body2 = "@{} @Deine_Nutzer_Id".format(bot_username)
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

            #
            # Befehl ändern
            #
            elif message_command in ["ändern", "change"]:
                if len(message_body.split(None, 3)) == 4 and message_body.split(None, 3)[1][0] == "@" \
                        and message_body.split(None, 3)[2].isdigit() and message_body.split(None, 3)[3].strip() != "":

                    user_id = message_body.split(None, 3)[1][1:].strip()
                    char_id = int(message_body.split(None, 3)[2])
                    text = message_body_c.split(None, 3)[3].strip()

                    auth = self.check_auth(self.character_persistent_class, message)
                    if user_id != self.get_from_userid(message) and auth is not True:
                        return [auth]

                    self.character_persistent_class.change_char(user_id, self.get_from_userid(message), text, char_id)
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Alles klar! Der {}. Charakter für @{} wurde gespeichert.".format(char_id, user_id),
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
                        body="Alles klar! Dein {}. Charakter wurde gespeichert.".format(char_id),
                        keyboards=[SuggestedResponseKeyboard(responses=[
                            self.generate_text_response("Anzeigen", self.get_from_userid(message), char_id, message),
                            self.generate_text_response("Bild-setzen", self.get_from_userid(message), char_id, message),
                            self.generate_text_response("Letzte-Löschen", self.get_from_userid(message), char_id, message, force_username=True),
                            TextResponse("Liste")
                        ])]
                    ))
                elif len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" and message_body.split(None, 2)[2].strip() != "":
                    user_id = message_body.split(None, 2)[1][1:].strip()

                    auth = self.check_auth(self.character_persistent_class, message)
                    if user_id != self.get_from_userid(message) and auth is not True:
                        return [auth]

                    self.character_persistent_class.change_char(message_body.split(None, 2)[1][1:].strip(), self.get_from_userid(message), message_body_c.split(None, 2)[2].strip())
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Alles klar! Der erste Charakter für @{} wurde gespeichert.".format(user_id),
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
                        body="Alles klar! Dein erster Charakter wurde gespeichert.",
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
                        body="Fehler beim Aufruf des Befehls. Siehe Hilfe.",
                        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                    ))

            #
            # Befehl Bild setzen
            #
            elif message_command in ["bild-setzen", "set-pic"]:

                response = None

                if len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" \
                        and message_body.split(None, 2)[2].isdigit():

                    user_id = message_body.split(None, 2)[1][1:].strip()
                    char_id = int(message_body.split(None, 2)[2])

                    auth = self.check_auth(self.character_persistent_class, message)
                    if user_id != self.get_from_userid(message) and auth is not True:
                        return [auth]

                elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].isdigit():

                    user_id = self.get_from_userid(message)
                    char_id = int(message_body.split(None, 1)[1])

                elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
                    user_id = message_body.split(None, 1)[1][1:].strip()
                    char_id = None

                    auth = self.check_auth(self.character_persistent_class, message)
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
                    body="Alles Klar! Bitte schicke jetzt das Bild direkt an @{}".format(bot_username)
                ))

            #
            # Befehl Anzeigen
            #
            elif message_command in ["anzeigen", "show", "steckbrief", "stecki"]:
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
                        body="Es wurde kein Charakter mit dem Namen {} des Nutzers @{} gefunden".format(char_name, selected_user),
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
                        body="Es wurden {} Charaktere mit dem Namen {} des Nutzers @{} gefunden".format(len(chars), char_name, selected_user),
                        keyboards=[SuggestedResponseKeyboard(responses=resp)]
                    ))
                elif char_data is None and char_id is not None:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Keine Daten zum {}. Charakter des Nutzers @{} gefunden".format(char_id, selected_user),
                        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
                    ))
                elif char_data is None:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Keine Daten zum Nutzer @{} gefunden".format(selected_user),
                        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
                    ))
                else:
                    (char_resp_msg, user_command_status, user_command_status_data) = self.create_char_messages(self.character_persistent_class,
                                                                   char_data, message, user_command_status, user_command_status_data)
                    response_messages += char_resp_msg

            #
            # Befehl Verschieben
            #
            elif message_command in ["verschieben", "move"]:
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
                            body = "Du hast erfolgreich deinen {}. Charakter auf @{} ({}.) verschoben.".format(char_id, selected_to_user, to_char_id)
                        else:
                            body = "Du hast erfolgreich deinen Charakter auf @{} ({}.) verschoben.".format(selected_to_user, to_char_id)

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

                    elif self.is_admin(message):
                        to_char_id = self.character_persistent_class.move_char(selected_from_user, selected_to_user, char_id)

                        if char_id is not None and char_id != CharacterPersistentClass.get_min_char_id():
                            body = "Du hast erfolgreich den {}. Charakter von @{} auf @{} ({}.) verschoben.".format(char_id, selected_from_user, selected_to_user, to_char_id)
                        else:
                            body = "Du hast erfolgreich den ersten Charakter von @{} auf @{} ({}.) verschoben.".format(selected_from_user, selected_to_user, to_char_id)

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
                            body="Du kannst keine Charaktere von anderen Nutzern verschieben.",
                            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
                        ))

                else:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Fehler beim Aufruf des Befehls. Siehe Hilfe.",
                        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                    ))

            #
            # Befehl Löschen
            #
            elif message_command in ["löschen", "del", "delete"]:
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
                            body = "Du hast erfolgreich deinen {}. Charakter gelöscht".format(char_id)
                        else:
                            body = "Du hast erfolgreich deinen Charakter gelöscht."

                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body=body,
                            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
                        ))

                    elif self.is_admin(message):
                        self.character_persistent_class.remove_char(selected_user,self.get_from_userid(message), char_id)

                        if char_id is not None:
                            body = "Du hast erfolgreich den {}. Charakter von @{} gelöscht.".format(char_id, selected_user)
                        else:
                            body = "Du hast erfolgreich den ersten Charakter von @{} gelöscht.".format(selected_user)

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
                            body="Du kannst keine Charaktere von anderen Nutzern löschen.",
                            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
                        ))

                else:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Fehler beim Aufruf des Befehls. Siehe Hilfe.",
                        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                    ))

            #
            # Befehl Löschen (letzte)
            #
            elif message_command in ["letzte-löschen", "del-last", "delete-last"]:
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
                            body = "Du hast erfolgreich die letzte Änderung am Charakter {} gelöscht.".format(char_id)
                        else:
                            body = "Du hast erfolgreich die letzte Änderung gelöscht."

                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body=body,
                            keyboards=[SuggestedResponseKeyboard(responses=[
                                TextResponse("Liste"),
                                self.generate_text_response("Anzeigen", selected_user, char_id, message)
                            ])]
                        ))

                    elif self.is_admin(message):
                        self.character_persistent_class.remove_last_char_change(selected_user, self.get_from_userid(message))

                        if char_id is not None:
                            body = "Du hast erfolgreich die letzte Änderung des Charakters {} von @{} gelöscht.".format(char_id, selected_user)
                        else:
                            body = "Du hast erfolgreich die letzte Änderung des Charakters von @{} gelöscht.".format(selected_user)

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
                            body="Du kannst keine Charaktere von anderen Nutzern löschen.",
                            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
                        ))

                else:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Fehler beim Aufruf des Befehls. Siehe Hilfe.",
                        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                    ))

            #
            # Befehl Suche
            #
            elif message_command in ["suche", "search"]:
                if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].strip() != "":
                    query = message_body.split(None, 1)[1].strip()

                    auth = self.check_auth(self.character_persistent_class, message)
                    if auth is not True:
                        return [auth]

                    chars = self.character_persistent_class.search_char(query)

                    if len(chars) == 0:
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Für die Suchanfrage wurden keine Charaktere gefunden.",
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
                            body="Es wurden mehrere Charaktere gefunden, die deiner Suchanfrage entsprechen.",
                            keyboards=[SuggestedResponseKeyboard(responses=resp)]
                        ))



                else:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Fehler beim Aufruf des Befehls. Siehe Hilfe.",
                        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                    ))

            #
            # Befehl Setze Befehl Tastaturen
            #
            elif message_command in ["setze-befehl-tastaturen", "set-command-keyboards", "set-cmd-keyboards"]:
                if self.is_admin(message):
                    if len(message_body.split(None, 2)) == 3:
                        keyboards = message_body_c.split(None, 2)[2].strip()
                        static_command = message_body.split(None, 2)[1].strip()
                        static_message = self.character_persistent_class.get_static_message(static_command)

                        if static_message is None:
                            response_messages.append(TextMessage(
                                to=message.from_user,
                                chat_id=message.chat_id,
                                body="Der Befehl '{}' existiert nicht.".format(static_message['command']),
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
                                body="Du hast erfolgreich die Tastaturen für den statischen Befehl '{}' aktualisiert.\n".format(static_message["command"]) +
                                "Du kannst auch alternative Befehle (wie z.B. 'h' für Hilfe oder 'rules' für Regeln) hinzufügen. Dies geht mit dem Befehl:\n\n" +
                                "@{} Setze-Befehl-Alternative-Befehle {} {}".format(bot_username, static_message["command"], example_alt_commands),
                                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse(static_message['command']), TextResponse("Admin-Hilfe")])]
                            ))
                    else:
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Fehler beim Aufruf des Befehls. Siehe Admin-Hilfe.",
                            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Admin-Hilfe")])]
                        ))
                else:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Du kannst keine statischen Antworten setzen."
                    ))

            #
            # Befehl Setze Befehl Alternative Befehle
            #
            elif message_command in ["setze-befehl-alternative-befehle", "set-command-alternative-commands", "set-cmd-alt-cmd"]:
                if self.is_admin(message):
                    if len(message_body.split(None, 2)) == 3:
                        alt_commands = message_body_c.split(None, 2)[2].strip()
                        static_command = message_body.split(None, 2)[1].strip()
                        static_message = self.character_persistent_class.get_static_message(static_command)

                        if static_message is None:
                            response_messages.append(TextMessage(
                                to=message.from_user,
                                chat_id=message.chat_id,
                                body="Der Befehl '{}' existiert nicht.".format(static_message['command']),
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
                                body="Du hast erfolgreich die alternativen Befehle für den Befehl '{}' aktualisiert.\n".format(static_message["command"]) +
                                "Du kannst jetzt noch mit dem folgenden Befehl die Antwort-Tastaturen setzen (Komma-getrennt):\n\n" +
                                "@{} Setze-Befehl-Tastaturen {} {}".format(bot_username, static_message["command"], example_keyboards),
                                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse(static_message['command']), TextResponse("Admin-Hilfe")])]
                            ))
                    else:
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Fehler beim Aufruf des Befehls. Siehe Admin-Hilfe.",
                            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Admin-Hilfe")])]
                        ))
                else:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Du kannst keine statischen Antworten setzen."
                    ))

            #
            # Befehl Setze Antwort
            #
            elif message_command in ["setze-befehl", "set-command", "set-cmd"]:
                if self.is_admin(message):
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
                            body="Du hast erfolgreich die statische Antwort auf den Befehl '{}' aktualisiert.\n".format(static_message["command"]) +
                                "Du kannst jetzt noch mit dem folgenden Befehl die Antwort-Tastaturen setzen (Komma-getrennt):\n\n" +
                                "@{} Setze-Befehl-Tastaturen {} {}\n\n\n".format(bot_username, static_message["command"], example_keyboards) +
                                "Du kannst auch alternative Befehle (wie z.B. 'h' für Hilfe oder 'rules' für Regeln) hinzufügen. Dies geht mit dem Befehl:\n\n" +
                                "@{} Setze-Befehl-Alternative-Befehle {} {}".format(bot_username, static_message["command"], example_alt_commands),
                            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse(static_message["command"]), TextResponse("Admin-Hilfe")])]
                        ))
                    else:
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Fehler beim Aufruf des Befehls. Siehe Admin-Hilfe.",
                            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Admin-Hilfe")])]
                        ))
                else:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Du kannst keine statischen Antworten setzen."
                    ))

            #
            # Befehl Auth
            #
            elif message_command in ["auth", "berechtigen", "authorize", "authorise"]:
                if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
                    selected_user = message_body.split(None, 1)[1][1:].strip()
                    result = self.character_persistent_class.auth_user(selected_user, message)

                    if result is True:
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Du hast erfolgreich den Nutzer @{} berechtigt.".format(selected_user)
                        ))

                    else:
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Der Nutzer @{} konnte nicht berechtigt werden.\n\n".format(selected_user) +
                                "Dies kann folgende Ursachen haben:\n" +
                                "1. Der Nutzer ist bereits berechtigt.\n" +
                                "2. Du bist nicht berechtigt, diesen Nutzer zu berechtigen."
                        ))

                else:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Fehler beim Aufruf des Befehls. Siehe Hilfe.",
                        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                    ))

            #
            # Befehl UnAuth
            #
            elif message_command in ["unauth", "entmachten", "unauthorize", "unauthorise"]:
                if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
                    selected_user = message_body.split(None, 1)[1][1:].strip()
                    result = self.character_persistent_class.unauth_user(selected_user, self.get_from_userid(message))

                    if result is True:
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Du hast erfolgreich den Nutzer @{} entmächtigt.".format(selected_user)
                        ))

                    else:
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Der Nutzer @{} konnte nicht entmächtigt werden.\n\n".format(selected_user) +
                                 "Dies kann folgende Ursachen haben:\n" +
                                 "Du bist nicht berechtigt, diesen Nutzer zu entmächtigen."
                        ))

                else:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Fehler beim Aufruf des Befehls. Siehe Hilfe.",
                        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                    ))

            #
            # Befehl Liste
            #
            elif message_command in ["liste", "list"]:
                if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].isdigit():
                    page = int(message_body.split(None, 1)[1])
                else:
                    page = 1

                auth = self.check_auth(self.character_persistent_class, message)
                if auth is not True:
                    return [auth]

                limit = 15
                chars = self.character_persistent_class.list_all_users_with_chars(page)
                user_ids = [item['user_id'] for item in chars[:limit]]

                body = "Liste aller Nutzer mit Charakteren:\n--- Seite {} ---\n".format(page)
                number = (page-1)*limit+1
                for char in chars[:limit]:
                    b = "{}.: {}\n".format(number, self.get_name(char['user_id'])) + \
                        "Nutzername: @{}\n".format(char['user_id']) + \
                        "Anz. Charaktere: {}\n".format(char['chars_cnt']) + \
                        "letzte Änderung: {}".format(datetime.datetime.fromtimestamp(char['created']).strftime('%d.%m.%Y'))

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
                    body += "\n\n(Weitere Seiten: {} und {} zum navigieren)".format(
                        u"\U00002B05\U0000FE0F",
                        u"\U000027A1\U0000FE0F"
                    )

                responses += [TextResponse("Anzeigen @{}".format(x)) for x in user_ids]

                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=body,
                    keyboards=[SuggestedResponseKeyboard(responses=responses)]
                ))


            #
            # Befehl Vorlage
            #
            elif message_body in ["vorlage", "charaktervorlage", "boilerplate", "draft", "template", "steckbrief", "steckbriefvorlage", "stecki"]:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=(
                        "Die folgende Charaktervorlage kann genutzt werden um einen neuen Charakter im RPG zu erstellen.\n"
                        "Dies ist eine notwendige Voraussetung um am RPG teilnehmen zu können.\n"
                        "Bitte poste diese Vorlage ausgefüllt im Gruppenchannel #{}\n".format(default_config.get("KikGroup", "somegroup")) +
                        "Wichtig: Bitte lasse die Schlüsselwörter (Vorname:, Nachname:, etc.) stehen.\n"
                        "Möchtest du die Vorlage nicht über den Bot speichern, dann entferne bitte die erste Zeile.\n"
                        "Hast du bereits einen Charakter und möchtest diesen aktualisieren, dann schreibe in der ersten Zeile 'ändern' anstatt 'hinzufügen'"
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe"), TextResponse("Weitere-Beispiele")])]
                ))

                template_message = self.character_persistent_class.get_static_message('nur-vorlage')

                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=(
                        "@{} hinzufügen \n".format(bot_username) + template_message["response"]
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe"), TextResponse("Weitere-Beispiele")])]
                ))

            elif message_body in ["weitere-beispiele", "more-examples"]:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=(
                        "Weitere Beispiele\n"
                        "Alle Beispiele sind in einzelnen Abschnitten mittels ----- getrennt.\n\n"
                        "------\n"
                        "@{} Hinzufügen @{}\n".format(bot_username, self.get_from_userid(message)) +
                        "Hier kann der Text zum Charakter stehen\n"
                        "Zeilenumbrüche sind erlaubt\n"
                        "In diesem Beispiel wurde der Nickname angegeben\n"
                        "------\n"
                        "@{} Ändern\n".format(bot_username) +
                        "Hier kann der Text zum Charakter stehen\n"
                        "Die Befehle Ändern und Hinzufügen bewirken das gleiche\n"
                        "Wird kein Benutzername angegeben so betrifft die Änderung bzw. das Hinzufügen einen selbst\n"
                        "------\n"
                        "@{} Anzeigen @ismil1110\n".format(bot_username) +
                        "------\n"
                        "@{} Anzeigen\n".format(bot_username) +
                        "------\n"
                        "@{} Löschen @{}\n".format(bot_username, self.get_from_userid(message)) +
                        "------\n"
                        "@{} Liste\n".format(bot_username) +
                        "------\n"
                        "@{} Hilfe\n".format(bot_username) +
                        "------\n"
                        "@{} Würfeln 8\n".format(bot_username) +
                        "------\n"
                        "@{} Würfeln Rot, Grün, Blau, Schwarz, Weiß\n".format(bot_username) +
                        "------\n"
                        "Bitte beachten, dass alle Befehle an den Bot mit @{} beginnen müssen. Die Nachricht darf".format(bot_username) +
                        " mit keinem Leerzeichen oder sonstigen Zeichen beginnen, da ansonsten die Nachricht nicht an den Bot weitergeleitet wird.\n"
                        "Wenn du bei dieser Nachricht auf Antworten tippst, werden dir unten 4 der oben gezeigten Beispiele als Vorauswahl angeboten"
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[
                        TextResponse("Hilfe"),
                        TextResponse((
                            "@{} Hinzufügen @{} ".format(bot_username, self.get_from_userid(message)) +
                            "Zeilenumbrüche sind nicht Pflicht."
                        )),
                        TextResponse("Anzeigen @ismil1110".format(bot_username)),
                        TextResponse("Anzeigen".format(bot_username)),
                        TextResponse("Liste".format(bot_username)),
                        TextResponse("Hilfe".format(bot_username)),
                        TextResponse("Würfeln 8".format(bot_username)),
                        TextResponse("Würfeln Rot, Grün, Blau, Schwarz, Weiß".format(bot_username))
                    ])]
                ))

            #
            # Befehl Würfeln
            #
            elif message_command in ["würfel", "würfeln", "dice", u"\U0001F3B2", "münze", "coin"]:

                if message_command in ["münze", "coin"]:
                    possibilities = ["Kopf", "Zahl"]
                    thing = "Die Münze zeigt"
                elif len(message_body.split(None, 1)) == 1 or message_body.split(None, 1)[1].strip() == "":
                    possibilities = list(range(1,7))
                    thing = "Der Würfel zeigt"
                elif message_body.split(None, 1)[1].isdigit():
                    count = int(message_body.split(None, 1)[1])
                    possibilities = list(range(1,count+1)) if count > 0 else [1]
                    thing = "Der Würfel zeigt"
                else:
                    possibilities = [x.strip() for x in message_body_c.split(None, 1)[1].split(',')]
                    thing = "Ich wähle"

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

            #
            # Befehl statische Antwort / keine Antwort
            #
            elif message_command != "":
                static_message = self.character_persistent_class.get_static_message(message_command)

                if static_message is not None:
                    if static_message["response_keyboards"] is None:
                        keyboards = ["Hilfe"]
                    else:
                        keyboards = json.loads(static_message["response_keyboards"])

                    keyboard_responses = list(map(TextResponse, keyboards))

                    body_split = static_message["response"].split("\n")
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
                        body="Sorry {}, den Befehl '{}' kenne ich nicht.".format(user.first_name, message_command),
                        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                    ))
            else:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body="Sorry {}, ich habe dich nicht verstanden.".format(user.first_name),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                ))
        elif isinstance(message, PictureMessage):
            status_obj = self.character_persistent_class.get_user_command_status(self.get_from_userid(message))
            if status_obj is None or status_obj['status'] != CharacterPersistentClass.STATUS_SET_PICTURE:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body="Sorry {}, mit diesem Bild kann ich leider nichts anfangen.".format(user.first_name),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                ))

            else:
                success = self.character_persistent_class.set_char_pic(status_obj['data']['user_id'], self.get_from_userid(message), message.pic_url, status_obj['data']['char_id'])
                if success is True:
                    body = "Alles klar! Das Bild wurde gesetzt."
                    show_resp = self.generate_text_response("Anzeigen", status_obj['data']['user_id'], status_obj['data']['char_id'], message)
                else:
                    body = "Beim hochladen ist ein Fehler aufgetreten. Bitte versuche es erneut."
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
                body="Sorry {}, ich habe dich nicht verstanden.".format(user.first_name),
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
    def check_auth(persistent_class, message, auth_command=False):
        if auth_command is False and message.chat_id == default_config.get("KikGroupChatId", ""):
            return True

        if persistent_class.is_auth_user(message) is False:
            return TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body="Du bist nicht berechtigt diesen Befehl auszuführen!\n" +
                     "Bitte melde dich in der Gruppe #{} und erfrage eine Berechtigung.".format(default_config.get("KikGroup", "somegroup")),
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
            body_char_appendix = "\n\n(Weitere Charaktere des Nutzers vorhanden: {} und {} zum navigieren)".format(
                u"\U00002B05\U0000FE0F",
                u"\U000027A1\U0000FE0F"
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

        body = "{}\n\n---\nCharakter von {}\nErstellt von {}\nErstellt am {}{}".format(
            char_data['text'],
            MessageController.get_name(char_data["user_id"], append_user_id=True),
            MessageController.get_name(char_data['creator_id'], append_user_id=True),
            datetime.datetime.fromtimestamp(char_data['created']).strftime('%Y-%m-%d %H:%M:%S'),
            body_char_appendix
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
        global kik_api_cache

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
    def is_admin(message: Message):
        if message.type == "public":
            return False
        return message.from_user.lower() in [x.strip().lower() for x in default_config.get("Admins", "admin1").split(',')]


class KikApiCache:

    def __init__(self):
        self.users = {}

    def get_user(self, user_id):

        try:
            if int(time.time()) > self.users[user_id.lower()]['last-request'] + 6*60*60:
                self.request_user(user_id.lower())
        except KeyError:
            self.request_user(user_id.lower())

        return self.users[user_id.lower()]["data"]

    def request_user(self, user_id):

        print("Kik API: Request User {}".format(user_id))

        try:
            user_data = kik_api.get_user(user_id.lower())
        except KikError:
            user_data = None

        self.users[user_id.lower()] = {
            "data": user_data,
            "last-request": int(time.time())
        }


class CharacterPersistentClass:

    STATUS_NONE = 0
    STATUS_SET_PICTURE = 1
    STATUS_DYN_MESSAGES = 2

    def __init__(self):
        self.connection = None
        self.cursor = None

    def __del__(self):
        if self.connection is not None:
            self.connection.commit()
            self.connection.close()

    def connect_database(self):
        if self.connection is None:
            self.connection = sqlite3.connect(database_path)
            self.connection.row_factory = sqlite3.Row
            self.cursor = self.connection.cursor()

    def commit(self):
        if self.connection is not None:
            self.connection.commit()

    @staticmethod
    def get_min_char_id():
        return 1

    def get_next_fee_char_id(self, user_id):
        self.connect_database()

        self.cursor.execute((
            "SELECT char_id "
            "FROM characters "
            "WHERE user_id=? "
            "ORDER BY char_id "
            "LIMIT 1 "
        ), [user_id])

        min_char_id = self.cursor.fetchone()
        if min_char_id is None or int(min_char_id['char_id']) != self.get_min_char_id():
            return self.get_min_char_id()

        self.cursor.execute((
            "SELECT char_id + 1 AS new_char_id "
            "FROM characters ch "
            "WHERE NOT EXISTS ( "
            "    SELECT  NULL "
            "    FROM    characters mi "
            "    WHERE   mi.char_id = ch.char_id + 1 AND mi.user_id=ch.user_id"
            ") AND ch.user_id=?"
            "ORDER BY char_id "
            "LIMIT 1 "
        ), [user_id])

        next_free_char_id = self.cursor.fetchone()
        if next_free_char_id is None:
            return self.get_min_char_id()
        return int(next_free_char_id['new_char_id'])

    def add_char(self, user_id, creator_id, text):
        self.connect_database()

        next_char_id = self.get_next_fee_char_id(user_id)
        data = (user_id, next_char_id, text, creator_id, int(time.time()) )
        self.cursor.execute((
            "INSERT INTO characters "
            "(user_id, char_id, text, creator_id, created) "
            "VALUES (?, ?, ?, ?, ?)"
        ), data)
        return next_char_id

    def change_char(self, user_id, creator_id, text, char_id=None):
        self.connect_database()

        if char_id is None:
            char_id = self.get_min_char_id()

        if self.get_char(user_id, char_id) is None:
            return False

        data = (user_id, char_id, text, creator_id, int(time.time()))
        self.cursor.execute((
            "INSERT INTO characters "
            "(user_id, char_id, text, creator_id, created) "
            "VALUES (?, ?, ?, ?, ?)"
        ), data)

    def set_char_pic(self, user_id, creator_id, pic_url, char_id=None):
        self.connect_database()

        timestamp = int(time.time())

        if char_id is None:
            char_id = self.get_min_char_id()

        picture_path = default_config.get("PicturePath", "{home}/pictures").format(home=str(Path.home()))
        file_wo_ext = "{}/{}-{}-{}-{}".format(picture_path, user_id, creator_id, char_id, timestamp)
        file_tmp = file_wo_ext + ".tmp"
        with open(file_tmp, 'wb') as handle:
            response = requests.get(pic_url, stream=True)

            for block in response.iter_content(1024):
                if not block:
                    break

                handle.write(block)

        handle.close()

        if response.status_code != 200:
            os.remove(file_tmp)
            return False

        try:
            ext = guess_extension(response.headers['content-type'].split()[0].rstrip(";"))
        except KeyError:
            ext = ".jpg"

        if ext == ".jpe":
            ext = ".jpg"

        os.rename(file_tmp, file_wo_ext + ext)

        data = (user_id, char_id, file_wo_ext + ext, creator_id, int(time.time()))
        self.cursor.execute((
            "INSERT INTO character_pictures "
            "(user_id, char_id, picture_filename, creator_id, created) "
            "VALUES (?, ?, ?, ?, ?)"
        ), data)

        return True

    def move_char(self, from_user_id, to_user_id, from_char_id=None):
        self.connect_database()

        if from_char_id is None:
            from_char_id = self.get_min_char_id()

        to_char_id = self.get_next_fee_char_id(to_user_id)

        data = (to_user_id, to_char_id, from_user_id, from_char_id)
        self.cursor.execute((
            "UPDATE characters "
            "SET user_id=?, char_id=? "
            "WHERE user_id LIKE ? AND char_id=?"
        ), data)

        return to_char_id

    def remove_char(self, user_id, deletor_id, char_id=None):
        self.connect_database()

        if char_id is None:
            char_id = self.get_min_char_id()

        if self.get_char(user_id, char_id) is None:
            return False

        data = (deletor_id, int(time.time()), user_id, char_id)
        self.cursor.execute((
            "UPDATE characters "
            "SET deletor_id=?, deleted=? "
            "WHERE user_id LIKE ? AND char_id=?"
        ), data)

    def remove_last_char_change(self, user_id, deletor_id, char_id=None):
        self.connect_database()

        if char_id is None:
            char_id = self.get_min_char_id()

        if self.get_char(user_id, char_id) is None:
            return False

        data = (deletor_id, int(time.time()), user_id, char_id)
        self.cursor.execute((
            "UPDATE characters "
            "SET deletor_id=?, deleted=? "
            "WHERE id = ("
            "    SELECT id "
            "    FROM characters "
            "    WHERE user_id LIKE ? AND char_id=? AND deleted IS NULL "
            "    ORDER BY created DESC "
            "    LIMIT 1"
            ")"
        ), data)

    def get_first_char_id(self, user_id):
        self.connect_database()

        self.cursor.execute((
            "SELECT MIN(char_id) AS min_char_id " 
            "  FROM  characters " 
            "  WHERE user_id = ? AND deleted IS NULL "
        ), [user_id])

        row = self.cursor.fetchone()
        if row is None or row["min_char_id"] is None:
            return None
        return int(row["min_char_id"])

    def get_char(self, user_id, char_id=None):
        self.connect_database()

        if char_id is None:
            char_id = self.get_first_char_id(user_id)

        self.cursor.execute((
            "SELECT id, user_id, char_id, text, creator_id, created, "
            "    (SELECT MIN(char_id) "
            "        FROM  characters AS c1 "
            "        WHERE c1.user_id = c.user_id AND c1.deleted IS NULL AND c1.char_id > c.char_id) AS next_char_id, "
            "    (SELECT MAX(char_id) "
            "        FROM  characters AS c2 "
            "        WHERE c2.user_id = c.user_id AND c2.deleted IS NULL AND c2.char_id < c.char_id) AS prev_char_id "
            "FROM  characters AS c "
            "WHERE user_id LIKE ? AND char_id=? AND deleted IS NULL "
            "ORDER BY created DESC "
            "LIMIT 1"
        ), [user_id, char_id])

        return self.cursor.fetchone()

    def get_char_pic_url(self, user_id, char_id):
        self.connect_database()

        if char_id is None:
            char_id = self.get_first_char_id(user_id)

        self.cursor.execute((
            "SELECT picture_filename "
            "FROM  character_pictures "
            "WHERE user_id LIKE ? AND char_id=? AND deleted IS NULL "
            "ORDER BY created DESC "
            "LIMIT 1"
        ), [user_id, char_id])

        pic_data = self.cursor.fetchone()
        if pic_data is None:
            return None

        return "{}:{}/picture/{}".format(
            default_config.get("RemoteHostIP", "www.example.com"),
            default_config.get("RemotePort", "8080"),
            os.path.basename(pic_data['picture_filename'])
        )

    def get_all_user_chars(self, user_id):
        self.connect_database()

        self.cursor.execute((
            "SELECT id, char_id, text, creator_id, MAX(created) AS created "
            "FROM characters "
            "WHERE user_id LIKE ? AND deleted IS NULL "
            "GROUP BY char_id"
        ), [user_id])
        chars = self.cursor.fetchall()
        return chars

    def list_all_users_with_chars(self, page=1, limit=15):
        self.connect_database()

        self.cursor.execute((
            "SELECT id, user_id, MAX(char_id) AS chars_cnt, created "
            "FROM characters "
            "WHERE deleted IS NULL "
            "GROUP BY user_id "
            "ORDER BY created DESC "
            "LIMIT ?,? "
        ), [(page-1)*limit, limit+1])
        return self.cursor.fetchall()

    def auth_user(self, user_id, message):
        if self.is_auth_user(message) or \
                MessageController.is_admin(message) is False and (self.is_unauth_user(user_id) or self.is_auth_user(message) is False):
            return False

        self.connect_database()

        data = (user_id, MessageController.get_from_userid(message), int(time.time()))
        self.cursor.execute((
            "INSERT INTO users "
            "(user_id, creator_id, created) "
            "VALUES (?, ?, ?)"
        ), data)
        return True

    def unauth_user(self, user_id, message):
        if MessageController.is_admin(message) is False:
            return False

        self.connect_database()

        data = (MessageController.get_from_userid(message), int(time.time()), user_id)
        self.cursor.execute((
            "UPDATE users "
            "SET deletor_id=?, deleted=? "
            "WHERE user_id LIKE ?"
        ), data)
        return True

    def is_auth_user(self, message):
        if MessageController.is_admin(message):
            return True

        self.connect_database()
        self.cursor.execute((
            "SELECT id "
            "FROM  users "
            "WHERE user_id LIKE ? AND deleted IS NULL "
            "LIMIT 1"
        ), [MessageController.get_from_userid(message)])
        return self.cursor.fetchone() is not None

    def is_unauth_user(self, user_id):
        self.connect_database()

        self.cursor.execute((
            "SELECT id "
            "FROM  users "
            "WHERE user_id LIKE ? AND deleted IS NULL "
            "LIMIT 1"
        ), [user_id])
        return self.cursor.fetchone() is None

    def find_char(self, name, user_id):
        self.connect_database()

        self.cursor.execute((
            "SELECT id, char_id, text, creator_id, MAX(created) AS created "
            "FROM characters "
            "WHERE user_id=? AND deleted IS NULL AND text LIKE ? "
            "GROUP BY user_id, char_id"
        ), [user_id, "%"+name+"%"])
        chars_raw = self.cursor.fetchall()
        chars = []

        for char in chars_raw:
            if re.search(r".*?name(.*?):[^a-z]*?{}[^a-z]*?".format(re.escape(name)), char['text'], re.MULTILINE+re.IGNORECASE) is not None:
                chars.append(char)

        return chars

    def search_char(self, query, type="name"):
        self.connect_database()

        self.cursor.execute((
            "SELECT id, user_id, char_id, text, creator_id, MAX(created) AS created "
            "FROM characters "
            "WHERE deleted IS NULL AND text LIKE ? "
            "GROUP BY user_id, char_id"
        ), ["%"+query+"%"])
        chars_raw = self.cursor.fetchall()
        chars = []

        for char in chars_raw:
            if re.search(r".*?{}(.*?):[^a-z]*?{}[^a-z]*?".format(re.escape(type), re.escape(query)), char['text'], re.MULTILINE+re.IGNORECASE) is not None:
                chars.append(char)

        return chars

    def update_user_command_status(self, user_id, status, status_data=None):
        self.connect_database()

        status_obj = {
            'status': status,
            'data': status_data
        }

        self.cursor.execute((
            "SELECT user_id, status "
            "FROM user_command_status "
            "WHERE user_id LIKE ? "
            "LIMIT 1"
        ), [user_id])

        if self.cursor.fetchone() is None:
            self.cursor.execute((
                "INSERT INTO user_command_status "
                "(user_id, status, updated) "
                "VALUES (?, ?, ?) "
            ), [user_id, json.dumps(status_obj), int(time.time())])
        else:
            self.cursor.execute((
                "UPDATE user_command_status "
                "SET status = ?, updated = ? "
                "WHERE user_id LIKE ? "
            ), [json.dumps(status_obj), int(time.time()), user_id])

    def get_user_command_status(self, user_id):
        self.connect_database()

        self.cursor.execute((
            "SELECT status "
            "FROM user_command_status "
            "WHERE user_id LIKE ? "
            "LIMIT 1"
        ), [user_id])

        status_data = self.cursor.fetchone()
        if status_data is None:
            return None
        else:
            return json.loads(status_data['status'])

    def set_static_message(self, command, response):
        self.connect_database()

        static_message = self.get_static_message(command)
        if static_message is None:
            self.cursor.execute((
                "INSERT INTO static_messages "
                "(command, response) "
                "VALUES (?, ?) "
            ), [command, response])
        else:
            self.cursor.execute((
                "UPDATE static_messages "
                "SET response = ? "
                "WHERE command LIKE ? "
            ), [response, command])

        return self.get_static_message(command)

    def set_static_message_keyboard(self, command, keyboard):
        self.connect_database()

        static_message = self.get_static_message(command)
        if static_message is not None:
            self.cursor.execute((
                "UPDATE static_messages "
                "SET response_keyboards = ? "
                "WHERE command LIKE ? "
            ), [json.dumps(keyboard), command])

        return self.get_static_message(command)

    def set_static_message_alt_commands(self, command, alt_commands):
        self.connect_database()

        static_message = self.get_static_message(command)
        if static_message is not None:
            self.cursor.execute((
                "UPDATE static_messages "
                "SET alt_commands = ? "
                "WHERE command LIKE ? "
            ), [json.dumps(alt_commands), command])

        return self.get_static_message(command)

    def get_static_message(self, command):
        self.connect_database()

        self.cursor.execute((
            "SELECT * "
            "FROM static_messages "
            "WHERE command LIKE ? OR alt_commands LIKE ? "
            "LIMIT 1"
        ), [command, "%\""+command+"\"%"])

        return self.cursor.fetchone()


def create_database(database_path):
    connection = sqlite3.connect(database_path)
    cursor = connection.cursor()

    cursor.executescript(open('database.sql', 'r').read())

    connection.commit()
    connection.close()
    print ("Datenbank {} angelegt".format(os.path.basename(database_path)))


configFile = os.environ.get('RPCHARBOT_CONF', 'config.ini')
print("Using conf {}.".format(configFile))

config = configparser.ConfigParser()
config.read(configFile)
default_config = config['DEFAULT'] # type: SectionProxy
bot_username = default_config.get("BotUsername", "botname")
print("Bot Username: {}".format(bot_username))

database_path = default_config.get("DatabasePath", "{home}/database.db").format(home=str(Path.home()))
if not os.path.exists(database_path):
    print("Datenbank {} nicht vorhanden - Datenbank wird anglegt.".format(os.path.basename(database_path)))
    create_database(database_path)

kik_api = KikApi(bot_username, default_config.get("BotAuthCode", "abcdef01-2345-6789-abcd-ef0123456789"))
kik_api_cache = KikApiCache()
# For simplicity, we're going to set_configuration on startup. However, this really only needs to happen once
# or if the configuration changes. In a production setting, you would only issue this call if you need to change
# the configuration, and not every time the bot starts.
kik_api.set_configuration(Configuration(webhook="{}:{}/incoming".format(default_config.get("RemoteHostIP", "www.example.com"), default_config.get("RemotePort", "8080"))))
