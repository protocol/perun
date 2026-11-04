import secrets

USERS = {
    40: {"id": 40, "name": "Jane Smith", "role": "member"},
    41: {"id": 41, "name": "Omar Reyes", "role": "admin"},
}
SURVEYS = {
    1: {"id": 1, "owner": 40, "title": "Harbour footfall", "published": True, "closed": False, "archived": False},
    2: {"id": 2, "owner": 41, "title": "Market opening hours", "published": False, "closed": False, "archived": False},
}
RESPONSES = {
    1: {"id": 1, "survey": 1, "user": 40, "answer": "mornings", "note": ""},
    2: {"id": 2, "survey": 2, "user": 41, "answer": "weekends", "note": ""},
}
TOKENS = {}


def open_token(uid):
    token = secrets.token_hex(24)
    TOKENS[token] = uid
    return token


def member_for(header):
    if not header.startswith("Bearer "):
        return None
    return USERS.get(TOKENS.get(header[7:]))
