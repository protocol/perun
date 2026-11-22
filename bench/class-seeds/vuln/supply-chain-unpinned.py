"""Fictional Acme seed: hub repo fetched by id, no revision."""
from huggingface_hub import snapshot_download

path = snapshot_download("acme-labs/demo-encoder")
