"""The single scoring implementation used by games, reports, and replays."""

from __future__ import annotations

BASE_POINTS = (5.0, 3.0, 2.0, 1.0)


def points_for(
    placements: list[int],
    unfinished: list[int],
    reason: str,
    rewards: tuple[float, ...] = BASE_POINTS,
) -> dict[int, float]:
    """Return points for every seat, including partial cap ties."""
    points = {seat: rewards[i] for i, seat in enumerate(placements)}
    if not unfinished:
        return {seat: points.get(seat, 0.0) for seat in range(len(rewards))}
    remaining = sum(rewards[len(placements) :])
    share = remaining / len(unfinished)
    for seat in unfinished:
        points[seat] = share
    return {seat: points.get(seat, 0.0) for seat in range(len(rewards))}


def rank_points(points: dict[int, float]) -> list[int]:
    return sorted(points, key=lambda seat: (-points[seat], seat))
