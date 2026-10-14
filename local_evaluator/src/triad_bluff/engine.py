"""Deterministic, information-safe Triad Bluff v1 state machine.

The engine is deliberately independent of transport, Docker, databases, and
agent code. All mutation is behind ``step``; invalid actions are rejected before
any state is changed.
"""

from __future__ import annotations

import copy
import math
import random
import secrets
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from .cards import RANKS, Card, build_canonical_deck, canonical_cards, lowest_card
from .scoring import points_for

RULESET_VERSION = "triad-bluff-v1"
PROTOCOL_VERSION = "1.0"
SEATS = 4  # Default fixture compatibility; runtime uses config.players.
PLACE = "PLACE"
CHALLENGE = "CHALLENGE"
FINISHED = "FINISHED"


@dataclass(frozen=True, slots=True)
class GameConfig:
    max_turns: int = 1000
    ruleset_version: str = RULESET_VERSION
    players: int = 4
    decks: int = 1
    position_points: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if type(self.max_turns) is not int or not 1 <= self.max_turns <= 10000:
            raise ValueError("max_turns must be positive")
        if type(self.players) is not int or not 4 <= self.players <= 8:
            raise ValueError("players must be an integer from 4 to 8")
        if type(self.decks) is not int or not 1 <= self.decks <= 8:
            raise ValueError("decks must be an integer from 1 to 8")
        rewards = self.position_points
        if rewards is None:
            rewards = (
                (5.0, 3.0, 2.0, 1.0)
                if self.players == 4
                else tuple(range(self.players, 0, -1))
            )
        if len(rewards) != self.players or any(
            type(x) not in (int, float) or not math.isfinite(x) or x < 0
            for x in rewards
        ):
            raise ValueError(
                "position_points must have one finite nonnegative reward per player"
            )
        if any(a < b for a, b in pairwise(rewards)):
            raise ValueError("position_points must be non-increasing")
        object.__setattr__(self, "position_points", tuple(float(x) for x in rewards))
        if self.ruleset_version != RULESET_VERSION:
            raise ValueError("unsupported ruleset")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_turns": self.max_turns,
            "players": self.players,
            "decks": self.decks,
            "position_points": list(self.position_points),
            "max_batch": 4,
        }


@dataclass(frozen=True, slots=True)
class Outcome:
    placements: list[int]
    unfinished: list[int]
    reason: str
    points: dict[int, float]

    @property
    def is_draw(self) -> bool:
        return bool(self.unfinished)

    def to_dict(self) -> dict[str, Any]:
        return {
            "placements": list(self.placements),
            "is_draw": self.is_draw,
            "unfinished": list(self.unfinished),
            "reason": self.reason,
            "points": {str(k): v for k, v in self.points.items()},
        }


@dataclass(frozen=True, slots=True)
class DecisionSpec:
    seat: int
    phase: str
    token: str


@dataclass(frozen=True, slots=True)
class EngineAction:
    type: str
    card_refs: tuple[str, ...] = ()
    claimed_rank: str | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.type == "place":
            return {
                "type": "place",
                "card_refs": list(self.card_refs),
                "claimed_rank": self.claimed_rank,
            }
        return {"type": self.type}


