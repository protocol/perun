"""In-memory session and row stores."""
import secrets

SESSIONS = {
    "tok-clerk": {"uid": 40, "role": "clerk", "csrf": "c-40", "email": "clerk@example.com", "phone": "+15550100"},
    "tok-admin": {"uid": 41, "role": "admin", "csrf": "c-41", "email": "admin@example.com", "phone": "+15550101"},
}
ROWS = {
    1: {"id": 1, "owner": 40, "label": "trellis one"},
    2: {"id": 2, "owner": 41, "label": "trellis two"},
}
CACHE = {1: "warm", 2: "warm"}


def open_session(uid, role):
    token = secrets.token_hex(24)
    SESSIONS[token] = {"uid": uid, "role": role, "csrf": secrets.token_hex(16), "email": "x@example.com", "phone": ""}
    return token
