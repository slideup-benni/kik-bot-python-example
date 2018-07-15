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
import argparse
import json
import re
from configparser import SectionProxy
from mimetypes import guess_extension
from pathlib import Path

import requests
from flask import Flask, request, Response, send_from_directory
from kik import KikApi, Configuration
from kik.messages import messages_from_json, TextMessage, PictureMessage, \
    SuggestedResponseKeyboard, TextResponse, StartChattingMessage
import os, sqlite3, time, datetime, configparser

class KikBot(Flask):
    """ Flask kik bot application class"""

    def __init__(self, kik_api, import_name, static_path=None, static_url_path=None, static_folder="static",
                 template_folder="templates", instance_path=None, instance_relative_config=False,
                 root_path=None):

        self.kik_api = kik_api

        super(KikBot, self).__init__(import_name, static_path, static_url_path, static_folder, template_folder,
                                     instance_path, instance_relative_config, root_path)

        self.route("/incoming", methods=["POST"])(self.incoming)
        self.route("/picture/<path:path>", methods=["GET"])(self.picture)

    def picture(self, path):
        picture_path = default_config.get("PicturePath", "{home}/pictures").format(home=str(Path.home()))
        return send_from_directory(picture_path, path)

    def incoming(self):
        """Handle incoming messages to the bot. All requests are authenticated using the signature in
        the 'X-Kik-Signature' header, which is built using the bot's api key (set in main() below).
        :return: Response
        """
        # verify that this is a valid request
        if not self.kik_api.verify_signature(
                request.headers.get("X-Kik-Signature"), request.get_data()):
            return Response(status=403)

        messages = messages_from_json(request.json["messages"])

        response_messages = []
        message_controller = MessageController()


        for message in messages:
            response_messages += message_controller.process_message(message, self.kik_api.get_user(message.from_user))
            self.kik_api.send_messages(response_messages)

        return Response(status=200)



