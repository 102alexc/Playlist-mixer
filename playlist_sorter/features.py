"""
Audio-feature providers.

Why this module exists: on Nov 27, 2024 Spotify closed `/audio-features`
to new apps (it returns 403). Apps approved earlier still get data, so we
support two interchangeable sources behind one function:

  * SpotifyFeatures    — the official endpoint, if your app still has access
  * ReccoBeatsFeatures — https://reccobeats.com, a free, keyless API that
                          accepts Spotify track IDs and returns the same
                          fields (tempo, key, mode, energy, valence)

Both are "providers": objects with a `fetch(track_ids) -> {id: features}`
method. `attach_features()` picks one based on the FEATURES_PROVIDER
setting and copies the values onto our Track objects. In "auto" mode it
tries Spotify first and falls back to ReccoBeats on a 403.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

import requests

from .models import Track
from .spotify.client import SpotifyAPIError, SpotifyClient, chunked

log = logging.getLogger(__name__)

FeatureMap = Dict[str, dict]  # spotify track id -> {"tempo":..., "key":..., ...}

FEATURE_FIELDS = ("tempo", "key", "mode", "energy", "valence")


class SpotifyFeatures:
    name = "Spotify"

    def __init__(self, client: SpotifyClient):
        self.client = client

    def fetch(self, track_ids: List[str]) -> FeatureMap:
        out: FeatureMap = {}
        for item in self.client.get_audio_features(track_ids):
            if item:  # Spotify returns null for tracks it has no data for
                out[item["id"]] = {f: item.get(f) for f in FEATURE_FIELDS}
        return out


class ReccoBeatsFeatures:
    name = "ReccoBeats"
    URL = "https://api.reccobeats.com/v1/audio-features"
    BATCH_SIZE = 40  # the API answers 400 Bad Request above 40 IDs

    def fetch(self, track_ids: List[str]) -> FeatureMap:
        out: FeatureMap = {}
        for batch in chunked(track_ids, self.BATCH_SIZE):
            resp = self._get(batch)
            for item in resp.get("content", []):
                # `id` is ReccoBeats' own UUID; the Spotify ID is the last
                # path segment of `href` ("https://open.spotify.com/track/<id>").
                spotify_id = (item.get("href") or "").rstrip("/").split("/")[-1]
                if spotify_id:
                    out[spotify_id] = {f: item.get(f) for f in FEATURE_FIELDS}
        return out

    def _get(self, batch: List[str], retries: int = 3) -> dict:
        for attempt in range(retries + 1):
            resp = requests.get(self.URL, params={"ids": ",".join(batch)}, timeout=20)
            if resp.status_code == 429 and attempt < retries:
                time.sleep(min(int(resp.headers.get("Retry-After", "2")), 30))
                continue
            if resp.status_code == 404:
                return {}  # none of the IDs in this batch are known
            resp.raise_for_status()
            return resp.json()
        return {}


def attach_features(tracks: List[Track], client: SpotifyClient, provider: str = "auto") -> str:
    """
    Fill tempo/key/mode/energy/valence on each Track in place.
    Returns the name of the provider that was used (shown in the UI).
    Tracks the provider does not know about keep `None` values.
    """
    ids = [t.id for t in tracks]
    features: Optional[FeatureMap] = None
    used = ""

    if provider in ("auto", "spotify"):
        try:
            features = SpotifyFeatures(client).fetch(ids)
            used = SpotifyFeatures.name
        except SpotifyAPIError as err:
            if provider == "spotify" or err.status != 403:
                raise
            log.info("Spotify /audio-features returned 403; falling back to ReccoBeats")

    if features is None:
        features = ReccoBeatsFeatures().fetch(ids)
        used = ReccoBeatsFeatures.name

    for track in tracks:
        values = features.get(track.id)
        if not values:
            continue
        track.tempo = values.get("tempo")
        track.key = values.get("key")
        track.mode = values.get("mode")
        track.energy = values.get("energy")
        track.valence = values.get("valence")
    return used
