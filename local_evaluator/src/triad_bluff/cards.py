"""Physical cards and canonical ordering for Triad Bluff.

Card identities stay inside the evaluator. Participant observations contain only
rank, suit, and request-local ``hN`` references.
"""

from __future__ import annotations

from dataclasses import dataclass

RANKS: tuple[str, ...] = (
    "A",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "J",
    "Q",
    "K",
)
SUITS: tuple[str, ...] = ("clubs", "diamonds", "hearts", "spades")
RANK_INDEX = {rank: i for i, rank in enumerate(RANKS)}
SUIT_INDEX = {suit: i for i, suit in enumerate(SUITS)}
DECK_SIZE = 52


@dataclass(frozen=True, slots=True)
class Card:
    """One physical card. ``uid`` is organizer-only."""

    rank: str
    suit: str
    uid: int

    def to_public_dict(self) -> dict[str, str]:
        return {"rank": self.rank, "suit": self.suit}

    def sort_key(self) -> tuple[int, int, int]:
        return (RANK_INDEX[self.rank], SUIT_INDEX[self.suit], self.uid)

    def label(self) -> str:
        return f"{self.rank} of {self.suit}"


def build_canonical_deck(decks: int = 1) -> list[Card]:
    if type(decks) is not int or not 1 <= decks <= 8:
        raise ValueError("decks must be an integer from 1 to 8")
    cards = [
        Card(rank, suit, i)
        for i, (rank, suit) in enumerate(
            (rank, suit) for rank in RANKS for suit in SUITS
        )
    ]
    cards = [
        Card(card.rank, card.suit, copy * DECK_SIZE + card.uid)
        for copy in range(decks)
        for card in cards
    ]
    assert len(cards) == DECK_SIZE * decks
    return cards


def canonical_cards(cards: list[Card]) -> list[Card]:
    return sorted(cards, key=Card.sort_key)


def rank_counts(cards: list[Card]) -> dict[str, int]:
    result = dict.fromkeys(RANKS, 0)
    for card in cards:
        result[card.rank] += 1
    return result


def lowest_card(cards: list[Card]) -> Card:
    if not cards:
        raise ValueError("cannot select a card from an empty hand")
    return min(cards, key=Card.sort_key)
