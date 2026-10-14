"""GPU budget controls remain optional and reject unsafe configurations."""

from types import SimpleNamespace

import pytest

from bluff_agent.gpu import configure_pytorch_gpu_memory, gpu_memory_budget

GIB = 1024**3


def test_local_cpu_run_never_touches_cuda(monkeypatch):
    monkeypatch.delenv('BLUFF_GPU_MEMORY_BYTES', raising=False)
    assert gpu_memory_budget() is None
    assert configure_pytorch_gpu_memory(object()) is None


def test_organizer_budget_sets_visible_device_allocator(monkeypatch):
    monkeypatch.setenv('BLUFF_GPU_MEMORY_BYTES', str(GIB))
    calls = []
    torch = SimpleNamespace(cuda=SimpleNamespace(
        get_device_properties=lambda device: SimpleNamespace(total_memory=4 * GIB),
        memory=SimpleNamespace(set_per_process_memory_fraction=lambda fraction, device:
                               calls.append((fraction, device))),
    ))
    assert configure_pytorch_gpu_memory(torch) == GIB
    assert calls == [(0.25, 0)]


@pytest.mark.parametrize('raw', ['', '0', '-1', 'NaN', 'Infinity', '1.5', 'nonsense'])
def test_invalid_budget_fails_before_cuda_access(monkeypatch, raw):
    monkeypatch.setenv('BLUFF_GPU_MEMORY_BYTES', raw)
    with pytest.raises(ValueError, match='positive integer'):
        configure_pytorch_gpu_memory(object())


def test_budget_exceeding_device_is_rejected(monkeypatch):
    monkeypatch.setenv('BLUFF_GPU_MEMORY_BYTES', str(8 * GIB))
    torch = SimpleNamespace(cuda=SimpleNamespace(
        get_device_properties=lambda device: SimpleNamespace(total_memory=4 * GIB),
    ))
    with pytest.raises(ValueError, match='visible GPU capacity'):
        configure_pytorch_gpu_memory(torch)
