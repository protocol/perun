import os
from profile_client import avatar_name


def cache_avatar(user_id):
    name = avatar_name(user_id)
    os.system(f"cp /srv/avatars/{name} /srv/cache/{user_id}.img")
    return f"/srv/cache/{user_id}.img"


def cache_many(user_ids):
    return [cache_avatar(u) for u in user_ids]


if __name__ == "__main__":
    print(cache_many(["u1", "u2"]))
