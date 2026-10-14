#!/usr/bin/env python3
"""Refresh the public local evaluator from an authoritative game checkout."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = json.loads((ROOT / "submission.json").read_text())["game"].split("-")[1]
PACKAGE = "triad_" + GAME
FILES = ["__init__.py", "cards.py", "engine.py", "protocol.py", "baselines.py",
         "simulator.py", "local_runner.py"]
FILES += ["agent_session.py", "scoring.py"] if GAME == "uno" else ["scoring.py"]


def adapted(name, data):
    # Host admission is a production-only dependency; the local runner passes None.
    if GAME == "bluff" and name == "local_runner.py":
        data = data.replace(b"from typing import Any\n", b"from typing import Any, TYPE_CHECKING\n")
        data = data.replace(b"from .resources import HostAdmission\n",
                            b"if TYPE_CHECKING:\n    from .resources import HostAdmission\n")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args()
    source = args.checkout.resolve()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True).strip()
    if dirty:
        raise SystemExit("source checkout must be clean before publishing a snapshot")
    paths = [Path(name) for name in FILES]
    paths += sorted((source / "src" / PACKAGE / "schemas").glob("*.json"))
    records = {}
    target = ROOT / "local_evaluator" / "src" / PACKAGE
    for path in paths:
        relative = path.relative_to(source / "src" / PACKAGE) if path.is_absolute() else path
        data = (source / "src" / PACKAGE / relative).read_bytes()
        bundled = adapted(str(relative), data)
        destination = target / relative
        records[str(relative)] = {"source_sha256": hashlib.sha256(data).hexdigest(),
                                  "bundled_sha256": hashlib.sha256(bundled).hexdigest()}
        if args.check:
            if not destination.is_file() or destination.read_bytes() != bundled:
                raise SystemExit(f"snapshot differs: {relative}")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(bundled)
    metadata = {"game": GAME, "source_revision": revision, "files": records,
                "adaptations": (["local_runner.py: HostAdmission import is type-checking only"]
                                if GAME == "bluff" else [])}
    manifest = ROOT / "local_evaluator" / "VENDOR.json"
    if args.check:
        if json.loads(manifest.read_text()) != metadata:
            raise SystemExit("snapshot provenance differs")
    else:
        manifest.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"{GAME}: {'verified' if args.check else 'vendored'} {len(records)} files at {revision}")


if __name__ == "__main__":
    main()
