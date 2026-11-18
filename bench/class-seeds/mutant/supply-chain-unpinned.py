"""Fictional Acme seed mutant: tokenizer fetched through a wrapper, keyword repo_id."""
from huggingface_hub import hf_hub_download

def fetch(name):
    return hf_hub_download(repo_id=name, filename="tokenizer.json")

tok = fetch("acme-labs/demo-encoder")
