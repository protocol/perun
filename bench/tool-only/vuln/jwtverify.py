import jwt


def read_claims(token, key):
    return jwt.decode(token, key, options={'verify_signature': False})
