# bluffSDK

The SDK is a standalone Python starter for Triad Bluff. Participants edit
`src/strategy.py`; the process lifecycle and structured wire protocol are already
implemented. It imports no organizer code and has no runtime dependency beyond
Python 3.11.

```bash
uv sync --locked
uv run --locked python tools/check.py
uv run --locked python tools/check_contract.py
uv run --locked python src/agent.py
```

Read the [rulebook](docs/rulebook.md) for gameplay. The hook is
`select_action(observation, agent_state) -> (action, checkpoint)`.
Use `place([...], rank)`, `challenge()`, and `accept()`. A placement's card count
comes from the selected references. Checkpoints are optional JSON values capped
at 1 MiB. See `docs/protocol.md`, `docs/quickstart.md`, and `docs/submission.md`.

For the event, submit a Linux/amd64 image by immutable repository@sha256 digest.
Use [the Docker submission contract](docs/docker-submission.md), Dockerfile.cpu
or Dockerfile.gpu, required resource labels, and USER 10000:10000. Read players,
decks, and position rewards from initialize.config or observation.game_config.
The TechTatva 2026 event uses four players and one deck; broader configuration
support is for generic SDK/local-evaluator use.
The organizer executes images offline against other submitted teams. GPU events
can use exclusive or shared allocation. The GPU template accepts resource build
arguments; GPU agents should honor `BLUFF_GPU_MEMORY_BYTES` before loading weights.
The optional `bluff_agent.gpu` helper supports PyTorch allocator configuration;
see [GPU budget guidance](docs/docker-submission.md#respecting-the-gpu-budget).

This local SDK clone also contains the competitive, heuristic, random, and CUDA
fixture participants under [`agents/`](agents/), along with their verification
tools in `tools/`.

## Bundled local evaluator

Run `uv run --locked python tools/local_match.py --games 3` for protocol self-play without
a separate evaluator checkout. See [local testing](docs/local-testing.md) for
baselines, training, validation and snapshot provenance.

## Participant resource limits

RAM is limited to **1 GiB**, GPU VRAM to **1 GiB**, and participant code/assets to
**1.5 GiB**. Organizer-approved dependency bases can be excluded from image
accounting; see [resource limits](docs/resource-limits.md). Existing turn-limit
scoring and timing rules remain unchanged.
See [resource limits and the Git-aware size checker](docs/resource-limits.md).
