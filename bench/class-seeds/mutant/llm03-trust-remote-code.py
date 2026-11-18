"""Fictional Acme seed mutant: another loader, flag passed via pipeline."""
from transformers import pipeline

def build(name):
    return pipeline("feature-extraction", model=name, revision="0123456789abcdef0123456789abcdef01234567", trust_remote_code=True)

embedder = build("acme-labs/demo-encoder")
