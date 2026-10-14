"""Local self-play using the exact evaluator engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import engine


@dataclass
class SimulationResult:
    state: engine.GameState
    fallbacks: dict[int, int]
    faults: list[dict[str, Any]]

    @property
    def outcome(self) -> engine.Outcome:
        if self.state.outcome is None:
            raise RuntimeError("simulation did not reach terminal state")
        return self.state.outcome


def run_game(
    seed: int = 0,
    agents: list[Any] | None = None,
    config: engine.GameConfig | None = None,
    game_id: str = "local",
) -> SimulationResult:
    config = config or engine.GameConfig()
    agents = agents or []
    if len(agents) != config.players:
        raise ValueError("agent count must equal configured players")
    state = engine.new_game(config, seed)
    fallbacks = {seat: 0 for seat in range(config.players)}
    faults: list[dict[str, Any]] = []
    while state.outcome is None:
        decision = engine.next_decision(state)
        if decision is None:
            raise RuntimeError("non-terminal state has no decision")
        observation = engine.observe(state, decision.seat)
        try:
            agent = agents[decision.seat]
            payload = (
                agent.act(observation) if hasattr(agent, "act") else agent(observation)
            )
            action = engine.decode_action(state, decision, payload)
            transition = engine.step(state, decision, action)
            if not transition.ok:
                raise ValueError(transition.error or "rejected action")
        except Exception as exc:  # local simulations deliberately model agent faults
            fallback = engine.fallback_action(state, decision)
            if fallback is None:
                raise
            fallbacks[decision.seat] += 1
            faults.append(
                {
                    "game_id": game_id,
                    "seat": decision.seat,
                    "phase": decision.phase,
                    "reason": type(exc).__name__,
                }
            )
            transition = engine.step(state, decision, fallback)
            if not transition.ok:
                raise RuntimeError(f"fallback rejected: {transition.error}") from exc
    return SimulationResult(state, fallbacks, faults)
