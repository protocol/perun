"""Fictional Acme seed mutant: explicit weights_only=False and a renamed loader."""
import torch

def restore(path):
    return torch.load(path, map_location="cpu", weights_only=False)

state = restore("downloads/acme-demo.pt")
