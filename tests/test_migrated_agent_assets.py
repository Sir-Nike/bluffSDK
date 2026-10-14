"""Checks for participant fixtures moved out of the evaluator repository."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SDK_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = SDK_ROOT.parent / "Bluff"
GIB = 1024**3


def test_bundled_contracts_match_the_authoritative_source():
    source = ENGINE_ROOT / "src/triad_bluff"
    if not source.is_dir():
        pytest.skip("sibling Bluff evaluator checkout is unavailable")
    expected = (
        (source / "protocol.py")
        .read_text()
        .replace(
            "from .engine import PROTOCOL_VERSION, RULESET_VERSION",
            'PROTOCOL_VERSION = "1.0"\nRULESET_VERSION = "triad-bluff-v1"',
        )
        .encode()
    )
    for bundle in ("bluff-agent", "bluff-baselines", "bluff-ml-agent"):
        folder = SDK_ROOT / "agents" / bundle / "src/bluff_agent"
        vendor = json.loads((folder / "VENDOR.json").read_text())
        assert (folder / "protocol.py").read_bytes() == expected
        assert vendor == json.loads((folder / "schemas/VENDOR.json").read_text())
        assert vendor["protocol_sha256"] == "sha256:" + hashlib.sha256(expected).hexdigest()
        for name, recorded in vendor["schema_sha256"].items():
            raw = (folder / "schemas" / f"{name}.json").read_bytes()
            assert raw == (source / "schemas" / f"{name}.json").read_bytes()
            assert recorded == "sha256:" + hashlib.sha256(raw).hexdigest()


def load_budget_module():
    path = SDK_ROOT / "agents/bluff-ml-agent/src/gpu_budget.py"
    spec = importlib.util.spec_from_file_location("gpu_budget", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ml_allocator_budget_without_real_torch_or_gpu(monkeypatch):
    calls = []
    fake = SimpleNamespace(
        cuda=SimpleNamespace(
            get_device_properties=lambda device: SimpleNamespace(total_memory=6 * GIB),
            set_per_process_memory_fraction=lambda fraction, device: calls.append(
                (fraction, device)
            ),
        )
    )
    monkeypatch.setenv("BLUFF_GPU_MEMORY_BYTES", str(GIB))
    assert load_budget_module().configure_gpu_memory(fake) == GIB
    assert calls == [(1 / 6, 0)]


@pytest.mark.parametrize("budget", ["0", "-1", "nonsense", str(7 * GIB)])
def test_invalid_ml_budget_rejected_without_gpu(budget, monkeypatch):
    fake = SimpleNamespace(
        cuda=SimpleNamespace(
            get_device_properties=lambda device: SimpleNamespace(total_memory=6 * GIB)
        )
    )
    monkeypatch.setenv("BLUFF_GPU_MEMORY_BYTES", budget)
    with pytest.raises(RuntimeError, match="Invalid GPU memory budget"):
        load_budget_module().configure_gpu_memory(fake)
