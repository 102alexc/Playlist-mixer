"""
Minimal Spotify Web API client built on `requests`.

Only the handful of endpoints this app needs are wrapped. Paths follow the
February 2026 API changes for Development Mode apps:

  GET  /me                       -> who is logged in
  GET  /playlists/{id}           -> playlist name/owner (metadata)
  GET  /playlists/{id}/items     -> the tracks (was /tracks before 2026)
  POST /me/playlists             -> create a playlist (was /users/{id}/playlists)
  POST /playlists/{id}/items     -> add tracks (was /tracks)
  GET  /audio-features?ids=...   -> tempo/key/energy... (403 for most apps
                                    created after Nov 27, 2024; see features.py)

Development Mode note: Spotify only returns the contents of playlists the
logged-in user OWNS or COLLABORATES ON. To sort someone else's playlist,
save a copy to your library in the Spotify app first.
"""
from __future__ import annotations

import re
import time
from typing import Iterable, Iterator, List, Optional

import requests

from ..models import Track

API_BASE = "https://api.spotify.com/v1"


class SpotifyAPIError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"Spotify API error {status}: {message}")
        self.status = status
        self.message = message


# Accepts all the ways people share a playlist:
#   https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abc
#   https://open.spotify.com/intl-es/playlist/37i9dQZF1DXcBWIGoYBM5M
#   spotify:playlist:37i9dQZF1DXcBWIGoYBM5M
#   37i9dQZF1DXcBWIGoYBM5M  (bare ID)
_PLAYLIST_RE = re.compile(r"playlist[/:]([A-Za-z0-9]{22})")
_BARE_ID_RE = re.compile(r"[A-Za-z0-9]{22}")


def parse_playlist_id(text: str) -> Optional[str]:
    """Extract the 22-character base-62 playlist ID, or None if not found."""
    text = text.strip()
    match = _PLAYLIST_RE.search(text)
    if match:
        return match.group(1)
    return text if _BARE_ID_RE.fullmatch(text) else None


def chunked(items: List, size: int) -> Iterator[List]:
    """Yield successive `size`-length slices (APIs cap batch sizes)."""
    for i in range(0, len(items), size):
        yield items[i:i + size]


class SpotifyClient:
    def __init__(self, access_token: str):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {access_token}"

    # ---- low-level -------------------------------------------------------

    def _request(self, method: str, path_or_url: str, *, max_retries: int = 3, **kwargs) -> dict:
        """
        Send a request and return the decoded JSON body.

        Handles 429 Too Many Requests by sleeping for the `Retry-After`
        seconds Spotify tells us, then retrying.
        """
        url = path_or_url if path_or_url.startswith("http") else API_BASE + path_or_url
        for attempt in range(max_retries + 1):
            resp = self.session.request(method, url, timeout=20, **kwargs)
            if resp.status_code == 429 and attempt < max_retries:
                wait = int(resp.headers.get("Retry-After", "2"))
                time.sleep(min(wait, 30))
                continue
            break

        if resp.status_code >= 400:
            try:
                message = resp.json().get("error", {}).get("message", resp.text)
            except ValueError:
                message = resp.text or resp.reason
            raise SpotifyAPIError(resp.status_code, message)

        return resp.json() if resp.content else {}

    # ---- reading ---------------------------------------------------------

    def me(self) -> dict:
        return self._request("GET", "/me")

    def get_playlist_meta(self, playlist_id: str) -> dict:
        """Name, owner and cover image. Works for any playlist."""
        data = self._request("GET", f"/playlists/{playlist_id}")
        images = data.get("images") or []
        return {
            "id": data["id"],
            "name": data.get("name", ""),
            "owner": (data.get("owner") or {}).get("display_name", ""),
            "image_url": images[0]["url"] if images else "",
        }

    def get_playlist_tracks(self, playlist_id: str) -> List[Track]:
        """
        All tracks in a playlist, following pagination.

        Spotify returns at most 100 items per page plus a `next` URL for
        the following page; we keep requesting until `next` is null.
        Local files and podcast episodes are skipped: they have no audio
        features and cannot always be re-added to a new playlist.
        """
        tracks: List[Track] = []
        url: Optional[str] = f"/playlists/{playlist_id}/items?limit=100"
        while url:
            page = self._request("GET", url)
            for entry in page.get("items", []):
                # Field was renamed `track` -> `item` in 2026; accept both.
                obj = entry.get("item") or entry.get("track")
                if not obj or obj.get("type") != "track" or entry.get("is_local"):
                    continue
                if not obj.get("id"):
                    continue
                album = obj.get("album") or {}
                images = album.get("images") or []
                tracks.append(
                    Track(
                        id=obj["id"],
                        uri=obj["uri"],
                        name=obj.get("name", ""),
                        artists=[a.get("name", "") for a in obj.get("artists", [])],
                        album=album.get("name", ""),
                        # Smallest image = last in the list; ideal for thumbnails.
                        image_url=images[-1]["url"] if images else "",
                        duration_ms=obj.get("duration_ms", 0),
                    )
                )
            url = page.get("next")
        return tracks

    def get_audio_features(self, track_ids: List[str]) -> List[Optional[dict]]:
        """Spotify's own batch endpoint (100 IDs max). Raises SpotifyAPIError(403) if blocked."""
        results: List[Optional[dict]] = []
        for batch in chunked(track_ids, 100):
            data = self._request("GET", "/audio-features", params={"ids": ",".join(batch)})
            results.extend(data.get("audio_features", []))
        return results

    # ---- writing ---------------------------------------------------------

    def create_playlist(self, name: str, description: str = "", public: bool = False) -> dict:
        return self._request(
            "POST",
            "/me/playlists",
            json={"name": name, "description": description, "public": public},
        )

    def add_items(self, playlist_id: str, uris: Iterable[str]) -> None:
        """Append tracks in order. Spotify accepts at most 100 URIs per call."""
        for batch in chunked(list(uris), 100):
            self._request("POST", f"/playlists/{playlist_id}/items", json={"uris": batch})
