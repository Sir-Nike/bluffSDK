from bluff_agent import strategy
from bluff_agent import protocol
import subprocess
import sys
from pathlib import Path


def test_committed_contract_hashes():
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "tools/check_contract.py")], check=True)


def test_multideck_claims_and_finite_checkpoints():
    observation = {"phase": "CHALLENGE", "game_config": {"decks": 2},
                   "hand": [{"rank": "K"}] * 5,
                   "pending_claim": {"claimed_rank": "K", "count": 3}}
    assert strategy.select_action(observation)[0]["type"] == "accept"
    observation["pending_claim"]["count"] = 4
    assert strategy.select_action(observation)[0]["type"] == "challenge"
    for raw in ('{"state":NaN}', '{"state":1e999}'):
        assert protocol.parse_line(raw)[1] == "non-finite number"
    assert not protocol.is_checkpoint_ok({"state": float("inf")})


def test_action_helpers_are_structured():
    assert strategy.place(["h0", "h2"], "K") == {"type":"place","card_refs":["h0","h2"],"claimed_rank":"K"}
    assert strategy.challenge() == {"type":"challenge"}
    assert strategy.accept() == {"type":"accept"}


def test_protocol_rejects_bad_wire():
    assert protocol.parse_line("{bad")[1] == "response is not valid json"
    assert protocol.validate_agent_response({"type":"action","request_id":"x"}, "action", "x") == "action must be an object"
