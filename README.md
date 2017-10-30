# Kik Python Bot Example
![](https://travis-ci.org/kikinteractive/kik-bot-python-example.svg?branch=master)
[![Coverage Status](https://coveralls.io/repos/github/kikinteractive/kik-bot-python-example/badge.svg)](https://coveralls.io/github/kikinteractive/kik-bot-python-example)
[![Hex.pm](https://img.shields.io/hexpm/l/plug.svg)]()


An example bot implemented in Python. 

It's designed to greet the user, send a suggested response and replies to them with their profile picture.

Remember to replace the `BOT_USERNAME_HERE`, `BOT_API_KEY_HERE` and `WEBHOOK_HERE` fields with your own.

See https://github.com/kikinteractive/kik-python for Kik's Python SDK documentation.

#Table Of Contents

* [Kik Python Bot Example](#kik-python-bot-example)
* [Table of Contents](#table-of-contents)
* [Setting up](#setting-up)
    * [Setting up Python](#setting-up-python)
    * [Get the Sample Bot](#get-the-sample-bot)
    * [Install Dependencies](#install-dependencies)
    * [Configure Your Server](#configuring-your-server)
    * [Configure Your Bot](#configure-your-bot)
* [Launch Your Bot](#launch-your-bot)
* [How Bots Work](#how-bots-work)
* [Talking to the Bot](#talking-to-the-bot)
* [Contributing](#contributing)
* [License](#license)


# Setting Up

#### Getting ready


##### Create Your Bot

Go over to [dev.kik.com](https://dev.kik.com/#/home). 

![Scan The Kik Code][scan_the_code]

...and in Kik, pull down on your conversations list to scan the code.

*(the above scan code is only an example, you must go to the [link above](https://dev.kik.com/#/home) for a valid scan code)*

![Scan Tutorial][scan_tutorial]

Pulling down will allow Kik to scan the code and introduce you to Botsworth, the bot maker bot. Follow the prompts to configure your bot.

Botsworth will ask you to give your bot a name which, is the first step. Choose wisely! Your bot should be cleverly and descriptively named - it should provide relatively clear indication as to the function of your bot. 
*Hint: Avoid numbers and special characters in your bot's name.*

Once you've chosen your bot's name, Botsworth will ask you to confirm, and will then log you into the Kik Bot Dashboard. 
You will be prompted to agree to the [Kik API Terms of Use](https://engine.kik.com/#/terms). 

Next step: Setting up your development environment!

## Setting up Python 

Make sure you're running at least Python 2.7 or Python 3. We'll be using Python 2.7 today on Linux / MacOS X using virtualenv

#### Get the sample bot

Clone this repository:

```bash
$ git clone https://github.com/kikinteractive/kik-bot-python-example.git
Cloning into 'kik-bot-python-example'...
remote: Counting objects: 88, done.
remote: Total 88 (delta 0), reused 0 (delta 0), pack-reused 88
Receiving objects: 100% (88/88), 18.40 KiB | 0 bytes/s, done.
Resolving deltas: 100% (30/30), done.
```

The example bot is developed as one file (very simply) using Flask. cd to the directory that was created when the repository was cloned.

```bash
$ cd kik-bot-python-example
```

#### Setup your [Virtualenv](https://virtualenv.pypa.io/en/stable/) environment. 
[Virtualenv](https://virtualenv.pypa.io/en/stable/) is a popular tool to create isolated Python environments. It is used by many python developers to create an environment that has its own installation directories, that does not share libraries with other environments.

```bash
$ virtualenv env
New python executable in ./kik-bot-python-example-internal/env/bin/python2.7
Also creating executable in ./kik-bot-python-example-internal/env/bin/python
Installing setuptools, pip, wheel...done.
$ source env/bin/activate
```

#### Install dependencies 

Install the python dependencies: 

```bash
(env) $ pip install -r requirements.dev.txt
ollecting flake8==2.5.4 (from -r requirements.dev.txt (line 1))
  Using cached flake8-2.5.4-py2.py3-none-any.whl
Collecting mock==2.0.0 (from -r requirements.dev.txt (line 2))
  Using cached mock-2.0.0-py2.py3-none-any.whl
Collecting kik==1.2.0 (from -r requirements.dev.txt (line 3))
Collecting Flask==0.11 (from -r requirements.dev.txt (line 4))
  Using cached Flask-0.11-py2.py3-none-any.whl
Collecting pyyaml (from -r requirements.dev.txt (line 5))
Collecting pep8 (from -r requirements.dev.txt (line 6))
  Using cached pep8-1.7.0-py2.py3-none-any.whl
Collecting nose (from -r requirements.dev.txt (line 7))
  Using cached nose-1.3.7-py2-none-any.whl
Collecting nose-cov (from -r requirements.dev.txt (line 8))
Collecting mccabe<0.5,>=0.2.1 (from flake8==2.5.4->-r requirements.dev.txt (line 1))
  Using cached mccabe-0.4.0-py2.py3-none-any.whl
Collecting pyflakes<1.1,>=0.8.1 (from flake8==2.5.4->-r requirements.dev.txt (line 1))
  Using cached pyflakes-1.0.0-py2.py3-none-any.whl
Collecting funcsigs>=1; python_version < "3.3" (from mock==2.0.0->-r requirements.dev.txt (line 2))
  Using cached funcsigs-1.0.2-py2.py3-none-any.whl
Collecting pbr>=0.11 (from mock==2.0.0->-r requirements.dev.txt (line 2))
  Using cached pbr-1.10.0-py2.py3-none-any.whl
Collecting six>=1.9 (from mock==2.0.0->-r requirements.dev.txt (line 2))
  Using cached six-1.10.0-py2.py3-none-any.whl
Collecting requests>=2.3.0 (from kik==1.2.0->-r requirements.dev.txt (line 3))
  Using cached requests-2.12.4-py2.py3-none-any.whl
Collecting click>=2.0 (from Flask==0.11->-r requirements.dev.txt (line 4))
  Using cached click-6.7-py2.py3-none-any.whl
Collecting Werkzeug>=0.7 (from Flask==0.11->-r requirements.dev.txt (line 4))
  Using cached Werkzeug-0.11.15-py2.py3-none-any.whl
Collecting Jinja2>=2.4 (from Flask==0.11->-r requirements.dev.txt (line 4))
  Using cached Jinja2-2.9.4-py2.py3-none-any.whl
Collecting itsdangerous>=0.21 (from Flask==0.11->-r requirements.dev.txt (line 4))
Collecting cov-core>=1.6 (from nose-cov->-r requirements.dev.txt (line 8))
Collecting MarkupSafe>=0.23 (from Jinja2>=2.4->Flask==0.11->-r requirements.dev.txt (line 4))
Collecting coverage>=3.6 (from cov-core>=1.6->nose-cov->-r requirements.dev.txt (line 8))
  Using cached coverage-4.3.1-cp27-cp27m-macosx_10_10_x86_64.whl
Installing collected packages: pep8, mccabe, pyflakes, flake8, funcsigs, pbr, six, mock, requests, kik, click, Werkzeug, MarkupSafe, Jinja2, itsdangerous, Flask, pyyaml, nose, coverage, cov-core, nose-cov
Successfully installed Flask-0.11 Jinja2-2.9.4 MarkupSafe-0.23 Werkzeug-0.11.15 click-6.7 cov-core-1.15.0 coverage-4.3.1 flake8-2.5.4 funcsigs-1.0.2 itsdangerous-0.24 kik-1.2.0 mccabe-0.4.0 mock-2.0.0 nose-1.3.7 nose-cov-1.6 pbr-1.10.0 pep8-1.7.0 pyflakes-1.0.0 pyyaml-3.12 requests-2.12.4 six-1.10.0```
```
#### Validate the installation

Validate the installation by running the unit tests. It should produce no errors. 

```
(env) $ nosetests
...............
----------------------------------------------------------------------
Ran 15 tests in 0.176s

OK
```

#### How Bots Work

Kik bots talk to the Kik infrastructure via HTTP requests: When sending a message, you send a request to us, and for messages to be received by your bot, 
Kik will make requests to your endpoint. In other words, Kik must be able to call your URL on your web server.

![Chat To Bot Flow Diagram][chat_bot_flow]


#### Configuring Your Server


For our bot to work, we need to have an address that's accessible from the internet.  Many production Kik bots run in cloud based services such as [Heroku](https://www.heroku.com), [Google App Engine](https://cloud.google.com/appengine/) or [Amazon Web Services](https://aws.amazon.com) - or in their own data center infrastructure. 

However, for development purposes you can use [ngrok](https://ngrok.com) to provide access to your bot running in your local network. Ngrok is easy to setup and use, and has [excellent documentation](https://ngrok.com/docs#expose). 

[Ngrok](https://ngrok.com)  is a handy tool and service that allows you tunnel requests from the wide open Internet to your local machine when it's behind a NAT or firewall. It's commonly used to develop web services and webhooks. 

If you're using [ngrok](https://ngrok.com), launch it now in a new terminal window:

```
$ ngrok http 8080
```

When it launches, you will see a screen similar to the following:

```
ngrok by @inconshreveable                                                                                                                                                                 (Ctrl+C to quit)
                                                                                                                                                                                                          
Session Status                online                                                                                                                                                                      
Account                       A Bot Developer (Plan: Free)                                                                                                                                                 
Version                       2.1.18                                                                                                                                                                      
Region                        United States (us)                                                                                                                                                          
Web Interface                 http://127.0.0.1:4040                                                                                                                                                       
Forwarding                    http://ABCDEFG123.ngrok.io -> localhost:8080                                                                                                                                  
Forwarding                    https://ABCDEFG123.ngrok.io -> localhost:8080                                                                                                                                 
                                                                                                                                                                                                          
Connections                   ttl     opn     rt1     rt5     p50     p90                                                                                                                                 
                              0       0       0.00    0.00    0.00    0.00  
```

Note the "Forwarding" address (https://ABCDEFG123.ngrok.io), as this will become part of your 'webhook' address.

#### Configuring Your Bot

To get the bot running, you're going to need your bot's username, and the API key. This is all available from [dev.kik.com](https://dev.kik.com/#/engine). It will be similar to the following screenshot:

![Bot Configuration Panel][bot_dashboard]

Here you can set the display name and "profile picture" for your bot. You'll need to copy/paste your API key into the bot's source code.  

Change:
```python
kik = KikApi('BOT_USERNAME_HERE', 'BOT_API_KEY_HERE')
```
so that your bot's username and your API key are passed to Kik API's constructor. For example, if we named our bot `ademobot`, and according the bot configuration panel our API key is 
`5a888dcb-4c6e-1973-b15t-308e1854f0ba`, then we would change the above line to:

```python
kik = KikApi('ademobot', '5a888dcb-4c6e-1973-b15t-308e1854f0ba')
```

Next, we'll need to set the webhook to the URL of your bot's "incoming messages" route on your web server. This is where Kik will send all the messages that users send to your bot. In the example code, the route for incoming messages is `/incoming`

Locate the following line in bot.py:

```python
kik.set_configuration(Configuration(webhook='WEBHOOK_HERE'))
```

Kik will send messages to this path upon receipt. So, if your web address is https://www.example.com then you'll set your webhook to https://www.example.com/incoming, as shown below. 

```python
kik.set_configuration(Configuration(webhook='https://www.example.com/incoming'))
```

If you're using [ngrok](https://ngrok.com) as shown above, you would set the webhook as follows:

```python
kik.set_configuration(Configuration(webhook='https://ABCDEFG123.ngrok.io/incoming'))
```

#### Launch Your Bot 

Start the bot by running the file as shown below:

```bash
$ python ./bot.py
 * Running on http://127.0.0.1:8080/ (Press CTRL+C to quit)
 * Restarting with stat
 * Debugger is active!
 * Debugger pin code: 300-736-125
```

##Talking to the bot

With your bot up and running, you'll be able to chat with it in Kik. It should already appear in your message list. Select it to start chatting:

![Start Chatting][start_chatting]

New users can click on the magnifying glass in their messages list to search for your bot. Once found, they can click on "Start Chatting" to subscribe to your bot and start interacting!
![Talk to your Bot][talk_to_the_bot]


#### 

Contributing
------------

If you're looking to contribute to this repository, check out the [Contributing Guide] (https://github.com/kikinteractive/kik-python-bot-example/blob/master/CONTRIBUTING.md).

This project adheres to the [Contributor Covenant Code of Conduct] (https://github.com/kikinteractive/kik-python-bot-example/blob/master/CODE_OF_CONDUCT.md).
By participating, you are expected to uphold this code. Please report unacceptable behavior to bots@kik.com.

License
-------

This bot is released under the terms of the Apache 2.0 license. 

```
(c) 2016 Kik Interactive Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
either express or implied. See the License for the specific
language governing permissions and limitations under the License.
```

See [LICENSE.md](https://github.com/kikinteractive/kik-node-bot-example/blob/master/LICENSE.md) for more information.


[scan_the_code]: images/scan_kik_code.png
[scan_tutorial]: images/scan-tutorial.gif
[bot_dashboard]: images/botdashboard.png
[chat_bot_flow]: images/chat_bot_flow.png
[start_chatting]: images/start-chatting.png
[talk_to_the_bot]: images/talktothebot.gif

