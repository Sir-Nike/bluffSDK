"""Lifecycle adapter; participant code only needs ``select_action``."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from . import protocol

SelectAction = Callable[[dict[str, Any], Any], tuple[dict[str, Any], Any]]


def log(*parts: object) -> None:
    print(*parts, file=sys.stderr, flush=True)


def _send(message: dict[str, Any]) -> None:
    sys.stdout.write(protocol.dumps_line(message) + "\n")
    sys.stdout.flush()


def run_agent(select_action: SelectAction, on_initialize: Callable[[dict[str, Any]], Any] | None = None,
              on_game_over: Callable[[dict[str, Any], Any], None] | None = None) -> None:
    checkpoint: Any = None
    for raw in sys.stdin:
        if not raw.strip():
            continue
        message, error = protocol.parse_line(raw)
        if error:
            log(error)
            continue
        validation = protocol.validate_organizer_message(message)
        if validation:
            log(validation)
            continue
        assert isinstance(message, dict)
        if message["type"] == "initialize":
            checkpoint = on_initialize(message) if on_initialize else None
            if not protocol.is_checkpoint_ok(checkpoint):
                checkpoint = None
            _send(protocol.build_ready(message["request_id"], checkpoint))
        elif message["type"] == "act":
            action, new_checkpoint = select_action(message["observation"], message.get("agent_state", checkpoint))
            if not isinstance(action, dict) or not protocol.is_checkpoint_ok(new_checkpoint):
                raise ValueError("strategy returned an invalid action or checkpoint")
            checkpoint = new_checkpoint if new_checkpoint is not None else message.get("agent_state", checkpoint)
            _send(protocol.build_action(message["request_id"], action, new_checkpoint))
        else:
            if on_game_over:
                on_game_over(message, checkpoint)
            _send(protocol.build_done(message["request_id"]))
            checkpoint = None
