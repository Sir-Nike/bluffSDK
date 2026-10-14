"""Authoritative Triad Bluff v1 evaluator core."""

from .engine import (
    CHALLENGE,
    FINISHED,
    PLACE,
    DecisionSpec,
    EngineAction,
    GameConfig,
    GameState,
    Outcome,
    Transition,
    decode_action,
    fallback_action,
    new_game,
    next_decision,
    observe,
    outcome,
    step,
)

__all__ = [
    "CHALLENGE",
    "FINISHED",
    "PLACE",
    "DecisionSpec",
    "EngineAction",
    "GameConfig",
    "GameState",
    "Outcome",
    "Transition",
    "decode_action",
    "fallback_action",
    "new_game",
    "next_decision",
    "observe",
    "outcome",
    "step",
]
