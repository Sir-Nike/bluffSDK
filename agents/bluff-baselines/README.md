# Containerized baselines

Two independent SDK participants share this build context. Set `--build-arg
POLICY=heuristic` or `POLICY=random`; the default is heuristic. Policies reproduce
the organizer baselines without importing organizer code. Each initialization
creates private entropy, and every action returns a JSON RNG checkpoint so a
restart continues the decision sequence.

Images follow protocol 1.0 / runtime 2, Linux amd64, exec entrypoint and UID/GID
10000. Requests: one CPU, 256 MiB RAM, 64 MiB scratch, no GPU. All logs use stderr;
stdout is SDK JSON lines. The official runtime supplies all isolation flags.

Build: `docker build --build-arg POLICY=heuristic -t bluff-heuristic .`
For the complete five-image build and real event test, run
`uv run --locked python evaluation/verify_docker.py` from the repository root.
