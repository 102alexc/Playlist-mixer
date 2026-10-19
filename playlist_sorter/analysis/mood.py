"""
Mood from valence and energy.

Spotify gives two 0..1 numbers that together map onto the classic
"circumplex" model of emotion (Russell, 1980):

                 energy ↑
      Intense    |    Happy
      (angry,    |    (upbeat,
       tense)    |     euphoric)
    -------------+-------------→ valence
      Sad        |    Chill
      (dark,     |    (content,
       mellow)   |     relaxed)

We group tracks with k-means clustering, implemented by hand below.
Each cluster starts at one of these four mood "prototypes" and keeps that
mood's name, so cluster labels stay meaningful. The clusters then move to
fit the real data, so on a playlist with only upbeat songs the "Sad"
cluster drifts toward "least happy of the bunch" instead of being empty.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

Point = Tuple[float, float]  # (valence, energy)


@dataclass(frozen=True)
class Mood:
    name: str
    emoji: str
    prototype: Point  # starting centroid (valence, energy)


MOODS: List[Mood] = [
    Mood("Sad", "🌧", (0.2, 0.25)),
    Mood("Chill", "🌿", (0.7, 0.3)),
    Mood("Happy", "☀️", (0.75, 0.75)),
    Mood("Intense", "🔥", (0.25, 0.8)),
]


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _mean(points: Sequence[Point]) -> Point:
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def kmeans(points: Sequence[Point], initial: Sequence[Point], max_iter: int = 50) -> Tuple[List[int], List[Point]]:
    """
    Lloyd's k-means algorithm in its simplest form.

    Repeat until nothing changes:
      1. Assignment: each point joins its nearest centroid.
      2. Update: each centroid moves to the mean of its points.

    Returns (assignment per point, final centroids). An empty cluster
    keeps its previous centroid. With fixed starting centroids the result
    is deterministic, so the same playlist always sorts the same way.
    """
    centroids = list(initial)
    assignment = [-1] * len(points)
    for _ in range(max_iter):
        new_assignment = [
            min(range(len(centroids)), key=lambda c: _dist(p, centroids[c])) for p in points
        ]
        if new_assignment == assignment:
            break  # converged
        assignment = new_assignment
        for c in range(len(centroids)):
            members = [p for p, a in zip(points, assignment) if a == c]
            if members:
                centroids[c] = _mean(members)
    return assignment, centroids


def cluster_moods(points: Sequence[Point]) -> Tuple[List[Mood], List[Point]]:
    """Return the Mood for each point plus each mood's final centroid."""
    if not points:
        return [], [m.prototype for m in MOODS]
    assignment, centroids = kmeans(points, [m.prototype for m in MOODS])
    return [MOODS[a] for a in assignment], centroids


def quadrant_mood(valence: float, energy: float) -> Mood:
    """No-clustering fallback: the mood whose prototype is closest."""
    return min(MOODS, key=lambda m: _dist((valence, energy), m.prototype))
