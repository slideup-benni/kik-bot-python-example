import time

from kik import KikError


class KikApiCache:

    _instance = None

    def __init__(self, kik_api):
        self.users = {}
        self.kik_api = kik_api
        KikApiCache._instances = self

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
            user_data = self.kik_api.get_user(user_id.lower())
        except KikError:
            user_data = None

        self.users[user_id.lower()] = {
            "data": user_data,
            "last-request": int(time.time())
        }

    @staticmethod
    def get_instance():
        return KikApiCache._instance
