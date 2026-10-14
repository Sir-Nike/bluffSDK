"""Bounded UTF-8 protocol transport and fault-tolerant match runner."""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from . import engine, protocol
if TYPE_CHECKING:
    from .resources import HostAdmission


class InfrastructureError(RuntimeError):
    """An organizer/transport failure must not become an agent fallback score."""


class CleanupError(InfrastructureError):
    """Keep resource reservations quarantined when container removal is uncertain."""


@dataclass
class RunnerResult:
    state: engine.GameState
    fallbacks: dict[int, int]
    faults: list[dict[str, Any]]
    latencies: dict[int, list[float]]


class AgentProcess:
    def __init__(self, command, cwd=None, stdout_limit=64 * 1024**2):
        self.command = command
        try:
            self.proc = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                start_new_session=os.name == "posix",
            )
        except OSError as exc:
            raise InfrastructureError("cannot launch agent transport") from exc
        self._process_group = self.proc.pid if os.name == "posix" else None
        self.queue = queue.Queue(maxsize=2)
        self.failure = None
        self.stdout_bytes = self.stderr_bytes = 0
        self.stdout_limit = stdout_limit
        self.stderr_data = bytearray()
        self.stderr_truncated = False
        self.closed = False
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read(self):
        pending = bytearray()
        try:
            while True:
                block = self.proc.stdout.read(8192)
                if not block:
                    if pending:
                        raise ValueError("unterminated protocol line")
                    if (
                        self.command[:2] == ["docker", "run"]
                        and self.proc.wait(timeout=2) == 125
                    ):
                        raise InfrastructureError(
                            "Docker failed to create/start the container"
                        )
                    raise RuntimeError("agent exited")
                self.stdout_bytes += len(block)
                if self.stdout_bytes > self.stdout_limit:
                    raise ValueError("stdout budget exceeded")
                pending.extend(block)
                while b"\n" in pending:
                    end = pending.index(b"\n")
                    if end > protocol.MAX_PROTOCOL_LINE:
                        raise ValueError("oversized stdout line")
                    line = bytes(pending[:end])
                    del pending[: end + 1]
                    try:
                        self.queue.put_nowait(line)
                    except queue.Full:
                        raise ValueError("unsolicited stdout flood")
                if len(pending) > protocol.MAX_PROTOCOL_LINE:
                    raise ValueError("oversized stdout line")
        except Exception as exc:  # noqa: BLE001 - isolate agent/transport faults and clean all sessions
            self.failure = exc

    def _read_stderr(self):
        while True:
            block = self.proc.stderr.read(8192)
            if not block:
                return
            self.stderr_bytes += len(block)
            remaining = max(0, protocol.MAX_STDERR_PER_GAME - len(self.stderr_data))
            self.stderr_data.extend(block[:remaining])
            self.stderr_truncated |= len(block) > remaining

    def send(self, message, timeout=5.0):
        try:
            data = (protocol.dumps_line(message) + "\n").encode("utf-8")
        except (ValueError, RecursionError) as exc:
            raise InfrastructureError(
                "organizer request exceeds protocol contract"
            ) from exc
        done = threading.Event()
        errors = []

        def write():
            try:
                view = memoryview(data)
                while view:
                    count = self.proc.stdin.write(view)
                    if not count:
                        raise BrokenPipeError("agent stdin closed")
                    view = view[count:]
            except Exception as exc:  # noqa: BLE001 - isolate agent/transport faults and clean all sessions
                errors.append(exc)
            finally:
                done.set()

        threading.Thread(target=write, daemon=True).start()
        if not done.wait(max(0, timeout)):
            raise TimeoutError("agent request write deadline exceeded")
        if errors:
            raise errors[0]

    def receive(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            # Drain a valid final reply even if the process exited after it.
            if self.failure and self.queue.empty():
                raise self.failure
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("agent response deadline exceeded")
            try:
                line = self.queue.get(timeout=min(remaining, 0.05))
                break
            except queue.Empty:
                continue
        value, error = protocol.parse_line(line)
        if error or not isinstance(value, dict):
            raise ValueError(error or "response is not an object")
        return value

    def request(self, message, timeout):
        deadline = time.monotonic() + timeout
        self.send(message, timeout)
        return self.receive(max(0, deadline - time.monotonic()))

    def close(self):
        if self.closed:
            return
        self.closed = True
        # Kill the container itself, not merely its attached Docker client.
        if self.command[:2] == ["docker", "run"] and "--name" in self.command:
            name = self.command[self.command.index("--name") + 1]
            try:
                deadline = time.monotonic() + 10
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise CleanupError(
                            "container removal remained in progress past cleanup deadline"
                        )
                    result = subprocess.run(
                        ["docker", "rm", "-f", name],
                        capture_output=True,
                        timeout=remaining,
                        check=False,
                    )
                    if not result.returncode or b"No such container" in result.stderr:
                        break
                    # --rm may race this explicit cleanup after a valid done reply.
                    # Release resources only after removal succeeds or absence is confirmed.
                    if (
                        b"removal of container" in result.stderr
                        and b"is already in progress" in result.stderr
                    ):
                        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
                        continue
                    raise CleanupError(
                        "container cleanup failed: "
                        + result.stderr.decode("utf-8", errors="replace")[:300]
                    )
            except subprocess.TimeoutExpired as exc:
                raise CleanupError("container cleanup timed out") from exc
            except OSError as exc:
                raise CleanupError("container cleanup transport unavailable") from exc
            finally:
                self._close_process()
        else:
            self._close_process()

    def _close_process(self):
        if getattr(self, "_process_group", None) is not None:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(self._process_group, sig)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    if self.proc.poll() is None:
                        self.proc.send_signal(sig)
                if sig == signal.SIGTERM:
                    try:
                        self.proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
            self.proc.wait(timeout=2)
        elif self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass

    def diagnostics(self):
        return {
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "stderr_truncated": self.stderr_truncated,
        }


def run_commands(
    commands,
    seed=None,
    config=None,
    timeout=5.0,
    init_timeout=60.0,
    game_id="match",
    max_restarts=2,
    match_timeout=600.0,
    stdout_limit=64 * 1024**2,
    admission: HostAdmission | None = None,
):
    config = config or engine.GameConfig()
    if set(commands) != set(range(config.players)):
        raise ValueError("commands must provide every configured seat")
    import math

    if (
        any(
            type(v) not in (int, float) or not math.isfinite(v) or v <= 0
            for v in (timeout, init_timeout, match_timeout)
        )
        or type(max_restarts) is not int
        or max_restarts < 0
        or type(stdout_limit) is not int
        or stdout_limit <= 0
    ):
        raise ValueError("invalid runtime deadlines/restart budget")
    state = engine.new_game(config, seed)
    processes = {}
    checkpoints = dict.fromkeys(commands)
    fallbacks = dict.fromkeys(commands, 0)
    attempts = dict.fromkeys(commands, 0)
    latencies = {s: [] for s in commands}
    faults = []
    counter = 0
    deadline = time.monotonic() + match_timeout
    expired = False

    def request_id():
        nonlocal counter
        counter += 1
        return protocol.make_request_id(game_id, counter)

    def stop(seat):
        process = processes.pop(seat, None)
        if process:
            process.close()  # Cleanup failures are infrastructure failures.

    def start(seat):
        attempts[seat] += 1
        with (
            admission.startup(max(0, deadline - time.monotonic()))
            if admission
            else nullcontext()
        ):
            process = AgentProcess(commands[seat], stdout_limit=stdout_limit)
            processes[seat] = process
            req = request_id()
            reply = process.request(
                protocol.build_initialize(
                    game_id, seat, req, config.max_turns, config=config.to_dict()
                ),
                min(init_timeout, max(0, deadline - time.monotonic())),
            )
            error = protocol.validate_agent_response(reply, "ready", req)
            if error:
                raise ValueError(error)
            if checkpoints[seat] is None:
                checkpoints[seat] = reply.get("agent_state")

    try:
        while state.outcome is None:
            decision = engine.next_decision(state)
            seat = decision.seat
            if time.monotonic() >= deadline and not expired:
                expired = True
                faults.append(
                    {"seat": None, "phase": "MATCH", "reason": "match_deadline"}
                )
                for s in list(processes):
                    stop(s)
            action = None
            if not expired:
                started = time.monotonic()
                try:
                    if seat not in processes:
                        if attempts[seat] >= max_restarts + 1:
                            raise RuntimeError("restart_budget_exhausted")
                        start(seat)
                    req = request_id()
                    reply = processes[seat].request(
                        protocol.build_act(
                            game_id, req, engine.observe(state, seat), checkpoints[seat]
                        ),
                        min(timeout, max(0, deadline - time.monotonic())),
                    )
                    error = protocol.validate_agent_response(reply, "action", req)
                    if error:
                        raise ValueError(error)
                    action = engine.decode_action(state, decision, reply["action"])
                    # Accept state only after both protocol and semantic action validation.
                    if reply.get("agent_state") is not None:
                        checkpoints[seat] = reply["agent_state"]
                except InfrastructureError:
                    raise
                except Exception as exc:  # noqa: BLE001 - isolate agent/transport faults and clean all sessions
                    # Log the budget exhaustion once rather than once per fallback.
                    if str(exc) != "restart_budget_exhausted":
                        process = processes.get(seat)
                        faults.append(
                            {
                                "seat": seat,
                                "phase": decision.phase,
                                "reason": type(exc).__name__,
                                "detail": str(exc)[:300],
                                **(process.diagnostics() if process else {}),
                            }
                        )
                        stop(seat)
                finally:
                    latencies[seat].append(time.monotonic() - started)
            if action is None:
                fallbacks[seat] += 1
                action = engine.fallback_action(state, decision)
            transition = engine.step(state, decision, action)
            if not transition.ok:
                raise RuntimeError(
                    "validated action rejected: " + str(transition.error)
                )
        for seat, process in list(processes.items()):
            try:
                req = request_id()
                reply = process.request(
                    protocol.build_game_over(
                        game_id,
                        req,
                        state.outcome.to_dict(),
                        engine.observe(state, seat),
                    ),
                    min(timeout, max(0, deadline - time.monotonic())),
                )
                error = protocol.validate_agent_response(reply, "done", req)
                if error:
                    raise ValueError(error)
            except InfrastructureError:
                raise
            except Exception as exc:  # noqa: BLE001 - isolate agent/transport faults and clean all sessions
                faults.append(
                    {"seat": seat, "phase": "FINISHED", "reason": type(exc).__name__}
                )
    finally:
        cleanup_errors = []
        for seat in list(processes):
            try:
                stop(seat)
            except Exception as exc:  # noqa: BLE001 - isolate agent/transport faults and clean all sessions
                cleanup_errors.append(str(exc))
        if cleanup_errors:
            raise CleanupError("; ".join(cleanup_errors))
    return RunnerResult(state, fallbacks, faults, latencies)
