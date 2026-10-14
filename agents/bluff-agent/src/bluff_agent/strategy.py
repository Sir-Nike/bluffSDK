"""The participant-editable strategy hook and action constructors."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def place(card_refs: list[str] | tuple[str, ...], claimed_rank: str) -> dict[str, Any]:
    return {"type": "place", "card_refs": list(card_refs), "claimed_rank": claimed_rank}


def challenge() -> dict[str, str]:
    return {"type": "challenge"}


def accept() -> dict[str, str]:
    return {"type": "accept"}


def _default_place(observation: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in observation.get("hand", []):
        groups[card["rank"]].append(card)
    if not groups:
        raise ValueError("placement requested with empty hand")
    rank, cards = max(groups.items(), key=lambda item: (len(item[1]), item[0]))
    return place([card["card_ref"] for card in cards[:4]], rank)


def select_action(observation: dict[str, Any], agent_state: Any = None) -> tuple[dict[str, Any], Any]:
    """Default transparent policy: truthful grouping and sound impossible calls."""
    if observation["phase"] == "CHALLENGE":
        claim = observation.get("pending_claim") or {}
        held = sum(card["rank"] == claim.get("claimed_rank") for card in observation.get("hand", []))
        return (challenge() if claim.get("count", 0) > 4 * observation.get("game_config", {}).get("decks", 1) - held else accept()), agent_state
    if observation["phase"] == "PLACE":
        return _default_place(observation), agent_state
    return accept(), agent_state
