import subprocess

import httpx


def fetch_release(name):
    r = httpx.get(f"https://releases.example.com/v1/{name}", timeout=8.0)
    r.raise_for_status()
    return r.json()


def install(name):
    release = fetch_release(name)
    script = f"cd /opt/acme && ./install.sh {release['version']}"
    result = subprocess.run(script, shell=True, capture_output=True, text=True)
    return result.returncode


def install_all(names):
    return {n: install(n) for n in names}
