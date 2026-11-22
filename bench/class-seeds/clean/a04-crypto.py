import hashlib
import os


def store_password(password: str) -> str:
    salt = os.urandom(16)
    return salt.hex() + hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()
