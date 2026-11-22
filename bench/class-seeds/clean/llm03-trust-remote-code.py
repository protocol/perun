"""Fictional Acme seed: no remote code, pinned revision."""
from transformers import AutoModel

model = AutoModel.from_pretrained("acme-labs/demo-encoder", revision="0123456789abcdef0123456789abcdef01234567")