class MessageController:

    def __init__(self):
        self.reload_config()
        self.character_persistent_class = CharacterPersistentClass()
        pass

    @staticmethod
    def reload_config():
        #reread config
        global config
        global default_config
        config.read(args.config)
        default_config = config['DEFAULT']  # type: SectionProxy


    def process_message(self, message, user):
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

            if message_body == "":
                return [TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body="Hi {}, ich bin der Character-Bot der Gruppe #germanrpu\n".format(user.first_name) +
                         "Für weitere Informationen tippe auf Antworten und dann auf Hilfe.",
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
                status_obj = self.character_persistent_class.get_user_command_status(message.from_user)
                if status_obj['status'] == CharacterPersistentClass.STATUS_DYN_MESSAGES:
                    message_body = status_obj['data']['left'].lower()

            elif message_body == u"\U000027A1\U0000FE0F":
                status_obj = self.character_persistent_class.get_user_command_status(message.from_user)
                if status_obj['status'] == CharacterPersistentClass.STATUS_DYN_MESSAGES:
                    message_body = status_obj['data']['right'].lower()

            message_command = message_body.split(None,1)[0]

            #
            # Befehl hinzufügen
            #
            if message_command in ["hinzufügen", "add"]:
                if len(message_body.split(None,2)) == 3 and message_body.split(None,2)[1][0] == "@" and message_body.split(None,2)[2].strip() != "":
                    selected_user = message_body.split(None,2)[1][1:]

                    auth = self.check_auth(self.character_persistent_class, message)
                    if selected_user != message.from_user and auth is not True:
                        return [auth]

                    char_id = self.character_persistent_class.add_char(message_body.split(None, 2)[1][1:].strip(), message.from_user, message.body.split(None, 2)[2].strip())

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
                    char_id = self.character_persistent_class.add_char(message.from_user, message.from_user, message.body.split(None, 1)[1].strip())

                    if char_id == CharacterPersistentClass.get_min_char_id():
                        body = "Alles klar! Dein erster Charakter wurde hinzugefügt."
                    else:
                        body = "Alles klar! Dein {}. Charakter wurde hinzugefügt.".format(char_id)

                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body=body,
                        keyboards=[SuggestedResponseKeyboard(responses=[
                            self.generate_text_response("Anzeigen", message.from_user, char_id, message),
                            self.generate_text_response("Bild-setzen", message.from_user, char_id, message),
                            self.generate_text_response("Löschen", message.from_user, char_id, message, force_username=True),
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
            # Befehl ändern
            #
            elif message_command in ["ändern", "change"]:
                if len(message_body.split(None, 3)) == 4 and message_body.split(None, 3)[1][0] == "@" \
                        and message_body.split(None, 3)[2].isdigit() and message_body.split(None, 3)[3].strip() != "":

                    user_id = message_body.split(None, 3)[1][1:].strip()
                    char_id = int(message_body.split(None, 3)[2])
                    text = message.body.split(None, 3)[3].strip()

                    auth = self.check_auth(self.character_persistent_class, message)
                    if user_id != message.from_user and auth is not True:
                        return [auth]

                    self.character_persistent_class.change_char(user_id, message.from_user, text, char_id)
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
                    text = message.body.split(None, 2)[2].strip()

                    self.character_persistent_class.change_char(message.from_user, message.from_user, text, char_id)
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Alles klar! Dein {}. Charakter wurde gespeichert.".format(char_id),
                        keyboards=[SuggestedResponseKeyboard(responses=[
                            self.generate_text_response("Anzeigen", message.from_user, char_id, message),
                            self.generate_text_response("Bild-setzen", message.from_user, char_id, message),
                            self.generate_text_response("Letzte-Löschen", message.from_user, char_id, message, force_username=True),
                            TextResponse("Liste")
                        ])]
                    ))
                elif len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" and message_body.split(None, 2)[2].strip() != "":
                    user_id = message_body.split(None, 2)[1][1:].strip()

                    auth = self.check_auth(self.character_persistent_class, message)
                    if user_id != message.from_user and auth is not True:
                        return [auth]

                    self.character_persistent_class.change_char(message_body.split(None, 2)[1][1:].strip(), message.from_user, message.body.split(None, 2)[2].strip())
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
                    self.character_persistent_class.change_char(message.from_user, message.from_user, message.body.split(None, 1)[1].strip())
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Alles klar! Dein erster Charakter wurde gespeichert.",
                        keyboards=[SuggestedResponseKeyboard(responses=[
                            self.generate_text_response("Anzeigen", message.from_user, None, message),
                            self.generate_text_response("Bild-setzen", message.from_user, None, message),
                            self.generate_text_response("Letzte-Löschen", message.from_user, None, message, force_username=True),
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
                    if user_id != message.from_user and auth is not True:
                        return [auth]

                elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1].isdigit():

                    user_id = message.from_user
                    char_id = int(message_body.split(None, 1)[1])

                elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
                    user_id = message_body.split(None, 1)[1][1:].strip()
                    char_id = None

                    auth = self.check_auth(self.character_persistent_class, message)
                    if user_id != message.from_user and auth is not True:
                        return [auth]

                else:
                    user_id = message.from_user
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
            elif message_command in ["anzeigen", "show"]:
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
                    selected_user = message.from_user
                    char_id = int(message_body.split(None,1)[1])
                elif len(message_body.split(None,1)) == 2 and message_body.split(None,1)[1][0] == "@":
                    selected_user = message_body.split(None,1)[1][1:].strip()
                    char_id = None
                elif len(message_body.split(None,1)) == 2 and message_body.split(None,1)[1].strip() != "":
                    char_name = message_body.split(None, 1)[1].strip()
                    chars = self.character_persistent_class.find_char(char_name, message.from_user)
                    selected_user = message.from_user
                    if len(chars) == 1:
                        char_id = chars[0]['char_id']
                        char_data = chars[0]
                    else:
                        char_id = None
                else:
                    selected_user = message.from_user
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
                    (char_resp_msg, user_command_status, user_command_status_data) = self.create_char_messages(self.character_persistent_class, selected_user,
                                                                   char_id, char_data, message, user_command_status, user_command_status_data)
                    response_messages += char_resp_msg


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

                    if selected_user == message.from_user:
                        self.character_persistent_class.remove_char(selected_user, message.from_user, char_id)

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

                    elif message.from_user in [x.strip() for x in default_config.get("Admins", "admin1").split(',')]:
                        self.character_persistent_class.remove_char(selected_user, message.from_user, char_id)

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


                    if selected_user == message.from_user:
                        self.character_persistent_class.remove_last_char_change(selected_user, message.from_user)

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

                    elif message.from_user in [x.strip() for x in default_config.get("Admins", "admin1").split(',')]:
                        self.character_persistent_class.remove_last_char_change(selected_user, message.from_user)

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
                        (char_resp_msg, user_command_status, user_command_status_data) = self.create_char_messages(self.character_persistent_class, chars[0]['user_id'],
                                                                       chars[0]['char_id'], chars[0], message, user_command_status, user_command_status_data)
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
            # Befehl Auth
            #
            elif message_command in ["auth", "berechtigen", "authorize", "authorise"]:
                if len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] == "@":
                    selected_user = message_body.split(None, 1)[1][1:].strip()
                    result = self.character_persistent_class.auth_user(selected_user, message.from_user)

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
                    result = self.character_persistent_class.unauth_user(selected_user, message.from_user)

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
                auth = self.check_auth(self.character_persistent_class, message)
                if auth is not True:
                    return [auth]

                chars = self.character_persistent_class.get_all_users_with_chars()
                user_ids = [item['user_id'] for item in chars]

                chars_text = []
                for char in chars:
                    if char['chars_cnt'] > CharacterPersistentClass.get_min_char_id():
                        chars_text.append("@{} ({})".format(char['user_id'], char['chars_cnt']))
                    else:
                        chars_text.append("@{}".format(char['user_id']))

                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=",\n".join(chars_text),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Anzeigen @{}".format(x)) for x in user_ids])]
                ))


            #
            # Befehl Vorlage
            #
            elif message_body in ["vorlage", "charaktervorlage", "boilerplate", "draft", "template"]:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=(
                        "Die folgende Charaktervorlage kann genutzt werden um einen neuen Charakter im Rollenspiel zu erstellen.\n"
                        "Dies ist eine notwendige Voraussetung um an dem Rollenspiel teilnehmen zu können.\n"
                        "Bitte poste diese Vorlage ausgefüllt im Gruppenchannel #germanrpu\n"
                        "Du kannst diese Vorlage über den Bot speichern, indem du die folgende Zeile als erste Zeile in den Charakterbogen schreibst:\n" +
                        "@{} hinzufügen\n".format(bot_username)
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe"), TextResponse("Weitere-Beispiele")])]
                ))
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=(
                        "Basics:\n"
                        "Originaler Charakter oder OC?:\n\n"
                        "Vorname:\n"
                        "Nachname:\n"
                        "Rufname/Spitzname:\n"
                        "Alter:\n"
                        "Blutgruppe:\n"
                        "Geschlecht:\n\n"
                        "Wohnort:\n\n"
                        "Apparance\n\n"
                        "Größe: \n"
                        "Gewicht: \n"
                        "Haarfarbe: \n"
                        "Haarlänge:\n"
                        "Augenfarbe: \n"
                        "Aussehen:\n"
                        "Merkmale:\n\n"
                        "About You\n\n"
                        "Persönlichkeit: (bitte mehr als 2 Sätze)\n\n"
                        "Mag:\n"
                        "Mag nicht:\n"
                        "Hobbys:\n\n"
                        "Wesen:\n\n"
                        "Fähigkeiten:\n\n"
                        "Waffen etc:\n\n\n"
                        "Altagskleidung:\n\n"
                        "Sonstiges\n\n"
                        "(Kann alles beinhalten, was noch nicht im Steckbrief vorkam)"
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe"), TextResponse("Weitere-Beispiele")])]
                ))


            #
            # Befehl Regeln
            #
            elif message_body in ["regeln", "rules"]:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=(
                        "*~RULES~*\n\n"
                        "1.\n"
                        "Kein Sex! (flirten ist OK, Sex per PN)\n\n"
                        "2.\n"
                        "Sachen die man tut: *......*\n"
                        "Sachen die man sagt: ohne Zeichen\n"
                        "Sachen die man denkt: //..... //\n"
                        "Sachen die nicht zum RP gehören (....)\n\n"
                        "3.\n"
                        "Es gibt 2 Gruppen:\n"
                        "Die öffentliche ist für alle Gespräche, die nicht zum RP gehören.\n"
                        "Die *REAL*RPG* Gruppe ist AUSSCHLIEẞLICH zum RPG zugelassen.\n\n"
                        "4.\n"
                        "Keine overpowerten und nur ernst gemeinte Charakter. (Es soll ja Spaß machen)\n\n"
                        "5.\n"
                        "RP Handlung:\n"
                        "Schön guten Abend, Seid ihr es nicht auch leid? Von jeglichen Menschen aus eurer "
                        "Heimat vertrieben zu werden? Gejagt, verfolgt oder auch nur verachtet zu werden? "
                        "Dann kommt zu uns! Wir bauen zusammen eine Stadt auf. Eine Stadt wo nur Wesen "
                        "wohnen und auch nur Eintritt haben.\n\n"
                        "6.\n"
                        "Sei Aktiv mindestens in 3 Tagen einmal!\n\n"
                        "7.\n"
                        "Keine Hardcore Horror Bilder. (höchstens per PN wenn ihr es unter bringen wollt mit der bestimmten Person)\n\n"
                        "8.\n"
                        "Wenn du ein Arsch bist oder dich einfach nicht an die Regeln hältst wirst "
                        "du verwarnt oder gekickt. Wenn es unverdient war schreib uns an.\n\n"
                        "9.\n"
                        "Übertreibt es nicht mit dem Drama.\n\n"
                        "10.\n"
                        "Wenn du bis hier gelesen hast sag 'Luke ich bin dein Vater' Antworte in den nächsten 10 Min."
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Charaktervorlage"), TextResponse("Hilfe"), TextResponse("Weitere-Beispiele")])]
                ))


            #
            # Befehl Hilfe
            #
            elif message_body in ["hilfe", "hilfe!", "help", "h", "?"]:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=(
                        "Folgende Befehle sind möglich:\n"
                        "Hilfe\n"
                        "Regeln\n"
                        "Vorlage\n"
                        "Hinzufügen (<username>) <text>\n"
                        "Ändern (<username>) (<char_id>) <text>\n"
                        "Bild-setzen (<username>) (<char_id>)\n"
                        "Anzeigen (<username>) (<char_id>|<char_name>)\n"
                        "Löschen <eigener_username> (<char_id>)\n"
                        "Letzte-Löschen <eigener_username> (<char_id>)\n"
                        "Suchen <char_name>\n"
                        "Berechtigen <username>\n"
                        "Liste\n\n"
                        "Die Befehle können ausgeführt werden indem man entweder den Bot direkt anschreibt oder in der Gruppe '@{} <Befehl>' eingibt.\n".format(bot_username) +
                        "Beispiel: '@{} Liste'\n\n".format(bot_username) +
                        "Der Parameter <char_id> ist nur relevant, wenn du mehr als einen Charakter speichern möchtest. Der erste Charakter "
                        "hat immer die Id 1. Legst du einen weiteren an, erhält dieser die Id 2 usw.\n\n"
                        "Der Bot kann nicht nur innerhalb einer Gruppe verwendet werden; man kann ihn auch direkt anschreiben (@{}) oder in PMs verwenden.".format(bot_username)
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[
                        TextResponse("Regeln"),
                        TextResponse("Kurzbefehle"),
                        TextResponse("Weitere-Beispiele"),
                        TextResponse("Charaktervorlage")
                    ])]
                ))

            elif message_body in ["hilfe2", "help2", "kurzbefehle"]:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=(
                        "Folgende Kurz-Befehle sind möglich:\n"
                        "help\n"
                        "rules\n"
                        "template\n"
                        "add (<username>) <text>\n"
                        "change (<username>) (<char_id>) <text>\n"
                        "set-pic (<username>) (<char_id>)\n"
                        "show (<username>) (<char_id>|<char_name>)\n"
                        "del <eigener_username> (<char_id>)\n"
                        "del-last <eigener_username> (<char_id>)\n"
                        "search <char_name>\n"
                        "auth <username>\n"
                        "list\n"
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("rules"), TextResponse("Weitere-Beispiele"), TextResponse("Template")])]
                ))
            elif message_body in ["admin-hilfe", "admin-help"]:
                auth = self.check_auth(self.character_persistent_class, message)
                if auth is not True:
                    return  [auth]

                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=(
                        "Folgende Admin-Befehle sind möglich:\n"
                        "auth/Berechtigen <username>\n"
                        "unauth/Entmachten <username>\n"
                        "del/Löschen <username> (<char_id>)\n"
                        "del-last/Letzte-Löschen <username> (<char_id>)\n"
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("rules"), TextResponse("Weitere-Beispiele"), TextResponse("Template")])]
                ))
            elif message_body in ["weitere-beispiele", "more-examples"]:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=(
                        "Weitere Beispiele\n"
                        "Alle Beispiele sind in einzelnen Abschnitten mittels ----- getrennt.\n\n"
                        "------\n"
                        "@{} Hinzufügen @{}\n".format(bot_username, message.from_user) +
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
                        "@{} Löschen @{}\n".format(bot_username, message.from_user) +
                        "------\n"
                        "@{} Liste\n".format(bot_username) +
                        "------\n"
                        "Bitte beachten, dass alle Befehle an den Bot mit @{} beginnen müssen. Die Nachricht darf".format(bot_username) +
                        " mit keinem Leerzeichen oder sonstigen Zeichen beginnen, da ansonsten die Nachricht nicht an den Bot weitergeleitet wird.\n"
                        "Wenn du bei dieser Nachricht auf Antworten tippst, werden dir unten 4 der oben gezeigten Beispiele als Vorauswahl angeboten"
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[
                        TextResponse("Hilfe"),
                        TextResponse((
                            "@{} Hinzufügen @{} ".format(bot_username, message.from_user) +
                            "Zeilenumbrüche sind nicht Pflicht."
                        )),
                        TextResponse("@{} Anzeigen @ismil1110".format(bot_username)),
                        TextResponse("@{} Anzeigen".format(bot_username)),
                        TextResponse("@{} Liste".format(bot_username))
                    ])]
                ))

            #
            # Befehl einer
            #
            elif message_body in ["anderer bot"]:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body=u"Es kann nur einen geben! \U0001F608"
                ))



            #
            # Befehl unbekannt
            #
            elif message_command != "":
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
            status_obj = self.character_persistent_class.get_user_command_status(message.from_user)
            if status_obj is None or status_obj['status'] != CharacterPersistentClass.STATUS_SET_PICTURE:
                response_messages.append(TextMessage(
                    to=message.from_user,
                    chat_id=message.chat_id,
                    body="Sorry {}, mit diesem Bild kann ich leider nichts anfangen.".format(user.first_name),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                ))

            else:
                success = self.character_persistent_class.set_char_pic(status_obj['data']['user_id'], message.from_user, message.pic_url, status_obj['data']['char_id'])
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

        self.character_persistent_class.update_user_command_status(message.from_user, user_command_status, user_command_status_data)
        self.character_persistent_class.commit()
        return response_messages


    @staticmethod
    def generate_text_response(command, user_id, char_id, message, force_username=False):
        return TextResponse(MessageController.generate_text(command, user_id, char_id, message, force_username=force_username))

    @staticmethod
    def generate_text(command, user_id, char_id, message, force_username=False):
        show_user = message.from_user != user_id or force_username is True
        show_char_id = char_id is not None and char_id > CharacterPersistentClass.get_min_char_id()

        if show_user and show_char_id:
            return "{} @{} {}".format(command, user_id, char_id)
        if show_user:
            return "{} @{}".format(command, user_id)
        if show_char_id:
            return "{} {}".format(command, char_id)
        return command

    @staticmethod
    def check_auth(persistent_class, message):
        if persistent_class.is_auth_user(message.from_user) is False:
            return TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body="Du bist nicht berechtigt diesen Befehl auszuführen. Bitte melde dich in der Gruppe #germanrpu und erfrage eine Berechtigung.",
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
            )
        return True

    @staticmethod
    def create_char_messages(character_persistent_class, selected_user, char_id, char_data, message, user_command_status, user_command_status_data):
        response_messages = []
        keyboard_responses = []

        max_char_id = character_persistent_class.get_max_char_id(selected_user)
        if char_id is None:
            char_id = CharacterPersistentClass.get_min_char_id()

        if max_char_id > CharacterPersistentClass.get_min_char_id():
            dyn_message_data = {}
            if char_id > CharacterPersistentClass.get_min_char_id():
                dyn_message_data['left'] = MessageController.generate_text("Anzeigen", selected_user, char_id - 1, message)
                keyboard_responses.append(TextResponse(u"\U00002B05\U0000FE0F"))
            if char_id < max_char_id:
                dyn_message_data['right'] = MessageController.generate_text("Anzeigen", selected_user, char_id + 1, message)
                keyboard_responses.append(TextResponse(u"\U000027A1\U0000FE0F"))
            if dyn_message_data != {}:
                user_command_status = CharacterPersistentClass.STATUS_DYN_MESSAGES
                user_command_status_data = dyn_message_data

        if selected_user == message.from_user:
            keyboard_responses.append(MessageController.generate_text_response("Bild-setzen", selected_user, char_id, message))

        keyboard_responses.append(TextResponse("Liste"))

        pic_url = character_persistent_class.get_char_pic_url(selected_user, char_id)

        if pic_url is not None:
            response_messages.append(PictureMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                pic_url=pic_url,
                #keyboards=[SuggestedResponseKeyboard(responses=keyboard_responses)]
            ))

        body = "{}\n\n--- erstellt von @{} am {}".format(char_data['text'], char_data['creator_id'],
                                                         datetime.datetime.fromtimestamp(char_data['created']).strftime('%Y-%m-%d %H:%M:%S'))
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

    def get_max_char_id(self, user_id):
        chars = self.get_all_user_chars(user_id)
        max_char_id = self.get_min_char_id()-1
        for char_data in chars:
            max_char_id = max(max_char_id, char_data['char_id'])
        return max_char_id

    def add_char(self, user_id, creator_id, text, char_name=None):
        self.connect_database()

        max_char_id = self.get_max_char_id(user_id)
        data = (user_id, max_char_id+1, text, creator_id, int(time.time()) )
        self.cursor.execute((
            "INSERT INTO characters "
            "(user_id, char_id, text, creator_id, created) "
            "VALUES (?, ?, ?, ?, ?)"
        ), data)
        return max_char_id+1

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

    def get_char(self, user_id, char_id=None):
        self.connect_database()

        if char_id is None:
            char_id = self.get_min_char_id()

        self.cursor.execute((
            "SELECT id, char_id, char_name, text, creator_id, created "
            "FROM  characters "
            "WHERE user_id LIKE ? AND char_id=? AND deleted IS NULL "
            "ORDER BY created DESC "
            "LIMIT 1"
        ), [user_id, char_id])

        return self.cursor.fetchone()

    def get_char_pic_url(self, user_id, char_id):
        self.connect_database()

        if char_id is None:
            char_id = self.get_min_char_id()

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
            "SELECT id, char_id, char_name, text, creator_id, MAX(created) AS created "
            "FROM characters "
            "WHERE user_id LIKE ? AND deleted IS NULL "
            "GROUP BY char_id"
        ), [user_id])
        chars = self.cursor.fetchall()
        return chars

    def get_all_users_with_chars(self):
        self.connect_database()

        self.cursor.execute((
            "SELECT id, user_id, MAX(char_id) AS chars_cnt "
            "FROM characters "
            "WHERE deleted IS NULL "
            "GROUP BY user_id "
            "ORDER BY created DESC"
        ))
        return self.cursor.fetchall()

    def auth_user(self, user_id, creator_id):
        if self.is_auth_user(user_id) or \
                creator_id not in [x.strip() for x in default_config.get("Admins", "admin1").split(',')] and (self.is_unauth_user(user_id) or self.is_auth_user(creator_id) is False):
            return False

        self.connect_database()

        data = (user_id, creator_id, int(time.time()))
        self.cursor.execute((
            "INSERT INTO users "
            "(user_id, creator_id, created) "
            "VALUES (?, ?, ?)"
        ), data)
        return True

    def unauth_user(self, user_id, deletor_id):
        if deletor_id not in [x.strip() for x in default_config.get("Admins", "admin1").split(',')]:
            return False

        self.connect_database()

        data = (deletor_id, int(time.time()), user_id)
        self.cursor.execute((
            "UPDATE users "
            "SET deletor_id=?, deleted=? "
            "WHERE user_id LIKE ?"
        ), data)
        return True

    def is_auth_user(self, user_id):
        if user_id in [x.strip() for x in default_config.get("Admins", "admin1").split(',')]:
            return True

        self.connect_database()
        self.cursor.execute((
            "SELECT id "
            "FROM  users "
            "WHERE user_id LIKE ? AND deleted IS NULL "
            "LIMIT 1"
        ), [user_id])
        return self.cursor.fetchone() is not None

    def is_unauth_user(self, user_id):
        #if user_id in [x.strip() for x in default_config.get("Admins", "admin1").split(',')]:
        #    return False

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
            "SELECT id, char_id, char_name, text, creator_id, MAX(created) AS created "
            "FROM characters "
            "WHERE user_id=? AND deleted IS NULL AND text LIKE ? "
            "GROUP BY char_id"
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
            "SELECT id, user_id, char_id, char_name, text, creator_id, MAX(created) AS created "
            "FROM characters "
            "WHERE deleted IS NULL AND text LIKE ? "
            "GROUP BY char_id"
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


