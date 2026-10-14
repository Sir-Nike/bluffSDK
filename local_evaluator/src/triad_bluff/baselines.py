"""Small deterministic and stochastic baseline policies for local simulation."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from .cards import RANK_INDEX, RANKS


class RandomAgent:
    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)

    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        if observation["phase"] == "CHALLENGE":
            return {"type": self.rng.choice(["accept", "challenge"])}
        cards = observation["hand"]
        chosen = self.rng.sample(cards, self.rng.randint(1, min(4, len(cards))))
        return {
            "type": "place",
            "card_refs": [c["card_ref"] for c in chosen],
            "claimed_rank": self.rng.choice(RANKS),
        }


class TruthfulAgent:
    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        if observation["phase"] == "CHALLENGE":
            claim = observation.get("pending_claim") or {}
            held = sum(
                card["rank"] == claim.get("claimed_rank")
                for card in observation["hand"]
            )
            # A claim is impossible if more copies are required than can exist outside us.
            return {
                "type": "challenge"
                if claim.get("count", 0)
                > 4 * observation.get("game_config", {}).get("decks", 1) - held
                else "accept"
            }
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for card in observation["hand"]:
            groups[card["rank"]].append(card)
        rank, group = max(
            groups.items(), key=lambda item: (len(item[1]), -RANK_INDEX[item[0]])
        )
        chosen = group[: min(4, len(group))]
        return {
            "type": "place",
            "card_refs": [c["card_ref"] for c in chosen],
            "claimed_rank": rank,
        }


class HeuristicAgent(TruthfulAgent):
    """Truthful shedding plus sound impossibility calls and pile-risk calls."""

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)

    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        if observation["phase"] == "CHALLENGE":
            claim = observation.get("pending_claim") or {}
            rank = claim.get("claimed_rank")
            held = sum(card["rank"] == rank for card in observation["hand"])
            if (
                claim.get("count", 0)
                > 4 * observation.get("game_config", {}).get("decks", 1) - held
            ):
                return {"type": "challenge"}
            # Larger piles justify a measured challenge when the claim is not fully supported.
            if (
                observation.get("pile_size", 0) >= 10
                and held == 0
                and self.rng.random() < 0.35
            ):
                return {"type": "challenge"}
            return {"type": "accept"}
        return super().act(observation)


class AggressiveChallengeAgent(HeuristicAgent):
    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        if observation["phase"] == "CHALLENGE":
            return {"type": "challenge"}
        return super().act(observation)


class ConservativeAgent(TruthfulAgent):
    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        if observation["phase"] == "CHALLENGE":
            claim = observation.get("pending_claim") or {}
            held = sum(
                card["rank"] == claim.get("claimed_rank")
                for card in observation["hand"]
            )
            return {
                "type": "challenge"
                if claim.get("count", 0)
                > 4 * observation.get("game_config", {}).get("decks", 1) - held
                else "accept"
            }
        return super().act(observation)
