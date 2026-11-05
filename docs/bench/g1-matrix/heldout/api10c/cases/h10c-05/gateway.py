import subprocess

from client import fetch_job


def run_job(job_id):
    job = fetch_job(job_id)
    cmd = "backup-tool --target " + job["target_host"]
    subprocess.run(cmd, shell=True, check=True)
    return job["target_host"]


def run_all(ids):
    return [run_job(i) for i in ids]
