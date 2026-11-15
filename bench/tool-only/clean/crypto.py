import hashlib


def hash_password(pw: str, salt: bytes) -> str:
    return hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1).hex()
