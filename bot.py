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
import importlib.util
import json
import os
import re
import time
import traceback

from configparser import SectionProxy
from datetime import datetime
from pathlib import Path
from typing import List

from flask import Flask, request, Response, send_from_directory, render_template
from flask_babel import Babel, force_locale
from flask_babel import gettext as _
from kik import KikApi, Configuration
from kik.messages import messages_from_json, TextMessage, SuggestedResponseKeyboard, Message, TextResponse
from werkzeug.exceptions import BadRequest

from modules.character_persistent_class import CharacterPersistentClass
from modules.kik_user import LazyKikUser
from modules.message_controller import MessageController
from wtforms import Form, StringField, TextAreaField, SelectField
from jinja2 import evalcontextfilter, Markup, escape

app = Flask(__name__, template_folder="templates")
babel = Babel(app)


@app.route("/picture/<path:path>", methods=["GET"])
def picture(path):
    picture_path = default_config.get("PicturePath", "{home}/pictures").format(home=str(Path.home()))
    return send_from_directory(picture_path, path)


@app.route("/module_static/<path:path>", methods=["GET"])
def module_static_file(path):
    if custom_module is not None and hasattr(custom_module, "ModuleMessageController"):
        message_controller = custom_module.ModuleMessageController(bot_username, config_file)
    else:
        message_controller = MessageController(bot_username, config_file)
    if message_controller.is_static_file(path):
        return message_controller.send_file(path)
    return BadRequest()


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

    if custom_module is not None and hasattr(custom_module, "ModuleMessageController"):
        message_controller = custom_module.ModuleMessageController(bot_username, config_file)
    else:
        message_controller = MessageController(bot_username, config_file)

    for message in messages:
        try:
            user = LazyKikUser.init(message.from_user) # type: LazyKikUser
            with force_locale(message_controller.get_config().get("BaseLanguage", "en")):
                response_messages += message_controller.process_message(message, user)
        except:
            error_id = hashlib.md5((str(int(time.time())) + message.from_user).encode('utf-8')).hexdigest()
            print("Message-Error: {error_id} ({bot_username})\n---\nTrace: {trace}\n---\nReq: {request}\n---\nResp: {response}".format(
                error_id=error_id,
                bot_username=bot_username,
                trace=traceback.format_exc(),
                request=json.dumps(message.__dict__, indent=4, sort_keys=True),
                response=json.dumps(response_messages, default=lambda o: getattr(o, '__dict__', str(o)), indent=4, sort_keys=True)
            ))

            if isinstance(message, TextMessage) and len(message.body) < 100:
                resp_keyboard = [MessageController.generate_text_response(message.body), MessageController.generate_text_response("Hilfe")]
            else:
                resp_keyboard = [MessageController.generate_text_response("Hilfe")]

            response_messages += [TextMessage(
                to=message.from_user,
                chat_id=message.chat_id,
                body=_("Leider ist ein Fehler aufgetreten. Bitte versuche es erneut.\n\n" +
                     "Sollte der Fehler weiterhin auftreten, mach bitte einen Screenshot und sprich @{admin_user} per PM an.\n\n" +
                     "Fehler-Informationen: {error_id}").format(
                    error_id=error_id,
                    admin_user=message_controller.get_config().get("Admins", "admin1").split(',')[0].strip()
                ),
                keyboards=[SuggestedResponseKeyboard(responses=resp_keyboard)]
            )]

        try:
            kik_api.send_messages(response_messages)
        except:
            error_id = hashlib.md5((str(int(time.time()))).encode('utf-8')).hexdigest()
            print("Kik-Send-Error: {error_id} ({bot_username})\n---\nTrace: {trace}\n---\nReq: {request}\n---\nResp: {response}".format(
                error_id=error_id,
                bot_username=bot_username,
                trace=traceback.format_exc(),
                request=json.dumps([m.__dict__ for m in messages], indent=4, sort_keys=True),
                response=json.dumps(response_messages, default=lambda o: getattr(o, '__dict__', str(o)), indent=4, sort_keys=True)
            ))
            error_response_messages = []
            for resp_message in response_messages: # type: Message
                error_response_messages.append(TextMessage(
                    to=resp_message.to,
                    chat_id=resp_message.chat_id,
                    body="Leider ist ein Fehler aufgetreten. Bitte versuche es erneut.\n\n"
                     "Sollte der Fehler weiterhin auftreten, mach bitte einen Screenshot und sprich @{admin_user} per PM an.\n\n"
                     "Fehler-Informationen: {error_id}".format(
                        error_id=error_id,
                        admin_user=message_controller.get_config().get("Admins", "admin1").split(',')[0].strip()
                    ),
                    keyboards=[SuggestedResponseKeyboard(responses=[MessageController.generate_text_response("Hilfe")])]
                ))

            kik_api.send_messages(error_response_messages)

    return Response(status=200)


