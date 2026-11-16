import subprocess


def ping(host: str):
    return subprocess.call(["/sbin/ping", "-c", "1", host])
