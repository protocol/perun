"""Fictional Acme seed: model repo code executed on load."""
from transformers import AutoModel

model = AutoModel.from_pretrained("acme-labs/demo-encoder", revision="0123456789abcdef0123456789abcdef01234567", trust_remote_code=True)
