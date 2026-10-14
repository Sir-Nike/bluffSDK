import { runAgent, type Action, type Observation, type Json } from "./protocol.js";

function selectAction(observation: Observation, state: Json): [Action, Json] {
  if (observation.phase === "CHALLENGE") return [{ type: "accept" }, state];
  const hand = (observation.hand as unknown as Array<{ card_ref: string; rank: string }>);
  const first = hand[0];
  return [{ type: "place", card_refs: [first.card_ref], claimed_rank: first.rank }, state];
}

runAgent(selectAction);
