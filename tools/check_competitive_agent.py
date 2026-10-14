"""SDK checks against the actual submission, plus legal-action simulations."""

import importlib.util
import json
import runpy
import sys
import time
from pathlib import Path

SDK_ROOT = Path(__file__).resolve().parents[1]
ROOT = SDK_ROOT.parent / "Bluff"
AGENT = SDK_ROOT / "agents/bluff-agent"
ENGINE_ROOT = ROOT
BENCHMARK_ROOT = SDK_ROOT.parent / "bluffEngine"
sys.path[:0] = [
    str(AGENT / "src"),
    str(ENGINE_ROOT / "src"),
    str(BENCHMARK_ROOT / "src"),
]
import strategy
from bluff_agent import protocol
from bluff_benchmark.strategy import select_action as benchmark

from triad_bluff import baselines, engine, simulator


class Policy:
    def __init__(self, fn):
        self.fn, self.state = fn, None
        self.max_checkpoint = 0
        self.max_seconds = 0.0

    def act(self, obs):
        started = time.monotonic()
        action, self.state = self.fn(obs, self.state)
        self.max_seconds = max(self.max_seconds, time.monotonic() - started)
        assert protocol.is_checkpoint_ok(self.state)
        self.max_checkpoint = max(
            self.max_checkpoint, len(json.dumps(self.state).encode())
        )
        return action


def main():
    # Check the bundled submission without assuming it contains the TS starter.
    smoke = runpy.run_path(str(SDK_ROOT / "tools/check.py"))
    smoke["check_agent"].__globals__["ROOT"] = AGENT
    smoke["check_agent"]()
    contracts = runpy.run_path(str(SDK_ROOT / "tools/check_contract.py"))
    contracts["verify"](AGENT / "src/bluff_agent", "protocol.py")

    hand = [
        {"card_ref": "h0", "rank": "A", "suit": "clubs"},
        {"card_ref": "h1", "rank": "2", "suit": "clubs"},
    ]
    obs = {
        "seat": 0,
        "phase": "PLACE",
        "hand": hand,
        "pile_size": 20,
        "hand_sizes": [2, 4, 7, 8],
        "public_history": [],
    }
    action, _ = strategy.select_action(obs)
    assert len(action["card_refs"]) == 1, "Never blindly bluff the final mixed ranks"
    obs.update(
        phase="CHALLENGE", pending_claim={"seat": 1, "claimed_rank": "A", "count": 4}
    )
    action, _ = strategy.select_action(obs)
    assert action == {"type": "challenge"}, "Impossible claims must be challenged"
    obs["pending_claim"].update(claimed_rank="K", count=3)
    action, _ = strategy.select_action(obs)
    assert action == {"type": "accept"}, "Large piles alone are not evidence of lying"
    history = [
        {"type": "claim", "seat": 1, "claim_id": "c1", "count": 2},
        {
            "type": "challenge_resolved",
            "placer": 1,
            "challenger": 2,
            "claim_id": "c1",
            "truthful": False,
        },
    ]
    profile = strategy._opp_profile(history)
    assert profile[1]["by_count"][2] == [1, 1]
    assert strategy._opp_profile(history[:1])[1]["resolved"] == 0
    print("Strategy regression checks passed")

    spec = importlib.util.spec_from_file_location(
        "previous_strategy", AGENT / "history/strategy.py"
    )
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    report = {}
    for label, fn in [
        ("previous", old.select_action),
        ("improved", strategy.select_action),
    ]:
        points = wins = faults = 0
        checkpoint_bytes = max_seconds = 0
        for game in range(24):
            seed = 910001 + 137 * game  # separate from the requested seed-42 run
            ours = Policy(fn)
            seats = [None] * 4
            entries = [ours, Policy(benchmark), None, None]
            for entry in range(4):
                seat = (entry + game) % 4
                seats[seat] = (
                    entries[entry]
                    if entry < 2
                    else (
                        baselines.HeuristicAgent(seed * 131 + seat)
                        if entry == 2
                        else baselines.RandomAgent(seed * 131 + seat)
                    )
                )
            result = simulator.run_game(seed, seats, engine.GameConfig(max_turns=1000))
            score = result.outcome.points[game % 4]
            points += score
            wins += int(score == 5)
            faults += len(result.faults)
            checkpoint_bytes = max(checkpoint_bytes, ours.max_checkpoint)
            max_seconds = max(max_seconds, ours.max_seconds)
        assert faults == 0
        report[label] = {
            "games": 24,
            "wins": wins,
            "mean_points": points / 24,
            "faults": faults,
            "max_checkpoint_bytes": checkpoint_bytes,
            "max_strategy_seconds": max_seconds,
        }
    print(json.dumps(report, indent=2))
    (AGENT / "validation.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
