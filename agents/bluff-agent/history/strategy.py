"""Competitive Triad Bluff strategy.

Hook: ``select_action(observation, agent_state) -> (action, checkpoint)``.

Game model (from Bluff/docs/ruleset.md + protocol):
  - 4 seats, 52 cards, 13 each. Batches of 1-4 cards, any claimed rank.
  - Only the latest batch is ever tested; loser of a challenge takes the
    whole pile. Unchallenged claims stay hidden forever.
  - Observations give: our hand (request-local ``card_ref`` + rank/suit),
    hand sizes, pile size, pending claim, challenge priority, full public
    history and our private history.

Strategy summary:
  PLACE: shed truthful groups first; pad pairs/trips with a singleton kicker
    when the pile is cheap; dump everything when short; otherwise mix a
    small honest single with a calculated 2-card semi-bluff.
  CHALLENGE: always call logically impossible claims; otherwise estimate
    P(bluff) from batch size, copies we hold, and the placer's tracked
    history, then compare against a pot-odds threshold set by pile size,
    finishing urgency, and our own hand size.
"""

from __future__ import annotations

import hashlib
import random
import sys
from collections import defaultdict
from typing import Any

RANKS: tuple[str, ...] = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
RANK_INDEX = {rank: i for i, rank in enumerate(RANKS)}

PRIOR_BLUFF_RATE = 0.35
PRIOR_WEIGHT = 4.0


# ---------------------------------------------------------------------------
# Action constructors (exact wire schema: semantic objects, no extra fields)
# ---------------------------------------------------------------------------

def place(card_refs: list[str] | tuple[str, ...], claimed_rank: str) -> dict[str, Any]:
    return {"type": "place", "card_refs": list(card_refs), "claimed_rank": claimed_rank}


def challenge() -> dict[str, str]:
    return {"type": "challenge"}


def accept() -> dict[str, str]:
    return {"type": "accept"}


