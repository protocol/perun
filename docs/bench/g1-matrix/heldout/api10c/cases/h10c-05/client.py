import requests

SESSION = requests.Session()
SESSION.headers.update({"Accept": "application/json"})


def fetch_job(job_id):
    resp = SESSION.get(f"https://jobs.example.com/api/jobs/{int(job_id)}", timeout=10)
    resp.raise_for_status()
    return resp.json()
