""" Unitests for Kik Example bot. Covers basic example bot functionality.

See https://github.com/kikinteractive/kik-python for Kik's Python
API documentation.

Apache 2.0 License

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

"""
import unittest
import mock
import bot
import json
from kik.messages import TextMessage, TextResponse, SuggestedResponseKeyboard, PictureMessage
from kik import User


class ExampleBotTests(unittest.TestCase):
    """ Example bot unit test class"""

    def setUp(self):
        """ Set up the tests"""
        testbot = bot.KikBot(mock.MagicMock(), 'testbot')
        testbot.config['TESTING'] = True
        self.app = testbot.test_client()
        self.testbot = testbot

    def tearDown(self):
        """ Teardown method. """
        pass

    @staticmethod
    def get_test_user():
        """ Gets a user for consumption by the test suite"""
        test_user = User("Davey", "Jones", profile_pic_url="http://example.com/me.png")
        return test_user

    @staticmethod
    def get_test_user_no_picture():
        """ Gets a user for consumption by the test suite"""
        test_user = User("Davey", "Jones")
        return test_user

    @staticmethod
    def get_picture_message_response():
        """ Gets a picture message for consumption by the test suite"""
        picture_message = PictureMessage(to="daveyjones",
                                         chat_id="0ee6d46753bfa6ac2f089149959363f3f59ae62b10cba89cc426490ce38ea92d",
                                         pic_url="http://example.com/me.png")
        return picture_message

    @staticmethod
    def get_text_message(message):
        """Gets a json formatted test message for consumption by the test suite"""

        data = {"messages": [{"chatId": "0ee6d46753bfa6ac2f089149959363f3f59ae62b10cba89cc426490ce38ea92d",
                              "id": "0115efde-e54b-43d5-873a-5fef7adc69fd",
                              "type": "text",
                              "from": "daveyjones",
                              "participants": ["daveyjones"],
                              "body": message,
                              "timestamp": 1439576628405,
                              "readReceiptRequested": True,
                              "mention": None
                              }]}

        return json.dumps(data)

    @staticmethod
    def get_picture_message():
        data = {"messages": [{"chatId": "0ee6d46753bfa6ac2f089149959363f3f59ae62b10cba89cc426490ce38ea92d",
                              "id": "0115efde-e54b-43d5-873a-5fef7adc69fd",
                              "type": "picture",
                              "from": "daveyjones",
                              "participants": ["daveyjones"],
                              "picUrl": "http://example.com/me.png",
                              "timestamp": 1439576628405,
                              "readReceiptRequested": True,
                              "mention": None
                              }]}

        return json.dumps(data)

    @staticmethod
    def get_start_chatting_message():
        """ Gets a json formatted test START CHATTING message"""

        data = """{"messages": [{
                    "chatId": "b3be3bc15dbe59931666c06290abd944aaa769bb2ecaaf859bfb65678880afab",
                    "type": "start-chatting",
                    "from": "daveyjones",
                    "participants": ["daveyjones"],
                    "id": "6d8d060c-3ae4-46fc-bb18-6e7ba3182c0f",
                    "timestamp": 1399303478832,
                    "readReceiptRequested": false,
                    "mention": null}]}"""
        return data

    def test_incoming_route(self):
        """Tests that the web framework is working properly"""
        data = self.get_text_message("Test")
        response = self.app.post('/incoming', data=data, content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_auth_failed(self):
        """Tests that the authentication logic gets called and 403s on failure"""
        self.testbot.kik_api.verify_signature = mock.MagicMock(return_value=False)
        data = self.get_text_message("Test")
        response = self.app.post('/incoming', data=data, content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_start_messaging(self):
        """Tests that the web framework properly handles a start-messenging event"""

        self.testbot.kik_api.get_user = mock.MagicMock(return_value=self.get_test_user())

        self.testbot.kik_api.verify_signature = mock.MagicMock(return_value=True)
        self.testbot.kik_api.send_messages = mock.MagicMock()
        data = self.get_start_chatting_message()
        response = self.app.post('/incoming', data=data, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        expected_result = TextMessage(to="daveyjones",
                                      chat_id="b3be3bc15dbe59931666c06290abd944aaa769bb2ecaaf859bfb65678880afab",
                                      body="Hey Davey, how are you?",
                                      keyboards=[SuggestedResponseKeyboard(
                                          responses=[TextResponse('Good'), TextResponse('Bad')])])

        self.testbot.kik_api.send_messages.assert_called_once()
        self.testbot.kik_api.send_messages.assert_called_once_with([expected_result])

    def test_unexpected_message_type(self):
        """Unexpected (non-text) message was received. """

        self.testbot.kik_api.get_user = mock.MagicMock(return_value=self.get_test_user())

        self.testbot.kik_api.verify_signature = mock.MagicMock(return_value=True)
        self.testbot.kik_api.send_messages = mock.MagicMock()
        response = self.app.post('/incoming', data=self.get_picture_message(), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        expected_results = [TextMessage(to="daveyjones",
                                        chat_id="0ee6d46753bfa6ac2f089149959363f3f59ae62b10cba89cc426490ce38ea92d",
                                        body="Sorry, I didn't quite understand that. How are you, Davey?",
                                        keyboards=[SuggestedResponseKeyboard(
                                            responses=[TextResponse('Good'), TextResponse('Bad')])])]

        self.testbot.kik_api.send_messages.assert_called_once()

        actual_results = self.testbot.kik_api.send_messages.call_args[0][0]
        self.assertEqual(actual_results, expected_results)

    def test_text_messaging_response_good(self):
        """The user's feeling good today"""

        self.testbot.kik_api.get_user = mock.MagicMock(return_value=self.get_test_user())

        self.testbot.kik_api.verify_signature = mock.MagicMock(return_value=True)
        self.testbot.kik_api.send_messages = mock.MagicMock()
        data = self.get_text_message("Good")
        response = self.app.post('/incoming', data=data, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        expected_results = [TextMessage(to="daveyjones",
                                        chat_id="0ee6d46753bfa6ac2f089149959363f3f59ae62b10cba89cc426490ce38ea92d",
                                        body="That's Great! :) Wanna see your profile pic?",
                                        keyboards=[SuggestedResponseKeyboard(responses=[
                                            TextResponse("Sure! I'd love to!"), TextResponse("No Thanks")])])]

        self.testbot.kik_api.send_messages.assert_called_once()
        self.testbot.kik_api.send_messages.assert_called_once_with(expected_results)

    def test_text_messaging_response_bad(self):
        """The user's feeling bad today."""

        self.testbot.kik_api.get_user = mock.MagicMock(return_value=self.get_test_user())

        self.testbot.kik_api.verify_signature = mock.MagicMock(return_value=True)
        self.testbot.kik_api.send_messages = mock.MagicMock()
        data = self.get_text_message("Bad")
        response = self.app.post('/incoming', data=data, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        expected_results = [TextMessage(to="daveyjones",
                                        chat_id="0ee6d46753bfa6ac2f089149959363f3f59ae62b10cba89cc426490ce38ea92d",
                                        body="Oh No! :( Wanna see your profile pic?",
                                        keyboards=[SuggestedResponseKeyboard(responses=[
                                            TextResponse("Yep! I Sure Do!"), TextResponse("No Thank You")])])]

        self.testbot.kik_api.send_messages.assert_called_once()
        self.testbot.kik_api.send_messages.assert_called_once_with(expected_results)

    def test_text_messaging_response_see_picture(self):
        """User chose to see their picture"""

        self.testbot.kik_api.get_user = mock.MagicMock(return_value=self.get_test_user())

        self.testbot.kik_api.verify_signature = mock.MagicMock(return_value=True)
        self.testbot.kik_api.send_messages = mock.MagicMock()
        data = self.get_text_message("Sure! I'd love to!")
        response = self.app.post('/incoming', data=data, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        expected_results = [self.get_picture_message_response(),
                            TextMessage(to="daveyjones",
                                        chat_id="0ee6d46753bfa6ac2f089149959363f3f59ae62b10cba89cc426490ce38ea92d",
                                        body="Here's your profile picture!")]

        self.testbot.kik_api.send_messages.assert_called_once()
        self.testbot.kik_api.send_messages.assert_called_once_with(expected_results)

    def test_text_messaging_response_see_no_picture(self):
        """User chose to see their picture, but they don't have one."""

        self.testbot.kik_api.get_user = mock.MagicMock(return_value=self.get_test_user_no_picture())

        self.testbot.kik_api.verify_signature = mock.MagicMock(return_value=True)
        self.testbot.kik_api.send_messages = mock.MagicMock()
        data = self.get_text_message("Sure! I'd love to!")
        response = self.app.post('/incoming', data=data, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        expected_results = [TextMessage(to="daveyjones",
                                        chat_id="0ee6d46753bfa6ac2f089149959363f3f59ae62b10cba89cc426490ce38ea92d",
                                        body="It does not look like you have a profile picture, you should set one")]

        self.testbot.kik_api.send_messages.assert_called_once()
        self.testbot.kik_api.send_messages.assert_called_once_with(expected_results)

    def test_text_messaging_response_no_see_picture(self):
        """user chose not to see their picture"""

        self.testbot.kik_api.get_user = mock.MagicMock(return_value=self.get_test_user_no_picture())

        self.testbot.kik_api.verify_signature = mock.MagicMock(return_value=True)
        self.testbot.kik_api.send_messages = mock.MagicMock()
        data = self.get_text_message("No Thank You")
        response = self.app.post('/incoming', data=data, content_type='application/json')
        self.assertEqual(response.status_code, 200)

        expected_results = [TextMessage(to="daveyjones",
                                        chat_id="0ee6d46753bfa6ac2f089149959363f3f59ae62b10cba89cc426490ce38ea92d",
                                        body="Ok, Davey. Chat with me again if you change your mind.")]

        self.testbot.kik_api.send_messages.assert_called_once()
        self.testbot.kik_api.send_messages.assert_called_once_with(expected_results)

    def test_response_hello(self):
        """Tests that the bot responds with a message, the picture and another message when texted."""

        self.testbot.kik_api.get_user = mock.MagicMock(return_value=self.get_test_user())

        self.testbot.kik_api.verify_signature = mock.MagicMock(return_value=True)
        self.testbot.kik_api.send_messages = mock.MagicMock()

        for message in ["Hi", "Hello", "Hi There", "Hello There"]:

            data = self.get_text_message(message)

            response = self.app.post('/incoming', data=data, content_type='application/json')
            self.assertEqual(response.status_code, 200)
            expected_results = [TextMessage(to="daveyjones",
                                            chat_id="0ee6d46753bfa6ac2f089149959363f3f59ae62b10cba89cc426490ce38ea92d",
                                            body="Hey Davey, how are you?",
                                            keyboards=[SuggestedResponseKeyboard(
                                                responses=[TextResponse('Good'), TextResponse('Bad')])])]

            self.testbot.kik_api.send_messages.assert_called_once()

            actual_results = self.testbot.kik_api.send_messages.call_args[0][0]
            self.assertEqual(actual_results, expected_results)

            self.testbot.kik_api.send_messages.reset_mock()

    def test_response_unexpected(self):
        """Tests that the bot responds with a message, the picture and another message when texted."""

        self.testbot.kik_api.get_user = mock.MagicMock(return_value=self.get_test_user())

        self.testbot.kik_api.verify_signature = mock.MagicMock(return_value=True)
        self.testbot.kik_api.send_messages = mock.MagicMock()
        data = self.get_text_message("omg r u real?")

        response = self.app.post('/incoming', data=data, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        expected_results = [TextMessage(to="daveyjones",
                                        chat_id="0ee6d46753bfa6ac2f089149959363f3f59ae62b10cba89cc426490ce38ea92d",
                                        body="Sorry Davey, I didn't quite understand that. How are you?",
                                        keyboards=[SuggestedResponseKeyboard(
                                            responses=[TextResponse('Good'), TextResponse('Bad')])])]

        self.testbot.kik_api.send_messages.assert_called_once()

        actual_results = self.testbot.kik_api.send_messages.call_args[0][0]
        self.assertEqual(actual_results, expected_results)

    def test_profile_pic_messages(self):
        """Test the profile pic helper method- should return a picture url"""
        actual_results = self.testbot.profile_pic_check_messages(self.get_test_user(), TextMessage())

        expected_results = [PictureMessage(pic_url="http://example.com/me.png"),
                            TextMessage(body="Here's your profile picture!")]

        self.assertEquals(actual_results, expected_results)

    def test_no_profile_pic_messages(self):
        """Test the profile pic helper method- no picture set, should return a test message"""
        test_user = User("Davey", "Jones")
        expected_results = [TextMessage(body="It does not look like you have a profile picture, you should set one")]
        actual_results = self.testbot.profile_pic_check_messages(test_user, TextMessage())

        self.assertAlmostEqual(actual_results, expected_results)


if __name__ == '__main__':
    unittest.main()
