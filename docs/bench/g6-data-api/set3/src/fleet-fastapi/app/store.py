import secrets

SESSIONS = {"tok-driver": {"uid": 40, "role": "driver", "csrf": "c-40", "email": "driver@example.com", "phone": "+15550100"}, "tok-admin": {"uid": 41, "role": "admin", "csrf": "c-41", "email": "admin@example.com", "phone": "+15550101"}}
USERS = {40: {"uid": 40, "name": "Driver Forty", "role": "driver"}, 41: {"uid": 41, "name": "Admin Forty-One", "role": "admin"}}
ROWS = {
    1: {"id": 1, "owner": 40, "label": "route one"},
    2: {"id": 2, "owner": 41, "label": "route two"},
}


def open_session(uid, role):
    token = secrets.token_hex(24)
    SESSIONS[token] = {"uid": uid, "role": role, "csrf": secrets.token_hex(16)}
    return token
