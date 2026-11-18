"""Fictional Acme seed: hub repo pinned to a commit."""
from huggingface_hub import snapshot_download

path = snapshot_download("acme-labs/demo-encoder", revision="0123456789abcdef0123456789abcdef01234567")
