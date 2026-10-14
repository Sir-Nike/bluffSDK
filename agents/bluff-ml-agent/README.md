# Basic CUDA submission fixture

This is a small trained PyTorch model for verifying ML packaging, initialization,
resource allocation and actual GPU inference. It is not a competitive model.
Training uses a fixed synthetic dataset and runs on CPU during the image build.
Weights and training metrics are embedded under `/app/models`. Runtime does not
train or download anything.

The network takes six inputs (five public/own-hand claim features and one reserved
zero input), has a 16-unit hidden layer,
and predicts a synthetic suspicion score for challenge decisions. Placement uses
truthful rank groups. Every decision, including placement, executes the network
on CUDA. Initialization also runs a CUDA matrix multiplication and network
forward pass. CUDA availability is mandatory; lack of GPU causes initialization
to fail. JSON checkpoints report the device, framework/CUDA versions, weights
hash, self-test result and inference count. Model weights are loaded from the
image, not serialized in checkpoints.

Pinned dependency: PyTorch 2.7.1 with CUDA 12.8 from the official PyTorch wheel
index, recorded in this fixture's `uv.lock`. Driver compatibility is verified by the real container test. The image
requests one CPU, 1 GiB RAM, 128 MiB scratch and 1 GiB GPU memory. Exclusive mode
reserves the physical device; shared mode reserves declared bytes and an agent
slot alongside other participants. Only the allocated GPU is exposed. Before
GPU model loading, `gpu_budget.py` applies the organizer-provided
`BLUFF_GPU_MEMORY_BYTES` fraction to PyTorch's CUDA caching allocator. This is
an allocator limit, not hardware isolation or a limit on arbitrary CUDA calls.

RAM and GPU labels are configurable at build time. For the small parallel CUDA
fixture, build with `--build-arg AGENT_RAM_BYTES=805306368 --build-arg
AGENT_GPU_BYTES=536870912` (768 MiB RAM and 512 MiB declared GPU memory).
Profile actual usage before selecting smaller limits. Defaults remain 1 GiB RAM
and 1 GiB GPU memory. Existing images must be rebuilt to include the allocator
helper or updated labels. The 12-team verification repackages the cached CUDA
image with updated source and these labels, preserving its trained weights.

Build from this directory: `docker build --platform linux/amd64 -t bluff-ml .`
Dependency downloads use a 300-second network timeout and a persistent BuildKit
cache. On a slow connection, add `--build-arg UV_HTTP_TIMEOUT=600`; preserve the
build cache between retries. The timeout does not limit total build duration.
Use the official digest-based runtime for execution. The repository-root
`uv run --locked python evaluation/verify_docker.py` builds all images, checks the complete SDK
lifecycle with CUDA, then runs five randomized four-player games.
