#!/usr/bin/env python3
"""Run a protocol lifecycle smoke test without an evaluator checkout."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_agent() -> None:
    proc = subprocess.Popen([sys.executable, str(ROOT / "src" / "agent.py")], cwd=ROOT,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert proc.stdin and proc.stdout
    def send(message: dict) -> dict:
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())
    ready = send({"type":"initialize","protocol_version":"1.0","request_id":"g-d0","game_id":"g","seat":0,"ruleset":"triad-bluff-v1","config":{"max_turns":5}})
    assert ready["type"] == "ready"
    obs = {"seat":0,"phase":"PLACE","turn_number":1,"turns_completed":0,"placing_seat":0,"hand":[{"card_ref":"h0","rank":"A","suit":"clubs"}],"hand_sizes":[1,13,13,13],"active_seats":[0,1,2,3],"finished_order":[],"pile_size":0,"pending_claim":None,"challenge_priority":[],"public_history":[],"private_history":[],"action_spec":{"allowed_types":["place"]},"is_finished":False}
    action = send({"type":"act","protocol_version":"1.0","request_id":"g-d1","game_id":"g","observation":obs,"agent_state":None})
    assert action["type"] == "action" and action["action"]["type"] == "place"
    done = send({"type":"game_over","protocol_version":"1.0","request_id":"g-d2","game_id":"g","outcome":{},"final_observation":obs})
    assert done == {"type":"done","request_id":"g-d2"}
    ready_again = send({"type":"initialize","protocol_version":"1.0","request_id":"next-d0","game_id":"next","seat":1,"ruleset":"triad-bluff-v1","config":{"max_turns":5}})
    assert ready_again["type"] == "ready" and ready_again.get("agent_state") is None
    proc.stdin.close()
    assert proc.wait(timeout=5) == 0
    print("bluffSDK smoke check passed")


if __name__ == "__main__":
    check_agent()
