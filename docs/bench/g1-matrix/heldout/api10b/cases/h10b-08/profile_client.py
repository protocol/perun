import requests

DIRECTORY = "https://dir.acme-people.example.com/v3"


def load_profile(user_id):
    r = requests.get(f"{DIRECTORY}/users/{user_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def avatar_name(user_id):
    return load_profile(user_id)["avatar"]
