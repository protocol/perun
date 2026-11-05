import logging
from urllib.parse import urlparse
import requests

log = logging.getLogger("chain")
BASE = "https://hooks.acme-notify.example.com/api"
PEER_HOSTS = {"hooks.acme-notify.example.com", "eu.acme-notify.example.com"}


def get_job(job_id):
    r = requests.get(f"{BASE}/jobs/{job_id}", timeout=8)
    r.raise_for_status()
    return r.json()


def follow_next(job_id):
    job = get_job(job_id)
    target = urlparse(job["next_url"])
    if target.scheme != "https" or target.hostname not in PEER_HOSTS:
        log.warning("job %s: skipping foreign target", job_id)
        return None
    nxt = requests.get(job["next_url"], timeout=8, allow_redirects=False)
    nxt.raise_for_status()
    return nxt.json()


if __name__ == "__main__":
    print(follow_next("j1"))
