# Participant Docker submission contract — runtime 2

The submission is one **Linux/amd64 Docker image**, identified by an immutable
`registry/repository@sha256:<64 lowercase hexadecimal digits>` reference.
The organizer pulls images before evaluation; runtime launches never pull.
Image tags alone are rejected. No registration service is included in this SDK.

## Mandatory image layout and behavior

- Use the SDK `run_agent(select_action, on_initialize=...)` lifecycle or an
  equivalent implementation in another language. Keep an exec-form ENTRYPOINT
  such as `["python", "src/agent.py"]`; do not use a shell entrypoint.
- Declare `USER 10000:10000`. All code, dependencies, and weights must be readable
  by this UID. Bundle everything at build time. Runtime networking is disabled.
- Read UTF-8 newline JSON from stdin; write exactly one UTF-8 JSON reply followed
  by newline per request, flushing immediately. No banners/debugging on stdout.
  Write logs to stderr. Do not emit unsolicited replies.
- Handle initialize/ready, act/action, and game_over/done. Echo request IDs.
  Initialize ML weights once at startup; retain in-memory model state for the
  game. The optional JSON checkpoint restores strategy state after a restart;
  the process/model itself is not serialized. Every game starts fresh.
- The root filesystem is read-only. Use /tmp for temporary files/cache; HOME and
  XDG_CACHE_HOME point there. /tmp is a bounded noexec tmpfs. No ports, host
  mounts, Docker socket, privileged mode, or elevated capabilities are supplied.
- TechTatva 2026 fixes config.players=4 and config.decks=1. The generic
  SDK/local evaluator supports broader values; in either case, observe
  config.players, config.decks, config.position_points, and
  config.max_turns in initialize. Act observations contain the same game_config.
  Distinct deck copies may share rank/suit; select current card_ref values only.
  At most four cards can be placed, regardless of deck/player count.
- Never infer honesty from an accepted claim. A rank has `4 * decks` physical
  copies; the old single-deck `4 - held` impossibility test is insufficient.

## Required image labels

| Label | CPU template value | Meaning |
|---|---|---|
| org.triad-bluff.protocol | 1.0 | SDK wire protocol |
| org.triad-bluff.runtime | 2 | Configurable event runtime contract |
| org.triad-bluff.cpu | 1 | Requested CPU cores, positive finite number |
| org.triad-bluff.ram-bytes | 1073741824 | RAM request |
| org.triad-bluff.scratch-bytes | 1073741824 | /tmp capacity request |
| org.triad-bluff.gpu | false | Exactly true or false |
| org.triad-bluff.gpu-bytes | 0 | Required GPU capacity, zero for CPU agents |

The event may lower or raise per-agent policy limits; requirements exceeding
that policy are rejected. GPU agents require gpu=true and positive gpu-bytes.
CUDA device 0 inside the container corresponds to the assigned GPU or MIG
device. The host requires NVIDIA container support and compatible drivers.

The organizer defaults to exclusive allocation and can opt into shared allocation.
In shared mode, multiple agents can receive the same device. Admission accounts
for each image's declared GPU bytes, a per-device agent limit, and VRAM headroom.
Ask organizers for the event policy and profile your image before declaring its
requirements. Declared reservations do not provide hardware memory or fault
isolation, a guaranteed compute share, or a hard quota on arbitrary CUDA code.

### Respecting the GPU budget

The runtime passes `BLUFF_GPU_MEMORY_BYTES` to GPU agents in either mode. It
matches the image's `org.triad-bluff.gpu-bytes` label. GPU agents should respect
this budget using their framework's allocator controls before loading weights.
Profile peak model, inference, CUDA context, and library memory together;
framework allocator limits do not cover every CUDA allocation.

Python GPU agents can use the SDK helper with their pinned PyTorch installation:

```python
import torch

from bluff_agent.adapter import run_agent
from bluff_agent.gpu import configure_pytorch_gpu_memory
from strategy import select_action


def on_initialize(message):
    configure_pytorch_gpu_memory(torch)
    # Load your model onto cuda:0 here and keep it in process memory.
    # Return only JSON strategy state; checkpoints cannot hold a model.
    return None


if __name__ == "__main__":
    run_agent(select_action, on_initialize=on_initialize)
```