def create_database(database_path):
    connection = sqlite3.connect(database_path)
    cursor = connection.cursor()
    cursor.execute((
        "CREATE TABLE characters ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    user_id TEXT NOT NULL,"
        "    char_id INTEGER DEFAULT 1,"
        "    text TEXT NOT NULL,"
        "    creator_id TEXT NOT NULL,"
        "    created INTEGER NOT NULL,"
        "    deletor_id TEXT,"
        "    deleted INTEGER"
        "); "
    ))
    cursor.execute((
        "CREATE TABLE character_pictures ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    user_id TEXT NOT NULL,"
        "    char_id INTEGER DEFAULT 1,"
        "    picture_filename TEXT NOT NULL,"
        "    creator_id TEXT NOT NULL,"
        "    created INTEGER NOT NULL,"
        "    deletor_id TEXT,"
        "    deleted INTEGER"
        "); "
    ))
    cursor.execute((
        "CREATE TABLE users ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    user_id TEXT NOT NULL,"
        "    creator_id TEXT NOT NULL,"
        "    created INTEGER NOT NULL,"
        "    deletor_id TEXT,"
        "    deleted INTEGER"
        ")"
    ))
    cursor.execute((
        "CREATE TABLE user_command_status ( "
        "    id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "    user_id TEXT NOT NULL, "
        "    status TEXT NOT NULL, "
        "    updated INTEGER NOT NULL "
        ")"
    ))

    connection.commit()
    connection.close()
    print ("Datenbank {} angelegt".format(os.path.basename(database_path)))


if __name__ == "__main__":
    """ Main program """

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', '-c', type=str, required=True, dest='config', help='The config-File')
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config)
    default_config = config['DEFAULT'] # type: SectionProxy

    database_path = default_config.get("DatabasePath", "{home}/database.db").format(home=str(Path.home()))
    if not os.path.exists(database_path):
        print("Datenbank {} nicht vorhanden - Datenbank wird anglegt.".format(os.path.basename(database_path)))
        create_database(database_path)

    bot_username = default_config.get("BotUsername", "botname")
    kik = KikApi(bot_username, default_config.get("BotAuthCode", "abcdef01-2345-6789-abcd-ef0123456789"))
    # For simplicity, we're going to set_configuration on startup. However, this really only needs to happen once
    # or if the configuration changes. In a production setting, you would only issue this call if you need to change
    # the configuration, and not every time the bot starts.
    kik.set_configuration(Configuration(webhook="{}:{}/incoming".format(default_config.get("RemoteHostIP", "www.example.com"), default_config.get("RemotePort", "8080"))))
    app = KikBot(kik, __name__)
    app.run(threaded=True, port=int(default_config.get("LocalPort", 8080)), host=default_config.get("LocalIP", "0.0.0.0"), debug=False)
