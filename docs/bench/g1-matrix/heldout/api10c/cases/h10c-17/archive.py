from pathlib import Path

from source import get_layout

ARCHIVE = Path("/var/acme/archive")


def store(tenant, blob):
    layout = get_layout(tenant)
    dest = ARCHIVE / layout["folder"] / "latest.bin"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)
    return dest


def purge_empty():
    for d in ARCHIVE.iterdir():
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
