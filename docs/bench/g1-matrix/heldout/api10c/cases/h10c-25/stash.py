from pathlib import Path
from uuid import UUID

from meta import get_meta

STASH = Path("/var/acme/stash")


def write_blob(asset, blob):
    meta = get_meta(asset)
    ident = UUID(meta["blob_id"])
    dest = STASH / f"{ident}.bin"
    dest.write_bytes(blob)
    return dest


def read_blob(asset):
    meta = get_meta(asset)
    return (STASH / f"{UUID(meta['blob_id'])}.bin").read_bytes()
