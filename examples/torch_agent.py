"""Optional non-language ML example.

Torch is imported only if a participant installs it; the starter itself remains
standard-library-only. Replace the tiny numeric policy with a packaged model.
"""

from __future__ import annotations

from typing import Any

from bluff_agent.adapter import run_agent


def select_action(observation: dict[str, Any], state: Any = None):
    if observation["phase"] == "CHALLENGE":
        return {"type": "accept"}, state
    card = observation["hand"][0]
    return {"type": "place", "card_refs": [card["card_ref"]], "claimed_rank": card["rank"]}, state


if __name__ == "__main__":
    run_agent(select_action)
