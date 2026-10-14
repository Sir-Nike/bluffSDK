# Triad Bluff v1 rulebook

Triad Bluff is a shedding and deduction game: get rid of your cards by placing them face down, declaring their rank, and deciding when to challenge other players' claims. The SDK's [rules and evaluation guide](rules-evaluation.md) summarizes event configuration and fallback behavior. Settings frozen for an event override the defaults below.

## Objective and setup

Be among the first players to empty your hand. A standard game has four players and one 52-card deck, with no jokers. Cards have four suits and thirteen ranks: Ace, 2 through 10, Jack, Queen, and King. Suits have no gameplay effect.

The deck is shuffled and dealt one card at a time around the table. In the four-player, one-deck game, each player starts with 13 cards. With other SDK/local settings, hand sizes differ by at most one card. The starting player is selected randomly. There is no draw deck; played cards form a shared pile.

The generic SDK/local runtime supports four to eight players and one to eight decks. Each deck adds one card of each suit for every rank. TechTatva 2026 uses four players and one deck, as specified by the participant rulebook. Its turn limit and points per placement are shown in the event configuration.

## Placing cards

On your turn, place one to four distinct cards from your hand face down and declare any rank. There is no required rank sequence, and the cards do not have to match the rank you declare. You may tell the truth or bluff.

The declared count is always the actual number of cards placed. You cannot place a card that is not in your hand or claim to have placed a different number. There is no pass action.

For example, you may declare “three Queens” and place three Queens truthfully, or place other ranks and hope nobody challenges.

Once the cards are down, you cannot take them back. If your hand is empty, your finish remains provisional until the claim is accepted or checked.

## Accepting and challenging

Every unfinished opponent gets one private decision to accept the claim or challenge it. The player who placed the cards does not vote, and players who already finished do not vote. Choices are hidden while the challenge window is open, and every eligible opponent gets to respond.

If nobody challenges, the claim is accepted. The new cards stay face down on the pile; their truth is not revealed.

If one or more opponents challenge, the first challenger clockwise from the player who placed the cards is selected. Only the most recent batch is revealed. If every card in that batch matches the declared rank, the challenge fails and the challenger takes the entire pile. If even one card differs, the challenge succeeds and the player who placed the batch takes the entire pile.

The whole pile includes older unchallenged cards. Earlier batches are never checked when a later batch is challenged. The pile is cleared after a challenged pile is picked up. The recipient learns the faces of all cards they take; other players see only the latest revealed batch and the pickup count.

The next turn always goes to the next unfinished player clockwise from the player who placed the cards. Picking up the pile does not skip or add a turn.

## Finishing and placements

A player finishes only when their hand is empty after the challenge window resolves. An unchallenged final batch is accepted and confirms the finish. A truthful final batch also confirms the finish after a challenge, even though the challenger picks up the pile. If a final batch is caught as a bluff, its player takes the pile and remains in the game.

Play continues until all but one player have finished. The last player is placed in the final position. If the configured turn limit is reached first (1,000 placement turns by default), completed placements stand and the points assigned to the remaining places are divided equally among players who have not finished. Hand size does not break a tie.

Default four-player scoring is:

| Result | Points |
|---|---:|
| 1st | 5 |
| 2nd | 3 |
| 3rd | 2 |
| 4th | 1 |

Other generic SDK/local games can configure a different number of players and a fixed, non-increasing reward for each placement. At the turn limit, unfinished players share the rewards for the places still open. For example, with default scoring, if only the first player has finished, the other three each receive 2 points (the remaining 3 + 2 + 1 points divided three ways).

## Information and event handling

You can see your hand, public claims and counts, player hand sizes, pile size, challenge results, and confirmed finishes. Other players' hands, hidden pile cards, and sealed challenge choices are private. A claim accepted without a challenge is not proof that it was truthful.

In SDK or event play, a malformed, missing, late, or illegal agent response is replaced by a deterministic legal fallback. On a placement fault, the fallback places one lowest-ranked card and declares its actual rank; on a challenge fault, it accepts. A permitted bluff is a legal move, not a protocol fault. See the [rules and evaluation guide](rules-evaluation.md) and [protocol guide](protocol.md) for submission behavior.

## Execution and submission limits

Algorithms and non-language ML models have the same limits: **1 GiB RAM**,
**1 GiB GPU VRAM** when using a GPU, and **1.5 GiB** for the complete frozen
submission and final runtime image. These are binary units (GiB); source size
is measured without Git metadata and image size includes runtime dependencies.
The existing configured turn limit and sharing of remaining placement points
remain in effect; there is no new one-point penalty. See
[resource limits](resource-limits.md) for enforcement and the pre-submission checker.
