import pickle


def load(blob: bytes):
    return pickle.loads(blob)