_paragraph_re = re.compile(r'(?:\r\n|\r|\n){2,}')
@app.template_filter()
@evalcontextfilter
def nl2br(eval_ctx, value):
    result = u'\n\n'.join(u'<p>%s</p>' % p.replace('\n', '<br>\n') for p in _paragraph_re.split(escape(value)))
    result = re.sub('(?P<url>http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)', "<a href=\"\g<url>\">\g<url></a>", result)
    result = re.sub('@(?P<user_id>[a-zA-Z0-9_\.]+)', "<a href=\"#\" class=\"user_link\" data-user-id=\"\g<user_id>\">@\g<user_id></a>", result)
    result = re.sub('#(?P<group_id>[a-zA-Z_\.][a-zA-Z0-9_\.]+)', "<a href=\"#\" class=\"group_link\" data-group-id=\"\g<group_id>\">#\g<group_id></a>", result)
    if eval_ctx.autoescape:
        result = Markup(result)
    return result


@app.template_filter()
@evalcontextfilter
def json_recursive(eval_ctx, value):
    result = json.dumps(value, default=lambda o: getattr(o, '__dict__', str(o)), indent=4, sort_keys=True)
    if eval_ctx.autoescape:
        result = Markup(result)
    return result


class DebugMessageForm(Form):
    message_body = TextAreaField("Message Body")
    message_from_user = StringField("Username")
    message_type = SelectField("Type", choices=[
        ("direct_bot","direct_bot"),
        ("direct_other_user","direct_other_user"),
        ("private_group","private_group"),
        ("public_group","public_group")
    ])
    message_lang = SelectField("Language", choices=[
        ("default", "Default"),
        ("de", "Deutsch"),
        ("en", "English")
    ])