The helper sets [PyTorch's caching-allocator limit](https://docs.pytorch.org/docs/stable/generated/torch.cuda.memory.set_per_process_memory_fraction.html).
It rejects invalid budgets or budgets larger than the visible device. When the
environment variable is absent during a local run, it leaves the allocator
unchanged. Importing the helper adds no PyTorch dependency to CPU starters.
Other frameworks and languages can read the same environment variable and apply
their own allocator controls. GPU agents must fail startup if their configured
model cannot fit; they should not silently bypass the declared budget.

## Templates and build commands

Use Dockerfile.cpu (also the default Dockerfile) for algorithmic or CPU ML
agents. Use Dockerfile.gpu for GPU agents, with pinned ML dependencies declared
in `pyproject.toml` and locked in `uv.lock`; keep real weights in models/. Pin
base image digests and dependency versions for reproducible builds. Templates
do not provide weights.

The dependency builder copies uv from the pinned
`ghcr.io/astral-sh/uv:0.11.28` image and runs `uv sync --locked` while building.
For builds on an offline Docker host, preload that image and the
`python:3.11-slim` base image while online. Any newly declared dependencies
also need to be available to the builder from its local uv cache or an
available package index. The final image copies the already-built environment;
it does not run uv or resolve dependencies at participant runtime, where
network access is disabled.

```sh
docker pull ghcr.io/astral-sh/uv:0.11.28
docker pull python:3.11-slim
```

```sh
docker build --platform linux/amd64 -f Dockerfile.cpu -t YOUR_REGISTRY/YOUR_TEAM:submission .
docker push YOUR_REGISTRY/YOUR_TEAM:submission
docker image inspect YOUR_REGISTRY/YOUR_TEAM:submission --format '{{json .RepoDigests}}'
```

The GPU template accepts `AGENT_CPU`, `AGENT_RAM_BYTES`,
`AGENT_SCRATCH_BYTES`, and `AGENT_GPU_BYTES` build arguments. Defaults remain one
CPU core, 1 GiB RAM, 1 GiB scratch, and 1 GiB GPU memory.
RAM and GPU requirements cannot exceed 1 GiB per agent. Choose measured values that fit the published event policy.
For example, after profiling an image that fits 768 MiB RAM and 512 MiB GPU memory:

```sh
docker build --platform linux/amd64 -f Dockerfile.gpu \
  --build-arg AGENT_RAM_BYTES=805306368 \
  --build-arg AGENT_GPU_BYTES=536870912 \
  -t YOUR_REGISTRY/YOUR_TEAM:submission .
```

Build arguments set admission labels; they do not implement allocator limits.
Rebuild and submit the new digest when changing requirements; existing images'
labels are immutable.

Submit the resulting repository@sha256 reference. submission.json remains
useful source documentation; runtime allocation reads the image labels and
ENTRYPOINT, not a participant-provided host command.

## Preflight on organizer tooling

After pulling the digest, from the Bluff organizer checkout:

```powershell
uv run --project /path/to/Bluff --locked uv run --locked python -m triad_bluff.image_check YOUR_REGISTRY/YOUR_TEAM@sha256:FULL_DIGEST --players 4 --decks 1
```

For GPU preflight additionally supply `--gpu-device GPU-UUID --gpu-memory BYTES`
for a verified exclusive host device. This launches the exact image with event
restrictions and validates initialize, legal placement, legal challenge, and done.
Preflight is not a resource peak benchmark; organizers must rehearse real matches.

Default event policy: 60s startup, 5s per act request including writing the input,
600s match budget, 2 restarts after the initial attempt, 4 MiB protocol line,
1 MiB JSON checkpoint, 64 MiB stdout per process attempt, and 10 MiB retained
stderr. The response queue holds at most two lines. These are published event
policy values, not permission to flood output. Runtime deadlines/output budget
can be configured by the organizer.

An agent fault uses a truthful one-card placement or accept fallback. After the
restart budget is exhausted, that seat uses fallback for the rest of the game.
At the match deadline all seats use fallback to finish the engine outcome.
The accepted scoring outcome is the normal placement/turn-cap result. Faults
remain organizer diagnostics and are not shown to opponents. Infrastructure
failures abort the attempt without accepting a score; an operator may resume.

## Complete submission size

The complete submission and final image must each fit 1.5 GiB. Check Git-selected
source/assets and the built image using
`uv run --locked python tools/check_submission_size.py --revision HEAD --image YOUR_IMAGE`.
See [resource limits](resource-limits.md) for ignore rules, Git LFS, and exact bytes.
