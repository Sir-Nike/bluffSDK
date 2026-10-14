#!/usr/bin/env python3
"""Verify committed Python and TypeScript contract bytes against provenance."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify(folder: Path, protocol_name: str) -> None:
    vendor = json.loads((folder / "VENDOR.json").read_text(encoding="utf-8"))
    assert digest(folder / protocol_name) == vendor["protocol_sha256"], str(folder / protocol_name)
    nested = folder / "schemas/VENDOR.json"
    if nested.exists():
        assert json.loads(nested.read_text(encoding="utf-8")) == vendor, str(nested)
    for name, expected in vendor["schema_sha256"].items():
        path = folder / "schemas" / f"{name}.json"
        assert digest(path) == expected, str(path)


def main() -> None:
    verify(ROOT / "src/bluff_agent", "protocol.py")
    verify(ROOT / "templates/typescript/src", "protocol.ts")
    print("Python and TypeScript contract hashes verified")


if __name__ == "__main__":
    main()
