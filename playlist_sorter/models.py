"""
The one data type the whole app passes around: a Track.

Fields fall into three groups:
  * identity/metadata  — straight from Spotify's playlist response
  * audio features     — from the features provider (may be missing!)
  * derived labels     — computed by us (Camelot code, mood)

Missing features are `None` rather than 0, so sorting code can tell
"unknown" apart from "really 0" and push unknown tracks to the end.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class Track:
    id: str
    uri: str
    name: str
    artists: List[str]
    album: str = ""
    image_url: str = ""
    duration_ms: int = 0

    # Audio features (Spotify's definitions):
    tempo: Optional[float] = None    # beats per minute
    key: Optional[int] = None        # pitch class 0=C, 1=C#/Db ... 11=B; -1 = unknown
    mode: Optional[int] = None       # 1 = major, 0 = minor
    energy: Optional[float] = None   # 0.0 (calm) .. 1.0 (intense)
    valence: Optional[float] = None  # 0.0 (sad/dark) .. 1.0 (happy/bright)

    # Derived by our analysis modules:
    camelot: Optional[str] = None    # e.g. "8A"
    mood: Optional[str] = None       # e.g. "Happy"
    extra: dict = field(default_factory=dict)  # per-strategy notes (e.g. transition info)
    manual: bool = False             # True if the user typed values in (see overrides.py)

    @property
    def has_features(self) -> bool:
        return self.tempo is not None

    @property
    def artist_str(self) -> str:
        return ", ".join(self.artists)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        return cls(**data)
