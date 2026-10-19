"""
Sorting strategies.

Every strategy is a plain function   List[Track] -> List[Track]
registered in the STRATEGIES dict below. The web layer just looks up the
name the user picked and calls it, so adding a new strategy only takes
a function plus one dict entry.

Rule shared by all strategies: tracks without audio features can't be
placed meaningfully, so they keep their original relative order and go
at the END of the list.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

from .analysis import camelot
from .analysis.mood import cluster_moods
from .models import Track

SortFn = Callable[[List[Track]], List[Track]]


# --------------------------------------------------------------------------
# Annotation: compute Camelot code + mood once, for every strategy to show.
# --------------------------------------------------------------------------

def annotate(tracks: List[Track]) -> None:
    """Set `track.camelot` and `track.mood` in place."""
    for t in tracks:
        t.camelot = camelot.to_camelot(t.key, t.mode)

    # Mood clustering needs the whole playlist at once, because k-means
    # adapts the clusters to this specific set of songs.
    with_mood = [t for t in tracks if t.valence is not None and t.energy is not None]
    moods, _ = cluster_moods([(t.valence, t.energy) for t in with_mood])
    for t, mood in zip(with_mood, moods):
        t.mood = mood.name
    for t in tracks:
        if t.mood is None:
            t.mood = "Unknown"


def _split(tracks: List[Track], has: Callable[[Track], bool]) -> Tuple[List[Track], List[Track]]:
    """Partition into (usable, unusable) while keeping the original order."""
    return [t for t in tracks if has(t)], [t for t in tracks if not has(t)]


def _clear_notes(tracks: List[Track]) -> None:
    for t in tracks:
        t.extra = {}


# --------------------------------------------------------------------------
# Strategy 0: keep the playlist as it is.
# --------------------------------------------------------------------------

def original(tracks: List[Track]) -> List[Track]:
    _clear_notes(tracks)
    return list(tracks)


# --------------------------------------------------------------------------
# Strategy 1 & 2: BPM ascending / descending.
# --------------------------------------------------------------------------

def bpm_ascending(tracks: List[Track]) -> List[Track]:
    _clear_notes(tracks)
    known, unknown = _split(tracks, lambda t: t.tempo is not None)
    # Python's sort is stable, and tuples compare element by element:
    # equal BPMs are ordered by energy as a tie-breaker.
    return sorted(known, key=lambda t: (t.tempo, t.energy or 0)) + unknown


def bpm_descending(tracks: List[Track]) -> List[Track]:
    _clear_notes(tracks)
    known, unknown = _split(tracks, lambda t: t.tempo is not None)
    return sorted(known, key=lambda t: (t.tempo, t.energy or 0), reverse=True) + unknown


# --------------------------------------------------------------------------
# Strategy 3: harmonic mixing along the Camelot wheel.
# --------------------------------------------------------------------------

# How much a BPM jump "costs" compared with one step on the Camelot wheel.
# 6% tempo change ~ the most a DJ can pitch a track without it sounding off,
# so we make a 6% jump cost the same as one key step.
BPM_PERCENT_PER_KEY_STEP = 6.0


def bpm_gap_percent(a: float, b: float) -> float:
    """
    Percentage tempo difference, counting half/double time as a match:
    a 70 BPM track mixes fine with a 140 BPM one (every other beat lines up).
    """
    if not a or not b:
        return 100.0
    return min(abs(a - cand) / a * 100 for cand in (b, b * 2, b / 2))


def transition_score(a: Track, b: Track) -> float:
    """Lower = better. Key distance plus a scaled BPM penalty."""
    key_cost = camelot.transition_cost(a.camelot, b.camelot)
    bpm_cost = bpm_gap_percent(a.tempo, b.tempo) / BPM_PERCENT_PER_KEY_STEP
    return key_cost + bpm_cost


def camelot_harmonic(tracks: List[Track]) -> List[Track]:
    """
    Build a mix order where each track flows into the next.

    Finding the best ordering is a Travelling Salesman Problem
    (exponential), so we use the classic greedy "nearest neighbour"
    heuristic, which is O(n²) and good enough for playlists:

      1. Start from the slowest, calmest track (a natural warm-up).
      2. Repeatedly append the unused track with the lowest
         transition_score from the current one.
      3. Tie-break toward slightly higher energy so the mix builds up.
    """
    _clear_notes(tracks)
    usable, rest = _split(tracks, lambda t: t.camelot is not None and t.tempo is not None)
    if not usable:
        return rest

    remaining = list(usable)
    current = min(remaining, key=lambda t: (t.tempo, t.energy or 0))
    remaining.remove(current)
    order = [current]
    current.extra = {"transition": "start"}

    while remaining:
        prev = current
        current = min(
            remaining,
            key=lambda t: (transition_score(prev, t), -(t.energy or 0)),
        )
        remaining.remove(current)
        current.extra = {
            "transition": f"{prev.camelot}→{current.camelot} · "
                          f"{camelot.describe_transition(prev.camelot, current.camelot)}",
            "smooth": camelot.transition_cost(prev.camelot, current.camelot) <= 1,
        }
        order.append(current)
    return order + rest


# --------------------------------------------------------------------------
# Strategy 4 & 5: mood journey (valence/energy clusters).
# --------------------------------------------------------------------------

def _mood_order(tracks: List[Track], reverse: bool) -> List[Track]:
    """
    Group tracks by mood cluster, order clusters from calm to intense (by
    their average energy) and, inside each cluster, order by energy then
    valence. The result plays like a gradual "build" (or a wind-down when
    reversed) instead of jumping between moods.
    """
    _clear_notes(tracks)
    known, unknown = _split(tracks, lambda t: t.valence is not None and t.energy is not None)

    groups: Dict[str, List[Track]] = {}
    for t in known:
        groups.setdefault(t.mood, []).append(t)

    def avg_energy(group: List[Track]) -> float:
        return sum(t.energy for t in group) / len(group)

    cluster_names = sorted(groups, key=lambda name: avg_energy(groups[name]), reverse=reverse)
    result: List[Track] = []
    for name in cluster_names:
        members = sorted(groups[name], key=lambda t: (t.energy, t.valence), reverse=reverse)
        result.extend(members)
    return result + unknown


def mood_build(tracks: List[Track]) -> List[Track]:
    return _mood_order(tracks, reverse=False)


def mood_wind_down(tracks: List[Track]) -> List[Track]:
    return _mood_order(tracks, reverse=True)


# --------------------------------------------------------------------------
# Registry used by the web layer.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Strategy:
    label: str
    description: str
    fn: SortFn


STRATEGIES: Dict[str, Strategy] = {
    "original": Strategy("Original order", "As it is on Spotify.", original),
    "bpm_asc": Strategy("BPM ↑ ascending", "Slowest to fastest.", bpm_ascending),
    "bpm_desc": Strategy("BPM ↓ descending", "Fastest to slowest.", bpm_descending),
    "camelot": Strategy(
        "Harmonic (Camelot)",
        "Each track moves to a compatible key with a close tempo.",
        camelot_harmonic,
    ),
    "mood_build": Strategy(
        "Mood: calm → intense",
        "Clusters by valence + energy, building up.",
        mood_build,
    ),
    "mood_down": Strategy(
        "Mood: intense → calm",
        "Same clusters, winding down.",
        mood_wind_down,
    ),
}


def apply_strategy(name: str, tracks: List[Track]) -> List[Track]:
    strategy = STRATEGIES.get(name, STRATEGIES["original"])
    return strategy.fn(tracks)
