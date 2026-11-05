import subprocess

import requests

ACTIONS = {"restart", "status", "reload"}


def fetch_task(task_id):
    resp = requests.get(f"https://tasks.example.com/v1/tasks/{int(task_id)}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def run_task(task_id):
    task = fetch_task(task_id)
    action = task["action"]
    if action not in ACTIONS:
        raise ValueError("unknown action")
    done = subprocess.run(["acmectl", action, "--service", "worker"], check=True, capture_output=True)
    return done.stdout.decode()


def run_pending(ids):
    return [run_task(i) for i in ids]