@app.route("/debug", methods=["GET", "POST"])
def debug():
    global kik_api

    if custom_module is not None and hasattr(custom_module, "ModuleMessageController"):
        message_controller = custom_module.ModuleMessageController(bot_username, config_file)
    else:
        message_controller = MessageController(bot_username, config_file)

    log_requests = message_controller.get_config().get("LogRequests", "False")
    if app.debug is False and log_requests is not True and str(log_requests).lower() != "true":
        return Response(status=403)

    form = DebugMessageForm(request.form)
    response_messages = list()  # type: List[TextMessage]
    keyboards = list()  # type: List[TextResponse]

    if request.method == 'POST' and form.validate():

        message = None
        message_body = re.sub("^@{bot_username}\s*".format(bot_username=bot_username), "", form.message_body.data.strip())

        if form.message_type.data == "direct_bot":
            message = TextMessage(
                to=None,
                id='2826c590-c590-46ef-a1ec-8205f6884cf0',
                chat_id='d3662c07b2a5c8623019328ea95525ed7d7cfa098bc25c637b67d33c7eed3e87',
                mention=None,
                participants=[form.message_from_user.data],
                from_user=form.message_from_user.data,
                delay=None,
                read_receipt_requested=True,
                timestamp=int(time.time()),
                metadata=None,
                keyboards=[],
                chat_type='direct',
                body=message_body,
                type_time=None
            )
        
        elif form.message_type.data == "direct_other_user":
            message = TextMessage(
                to=None,
                id='0126d9de-9180-4945-ad20-35694597d50d',
                chat_id='68c4dbb6315dfcd32376d576db09634789b99c0cbf2312873c3500f026c4c5cf',
                mention=bot_username,
                participants=[form.message_from_user.data, 'silverfys'],
                from_user=form.message_from_user.data,
                delay=None,
                read_receipt_requested=True,
                timestamp=int(time.time()),
                metadata=None,
                keyboards=[],
                chat_type='private',
                body=message_body,
                type_time=None
            )
        
        elif form.message_type.data == "private_group":
            message = TextMessage(
                to=None,
                id='ee056960-6577-4608-a9a4-57d803ee22e9',
                chat_id='3f38ad5b3b0246530f0d48ab4c6326d2594f498ad40613056607cace88922507',
                mention=bot_username,
                participants=['pandi1998','leon2872','zeloslito','hzuter','darkorpheus','_miss_marple_','flumbauer',form.message_from_user.data,'nekogirl0102','garfieldsan','ayaacord',
                                    'miku028','nanunene','silverfys','kitty_jule66','nanamishiina','_scirocco'],
                from_user=form.message_from_user.data,
                delay=None,
                read_receipt_requested=True,
                timestamp=int(time.time()),
                metadata=None,
                keyboards=[],
                chat_type='private',
                body=message_body,
                type_time=None
            )
        
        elif form.message_type.data == "public_group":
            message = TextMessage(
                to=None,
                id='b73f2566-4029-4022-9a6b-086a78564ec4',
                chat_id='22fffcd3e8dcf646354a9a20f722735f2d0f5a1df44a812e16367a1cc9a45b0a',
                mention=bot_username,
                participants=['tailpbrihdyd3w7qjq3ws6kdrydgnb64ieisaxwozpsr3kod5fla','kdmnsdbwpsqf566apivlqukodvc3r3e4yaq2lmkdscahd56pwgda',
                              '3flmfyzcihhmylntogxavfyrje2g5kvoisfzhyi465jyxxk2bi6a','bwitfk5fdktevcsv2fofkpi7om333rhrnoyfrgojz6dlwrwmit2q',
                              'wamuqu5sau4mrp7cl33x2yows2timw3yfe7gd277kmkyesnblwea','hk6hxmjzyqspcaa7aghqfkowtvqobcz4x4fqbitfoa4nqcn6cmjq',
                              'o7fdnas4p6ydk6bhe7ys6kjbootygaxcg4v7yctv4ll2ow442jdq','vrz7a6jb44uakt76zysbjeenwu2dqvyqifpozu25t2exfyziug3q',
                              '7akh5gvmmworgr3vcztcjkmnsd5c2k7jebgvcwkf6fyp5ecgou2q','6fjab2voell7q66rtjndywnfifwivptyfvfi23nvzj22rdhe3f7a',
                              'jjrimzmshyp4yem5btvfme3wksogiahcixv5c6gvqfx7ooutbhva','c5evdk2nscvxmx5fboptakbc6u5nwh32s4yg3r6ayrjdzrotn32q',
                              'tnq2luthewjwynr3zhi7p6d6p5ekfumen33nbfjezbhtjbuxzkpa','trtammagrcsw55orwbyr35wfmhlrd6zz2kkerxuhdi3pxqcnzeaq',
                              'e734c7avg3s2juza6pdnyhcvfumdbadi62sca4iz377tzfzo4ywq','gq47ratq6kjejfbv3beeztkw3z3eqkyi4dm3bowib7igcpf4pp4q',
                              'kladrhrnct2iya6hbrdfc5llqtqhj2iujus26dfwxisjjm24gmda','uredvnjoie5gns4fovdttvv2rgv6wzc7yozex2e2jnqho4xsca2q',
                              'vyzcfqb2qi7bejvntmufj2anjctet7q5e2u66gub6jhahm3mz2ka','qzgj3gwlfdlolftuujp53gac5k3ucbtcro6mi3qvi5t3zigw4rka',
                              'u2lf5osu6hfqo2jhex5kaux4dc66u2ybddvbbr4ru3qajib2lb4a','b7mciin2ul6r3uzi6dm3tsi462bnwvk6onkaoxaz7slz2heetqxa'],
                from_user='tnq2luthewjwynr3zhi7p6d6p5ekfumen33nbfjezbhtjbuxzkpa',
                delay=None,
                read_receipt_requested=True,
                timestamp=int(time.time()),
                metadata=None,
                keyboards=[],
                chat_type='public',
                body=message_body,
                type_time=None
            )

        if message is not None:

            user = LazyKikUser.init("ismil1110") # type: LazyKikUser
            lang = form.message_lang.data if form.message_lang.data != "default" else message_controller.get_config().get("BaseLanguage", "en")
            with force_locale(lang):
                response_messages = message_controller.process_message(message, user)
                print(json.dumps(response_messages, default=lambda o: getattr(o, '__dict__', str(o)), indent=4, sort_keys=True))

    if len(response_messages) > 0 and len(response_messages[len(response_messages)-1].keyboards) > 0:
        keyboards = response_messages[len(response_messages)-1].keyboards[0].responses

    return render_template(
        'debug.html',
        form=form,
        messages=response_messages,
        keyboards=keyboards,
        bot_username=message_controller.bot_username,
        config_file=os.path.basename(config_file),
        database_file=os.path.basename(message_controller.character_persistent_class.database_path)
    )

