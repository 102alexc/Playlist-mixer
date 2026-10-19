"""
Manual audio-feature overrides, saved to `overrides.json` next to `.env`.

Why: neither Spotify nor ReccoBeats knows every track. Here you can type in
BPM / key / energy / valence yourself (e.g. read off the Spotify desktop
app, which shows BPM and key) and the app remembers it across restarts.

File format (keyed by Spotify track ID, so it works in any playlist):
    {"4uLU6hMCjMI75M1A2tKUQC": {"tempo": 105.0, "key": 9, "mode": 0,
                                "energy": 0.6, "valence": null}}
Only the fields you filled in are stored; empty ones fall back to whatever
the provider found (or stay unknown).
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Dict, List, Optional

from .analysis import camelot
from .config import PROJECT_ROOT
from .models import Track

OVERRIDES_PATH = PROJECT_ROOT / "overrides.json"
FIELDS = ("tempo", "key", "mode", "energy", "valence")


def load_all() -> Dict[str, dict]:
    """Read the file; a missing or corrupt file just means 'no overrides'."""
    try:
        return json.loads(OVERRIDES_PATH.read_text())
    except (OSError, ValueError):
        return {}


def _save_all(data: Dict[str, dict]) -> None:
    # Write to a temp file then rename, so a crash can't leave half a file.
    fd, tmp = tempfile.mkstemp(dir=OVERRIDES_PATH.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, OVERRIDES_PATH)


def set_override(track_id: str, values: dict) -> None:
    """Store non-empty fields for a track; an empty dict removes the override."""
    data = load_all()
    clean = {k: v for k, v in values.items() if k in FIELDS and v is not None}
    if clean:
        data[track_id] = clean
    else:
        data.pop(track_id, None)
    _save_all(data)


def clear_override(track_id: str) -> None:
    set_override(track_id, {})


def apply_overrides(tracks: List[Track]) -> None:
    """Overwrite features on tracks that have an override; flag them in `extra`."""
    data = load_all()
    for t in tracks:
        values = data.get(t.id)
        if not values:
            continue
        for field in FIELDS:
            if values.get(field) is not None:
                setattr(t, field, values[field])
        t.manual = True


# ---- parsing what the user typed in the form -----------------------------

class OverrideInputError(ValueError):
    pass


def _number(text: str, low: float, high: float, label: str) -> Optional[float]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        raise OverrideInputError(f"{label} must be a number.")
    if not low <= value <= high:
        raise OverrideInputError(f"{label} must be between {low:g} and {high:g}.")
    return value


def parse_form(bpm: str, key: str, energy: str, valence: str) -> dict:
    """
    Turn raw form strings into override values. Blank = not provided.
    Key is a Camelot code (e.g. 8A), which is what the table displays.
    Energy and valence are typed as 0-100 and stored as 0-1.
    """
    values: dict = {"tempo": _number(bpm, 30, 300, "BPM")}

    key = (key or "").strip().upper()
    if key:
        parsed = camelot.from_camelot(key)
        if parsed is None:
            raise OverrideInputError("Key must be a Camelot code like 8A or 11B.")
        values["key"], values["mode"] = parsed

    for name, raw in (("energy", energy), ("valence", valence)):
        num = _number(raw, 0, 100, name.capitalize())
        values[name] = None if num is None else num / 100
    return values
