import json
import time
from random import randrange

from kik import KikApi, KikError


class User:

    def __init__(self, user_db):
        self.user_db = dict(user_db)

    def __getitem__(self, item):
        return self.__getattr__(item)

    def __getattr__(self, item):
        if item in self.user_db:
            return self.user_db[item]
        return None

    def update_status(self, status, status_data=None):
        status_obj = {
            'status': status,
            'data': status_data
        }
        self.user_db["status"] = json.dumps(status_obj)

    def get_status_obj(self):
        if "status" in self.user_db:
            return json.loads(self.user_db["status"])
        return None

    def get_db_id(self):
        if "id" in self.user_db:
            return self.user_db["id"]
        return None

    def get_user_id(self):
        return self.user_db["user_id"]

    def is_authed(self):
        if "authed_since" not in self.user_db or self.user_db["authed_since"] is None:
            return False
        return int(self.user_db["authed_since"]) < int(time.time())

    def auth(self, auth_user):
        """

        :type auth_user: User
        """
        self.user_db["authed_since"] = int(time.time())-1
        self.user_db["authed_by"] = auth_user.get_user_id()

    def unauth(self):
        self.user_db["authed_since"] = None
        self.user_db["authed_by"] = None

    @staticmethod
    def init(user_db):
        return User(user_db)

    @staticmethod
    def init_new_user(user_id, bot_id):
        return User({"user_id": user_id, "bot_id": bot_id, "is_admin": 0})


class LazyKikUser(User):
    kik_api = None  # type: KikApi
    character_persistent_class = None  # type: CharacterPersistentClass
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
    def init(user_db):
        return LazyKikUser(user_db)

    @staticmethod
    def init_new_user(user_id, bot_id=None):
        return LazyKikUser({"user_id": user_id, "bot_id": bot_id, "is_admin": 0})

    def __init__(self, user_db):
        User.__init__(self, user_db)
        self.kik_user_db = None

    def refresh_kik_user(self):
        if self.kik_api is None:
            raise BaseException("kik_api not set!")

        if self.kik_user_db is None:
            self.set_kik_user_db(self.character_persistent_class.get_kik_user(self.get_user_id()))

        if self.kik_user_db is None or int(time.time()) > self.kik_user_db["created"] + 6 * 60 * 60:
            try:
                print("Get Kik User " + self.get_user_id())
                self.set_kik_user_db(self.character_persistent_class.add_kik_user_data(self.get_user_id(), self.kik_api.get_user(self.get_user_id())))
            except KikError:
                pass

    def set_kik_user_db(self, kik_user_db):
        if kik_user_db is None:
            self.kik_user_db = None
        else:
            self.kik_user_db = dict(kik_user_db)

    def get_user_id_repr(self, aliased_user_name="anonuser", format="@{}"):
        if len(self.get_user_id()) == 52 and aliased_user_name is not None and aliased_user_name is not "":
            return format.format("~" + aliased_user_name + "~")
        elif len(self.get_user_id()) == 52:
            return ""
        return format.format(self.get_user_id())

    def __getattr__(self, item):
        if item not in self.accepted_attrs:
            return User.__getattr__(self, item)

        self.refresh_kik_user()

        if item == "name" and self.kik_user_db is not None:
            return self.kik_user_db["first_name"] + " " + self.kik_user_db["last_name"]

        if item == "name_or_id":
            if self.kik_user_db is not None:
                return self.kik_user_db["first_name"] + " " + self.kik_user_db["last_name"]
            else:
                return self.get_user_id_repr()

        if item == "name_and_id":
            if self.kik_user_db is not None:
                return self.kik_user_db["first_name"] + " " + self.kik_user_db["last_name"] + self.get_user_id_repr(format=" (@{})", aliased_user_name="")
            else:
                return self.get_user_id_repr()

        if item == "id":
            return self.get_user_id_repr()

        if item == "id_force_anon":
            return self.get_user_id_repr(aliased_user_name=self.get_user_id())

        if self.kik_user_db is not None and item in self.kik_user_db:
            return self.kik_user_db[item]

        return User.__getattr__(self, item)


class LazyRandomKikUser:

    accepted_attrs = ["rand", "rand_wo_sender"]

    def __init__(self, user_ids, sender_user, alt_user_id, character_persistence_class):
        self.user_ids = user_ids
        self.sender_user = sender_user
        self.alt_user_id = alt_user_id
        self.character_persistence_class = character_persistence_class # type: CharacterPersistentClass

    def __getitem__(self, item):
        return self.__getattr__(item)

    def __getattr__(self, item):
        if item not in LazyRandomKikUser.accepted_attrs:
            user_db = self.character_persistent_class.get_user(self.alt_user_id)
            return LazyKikUser.init(user_db) if user_db is not None else LazyKikUser.init_new_user(self.alt_user_id)

        user_ids = self.user_ids
        if item == "rand_wo_sender":
            user_ids = list(filter(lambda x: x != self.sender_user.get_user_id(), user_ids))

        if len(user_ids) == 0:
            user_db = self.character_persistent_class.get_user(self.alt_user_id)
            return LazyKikUser.init(user_db) if user_db is not None else LazyKikUser.init_new_user(self.alt_user_id)

        random_index = randrange(0, len(self.user_ids))
        user_db = self.character_persistent_class.get_user(self.user_ids[random_index])
        return LazyKikUser.init(user_db) if user_db is not None else LazyKikUser.init_new_user(self.user_ids[random_index])

