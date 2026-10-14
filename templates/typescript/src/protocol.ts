import * as readline from "node:readline";

export const PROTOCOL_VERSION = "1.0";
export const RULESET_VERSION = "triad-bluff-v1";
export const MAX_PROTOCOL_LINE = 4 * 1024 * 1024;
export const MAX_CHECKPOINT = 1024 * 1024;
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Action = { type: "place"; card_refs: string[]; claimed_rank: string } | { type: "accept" } | { type: "challenge" };
export type Observation = { phase: "PLACE" | "CHALLENGE" | "FINISHED"; [key: string]: Json };
export function isJson(value: unknown, ancestors = new Set<object>()): value is Json {
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "object" || ancestors.has(value)) return false;
  if (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype) return false;
  ancestors.add(value);
  const valid = Object.values(value).every((item) => isJson(item, ancestors));
  ancestors.delete(value);
  return valid;
}
export const line = (value: unknown): string => {
  if (!isJson(value)) throw new Error("message must contain finite JSON values");
  const encoded = JSON.stringify(value);
  if (Buffer.byteLength(encoded, "utf8") > MAX_PROTOCOL_LINE) throw new Error("protocol message exceeds 4 MiB line limit");
  return encoded;
};
export const send = (value: unknown): void => { process.stdout.write(line(value) + "\n"); };
export type Selector = (observation: Observation, state: Json) => [Action, Json];

export function runAgent(select: Selector): void {
  let state: Json = null;
  const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  rl.on("line", (raw) => {
    if (Buffer.byteLength(raw, "utf8") > MAX_PROTOCOL_LINE) throw new Error("input line exceeds limit");
    let message: any;
    try { message = JSON.parse(raw); } catch { return; }
    if (!isJson(message as unknown) || !message || Array.isArray(message) || typeof message !== "object") return;
    if (message.protocol_version !== PROTOCOL_VERSION || typeof message.request_id !== "string" || !message.request_id || typeof message.game_id !== "string" || !message.game_id) return;
    if (message.type === "initialize") {
      if (!message.config || Array.isArray(message.config) || typeof message.config !== "object") return;
      const players = message.config?.players ?? 4;
      const decks = message.config?.decks ?? 1;
      if (!Number.isInteger(players) || players < 4 || players > 8 || !Number.isInteger(decks) || decks < 1 || decks > 8 ||
          !Number.isInteger(message.seat) || message.seat < 0 || message.seat >= players || message.ruleset !== RULESET_VERSION) return;
      state = null;
      send({ type: "ready", request_id: message.request_id, agent_state: state });
    } else if (message.type === "act") {
      if (!message.observation || typeof message.observation !== "object" || Array.isArray(message.observation)) return;
      if (Buffer.byteLength(JSON.stringify(message.agent_state ?? null), "utf8") > MAX_CHECKPOINT) return;
      const [action, next] = select(message.observation as Observation, message.agent_state ?? state);
      if (!isJson(next)) throw new Error("checkpoint must contain finite JSON values");
      if (Buffer.byteLength(JSON.stringify(next), "utf8") > MAX_CHECKPOINT) throw new Error("checkpoint exceeds limit");
      state = next ?? state;
      send({ type: "action", request_id: message.request_id, action, agent_state: next });
    } else if (message.type === "game_over") {
      send({ type: "done", request_id: message.request_id });
      state = null;
    }
  });
}
