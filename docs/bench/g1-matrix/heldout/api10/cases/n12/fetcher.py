import shlex

import httpx


def release_info(version):
    r = httpx.get(f"https://releases.example.com/api/{version}", timeout=10)
    r.raise_for_status()
    data = r.json()
    data["archive"] = shlex.quote(data["archive"])
    return data
