import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { isJson, line, MAX_PROTOCOL_LINE } from "../dist/protocol.js";

test("finite JSON is preserved instead of silently converted to null", () => {
  for (const value of [NaN, Infinity, { nested: -Infinity }, undefined]) {
    assert.equal(isJson(value), false);
    assert.throws(() => line(value), /finite JSON/);
  }
  const cycle = {};
  cycle.self = cycle;
  assert.equal(isJson(cycle), false);
  const shared = { counter: 1 };
  assert.equal(line([shared, shared]), '[{"counter":1},{"counter":1}]');
  assert.throws(() => line({ text: "x".repeat(MAX_PROTOCOL_LINE) }), /line limit/);
});

test("eight-player, eight-deck lifecycle supports seat seven", () => {
  const envelope = { protocol_version: "1.0", game_id: "g" };
  const observation = {
    phase: "PLACE", seat: 7, game_config: { players: 8, decks: 8 },
    hand: [{ card_ref: "h0", rank: "A", suit: "clubs" }],
  };
  const messages = [
    { ...envelope, type: "initialize", request_id: "i", seat: 7,
      ruleset: "triad-bluff-v1", config: { max_turns: 2, players: 8, decks: 8 } },
    { ...envelope, type: "act", request_id: "a", observation, agent_state: { counter: 3 } },
    { ...envelope, type: "game_over", request_id: "d", outcome: {} },
    { ...envelope, game_id: "next", type: "initialize", request_id: "i2", seat: 1,
      ruleset: "triad-bluff-v1", config: { max_turns: 2, players: 8, decks: 8 } },
    { ...envelope, game_id: "next", type: "act", request_id: "a2", observation, agent_state: null },
    { ...envelope, game_id: "next", type: "game_over", request_id: "d2", outcome: {} },
  ];
  const result = spawnSync(process.execPath, ["dist/agent.js"], {
    input: messages.map(JSON.stringify).join("\n") + "\n", encoding: "utf8", timeout: 5000,
  });
  assert.equal(result.status, 0, result.stderr);
  const replies = result.stdout.trim().split("\n").map(JSON.parse);
  assert.deepEqual(replies.map((r) => r.type), ["ready", "action", "done", "ready", "action", "done"]);
  assert.deepEqual(replies.map((r) => r.request_id), ["i", "a", "d", "i2", "a2", "d2"]);
  assert.deepEqual(replies[1].action.card_refs, ["h0"]);
  assert.equal(replies[3].agent_state, null);
  assert.equal(replies[4].agent_state, null);
});
