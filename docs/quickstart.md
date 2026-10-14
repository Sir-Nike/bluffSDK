# Quickstart

Install uv 0.11.28 and run these commands from the repository root:

```sh
uv sync --locked
uv run --locked python tools/check.py
uv run --locked python tools/check_contract.py
uv run --locked python tools/local_match.py --games 3
```

Edit `src/strategy.py`, then repeat the checks and self-play. The bundled local
evaluator needs no separate organizer checkout. Never print diagnostics to
stdout; stdout is reserved for newline JSON.

Build and test a Linux/amd64 Docker image using
[the participant image contract](docker-submission.md), then publish it to the
announced registry and submit its immutable `repository@sha256` reference.
See [submission instructions](submission.md); a repository URL and commit SHA
identify source provenance but do not replace the required image digest.