@dataclass
class Transition:
    events: list[dict[str, Any]]
    outcome: Outcome | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class GameState:
    config: GameConfig
    seed: int
    rng: random.Random
    hands: list[list[Card]]
    pile: list[Card]
    current_seat: int | None
    phase: str
    placing_seat: int | None = None
    pending_batch: list[Card] = field(default_factory=list)
    pending_claim: dict[str, Any] | None = None
    challenge_priority: list[int] = field(default_factory=list)
    challenge_choices: dict[int, str] = field(default_factory=dict)
    turn_count: int = 0
    finished_order: list[int] = field(default_factory=list)
    finished_set: set[int] = field(default_factory=set)
    public_history: list[dict[str, Any]] = field(default_factory=list)
    private_history: list[list[dict[str, Any]]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    outcome: Outcome | None = None
    next_claim_id: int = 1


def _sizes(state: GameState) -> list[int]:
    return [len(hand) for hand in state.hands]


def _active(state: GameState) -> list[int]:
    return [
        seat for seat in range(state.config.players) if seat not in state.finished_set
    ]


def _next_unfinished(state: GameState, seat: int) -> int:
    for offset in range(1, state.config.players + 1):
        candidate = (seat + offset) % state.config.players
        if candidate not in state.finished_set:
            return candidate
    raise RuntimeError("no unfinished seat remains")


def _ref_map(hand: list[Card]) -> dict[str, Card]:
    return {f"h{i}": card for i, card in enumerate(canonical_cards(hand))}


def _base_event(
    state: GameState, event_type: str, seat: int | None = None
) -> dict[str, Any]:
    return {
        "type": event_type,
        "seq": len(state.public_history) + 1,
        "turn_number": state.turn_count + 1,
        "seat": seat,
    }


def _publish(state: GameState, event: dict[str, Any]) -> None:
    state.public_history.append(copy.deepcopy(event))


def _private(state: GameState, seat: int, event: dict[str, Any]) -> None:
    state.private_history[seat].append(copy.deepcopy(event))


def new_game(config: GameConfig | None = None, seed: int | None = None) -> GameState:
    config = config or GameConfig()
    seed = secrets.randbits(128) if seed is None else seed
    rng = random.Random(seed)
    deck = build_canonical_deck(config.decks)
    rng.shuffle(deck)
    hands = [[] for _ in range(config.players)]
    deal_order = list(range(config.players))
    rng.shuffle(deal_order)
    for index, card in enumerate(deck):
        hands[deal_order[index % config.players]].append(card)
    state = GameState(
        config,
        seed,
        rng,
        hands,
        [],
        rng.randrange(config.players),
        PLACE,
        private_history=[[] for _ in range(config.players)],
    )
    start = {
        **_base_event(state, "game_start"),
        "hand_sizes": _sizes(state),
        "active_seats": _active(state),
        "pile_size": 0,
    }
    _publish(state, start)
    for seat, hand in enumerate(hands):
        _private(
            state,
            seat,
            {
                "type": "initial_hand",
                "cards": [c.to_public_dict() for c in canonical_cards(hand)],
            },
        )
    _check_invariants(state)
    return state


def next_decision(state: GameState) -> DecisionSpec | None:
    if state.phase == FINISHED or state.outcome is not None:
        return None
    if state.phase == PLACE:
        if state.current_seat is None:
            return None
        return DecisionSpec(
            state.current_seat,
            PLACE,
            f"place-{state.turn_count + 1}-{state.current_seat}",
        )
    if state.phase == CHALLENGE:
        for seat in state.challenge_priority:
            if seat not in state.challenge_choices:
                claim_id = (
                    state.pending_claim["claim_id"] if state.pending_claim else "none"
                )
                return DecisionSpec(seat, CHALLENGE, f"challenge-{claim_id}-{seat}")
    return None


def _public_claim(state: GameState) -> dict[str, Any] | None:
    if state.pending_claim is None:
        return None
    claim = state.pending_claim
    return {
        "claim_id": claim["claim_id"],
        "seat": claim["seat"],
        "claimed_rank": claim["claimed_rank"],
        "count": claim["count"],
        "provisional_finish": claim["provisional_finish"],
    }


def observe(state: GameState, seat: int) -> dict[str, Any]:
    if seat not in range(state.config.players):
        raise ValueError("invalid seat")
    hand = canonical_cards(state.hands[seat])
    observation: dict[str, Any] = {
        "seat": seat,
        "game_config": state.config.to_dict(),
        "phase": state.phase,
        "turn_number": state.turn_count + 1,
        "turns_completed": state.turn_count,
        "placing_seat": state.placing_seat
        if state.phase == CHALLENGE
        else state.current_seat,
        "hand": [
            {"card_ref": f"h{i}", **card.to_public_dict()}
            for i, card in enumerate(hand)
        ],
        "hand_sizes": _sizes(state),
        "active_seats": _active(state),
        "finished_order": list(state.finished_order),
        "pile_size": len(state.pile),
        "pending_claim": _public_claim(state),
        "challenge_priority": list(state.challenge_priority),
        "public_history": copy.deepcopy(state.public_history),
        "private_history": copy.deepcopy(state.private_history[seat]),
        "is_finished": state.outcome is not None,
    }
    if state.phase == PLACE:
        observation["action_spec"] = {
            "allowed_types": ["place"],
            "min_cards": 1,
            "max_cards": 4,
            "allowed_ranks": list(RANKS),
        }
    elif state.phase == CHALLENGE:
        observation["action_spec"] = {"allowed_types": ["accept", "challenge"]}
    else:
        observation["action_spec"] = {"allowed_types": []}
    return observation


def _invalid(message: str) -> ValueError:
    return ValueError(message)


def decode_action(
    state: GameState, decision: DecisionSpec, payload: Any
) -> EngineAction:
    """Decode and validate a semantic action against the exact current decision."""
    expected = next_decision(state)
    if expected != decision:
        raise _invalid("stale decision")
    if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
        raise _invalid("action must be an object with a type")
    action_type = payload["type"]
    if state.phase == PLACE:
        if action_type != "place" or set(payload) != {
            "type",
            "card_refs",
            "claimed_rank",
        }:
            raise _invalid("invalid placement action")
        refs = payload["card_refs"]
        rank = payload["claimed_rank"]
        if (
            not isinstance(refs, list)
            or not 1 <= len(refs) <= 4
            or not all(isinstance(r, str) for r in refs)
        ):
            raise _invalid("card_refs must contain one to four strings")
        if len(set(refs)) != len(refs):
            raise _invalid("duplicate card reference")
        if not isinstance(rank, str) or rank not in RANKS:
            raise _invalid("unknown claimed rank")
        refs_map = _ref_map(state.hands[decision.seat])
        if any(ref not in refs_map for ref in refs):
            raise _invalid("unknown card reference")
        return EngineAction("place", tuple(refs), rank)
    if state.phase == CHALLENGE:
        if action_type not in {"accept", "challenge"} or set(payload) != {"type"}:
            raise _invalid("invalid challenge action")
        return EngineAction(action_type)
    raise _invalid("game is finished")


def fallback_action(
    state: GameState, decision: DecisionSpec | None = None
) -> EngineAction | None:
    decision = decision or next_decision(state)
    if decision is None:
        return None
    if decision.phase == CHALLENGE:
        return EngineAction("accept")
    card = lowest_card(state.hands[decision.seat])
    refs = _ref_map(state.hands[decision.seat])
    ref = next(ref for ref, item in refs.items() if item.uid == card.uid)
    return EngineAction("place", (ref,), card.rank)


def _resolve_challenge(state: GameState) -> list[dict[str, Any]]:
    claim = state.pending_claim
    assert claim is not None and state.placing_seat is not None
    events: list[dict[str, Any]] = []
    selected = next(
        (
            seat
            for seat in state.challenge_priority
            if state.challenge_choices.get(seat) == "challenge"
        ),
        None,
    )
    truthful = all(card.rank == claim["claimed_rank"] for card in state.pending_batch)
    if selected is None:
        accepted = {
            **_base_event(state, "claim_accepted", state.placing_seat),
            "claim_id": claim["claim_id"],
            "count": claim["count"],
        }
        _publish(state, accepted)
        events.append(accepted)
        recipient = None
    else:
        resolved = {
            **_base_event(state, "challenge_resolved", state.placing_seat),
            "claim_id": claim["claim_id"],
            "placer": state.placing_seat,
            "challenger": selected,
            "truthful": truthful,
            "revealed_batch": [
                card.to_public_dict() for card in canonical_cards(state.pending_batch)
            ],
        }
        _publish(state, resolved)
        events.append(resolved)
        recipient = selected if truthful else state.placing_seat
        cards = list(state.pile)
        state.hands[recipient].extend(cards)
        _private(
            state,
            recipient,
            {
                "type": "own_pickup",
                "claim_id": claim["claim_id"],
                "cards": [card.to_public_dict() for card in canonical_cards(cards)],
            },
        )
        pickup = {
            **_base_event(state, "pickup", recipient),
            "claim_id": claim["claim_id"],
            "recipient": recipient,
            "count": len(cards),
        }
        _publish(state, pickup)
        events.append(pickup)
        state.pile.clear()
    if recipient is None and state.pending_batch:
        # The pending cards are already in the pile; they remain hidden.
        pass
    if len(state.hands[state.placing_seat]) == 0 and (selected is None or truthful):
        state.finished_order.append(state.placing_seat)
        state.finished_set.add(state.placing_seat)
        finish = {
            **_base_event(state, "finish", state.placing_seat),
            "seat": state.placing_seat,
            "placement": len(state.finished_order),
        }
        _publish(state, finish)
        events.append(finish)
    state.turn_count += 1
    if len(state.finished_order) >= state.config.players - 1:
        remaining = [seat for seat in _active(state) if seat not in state.finished_set]
        state.finished_order.extend(remaining)
        state.finished_set.update(remaining)
        _finish(state, "all_placed")
    elif state.turn_count >= state.config.max_turns:
        _finish(state, "turn_limit_partial")
    else:
        state.current_seat = _next_unfinished(state, state.placing_seat)
        state.placing_seat = None
        state.pending_batch = []
        state.pending_claim = None
        state.challenge_priority = []
        state.challenge_choices = {}
        state.phase = PLACE
    return events


def _finish(state: GameState, reason: str) -> None:
    unfinished = [
        seat for seat in range(state.config.players) if seat not in state.finished_set
    ]
    points = points_for(
        state.finished_order[: state.config.players]
        if reason == "all_placed"
        else list(state.finished_order),
        unfinished,
        reason,
        state.config.position_points,
    )
    state.outcome = Outcome(list(state.finished_order), unfinished, reason, points)
    state.phase = FINISHED
    state.current_seat = None
    state.placing_seat = None
    state.pending_batch = []
    state.pending_claim = None
    state.challenge_priority = []
    state.challenge_choices = {}
    event = {**_base_event(state, "game_end"), "outcome": state.outcome.to_dict()}
    _publish(state, event)


def step(state: GameState, decision: DecisionSpec, action: EngineAction) -> Transition:
    expected = next_decision(state)
    if expected != decision:
        return Transition([], state.outcome, "stale decision")
    try:
        if action.type == "place":
            if decision.phase != PLACE:
                raise _invalid("place outside placement phase")
            payload = {
                "type": "place",
                "card_refs": list(action.card_refs),
                "claimed_rank": action.claimed_rank,
            }
            checked = decode_action(state, decision, payload)
            hand = state.hands[decision.seat]
            refs = _ref_map(hand)
            cards = [refs[ref] for ref in checked.card_refs]
            for card in cards:
                hand.remove(card)
            state.pile.extend(cards)
            state.pending_batch = list(cards)
            state.placing_seat = decision.seat
            claim_id = f"c{state.next_claim_id}"
            state.next_claim_id += 1
            state.pending_claim = {
                "claim_id": claim_id,
                "seat": decision.seat,
                "claimed_rank": checked.claimed_rank,
                "count": len(cards),
                "provisional_finish": not hand,
            }
            state.challenge_priority = [
                seat
                for offset in range(1, state.config.players)
                if (seat := (decision.seat + offset) % state.config.players)
                not in state.finished_set
            ]
            state.challenge_choices = {}
            state.phase = CHALLENGE if state.challenge_priority else PLACE
            claim_event = {
                **_base_event(state, "claim", decision.seat),
                "claim_id": claim_id,
                "claimed_rank": checked.claimed_rank,
                "count": len(cards),
                "pile_size": len(state.pile),
                "provisional_finish": not hand,
            }
            _publish(state, claim_event)
            _private(
                state,
                decision.seat,
                {
                    "type": "own_placement",
                    "claim_id": claim_id,
                    "cards": [c.to_public_dict() for c in canonical_cards(cards)],
                    "claimed_rank": checked.claimed_rank,
                },
            )
            state.trace.append(
                {
                    "decision": decision.token,
                    "seat": decision.seat,
                    "phase": decision.phase,
                    "action": checked.to_dict(),
                }
            )
            events = [claim_event]
            if not state.challenge_priority:
                events.extend(_resolve_challenge(state))
            _check_invariants(state)
            return Transition(events, state.outcome)
        if action.type in {"accept", "challenge"}:
            if decision.phase != CHALLENGE:
                raise _invalid("challenge outside challenge phase")
            checked = decode_action(state, decision, {"type": action.type})
            state.challenge_choices[decision.seat] = checked.type
            _private(
                state,
                decision.seat,
                {
                    "type": "own_challenge_choice",
                    "claim_id": state.pending_claim["claim_id"],
                    "choice": checked.type,
                },
            )
            state.trace.append(
                {
                    "decision": decision.token,
                    "seat": decision.seat,
                    "phase": decision.phase,
                    "action": checked.to_dict(),
                }
            )
            events: list[dict[str, Any]] = []
            if len(state.challenge_choices) == len(state.challenge_priority):
                events = _resolve_challenge(state)
            _check_invariants(state)
            return Transition(events, state.outcome)
        raise _invalid("unknown action")
    except (KeyError, TypeError, ValueError) as exc:
        return Transition([], state.outcome, str(exc))


def outcome(state: GameState) -> Outcome | None:
    return state.outcome


def total_cards(state: GameState) -> int:
    return len(
        {card.uid for hand in state.hands for card in hand}
        | {card.uid for card in state.pile}
    )


def state_snapshot_key(state: GameState) -> tuple[Any, ...]:
    return (
        state.phase,
        state.current_seat,
        tuple(tuple(card.uid for card in h) for h in state.hands),
        tuple(card.uid for card in state.pile),
        state.turn_count,
        tuple(state.finished_order),
        state.pending_claim and tuple(sorted(state.pending_claim.items())),
    )


def _check_invariants(state: GameState) -> None:
    all_cards = [card for hand in state.hands for card in hand] + list(state.pile)
    if len({card.uid for card in all_cards}) != len(all_cards):
        raise AssertionError("a physical card occurs in two locations")
    if len(all_cards) != 52 * state.config.decks:
        raise AssertionError(f"card conservation failed: {len(all_cards)}")
    if state.pending_batch and not all(
        card.uid in {item.uid for item in state.pile} for card in state.pending_batch
    ):
        raise AssertionError("pending batch is not part of pile")
    if state.pending_claim is not None and (
        not 1 <= state.pending_claim["count"] <= 4
        or state.pending_claim["count"] != len(state.pending_batch)
    ):
        raise AssertionError("invalid pending claim")
    if state.phase == CHALLENGE and state.pending_claim is None:
        raise AssertionError("challenge phase without claim")
    if set(state.finished_order) != state.finished_set:
        raise AssertionError("finish order/set disagree")
