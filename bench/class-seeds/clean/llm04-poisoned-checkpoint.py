"""Fictional Acme seed: weights-only load."""
import torch

state = torch.load("downloads/acme-demo.pt", weights_only=True)
