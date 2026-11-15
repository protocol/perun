import json


def load(blob: bytes):
    return json.loads(blob)