@babel.localeselector
def get_locale():
    return default_config.get("BaseLanguage", "en")


config_file = os.environ.get('RPCHARBOT_CONF', 'config.ini')
print("Using conf {}.".format(config_file))

config = configparser.ConfigParser()
config.read(config_file)
default_config = config['DEFAULT'] # type: SectionProxy
bot_username = default_config.get("BotUsername", "botname").strip()
print("[{bot_username}] Bot Username: {bot_username}".format(
    bot_username=bot_username
))

custom_module_name = default_config.get("CustomModule", "False")
custom_module = None
if custom_module_name is not False and str(custom_module_name).lower() != "false":
    custom_module_name = str(custom_module_name).strip()
    custom_spec = importlib.util.find_spec("custom_modules.{}".format(custom_module_name))
    if custom_spec is not None:
        custom_module = importlib.util.module_from_spec(custom_spec)
        custom_spec.loader.exec_module(custom_module)
        print("[{bot_username}] Loaded custom module: custom_modules.{custom_module}".format(
            custom_module=custom_module_name,
            bot_username=bot_username
        ))
    else:
        print("[{bot_username}] Could not load custom module: custom_modules.{custom_module} ... - ignoring".format(
            custom_module=custom_module_name,
            bot_username=bot_username
        ))

# prepare database
if custom_module is not None and hasattr(custom_module, "ModuleCharacterPersistentClass"):
    db_class = custom_module.ModuleCharacterPersistentClass(default_config)
else:
    db_class = CharacterPersistentClass(default_config)
del db_class

kik_api = KikApi(bot_username, default_config.get("BotAuthCode", "abcdef01-2345-6789-abcd-ef0123456789"))
LazyKikUser.kik_api = kik_api
# For simplicity, we're going to set_configuration on startup. However, this really only needs to happen once
# or if the configuration changes. In a production setting, you would only issue this call if you need to change
# the configuration, and not every time the bot starts.
kik_api.set_configuration(Configuration(webhook="{}:{}/incoming".format(default_config.get("RemoteHostIP", "www.example.com"), default_config.get("RemotePort", "8080"))))

print("[{bot_username}] Debug URL: {host}:{port}/debug".format(
    bot_username=bot_username,
    host=default_config.get("RemoteHostIP", "www.example.com"),
    port=default_config.get("RemotePort", "8080")
))
print("[{bot_username}] Started: {now:%d.%m.%Y %H:%M:%S}".format(
    bot_username=bot_username,
    now=datetime.now()
))