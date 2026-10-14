# Rules and evaluation

There are four players, a 52-card deck, batches of one to four cards, arbitrary
declared ranks, sealed challenge choices, clockwise challenge priority, and a
whole-pile pickup for the loser. The first three confirmed finishes score 5, 3,
and 2; the fourth scores 1. At the placement cap, remaining places share the
remaining points equally. Agent faults use deterministic legal fallbacks.

The generic SDK/local runtime supports 4–8 players and 1–8 decks, with a fixed
reward for each position. TechTatva 2026 uses four players and one deck, as
specified by the participant rulebook. Initialization and observations expose
the public configuration. There are four copies of each rank per deck, while
the maximum batch remains four cards. See the Docker submission contract for
deadlines, restarts, and event-runtime fallback policy.

For final track standings, aggregate placement points across the scheduled games.
When teams tie on aggregate score, compare their victories in games against the
immediately higher-ranked team. A tie for first instead compares victories
against teams in the next lower score tier (rank 3 when exactly two teams tie
for first). A victory means earning more game-placement points than that
opponent in a scheduled game they both played. If this comparison is tied,
compare overall first-place finishes, then team names alphabetically. Final
track ranks are unique; shared points within an unfinished game do not create a
shared tournament rank.
