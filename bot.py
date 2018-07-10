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
from configparser import SectionProxy
from pathlib import Path

from flask import Flask, request, Response
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

        for message in messages:
            user = self.kik_api.get_user(message.from_user)
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
                user = self.kik_api.get_user(message.from_user)
                message_body = message.body.lower()

                if message_body == "":
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body="Hi {}, ich bin der Character-Bot der Gruppe #germanrpu\n".format(user.first_name) +
                             "Für weitere Informationen tippe auf Antworten und dann auf Hilfe.",
                        keyboards=[SuggestedResponseKeyboard(responses=[
                            TextResponse("Hilfe"),
                            TextResponse("Regeln"),
                            TextResponse("Vorlage")
                        ])]
                    ))
                    self.kik_api.send_messages(response_messages)
                    continue

                message_command = message_body.split(None,1)[0]

                #
                # Befehl hinzufügen
                #
                if message_command in ["hinzufügen", "add"]:
                    if len(message_body.split(None,2)) == 3 and message_body.split(None,2)[1][0] == "@" and message_body.split(None,2)[2].strip() != "":
                        char_id = CharacterPersistentClass().add_char(message_body.split(None, 2)[1][1:].strip(), message.from_user, message.body.split(None, 2)[2].strip())
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Alles klar! Der Charakter für {} wurde hinzugefügt.".format(message_body.split(None,2)[1]),
                            keyboards=[SuggestedResponseKeyboard(responses=[
                                TextResponse("Anzeigen @{} {}".format(message_body.split(None,2)[1][1:], char_id)),
                                TextResponse("Löschen @{} {}".format(message_body.split(None,2)[1][1:], char_id)),
                                TextResponse("Liste")
                            ])]
                        ))
                    elif len(message_body.split(None,1)) == 2 and message_body.split(None,1)[1][0] != "@":
                        char_id = CharacterPersistentClass().add_char(message.from_user, message.from_user, message.body.split(None, 1)[1].strip())
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Alles klar! Dein Charakter wurde hinzugefügt.",
                            keyboards=[SuggestedResponseKeyboard(responses=[
                                TextResponse("Anzeigen {}".format(char_id)),
                                TextResponse("Löschen @{} {}".format(message.from_user, char_id)),
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

                        CharacterPersistentClass().change_char(user_id, message.from_user, text, char_id)
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Alles klar! Der Charakter für {} wurde gespeichert.".format(message_body.split(None, 2)[1]),
                            keyboards=[SuggestedResponseKeyboard(responses=[
                                TextResponse("Anzeigen @{} {}".format(user_id, char_id)),
                                TextResponse("Letzte-Löschen @{}".format(user_id, char_id)),
                                TextResponse("Liste")
                            ])]
                        ))
                    elif len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1].isdigit() and message_body.split(None, 2)[2].strip() != "":

                        char_id = int(message_body.split(None, 2)[1])
                        text = message.body.split(None, 2)[2].strip()

                        CharacterPersistentClass().change_char(message.from_user, message.from_user, text, char_id)
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Alles klar! Dein Charakter wurde gespeichert.",
                            keyboards=[SuggestedResponseKeyboard(responses=[
                                TextResponse("Anzeigen {}".format(char_id)),
                                TextResponse("Letzte-Löschen @{} {}".format(message.from_user, char_id)),
                                TextResponse("Liste")
                            ])]
                        ))
                    elif len(message_body.split(None, 2)) == 3 and message_body.split(None, 2)[1][0] == "@" and message_body.split(None, 2)[2].strip() != "":
                        CharacterPersistentClass().change_char(message_body.split(None, 2)[1][1:].strip(), message.from_user, message.body.split(None, 2)[2].strip())
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Alles klar! Der Charakter für {} wurde gespeichert.".format(message_body.split(None, 2)[1]),
                            keyboards=[SuggestedResponseKeyboard(responses=[
                                TextResponse("Anzeigen @{}".format(message_body.split(None, 2)[1][1:])),
                                TextResponse("Letzte-Löschen @{}".format(message_body.split(None, 2)[1][1:])),
                                TextResponse("Liste")
                            ])]
                        ))
                    elif len(message_body.split(None, 1)) == 2 and message_body.split(None, 1)[1][0] != "@":
                        CharacterPersistentClass().change_char(message.from_user, message.from_user, message.body.split(None, 1)[1].strip())
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Alles klar! Dein Charakter wurde gespeichert.",
                            keyboards=[SuggestedResponseKeyboard(responses=[
                                TextResponse("Anzeigen"),
                                TextResponse("Letzte-Löschen @{}".format(message.from_user)),
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
                # Befehl Anzeigen
                #
                elif message_command in ["anzeigen", "show"]:
                    if len(message_body.split(None,2)) == 3 and message_body.split(None,2)[1][0] == "@" and message_body.split(None,2)[2].isdigit():
                        selected_user = message_body.split(None,2)[1][1:].strip()
                        char_id = int(message_body.split(None,2)[2])
                    elif len(message_body.split(None,1)) == 2 and message_body.split(None,1)[1].isdigit():
                        selected_user = message.from_user
                        char_id = int(message_body.split(None,1)[1])
                    elif len(message_body.split(None,1)) == 2 and message_body.split(None,1)[1][0] == "@":
                        selected_user = message_body.split(None,1)[1][1:].strip()
                        char_id = None
                    else:
                        selected_user = message.from_user
                        char_id = None

                    character_persistent_class = CharacterPersistentClass()
                    char_data = character_persistent_class.get_char(selected_user, char_id)

                    if char_data is None and char_id is not None:
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Keine Daten zum Charakter {} des Users @{} gefunden".format(char_id, selected_user),
                            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
                        ))
                    elif char_data is None:
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body="Keine Daten zum User @{} gefunden".format(selected_user),
                            keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
                        ))
                    else:
                        keyboard_responses = []

                        max_char_id = character_persistent_class.get_max_char_id(selected_user)
                        if max_char_id > CharacterPersistentClass.get_min_char_id():
                            if char_id is not None and char_id > 1:
                                keyboard_responses.append(TextResponse("Anzeigen @{} {}".format(selected_user, char_id-1)))
                            if char_id is None or char_id < max_char_id:
                                next_char_id = CharacterPersistentClass.get_min_char_id()+1 if char_id is None else char_id+1
                                keyboard_responses.append(TextResponse("Anzeigen @{} {}".format(selected_user, next_char_id)))

                        keyboard_responses.append(TextResponse("Liste"))

                        body = "{}\n\n--- erstellt von @{} am {}".format(char_data['text'], char_data['creator_id'], datetime.datetime.fromtimestamp(char_data['created']).strftime('%Y-%m-%d %H:%M:%S'))
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

                        #bodys = textwrap.wrap(body, 1500, replace_whitespace=False)
                        #for body in bodys:
                        response_messages.append(TextMessage(
                            to=message.from_user,
                            chat_id=message.chat_id,
                            body=new_body,
                            keyboards=[SuggestedResponseKeyboard(responses=keyboard_responses)]
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

                        if selected_user == message.from_user:
                            CharacterPersistentClass().remove_char(selected_user, message.from_user, char_id)

                            if char_id is not None:
                                body = "Du hast erfolgreich deinen Charakter {} gelöscht".format(char_id)
                            else:
                                body = "Du hast erfolgreich deinen Charakter gelöscht."

                            response_messages.append(TextMessage(
                                to=message.from_user,
                                chat_id=message.chat_id,
                                body=body,
                                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste")])]
                            ))

                        elif message.from_user in [x.strip() for x in default_config.get("Admins", "admin1").split(',')]:
                            CharacterPersistentClass().remove_char(selected_user, message.from_user, char_id)

                            if char_id is not None:
                                body = "Du hast erfolgreich den Charakter {} von @{} gelöscht.".format(char_id, selected_user)
                            else:
                                body = "Du hast erfolgreich den Charakter von @{} gelöscht.".format(selected_user)

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
                                body="Du kannst keine Charaktere von anderen Usern löschen.",
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
                            CharacterPersistentClass().remove_last_char_change(selected_user, message.from_user)

                            if char_id is not None:
                                body = "Du hast erfolgreich die letzte Änderung am Charakter {} gelöscht.".format(char_id)
                                show_resp = "Anzeigen {}".format(char_id)
                            else:
                                body = "Du hast erfolgreich die letzte Änderung gelöscht."
                                show_resp = "Anzeigen"

                            response_messages.append(TextMessage(
                                to=message.from_user,
                                chat_id=message.chat_id,
                                body=body,
                                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste"), TextResponse(show_resp)])]
                            ))

                        elif message.from_user in [x.strip() for x in default_config.get("Admins", "admin1").split(',')]:
                            CharacterPersistentClass().remove_last_char_change(selected_user, message.from_user)

                            if char_id is not None:
                                body = "Du hast erfolgreich die letzte Änderung des Charakters {} von @{} gelöscht.".format(char_id, selected_user)
                                show_resp = "Anzeigen @{} {}".format(selected_user, char_id)
                            else:
                                body = "Du hast erfolgreich die letzte Änderung des Charakters von @{} gelöscht.".format(selected_user)
                                show_resp = "Anzeigen @{}".format(selected_user)

                            response_messages.append(TextMessage(
                                to=message.from_user,
                                chat_id=message.chat_id,
                                body=body,
                                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Liste"), TextResponse(show_resp)])]
                            ))

                        else:
                            response_messages.append(TextMessage(
                                to=message.from_user,
                                chat_id=message.chat_id,
                                body="Du kannst keine Charaktere von anderen Usern löschen.",
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
                # Befehl Liste
                #
                elif message_command in ["liste", "list"]:
                    chars = CharacterPersistentClass().get_all_users_with_chars()
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
                elif message_body in ["hilfe", "hilfe!", "help"]:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body=("Folgende Befehle sind möglich:\n"
                            "Hilfe\n"
                            "Regeln\n"
                            "Vorlage\n"
                            "Hinzufügen (<username>) <text>\n"
                            "Ändern (<username>) (<char_id>) <text>\n"
                            "Anzeigen (<username>) (<char_id>)\n"
                            "Löschen <username> (<char_id>)\n"
                            "Letzte-Löschen <username> (<char_id>)\n"
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
                        body=("Folgende Kurz-Befehle sind möglich:\n"
                            "help\n"
                            "rules\n"
                            "template\n"
                            "add (<username>) <text>\n"
                            "change (<username>) (<char_id>) <text>\n"
                            "show (<username>) (<char_id>)\n"
                            "del <username> (<char_id>)\n"
                            "del-last <username> (<char_id>)\n"
                            "list\n"
                        ),
                        keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("rules"), TextResponse("Weitere-Beispiele"), TextResponse("Template")])]
                    ))
                elif message_body in ["weitere-beispiele", "more-examples"]:
                    response_messages.append(TextMessage(
                        to=message.from_user,
                        chat_id=message.chat_id,
                        body=("Weitere Beispiele\n"
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

            self.kik_api.send_messages(response_messages)

        return Response(status=200)


class CharacterPersistentClass:

    def __init__(self):
        self.connection = None
        self.cursor = None

    def __del__(self):
        if self.connection is not None:
            self.connection.commit()
            self.connection.close()

    def connect_database(self):
        self.connection = sqlite3.connect(database_path)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()

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
            "WHERE user_id=? AND char_id=?"
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
            "    WHERE user_id=? AND char_id=? AND deleted IS NULL "
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
            "WHERE user_id=? AND char_id=? AND deleted IS NULL "
            "ORDER BY created DESC "
            "LIMIT 1"
        ), [user_id, char_id])
        char_data = self.cursor.fetchone()
        return char_data

    def get_all_user_chars(self, user_id):
        self.connect_database()

        self.cursor.execute((
            "SELECT id, char_id, char_name, text, creator_id, MAX(created) AS created "
            "FROM characters "
            "WHERE user_id=? AND deleted IS NULL "
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


def create_database(database_path):
    connection = sqlite3.connect(database_path)
    cursor = connection.cursor()
    sql = (
        "CREATE TABLE characters ("
        "    id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "    user_id TEXT NOT NULL,"
        "    char_id INTEGER DEFAULT 1,"
        "    text TEXT NOT NULL,"
        "    creator_id TEXT NOT NULL,"
        "    created INTEGER NOT NULL,"
        "    deletor_id TEXT,"
        "    deleted INTEGER"
        ")"
    )
    cursor.execute(sql)
    connection.commit()
    connection.close()
    print ("Datenbank {} angelegt".format(os.path.basename(database_path)))


if __name__ == "__main__":
    """ Main program """

    config = configparser.ConfigParser()
    config.read(os.path.dirname(__file__)+'/config.ini')
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
    app.run(port=int(default_config.get("LocalPort", 8080)), host=default_config.get("LocalIP", "0.0.0.0"), debug=False)
