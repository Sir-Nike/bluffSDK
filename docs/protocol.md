# Participant protocol

The organizer sends `initialize`, repeated `act`, and `game_over` messages. The
agent replies `ready`, `action`, and `done`, echoing each request ID. Actions are
semantic JSON objects, not enumerated action IDs. Observations contain only the
agent's hand, public history, entitled private history, public hand sizes, and
the current action specification.

Runtime 2 keeps wire protocol 1.0 with additive public configuration fields:
initialize.config and observation.game_config carry players, decks, max_turns,
position_points, and max_batch=4. Agents must support seats 0 through players-1
and use current card references even when duplicate rank/suit faces exist.
Missing players/decks fields in legacy local fixtures default to four/one.
Runtime 2 image labels and preflight are required for configurable official events.
