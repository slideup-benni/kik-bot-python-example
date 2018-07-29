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
import hashlib
import json
import os
import time
import traceback

from configparser import SectionProxy
from pathlib import Path
from flask import Flask, request, Response, send_from_directory
from kik import User, KikApi, Configuration
from kik.messages import messages_from_json, TextMessage, SuggestedResponseKeyboard, TextResponse, Message

from modules.character_persistent_class import CharacterPersistentClass
from modules.kik_api_cache import KikApiCache
from modules.message_controller import MessageController

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
    message_controller = MessageController(bot_username, config_file)

    for message in messages:
        try:
            user = kik_api.get_user(message.from_user) # type: User
            response_messages += message_controller.process_message(message, user)
        except:
            error_id = hashlib.md5((str(int(time.time())) + message.from_user).encode('utf-8')).hexdigest()
            print("Message-Error: {} ({})\n---\nTrace: {}\n---\nReq: {}".format(error_id, bot_username, traceback.format_exc(), json.dumps(message.__dict__)))

            response_messages += [TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body="Leider ist ein Fehler aufgetreten. Bitte versuche es erneut.\n\n" +
                     "Sollte der Fehler weiterhin auftreten, mach bitte einen Screenshot und sprich @ismil1110 per PM an.\n\n" +
                     "Fehler-Informationen: {}".format(error_id),
                keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
            )]

        try:
            kik_api.send_messages(response_messages)
        except:
            error_id = hashlib.md5((str(int(time.time()))).encode('utf-8')).hexdigest()
            print("Kik-Send-Error: {} ({})\n---\nTrace: {}\n---\nReq: {}".format(error_id, bot_username, traceback.format_exc(),
                                                                                 json.dumps([m.__dict__ for m in messages])))
            error_response_messages = []
            for resp_message in response_messages: # type: Message
                error_response_messages.append(TextMessage(
                    to=resp_message.to,
                    chat_id=resp_message.chat_id,
                    body="Leider ist ein Fehler aufgetreten. Bitte versuche es erneut.\n\n" +
                     "Sollte der Fehler weiterhin auftreten, mach bitte einen Screenshot und sprich @ismil1110 per PM an.\n\n" +
                     "Fehler-Informationen: {}".format(error_id),
                    keyboards=[SuggestedResponseKeyboard(responses=[TextResponse("Hilfe")])]
                ))

            kik_api.send_messages(error_response_messages)

    return Response(status=200)


def get_kik_api_cache():
    return kik_api_cache


config_file = os.environ.get('RPCHARBOT_CONF', 'config.ini')
print("Using conf {}.".format(config_file))

config = configparser.ConfigParser()
config.read(config_file)
default_config = config['DEFAULT'] # type: SectionProxy
bot_username = default_config.get("BotUsername", "botname")
print("Bot Username: {}".format(bot_username))

# prepare database
db_class = CharacterPersistentClass(default_config)
del db_class

kik_api = KikApi(bot_username, default_config.get("BotAuthCode", "abcdef01-2345-6789-abcd-ef0123456789"))
kik_api_cache = KikApiCache(kik_api)
# For simplicity, we're going to set_configuration on startup. However, this really only needs to happen once
# or if the configuration changes. In a production setting, you would only issue this call if you need to change
# the configuration, and not every time the bot starts.
kik_api.set_configuration(Configuration(webhook="{}:{}/incoming".format(default_config.get("RemoteHostIP", "www.example.com"), default_config.get("RemotePort", "8080"))))
