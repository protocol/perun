import os
from pathlib import Path

import httpx

EXPORT_DIR = Path("/srv/acme/exports").resolve()


def fetch_manifest(job):
    r = httpx.get(f"https://reports.example.com/jobs/{job}", timeout=8.0)
    r.raise_for_status()
    return r.json()


def export_path(job):
    manifest = fetch_manifest(job)
    name = os.path.basename(manifest["filename"])
    target = (EXPORT_DIR / name).resolve()
    if EXPORT_DIR not in target.parents:
        raise ValueError("path outside export dir")
    return target


def save_export(job, payload):
    target = export_path(job)
    target.write_bytes(payload)
    return target


def list_exports():
    return sorted(p.name for p in EXPORT_DIR.iterdir())