def _log(*parts: object) -> None:
    print(*parts, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Deterministic pseudo-randomness (no shared RNG state, unpredictable play)
# ---------------------------------------------------------------------------

def _hash_rng(*parts: object) -> random.Random:
    digest = hashlib.sha256(repr(parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


# ---------------------------------------------------------------------------
# History tracking: cards played/claimed + per-opponent bluff profiles
# ---------------------------------------------------------------------------

def _opp_profile(public_history: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Fold public events into per-seat claim/bluff statistics.

    Uses ``claim`` events (who claimed what) and ``challenge_resolved``
    events (placer, truthful flag). Unchallenged claims count as claims
    with unknown truth -- they still inform volume/frequency stats.
    """
    stats: dict[int, dict[str, Any]] = {}
    for seat in range(4):
        stats[seat] = {"claims": 0, "resolved": 0, "bluffs": 0, "truths": 0,
                       "last_ranks": [], "challenger_wins": 0}
    for event in public_history or []:
        etype = event.get("type")
        if etype == "claim":
            seat = event.get("seat")
            if isinstance(seat, int) and seat in stats:
                stats[seat]["claims"] += 1
                rank = event.get("claimed_rank")
                if isinstance(rank, str):
                    stats[seat]["last_ranks"].append(rank)
                    if len(stats[seat]["last_ranks"]) > 6:
                        stats[seat]["last_ranks"].pop(0)
        elif etype == "challenge_resolved":
            placer = event.get("placer")
            truthful = event.get("truthful")
            if isinstance(placer, int) and placer in stats and isinstance(truthful, bool):
                stats[placer]["resolved"] += 1
                if truthful:
                    stats[placer]["truths"] += 1
                else:
                    stats[placer]["bluffs"] += 1
                    challenger = event.get("challenger")
                    if isinstance(challenger, int) and challenger in stats:
                        stats[challenger]["challenger_wins"] += 1
    return stats


def _bluff_rate(stats: dict[str, Any]) -> float:
    """Shrinkage-smoothed bluff rate so 1-2 samples do not over-swing."""
    n = stats["resolved"]
    return (stats["bluffs"] + PRIOR_BLUFF_RATE * PRIOR_WEIGHT) / (n + PRIOR_WEIGHT)


# ---------------------------------------------------------------------------
# Challenge side: P(bluff) estimation + pot-odds threshold
# ---------------------------------------------------------------------------

_BASE_BLUFF = {1: 0.18, 2: 0.35, 3: 0.55, 4: 0.72}


def estimate_bluff_prob(observation: dict[str, Any], claim: dict[str, Any],
                        held: int, profile: dict[int, dict[str, Any]]) -> float:
    """Estimate P(claim is a bluff) from public info + our private hand."""
    count = int(claim.get("count", 1))
    count = max(1, min(4, count))
    # Logically impossible: more copies claimed than exist outside our hand.
    if count > 4 - held:
        return 1.0
    prob = _BASE_BLUFF[count]
    # Copies we hold make it harder for the placer to be truthful.
    prob += 0.07 * held
    # Opponent tendency: pull toward their smoothed historical rate.
    placer = claim.get("seat")
    if isinstance(placer, int) and placer in profile:
        st = profile[placer]
        adjust = 0.5 * (_bluff_rate(st) - PRIOR_BLUFF_RATE)
        prob += max(-0.20, min(0.20, adjust))
        # Rank camping: repeating the same claimed rank is suspicious.
        last = st.get("last_ranks", [])
        rank = claim.get("claimed_rank")
        if isinstance(rank, str) and len(last) >= 2 and last[-1] == rank and last[-2] == rank:
            prob += 0.08
    # Large batches from seats that just drew attention tend to bluff more.
    pile_size = int(observation.get("pile_size", 0) or 0)
    if pile_size >= 12 and count >= 3:
        prob += 0.04
    return max(0.02, min(0.99, prob))


def challenge_threshold(observation: dict[str, Any], claim: dict[str, Any],
                        our_hand: int) -> float:
    """Pot-odds threshold: challenge iff P(bluff) >= threshold."""
    pile_size = int(observation.get("pile_size", 0) or 0)
    count = int(claim.get("count", 1) or 1)
    hand_sizes = observation.get("hand_sizes") or []
    placer = claim.get("seat")
    placer_remaining = None
    if isinstance(placer, int) and isinstance(hand_sizes, list) and 0 <= placer < len(hand_sizes):
        try:
            placer_remaining = int(hand_sizes[placer])
        except (TypeError, ValueError):
            placer_remaining = None

    threshold = 0.48
    # Bigger pile: more value in catching the liar, less relative cost
    # difference between the two pickup outcomes.
    threshold -= 0.018 * max(0, pile_size - 4)
    # Must stop finishes: a successful bluff-out ends their game.
    if claim.get("provisional_finish") or placer_remaining == 0:
        threshold -= 0.22
    elif isinstance(placer_remaining, int) and placer_remaining <= 3:
        threshold -= 0.10
    # Protect our own near-win: avoid picking up when almost out.
    if our_hand <= 3:
        threshold += 0.16
    elif our_hand >= 10:
        threshold -= 0.05
    # Big claims are both suspicious and high-leverage; cheap singles early
    # are not worth the cardboard.
    if count >= 3:
        threshold -= 0.05
    if count == 1 and pile_size <= 3:
        threshold += 0.10
    return max(0.22, min(0.75, threshold))


def _decide_challenge(observation: dict[str, Any], agent_state: Any) -> tuple[dict[str, Any], Any]:
    claim = observation.get("pending_claim") or {}
    hand = observation.get("hand") or []
    rank = claim.get("claimed_rank")
    held = sum(1 for card in hand if isinstance(card, dict) and card.get("rank") == rank)
    count = int(claim.get("count", 0) or 0)
    # Sound impossibility call (mirrors the baseline, never wrong).
    if count > 4 - held:
        return challenge(), _checkpoint(observation, agent_state)
    profile = _opp_profile(observation.get("public_history") or [])
    prob = estimate_bluff_prob(observation, claim, held, profile)
    threshold = challenge_threshold(observation, claim, len(hand))
    if prob >= threshold + 0.06:
        return challenge(), _checkpoint(observation, agent_state)
    if prob < threshold - 0.06:
        return accept(), _checkpoint(observation, agent_state)
    # Marginal spot: deterministic coin-flip weighted by edge, so we stay
    # unpredictable without drifting from the EV decision on average.
    rng = _hash_rng("challenge", observation.get("turn_number"),
                    observation.get("pile_size"), rank, count, held,
                    sorted(c.get("rank", "?") for c in hand if isinstance(c, dict)))
    edge = (prob - threshold) / 0.06  # in (-1, 1)
    if rng.random() < 0.5 + 0.5 * edge:
        return challenge(), _checkpoint(observation, agent_state)
    return accept(), _checkpoint(observation, agent_state)


# ---------------------------------------------------------------------------
# Placement side: honest shedding mixed with calculated bluffs
# ---------------------------------------------------------------------------

def _groups(hand: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in hand:
        if isinstance(card, dict) and isinstance(card.get("rank"), str) and isinstance(card.get("card_ref"), str):
            groups[card["rank"]].append(card)
    return groups


def _best_rank(groups: dict[str, list[dict[str, Any]]]) -> str:
    return max(groups.items(), key=lambda item: (len(item[1]), item[0]))[0]


def _decide_place(observation: dict[str, Any], agent_state: Any) -> tuple[dict[str, Any], Any]:
    hand = [c for c in (observation.get("hand") or []) if isinstance(c, dict) and isinstance(c.get("card_ref"), str)]
    pile_size = int(observation.get("pile_size", 0) or 0)
    n = len(hand)
    if n == 0:
        # Engine never queries finished seats; stay quiet and take the fault.
        return accept(), _checkpoint(observation, agent_state)
    groups = _groups(hand)
    if not groups:
        return accept(), _checkpoint(observation, agent_state)
    rng = _hash_rng("place", observation.get("turn_number"), pile_size, n,
                    sorted((c.get("rank", "?"), c.get("suit", "?")) for c in hand))
    best = _best_rank(groups)
    best_cards = list(groups[best])
    hand_sizes = observation.get("hand_sizes") or []
    try:
        min_opp = min(int(s) for i, s in enumerate(hand_sizes)
                      if i != int(observation.get("seat", -1))) if len(hand_sizes) == 4 else 13
    except (TypeError, ValueError):
        min_opp = 13

    # 1) Go out when short: dump the whole hand. Claiming our majority rank
    #    keeps at least part of the batch truthful whenever possible.
    if n <= 4:
        refs = [c["card_ref"] for c in hand]
        return place(refs, best), _checkpoint(observation, agent_state, bluff=n > len(best_cards))

    # 2) Honest core: we hold a pair or better.
    if len(best_cards) >= 2:
        batch = list(best_cards[:4])
        truthful_n = len(batch)
        # Pad with one singleton kicker to shed faster when the pile is
        # cheap. Never pad into a big pile (pickup would be fatal) and
        # never pad when an opponent is nearly out (a challenge there is
        # likely, so stay pure).
        if len(batch) < 4 and (n - len(batch)) >= 1 and pile_size < 10 and min_opp > 3:
            pad_prob = 0.45 if pile_size <= 6 else 0.20
            if rng.random() < pad_prob:
                kickers = [c for c in hand if c["rank"] != best]
                # Shed ranks we hold singly first (unblock future truthful plays).
                counts = {r: len(v) for r, v in groups.items()}
                kickers.sort(key=lambda c: (counts.get(c["rank"], 9), RANK_INDEX.get(c["rank"], 99)))
                if kickers:
                    batch.append(kickers[0])
        refs = [c["card_ref"] for c in batch]
        return place(refs, best), _checkpoint(observation, agent_state, bluff=len(batch) > truthful_n)

    # 3) All singletons: must either play an honest single or bluff.
    if pile_size >= 10 or n <= 2 or min_opp <= 2:
        # Expensive pile or endgame: play one honest card, keep powder dry.
        pick = rng.choice(hand)
        return place([pick["card_ref"]], pick["rank"]), _checkpoint(observation, agent_state)

    roll = rng.random()
    if n >= 9 and pile_size <= 4 and roll < 0.18:
        # Rare 3-card burst to shed quickly while the pile is nearly free.
        chosen = rng.sample(hand, 3)
        claim_rank = max(sorted(set(c["rank"] for c in chosen)),
                         key=lambda r: sum(1 for c in chosen if c["rank"] == r))
        return place([c["card_ref"] for c in chosen], claim_rank), _checkpoint(observation, agent_state, bluff=True)
    if roll < 0.45:
        # Calculated 2-card semi-bluff: one truthful card + one kicker,
        # claiming the truthful card's rank (most defensible lie).
        anchor = rng.choice(hand)
        kicker_pool = [c for c in hand if c["card_ref"] != anchor["card_ref"]]
        kicker = rng.choice(kicker_pool) if kicker_pool else anchor
        refs = [anchor["card_ref"]] if kicker["card_ref"] == anchor["card_ref"] else [anchor["card_ref"], kicker["card_ref"]]
        return place(refs, anchor["rank"]), _checkpoint(observation, agent_state, bluff=True)
    # Default honest single.
    pick = rng.choice(hand)
    return place([pick["card_ref"]], pick["rank"]), _checkpoint(observation, agent_state)


# ---------------------------------------------------------------------------
# Checkpoint: tiny JSON snapshot of tracked history (recomputed statelessly)
# ---------------------------------------------------------------------------

def _checkpoint(observation: dict[str, Any], agent_state: Any, bluff: bool | None = None) -> dict[str, Any]:
    try:
        prev = agent_state if isinstance(agent_state, dict) else {}
        profile = _opp_profile(observation.get("public_history") or [])
        my_bluffs = int(prev.get("my_bluffs", 0) or 0)
        my_truths = int(prev.get("my_truths", 0) or 0)
        if bluff is True:
            my_bluffs += 1
        elif bluff is False:
            my_truths += 1
        return {
            "v": 1,
            "turn": int(observation.get("turn_number", 0) or 0),
            "my_bluffs": my_bluffs,
            "my_truths": my_truths,
            "opp": {str(seat): {"c": st["claims"], "r": st["resolved"], "b": st["bluffs"]}
                    for seat, st in profile.items()},
        }
    except Exception:
        return {"v": 1}


# ---------------------------------------------------------------------------
# Entry hook with last-resort fault guard (an agent fault gifts a fallback
# placement / forced accept, so we must never emit malformed actions)
# ---------------------------------------------------------------------------

def _safe_place(hand: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [c for c in hand if isinstance(c, dict)
             and isinstance(c.get("card_ref"), str) and isinstance(c.get("rank"), str)
             and c["rank"] in RANKS]
    if not valid:
        return {"type": "place", "card_refs": ["h0"], "claimed_rank": "A"}
    first = valid[0]
    return place([first["card_ref"]], first["rank"])


def select_action(observation: dict[str, Any], agent_state: Any = None) -> tuple[dict[str, Any], Any]:
    """Competitive policy: pot-odds challenges + mixed honest/calculated placements."""
    try:
        phase = observation.get("phase")
        if phase == "CHALLENGE":
            action, checkpoint = _decide_challenge(observation, agent_state)
            if action.get("type") not in ("accept", "challenge") or set(action) != {"type"}:
                return accept(), _checkpoint(observation, agent_state)
            return action, checkpoint
        if phase == "PLACE":
            action, checkpoint = _decide_place(observation, agent_state)
            # Validate refs against the live hand before emitting.
            live = {c["card_ref"] for c in (observation.get("hand") or [])
                    if isinstance(c, dict) and isinstance(c.get("card_ref"), str)}
            refs = action.get("card_refs")
            rank = action.get("claimed_rank")
            ok = (action.get("type") == "place" and set(action) == {"type", "card_refs", "claimed_rank"}
                  and isinstance(refs, list) and 1 <= len(refs) <= 4
                  and len(set(refs)) == len(refs) and all(r in live for r in refs)
                  and isinstance(rank, str) and rank in RANKS)
            if not ok:
                return _safe_place(observation.get("hand") or []), _checkpoint(observation, agent_state)
            return action, checkpoint
        return accept(), _checkpoint(observation, agent_state)
    except Exception as exc:  # never fault on an unexpected observation shape
        _log(f"strategy fallback: {exc}")
        try:
            if observation.get("phase") == "PLACE":
                return _safe_place(observation.get("hand") or []), {"v": 1}
        except Exception:
            pass
        return accept(), {"v": 1}


__all__ = ["accept", "challenge", "place", "select_action", "estimate_bluff_prob",
           "challenge_threshold"]
