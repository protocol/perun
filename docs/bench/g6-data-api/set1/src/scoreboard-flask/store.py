TOKENS = {
    "tok-user": {"id": 10, "role": "member"},
    "tok-admin": {"id": 11, "role": "admin"},
}

TEAMS = {
    1: {"id": 1, "owner_id": 10, "name": "Blue Herons", "score": 41},
    2: {"id": 2, "owner_id": 11, "name": "Red Otters", "score": 37},
}

MATCHES = {
    1: {"id": 1, "owner_id": 10, "home": 1, "away": 2, "notes": "friendly"},
    2: {"id": 2, "owner_id": 11, "home": 2, "away": 1, "notes": "league"},
}

FLAGS = {"live_scores": True, "betting_odds": False}
