"""
Spotify key/mode  ->  Camelot wheel notation, plus a compatibility score.

Spotify describes a track's key with two integers:
  key  = pitch class, 0..11 (0=C, 1=C#/Db, 2=D, ... 11=B), -1 if unknown
  mode = 1 for major, 0 for minor

The Camelot wheel is the circle of fifths re-labelled for DJs: 12 numbers
(the "hours" of a clock) times two letters:
  B = major keys (outer ring), A = minor keys (inner ring)

Moving one hour around the wheel = moving a perfect fifth, and every key
shares 6 of its 7 notes with its neighbours, so those transitions sound
smooth. Rules of thumb for harmonic mixing from a track at 8A:
  8A -> 8A   same key                    (perfect)
  8A -> 7A/9A one step, same letter       (perfect fifth / fourth)
  8A -> 8B   same number, other letter    (relative major/minor)
  8A -> 10A  two steps ("energy boost")   (works, adds tension)
  anything further sounds increasingly clashy.
"""
from __future__ import annotations

from typing import Optional, Tuple

PITCH_NAMES = ["C", "C♯/D♭", "D", "D♯/E♭", "E", "F", "F♯/G♭", "G", "G♯/A♭", "A", "A♯/B♭", "B"]

# Written out in full so you can check it against any Camelot chart.
# Index = Spotify pitch class.
MAJOR_TO_CAMELOT = [8, 3, 10, 5, 12, 7, 2, 9, 4, 11, 6, 1]   # C major = 8B, G major = 9B...
MINOR_TO_CAMELOT = [5, 12, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10]   # A minor = 8A, E minor = 9A...

# The tables follow a pattern: one step on the wheel = +7 semitones
# (a fifth), and 7 is its own inverse mod 12 (7*7 = 49 = 1 mod 12), so:
#     major number = (7 * pitch + 8) mod 12   (0 is shown as 12)
#     minor number = (7 * pitch + 5) mod 12
# tests/test_camelot.py checks that the formula and the tables agree.


def to_camelot(key: Optional[int], mode: Optional[int]) -> Optional[str]:
    """(9, 0) -> '8A'. Returns None when Spotify doesn't know the key."""
    if key is None or mode is None or not 0 <= key <= 11:
        return None
    if mode == 1:
        return f"{MAJOR_TO_CAMELOT[key]}B"
    return f"{MINOR_TO_CAMELOT[key]}A"


def from_camelot(code: str) -> Optional[Tuple[int, int]]:
    """Inverse of to_camelot: '8A' -> (9, 0). None if the code is invalid."""
    code = (code or "").strip().upper()
    if len(code) < 2 or code[-1] not in "AB" or not code[:-1].isdigit():
        return None
    number = int(code[:-1])
    if not 1 <= number <= 12:
        return None
    table, mode = (MAJOR_TO_CAMELOT, 1) if code[-1] == "B" else (MINOR_TO_CAMELOT, 0)
    return table.index(number), mode


def key_name(key: Optional[int], mode: Optional[int]) -> str:
    """Human-readable key, e.g. 'A minor'."""
    if key is None or mode is None or not 0 <= key <= 11:
        return "Unknown"
    return f"{PITCH_NAMES[key]} {'major' if mode == 1 else 'minor'}"


def parse_camelot(code: str) -> Tuple[int, str]:
    """'12B' -> (12, 'B')."""
    return int(code[:-1]), code[-1].upper()


def wheel_distance(a: int, b: int) -> int:
    """Steps between two numbers around a 12-hour clock (0..6)."""
    diff = abs(a - b) % 12
    return min(diff, 12 - diff)


def transition_cost(code_a: str, code_b: str) -> int:
    """
    How "far" two Camelot codes are, as a small integer. Lower = smoother.

        cost = steps around the wheel + (1 if switching major<->minor)

    This one line reproduces the DJ rules above:
        same key = 0, ±1 step = 1, relative major/minor = 1,
        ±2 steps = 2, diagonal (e.g. 8A->9B) = 2, ...
    """
    num_a, letter_a = parse_camelot(code_a)
    num_b, letter_b = parse_camelot(code_b)
    return wheel_distance(num_a, num_b) + (0 if letter_a == letter_b else 1)


def describe_transition(code_a: str, code_b: str) -> str:
    """Short label for the UI explaining why a transition works (or doesn't)."""
    num_a, letter_a = parse_camelot(code_a)
    num_b, letter_b = parse_camelot(code_b)
    steps = wheel_distance(num_a, num_b)
    if code_a == code_b:
        return "same key"
    if letter_a == letter_b and steps == 1:
        return "±1 step"
    if num_a == num_b:
        return "relative maj/min"
    if letter_a == letter_b and steps == 2:
        return "±2 steps (energy shift)"
    return "key clash" if transition_cost(code_a, code_b) > 2 else "diagonal"
