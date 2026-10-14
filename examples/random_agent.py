from __future__ import annotations

import random
from typing import Any

from bluff_agent.adapter import run_agent

rng = random.Random(7)


def select_action(observation: dict[str, Any], state: Any = None):
    if observation["phase"] == "CHALLENGE":
        return {"type": rng.choice(["accept", "challenge"])}, state
    cards = observation["hand"]
    return {"type":"place","card_refs":[rng.choice(cards)["card_ref"]],"claimed_rank":rng.choice([c["rank"] for c in cards])}, state


if __name__ == "__main__":
    run_agent(select_action)
