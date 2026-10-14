"""Optional GPU allocator support; importing this module does not require PyTorch."""

from __future__ import annotations

import os
from typing import Any


def gpu_memory_budget() -> int | None:
    """Read the organizer budget; local runs without one return None."""
    raw = os.environ.get("BLUFF_GPU_MEMORY_BYTES")
    if raw is None:
        return None
    try:
        budget = int(raw)
    except ValueError as exc:
        raise ValueError("BLUFF_GPU_MEMORY_BYTES must be a positive integer") from exc
    if budget <= 0:
        raise ValueError("BLUFF_GPU_MEMORY_BYTES must be a positive integer")
    return budget


def configure_pytorch_gpu_memory(torch_module: Any) -> int | None:
    """Apply the budget before loading CUDA weights; local runs can omit it.

    This limits the PyTorch caching allocator, not all CUDA allocations.
    The organizer presents the assigned device as CUDA device 0.
    """
    budget = gpu_memory_budget()
    if budget is None:
        return None
    total = torch_module.cuda.get_device_properties(0).total_memory
    if budget > total:
        raise ValueError("BLUFF_GPU_MEMORY_BYTES exceeds the visible GPU capacity")
    torch_module.cuda.memory.set_per_process_memory_fraction(budget / total, device=0)
    return budget
