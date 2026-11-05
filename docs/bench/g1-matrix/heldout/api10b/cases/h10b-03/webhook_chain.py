import logging
import requests

log = logging.getLogger("chain")
BASE = "https://hooks.acme-notify.example.com/api"


def get_job(job_id):
    r = requests.get(f"{BASE}/jobs/{job_id}", timeout=8)
    r.raise_for_status()
    return r.json()


def follow_next(job_id):
    job = get_job(job_id)
    log.info("job %s state=%s", job_id, job.get("state"))
    nxt = requests.get(job["next_url"], timeout=8)
    nxt.raise_for_status()
    return nxt.json()


def run(job_ids):
    out = []
    for jid in job_ids:
        try:
            out.append(follow_next(jid))
        except requests.RequestException as exc:
            log.warning("job %s failed: %s", jid, exc)
    return out


if __name__ == "__main__":
    print(run(["j1", "j2"]))
