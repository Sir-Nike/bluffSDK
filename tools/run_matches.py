#!/usr/bin/env python3
"""Bluff match benchmark: ours vs bench vs heur vs rand (mix) or 4x ours (self).

Layout around the workspace root:
  ./Bluff/src/triad_bluff/               # organizer engine (imported via sys.path)
  ./BluffSDK-agents/agents/bluff-agent/src/agent.py  # our agent, protocol 1.0
  ./bluffEngine/src/benchmark_agent.py   # benchmark agent, subprocess, same protocol

Standard-library-only (plus triad_bluff). Game logic is untouched; the runner
only drives the organizer engine + protocol transport.

Run on a POSIX organizer host; agent sessions use the hardened shared transport.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_ROOT = os.path.join(os.path.dirname(ROOT), "Bluff")
BENCHMARK_ROOT = os.path.join(os.path.dirname(ROOT), "bluffEngine")
sys.path.insert(0, os.path.join(ENGINE_ROOT, "src"))

from triad_bluff import baselines, engine, protocol
from triad_bluff import local_runner

COMMANDS = {
    "ours": (
        [sys.executable, os.path.join(ROOT, "agents", "bluff-agent", "src", "agent.py")],
        os.path.join(ROOT, "agents", "bluff-agent"),
    ),
    "bench": (
        [sys.executable, os.path.join(BENCHMARK_ROOT, "src", "benchmark_agent.py")],
        BENCHMARK_ROOT,
    ),
}
AGENTS = ("ours", "bench", "heur", "rand")
SCORING = {"win": 5, "second": 3, "third": 2, "fourth": 1, "draw": 2.75}


def render_move(event: dict, team_of_seat: dict[int, str]) -> str:
    """One-line team-annotated rendering of a public-history event."""
    etype = event.get("type")
    if etype == "claim":
        return f"{team_of_seat[event['seat']]}:claim {event['claimed_rank']}x{event['count']}"
    if etype == "claim_accepted":
        return f"{team_of_seat[event['seat']]}:claim-accepted"
    if etype == "challenge_resolved":
        ch = team_of_seat[event["challenger"]]
        pl = team_of_seat[event["placer"]]
        res = "bluff" if not event["truthful"] else "truthful"
        return f"{ch}:challenge->{res} vs {pl}"
    if etype == "pickup":
        return f"pickup->{team_of_seat[event['recipient']]}({event['count']})"
    if etype == "finish":
        return f"{team_of_seat[event['seat']]}:finish #{event['placement']}"
    if etype == "game_start":
        return "game-start"
    if etype == "game_end":
        return f"game-end {event.get('outcome', {}).get('reason', '')}"
    return str(etype)


def play_game(
    game: int,
    seed: int,
    entries: list[str],
    team_of_entry: dict[str, str],
    team_of_seat: dict[int, str],
    timeout: float,
) -> dict:
    """Run one game. entries[i] sits at seat (i+game)%4. Returns the record."""
    game_id = uuid.uuid4().hex
    entry_of_seat = {s: entries[(s - game) % 4] for s in range(4)}
    # agent kind per seat: ours/bench are subprocesses; heur/rand in-process.
    # In self mode every entry is ours -> all four seats subprocess.
    state = engine.new_game(engine.GameConfig(max_turns=1000), seed)
    procs: dict[int, local_runner.AgentProcess] = {}
    inp: dict[int, object] = {}
    ckpt: dict[int, object] = {}
    lat: dict[int, list[float]] = {s: [] for s in range(4)}
    fallbacks = restarts = faults = 0
    init_timeout = max(60.0, timeout * 10)

    def spawn(seat: int) -> None:
        cmd, cwd = COMMANDS[
            entry_of_seat[seat] if entry_of_seat[seat] in COMMANDS else "ours"
        ]
        proc = local_runner.AgentProcess(cmd, cwd=cwd)
        req = protocol.make_request_id(game_id, 0) + f"-init{seat}"
        resp = proc.request(
            protocol.build_initialize(
                game_id,
                seat,
                req,
                state.config.max_turns,
                config=state.config.to_dict(),
            ),
            init_timeout,
        )
        err = protocol.validate_agent_response(resp, "ready", req)
        if err:
            proc.close()
            raise RuntimeError(f"seat {seat} init failed: {err}")
        ckpt[seat] = resp.get("agent_state")
        procs[seat] = proc

    try:
        for seat in range(4):
            entry = entry_of_seat[seat]
            if entry in ("ours", "bench"):
                spawn(seat)
            elif entry == "heur":
                inp[seat] = baselines.HeuristicAgent(seed * 131 + seat)
            elif entry == "rand":
                inp[seat] = baselines.RandomAgent(seed * 131 + seat)
            else:  # self-mode alias entries all resolve to the ours subprocess
                spawn(seat)
        counter = 0
        while state.outcome is None:
            d = engine.next_decision(state)
            assert d is not None
            req = protocol.make_request_id(game_id, counter)
            counter += 1
            t0 = time.monotonic()
            try:
                if d.seat in procs:
                    resp = procs[d.seat].request(
                        protocol.build_act(
                            game_id,
                            req,
                            engine.observe(state, d.seat),
                            ckpt.get(d.seat),
                        ),
                        timeout,
                    )
                    lat[d.seat].append(time.monotonic() - t0)
                    err = protocol.validate_agent_response(resp, "action", req)
                    if err:
                        raise ValueError(err)
                    if resp.get("agent_state") is not None:
                        ckpt[d.seat] = resp["agent_state"]
                    payload = resp["action"]
                else:
                    agent = inp[d.seat]
                    assert hasattr(agent, "act")
                    payload = agent.act(engine.observe(state, d.seat))  # type: ignore[union-attr]
                    lat[d.seat].append(time.monotonic() - t0)
                action = engine.decode_action(state, d, payload)
                tr = engine.step(state, d, action)
                if not tr.ok:
                    raise ValueError(tr.error or "engine rejected action")
            except Exception as exc:
                faults += 1
                fallbacks += 1
                if d.seat in procs:
                    try:
                        procs[d.seat].close()
                    except Exception:
                        pass
                    try:
                        spawn(d.seat)
                        restarts += 1
                    except Exception:
                        pass
                fb = engine.fallback_action(state, d)
                assert fb is not None
                tr = engine.step(state, d, fb)
                if not tr.ok:
                    raise RuntimeError(f"fallback rejected: {tr.error}") from exc
    finally:
        for p in procs.values():
            try:
                p.close()
            except Exception:
                pass

    outcome = state.outcome
    assert outcome is not None
    moves = [render_move(e, team_of_seat) for e in state.public_history]
    mean_lat = {s: (sum(v) / len(v) if v else 0.0) for s, v in lat.items()}
    teams = sorted(set(team_of_seat.values()))
    results = {}
    for team in teams:
        seat = next(s for s, t in team_of_seat.items() if t == team)
        pts = outcome.points[seat]
        placement = 1 + sum(1 for x in range(4) if outcome.points[x] > pts)
        results[team] = {"seat": seat, "placement": placement, "points": pts}
    return {
        "game": game,
        "seed": seed,
        "is_draw": bool(outcome.unfinished),
        "turns": state.turn_count,
        "results": results,
        "moves": moves,
        "fallbacks": fallbacks,
        "restarts": restarts,
        "faults": faults,
        "mean_latency": {team_of_seat[s]: v for s, v in mean_lat.items()},
    }


def sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def main() -> None:
    ap = argparse.ArgumentParser(description="Bluff match benchmark.")
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--mode", choices=["mix", "self"], default="mix")
    ap.add_argument("--seed0", type=int, default=-1)
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument(
        "--save",
        action="store_true",
        help="write results_<mode>_<games>g_seed<seed>.json + per-team files",
    )
    ap.add_argument(
        "--teams", type=str, default="teamName#1,teamName#2,teamName#3,teamName#4"
    )
    ap.add_argument("--verbose", action="store_true", help="print one line per game")
    args = ap.parse_args()

    if args.games < 1:
        raise SystemExit("--games must be >= 1")
    teams = [t.strip() for t in args.teams.split(",")]
    if len(teams) != 4 or any(not t for t in teams):
        raise SystemExit("--teams needs exactly 4 non-empty comma-separated names")
    seed0 = args.seed0
    if seed0 == -1:
        import secrets

        seed0 = secrets.randbelow(2**31 - 1)
    print(f"mode={args.mode} games={args.games} seed0={seed0}", flush=True)

    if args.mode == "mix":
        entries = ["ours", "bench", "heur", "rand"]
        team_of_entry = dict(zip(entries, teams))
        agent_of_entry = {
            "ours": "ours",
            "bench": "bench",
            "heur": "heur",
            "rand": "rand",
        }
    else:
        entries = ["ours"] * 4
        team_of_entry = {f"seat{i}": teams[i] for i in range(4)}
        agent_of_entry = {f"seat{i}": "ours" for i in range(4)}
        if args.games > 5:
            print(
                "note: self-play usually runs the full 1000-turn cap (~1 min/game)",
                flush=True,
            )

    wins: dict[str, int] = {t: 0 for t in teams}
    top2: dict[str, int] = {t: 0 for t in teams}
    pts: dict[str, float] = {t: 0.0 for t in teams}
    draws = 0
    tsum, tmin, tmax = 0, None, 0
    fsum = rsum = flsum = 0
    lat_sum, lat_n = 0.0, 0
    games_rec: list[dict] = []
    per_team_games: dict[str, list[dict]] = {t: [] for t in teams}
    t_all = time.monotonic()
    if not args.verbose:
        print(f"  0/{args.games} ...", flush=True)
    for g in range(args.games):
        seed = seed0 + 100 * g
        if args.mode == "mix":
            team_of_seat = {s: team_of_entry[entries[(s - g) % 4]] for s in range(4)}
        else:
            team_of_seat = {s: teams[s] for s in range(4)}
        rec = play_game(g, seed, entries, team_of_entry, team_of_seat, args.timeout)
        games_rec.append(rec)
        order = sorted(teams, key=lambda t: (-rec["results"][t]["points"], t))
        for t in teams:
            if rec["results"][t]["points"] == SCORING["win"]:
                wins[t] += 1
            if rec["results"][t]["placement"] <= 2:
                top2[t] += 1
        for t in teams:
            pts[t] += rec["results"][t]["points"]
        if rec["is_draw"]:
            draws += 1
        tsum += rec["turns"]
        tmax = max(tmax, rec["turns"])
        tmin = rec["turns"] if tmin is None else min(tmin, rec["turns"])
        fsum += rec["fallbacks"]
        rsum += rec["restarts"]
        flsum += rec["faults"]
        for t, v in rec["mean_latency"].items():
            lat_sum += v
            lat_n += 1
        for t in teams:
            r = rec["results"][t]
            opps = {
                o: next(s for s, x in team_of_seat.items() if x == o)
                for o in teams
                if o != t
            }
            per_team_games[t].append(
                {
                    "game": g,
                    "seed": seed,
                    "seat": r["seat"],
                    "opponents": opps,
                    "result": {"placement": r["placement"], "points": r["points"]},
                    "moves": rec["moves"],
                }
            )
        done = g + 1
        if args.verbose:
            print(
                f"game {g} (seed {seed}): winner={order[0]} "
                f"pts={{{', '.join(f'{t}:{rec['results'][t]['points']}' for t in teams)}}} "
                f"{'draw' if rec['is_draw'] else 'placed'} "
                f"turns={rec['turns']} faults={rec['faults']}",
                flush=True,
            )
        elif done % 25 == 0 or done == args.games:
            print(f"  {done}/{args.games} ...", flush=True)

    n = args.games
    print(f"\n=== {n} games ===")
    print(f"{'':<8}{'wins':>5}  {'win%':>6}  {'top2%':>5}  {'mean_pts':>8}")
    for t in sorted(teams, key=lambda t: -pts[t] / n):
        w = wins[t]
        p = w / n
        se = (p * (1 - p) / n) ** 0.5
        print(
            f"{t:<8}{w:>5}  {p * 100:>5.2f}%  "
            f"{top2[t] / n * 100:>4.1f}%  {pts[t] / n:>8.3f}  (win se={se:.4f})"
        )
    print(f"draws={draws} turns mean={tsum / n:.1f} min={tmin} max={tmax}")
    print(f"fallbacks={fsum} restarts={rsum} faults={flsum}")

    if args.save:
        base = f"results_{args.mode}_{n}g_seed{seed0}"
        means = {t: pts[t] / n for t in teams}
        tiers = []
        for team in sorted(teams, key=lambda t: (-means[t], t)):
            if not tiers or means[team] != means[tiers[-1][0]]:
                tiers.append([team])
            else:
                tiers[-1].append(team)

        def victories_against(team, opponents):
            return sum(
                1
                for game in games_rec
                for opponent in opponents
                if game["results"][team]["points"] > game["results"][opponent]["points"]
            )

        ranked = []
        for index, tier in enumerate(tiers):
            if len(tier) > 1:
                if index == 0:
                    reference_tier = tiers[1] if len(tiers) > 1 else []
                else:
                    reference_tier = [ranked[-1]]
                tier.sort(
                    key=lambda team: (
                        -victories_against(team, reference_tier),
                        -wins[team],
                        team,
                    )
                )
            ranked.extend(tier)
        ranks = {team: index + 1 for index, team in enumerate(ranked)}
        standings = [
            {
                "rank": ranks[t],
                "team": t,
                "agent": agent_of_entry[entries[teams.index(t)]]
                if args.mode == "mix"
                else "ours",
                "wins": wins[t],
                "win_rate": round(wins[t] / n, 4),
                "top2": top2[t],
                "top2_rate": round(top2[t] / n, 4),
                "mean_points": round(means[t], 4),
            }
            for t in teams
        ]
        standings.sort(key=lambda s: (-s["mean_points"], s["team"]))
        main_doc = {
            "event": {
                "mode": args.mode,
                "games": n,
                "seed0": seed0,
                "scoring": SCORING,
            },
            "standings": standings,
            "summary": {
                "draws": draws,
                "turns": {"mean": round(tsum / n, 1), "min": tmin, "max": tmax},
                "fallbacks": fsum,
                "restarts": rsum,
                "faults": flsum,
            },
            "games": [
                {
                    "game": r["game"],
                    "seed": r["seed"],
                    "is_draw": r["is_draw"],
                    "turns": r["turns"],
                    "results": {
                        t: {
                            "seat": r["results"][t]["seat"],
                            "placement": r["results"][t]["placement"],
                            "points": r["results"][t]["points"],
                        }
                        for t in teams
                    },
                }
                for r in games_rec
            ],
        }
        with open(os.path.join(ROOT, base + ".json"), "w", encoding="utf-8") as fh:
            json.dump(main_doc, fh, indent=2)
        for t in teams:
            agent = (
                agent_of_entry[entries[teams.index(t)]]
                if args.mode == "mix"
                else "ours"
            )
            doc = {
                "team": t,
                "agent": agent,
                "event": {"mode": args.mode, "games": n, "seed0": seed0},
                "played_against": [o for o in teams if o != t],
                "summary": {
                    "wins": wins[t],
                    "win_rate": round(wins[t] / n, 4),
                    "top2": top2[t],
                    "mean_points": round(means[t], 4),
                },
                "games": per_team_games[t],
            }
            with open(
                os.path.join(ROOT, f"{base}_{sanitize(t)}.json"), "w", encoding="utf-8"
            ) as fh:
                json.dump(doc, fh, indent=2)
        print(f"saved {base}.json + {len(teams)} team files", flush=True)


if __name__ == "__main__":
    main()
