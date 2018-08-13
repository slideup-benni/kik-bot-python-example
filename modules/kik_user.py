import time
from random import randrange

from kik import User as KikUser, KikApi, KikError


class User:
    pass


class LazyKikUser(User):
    kik_api = None  # type: KikApi
    cached_users = dict()
    accepted_attrs = [
            "first_name",
            "last_name",
            "profile_pic_url",
            "profile_pic_last_modified",
            "timezone",
            "name",
            "name_or_id",
            "name_and_id",
            "id",
            "id_force_anon"
        ]

    @staticmethod
    def init(user_id):
        if user_id not in LazyKikUser.cached_users:
            LazyKikUser.cached_users[user_id] = LazyKikUser(user_id)

        return LazyKikUser.cached_users[user_id]

    def __init__(self, user_id):
        self.user_id = user_id
        self.last_request = 0
        self.user_data = None  # type: KikUser

    def populate_user_data(self):
        if self.kik_api is None:
            raise BaseException("kik_api not set!")

        if int(time.time()) > self.last_request + 6 * 60 * 60:
            try:
                print("Get Kik User " + self.user_id)
                self.user_data = LazyKikUser.kik_api.get_user(self.user_id)
            except KikError:
                self.user_data = None
            self.last_request = int(time.time())

    def get_user_id_repr(self, aliased_user_name="anonuser", format="@{}"):
        if len(self.user_id) == 52 and aliased_user_name is not None and aliased_user_name is not "":
            return format.format("~" + aliased_user_name + "~")
        elif len(self.user_id) == 52:
            return ""
        return format.format(self.user_id)

    def __getitem__(self, item):
        return self.__getattr__(item)

    def __getattr__(self, item):
        if item not in LazyKikUser.accepted_attrs:
            return None

        self.populate_user_data()

        if item == "name" and self.user_data is not None:
            return self.user_data.first_name + " " + self.user_data.last_name

        if item == "name_or_id":
            if self.user_data is not None:
                return self.user_data.first_name + " " + self.user_data.last_name
            else:
                return self.get_user_id_repr()

        if item == "name_and_id":
            if self.user_data is not None:
                return self.user_data.first_name + " " + self.user_data.last_name + self.get_user_id_repr(format=" (@{})", aliased_user_name="")
            else:
                return self.get_user_id_repr()

        if item == "id":
            return self.get_user_id_repr()

        if item == "id_force_anon":
            return self.get_user_id_repr(aliased_user_name=self.user_id)

        if self.user_data is not None and item in self.user_data.__dict__:
            return self.user_data.__dict__[item]

        return None


class LazyRandomKikUser:

    accepted_attrs = ["rand", "rand_wo_sender"]

    def __init__(self, user_ids, sender_user_id, alt_user):
        self.user_ids = user_ids
        self.sender_user_id = sender_user_id
        self.alt_user = alt_user

    def __getitem__(self, item):
        return self.__getattr__(item)

    def __getattr__(self, item):
        if item not in LazyRandomKikUser.accepted_attrs:
            return LazyKikUser.init(self.alt_user)

        user_ids = self.user_ids
        if item == "rand_wo_sender":
            user_ids = list(filter(lambda x: x != self.sender_user_id, user_ids))

        if len(user_ids) == 0:
            return LazyKikUser.init(self.alt_user)

        random_index = randrange(0, len(self.user_ids))
        return LazyKikUser.init(self.user_ids[random_index])

