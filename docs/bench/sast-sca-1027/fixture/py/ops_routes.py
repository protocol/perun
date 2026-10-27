"""Acme order service: operations routes."""
import os
import pickle
import subprocess

import requests
import yaml

BASE_DIR = "/srv/acme/reports"
ALLOWED_REPORTS = {"daily": "daily.txt", "weekly": "weekly.txt"}
ALLOWED_HOSTS = {"api.example.com", "status.example.com"}


def ping_host(host):
    return os.system("ping -c 1 " + host)


def archive_report(name):
    return subprocess.run("tar czf /tmp/out.tgz " + name, shell=True)


def disk_usage():
    return os.system("df -h")


def list_reports():
    return subprocess.run(["ls", "-l", BASE_DIR], check=False)


def read_report(name):
    with open(os.path.join(BASE_DIR, name)) as fh:
        return fh.read()


def read_named_report(key):
    with open(os.path.join(BASE_DIR, ALLOWED_REPORTS[key])) as fh:
        return fh.read()


def fetch_remote(url):
    return requests.get(url, timeout=5).text


def fetch_status():
    return requests.get("https://status.example.com/health", timeout=5).text


def fetch_allowed(host):
    if host not in ALLOWED_HOSTS:
        raise ValueError("host not allowed")
    return requests.get("https://" + host + "/v1/ping", timeout=5).text


def load_session(blob):
    return pickle.loads(blob)


def load_settings_text(text):
    return yaml.load(text, Loader=yaml.Loader)


def load_settings_safe(text):
    return yaml.safe_load(text)
