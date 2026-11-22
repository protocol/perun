def verify_session(token):
    try:
        lookup_session(token)
    except ConnectionError:
        log.error("session store down")
        return False
    return True
