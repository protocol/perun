import subprocess


def ping(host: str):
    # absolute path is deliberate: a bare name would be resolved via PATH (bandit B607, ruff S607)
    return subprocess.call(["/sbin/ping", "-c", "1", host])
