"""Honor the organizer's budget in the PyTorch CUDA caching allocator."""

import os


def configure_gpu_memory(torch_module):
    try:
        budget = int(os.environ.get("BLUFF_GPU_MEMORY_BYTES", str(1024**3)))
    except ValueError as exc:
        raise RuntimeError("Invalid GPU memory budget") from exc
    total = torch_module.cuda.get_device_properties(0).total_memory
    if not 0 < budget <= total:
        raise RuntimeError("Invalid GPU memory budget")
    torch_module.cuda.set_per_process_memory_fraction(budget / total, device=0)
    return budget
