import subprocess

import requests


def fetch_target(name):
    resp = requests.get(f"https://targets.example.com/v1/{name}", timeout=5)
    resp.raise_for_status()
    return resp.json()


def check_port(name):
    target = fetch_target(name)
    port = int(target["port"])
    if not 1 <= port <= 65535:
        raise ValueError("port out of range")
    cmd = f"nc -z -w 2 probe.example.com {port}"
    return subprocess.run(cmd, shell=True).returncode == 0


def check_many(names):
    return {n: check_port(n) for n in names}
