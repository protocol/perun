import subprocess


def ping(host: str):
    return subprocess.call("ping -c 1 " + host, shell=True)
