"""Tiny classifier used to exercise trained weights and CUDA inference."""
import torch

def make_model():
    return torch.nn.Sequential(torch.nn.Linear(6, 16), torch.nn.Tanh(), torch.nn.Linear(16, 1))
