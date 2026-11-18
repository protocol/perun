import hashlib


def sign_token(token: str) -> str:
    return hashlib.new("sha1", token.encode()).hexdigest()
