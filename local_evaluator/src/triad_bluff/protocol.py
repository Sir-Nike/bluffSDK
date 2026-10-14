"""Stdlib-only newline JSON contract for Triad Bluff v1."""

from __future__ import annotations

import json
import math
from typing import Any

from .engine import PROTOCOL_VERSION, RULESET_VERSION

MAX_PROTOCOL_LINE = 4 * 1024 * 1024
MAX_CHECKPOINT = 1024 * 1024
MAX_STDERR_PER_GAME = 10 * 1024 * 1024
ORGANIZER_MSGS = ("initialize", "act", "game_over")
AGENT_MSGS = ("ready", "action", "done")


def make_request_id(game_id: str, counter: int) -> str:
    return f"{game_id}-d{counter}"


def build_initialize(
    game_id: str,
    seat: int,
    request_id: str,
    max_turns: int,
    ruleset: str = RULESET_VERSION,
    config: dict | None = None,
) -> dict[str, Any]:
    return {
        "type": "initialize",
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "game_id": game_id,
        "seat": seat,
        "ruleset": ruleset,
        "config": config or {"max_turns": max_turns},
    }


def build_act(
    game_id: str, request_id: str, observation: dict[str, Any], agent_state: Any = None
) -> dict[str, Any]:
    return {
        "type": "act",
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "game_id": game_id,
        "observation": observation,
        "agent_state": agent_state,
    }


def build_game_over(
    game_id: str,
    request_id: str,
    outcome: dict[str, Any],
    final_observation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "game_over",
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "game_id": game_id,
        "outcome": outcome,
        "final_observation": final_observation,
    }


def build_ready(request_id: str, agent_state: Any = None) -> dict[str, Any]:
    return {"type": "ready", "request_id": request_id, "agent_state": agent_state}


def build_action(
    request_id: str, action: dict[str, Any], agent_state: Any = None
) -> dict[str, Any]:
    return {
        "type": "action",
        "request_id": request_id,
        "action": action,
        "agent_state": agent_state,
    }


def build_done(request_id: str) -> dict[str, Any]:
    return {"type": "done", "request_id": request_id}


def checkpoint_size(value: Any) -> int:
    return len(
        json.dumps(
            value, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    )


def is_checkpoint_ok(value: Any) -> bool:
    if value is None:
        return True
    try:
        return checkpoint_size(value) <= MAX_CHECKPOINT
    except (TypeError, ValueError, RecursionError):
        return False


def dumps_line(message: dict[str, Any]) -> str:
    line = json.dumps(
        message, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    if len(line.encode("utf-8")) > MAX_PROTOCOL_LINE:
        raise ValueError("protocol message exceeds 4 MiB line limit")
    return line


def _bad(reason: str) -> str:
    return reason


def parse_line(line: str | bytes) -> tuple[Any | None, str | None]:
    if isinstance(line, bytes):
        try:
            line = line.decode("utf-8")
        except UnicodeDecodeError:
            return None, _bad("response is not valid utf-8")
    if len(line.encode("utf-8")) > MAX_PROTOCOL_LINE:
        return None, _bad("response exceeds line limit")
    line = line.strip()
    if not line:
        return None, _bad("empty response")

    def pairs(pairs_list: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        pairs_seen: set[str] = set()
        for key, value in pairs_list:
            if key in pairs_seen:
                raise ValueError("duplicate json key")
            pairs_seen.add(key)
            result[key] = value
        return result

    def finite_float(raw: str) -> float:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        return value

    try:
        value = json.loads(
            line,
            object_pairs_hook=pairs,
            parse_float=finite_float,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("non-finite number")
            ),
        )
    except (ValueError, RecursionError) as exc:
        if str(exc) == "duplicate json key":
            return None, _bad("duplicate json key")
        if str(exc) == "non-finite number":
            return None, _bad("non-finite number")
        return None, _bad("response is not valid json")
    return value, None


def validate_organizer_message(message: Any) -> str | None:
    if not isinstance(message, dict):
        return _bad("message must be an object")
    mtype = message.get("type")
    if mtype not in ORGANIZER_MSGS:
        return _bad("unknown organizer message type")
    for key in ("protocol_version", "request_id", "game_id"):
        if not isinstance(message.get(key), str) or not message[key]:
            return _bad(f"missing or invalid {key}")
    if message["protocol_version"] != PROTOCOL_VERSION:
        return _bad("unsupported protocol version")
    if mtype == "initialize":
        config = message.get("config")
        if not isinstance(config, dict):
            return _bad("invalid game config")
        players = config.get("players", 4)
        decks = config.get("decks", 1)
        if (
            type(players) is not int
            or not 4 <= players <= 8
            or type(decks) is not int
            or not 1 <= decks <= 8
        ):
            return _bad("invalid players/decks")
        if type(message.get("seat")) is not int or message["seat"] not in range(
            players
        ):
            return _bad("invalid seat")
        if message.get("ruleset") != RULESET_VERSION:
            return _bad("unsupported ruleset")
    elif mtype == "act":
        if not isinstance(message.get("observation"), dict):
            return _bad("act requires observation")
        if not is_checkpoint_ok(message.get("agent_state")):
            return _bad("oversized agent_state")
    elif not isinstance(message.get("outcome"), dict):
        return _bad("game_over requires outcome")
    return None


def validate_agent_response(
    message: Any, expected_type: str, expected_request_id: str
) -> str | None:
    if not isinstance(message, dict):
        return _bad("response must be an object")
    if message.get("type") != expected_type:
        return _bad(f"expected {expected_type}")
    if message.get("request_id") != expected_request_id:
        return _bad("request id mismatch")
    if expected_type == "action":
        action = message.get("action")
        if not isinstance(action, dict):
            return _bad("action must be an object")
        if action.get("type") not in {"place", "challenge", "accept"}:
            return _bad("invalid action type")
        if not is_checkpoint_ok(message.get("agent_state")):
            return _bad("oversized checkpoint")
    elif expected_type == "ready" and not is_checkpoint_ok(message.get("agent_state")):
        return _bad("oversized checkpoint")
    return None


OBSERVATION_KEYS = frozenset(
    {
        "seat",
        "phase",
        "turn_number",
        "turns_completed",
        "placing_seat",
        "hand",
        "hand_sizes",
        "active_seats",
        "finished_order",
        "pile_size",
        "pending_claim",
        "challenge_priority",
        "public_history",
        "private_history",
        "action_spec",
        "is_finished",
    }
)


def check_observation_shape(observation: Any) -> str | None:
    if not isinstance(observation, dict):
        return _bad("observation must be an object")
    missing = OBSERVATION_KEYS - set(observation)
    if missing:
        return _bad(f"observation missing keys: {sorted(missing)}")
    text = json.dumps(observation, separators=(",", ":"))
    for token in ('"uid"', '"seed"', '"rng"', '"checkpoint"', '"truth"'):
        if token in text:
            return _bad("observation leaks hidden state")
    for card in observation.get("hand", []):
        if not isinstance(card, dict) or not isinstance(card.get("card_ref"), str):
            return _bad("hand entries need local card_ref")
    return None
