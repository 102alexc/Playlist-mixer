"""
End-to-end route tests with Spotify replaced by a fake client, so they run
offline and without credentials. A good template for testing your own
changes to the web layer.
"""
import time

import pytest

from playlist_sorter import app as app_module
from playlist_sorter.config import Settings
from playlist_sorter.models import Track

PLAYLIST_ID = "37i9dQZF1DXcBWIGoYBM5M"


class FakeClient:
    created = {}

    def __init__(self, token):
        pass

    def get_playlist_meta(self, pid):
        return {"id": pid, "name": "Test Mix", "owner": "me", "image_url": ""}

    def get_playlist_tracks(self, pid):
        return [Track(id=f"t{i}", uri=f"spotify:track:t{i}", name=f"Song {i}", artists=["A"])
                for i in range(3)]

    def create_playlist(self, name, description="", public=False):
        FakeClient.created = {"name": name, "uris": []}
        return {"id": "new", "external_urls": {"spotify": "https://open.spotify.com/playlist/new"}}

    def add_items(self, pid, uris):
        FakeClient.created["uris"] = list(uris)


def fake_features(tracks, client, provider):
    for t, (bpm, key, mode, energy, valence) in zip(
        tracks, [(128, 9, 0, .8, .7), (90, 0, 1, .2, .3), (110, 4, 0, .5, .6)]
    ):
        t.tempo, t.key, t.mode, t.energy, t.valence = bpm, key, mode, energy, valence
    return "Fake"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_module, "load_settings", lambda: Settings(
        "id", "secret", "http://127.0.0.1:8000/callback", "test-key", "auto"))
    monkeypatch.setattr(app_module, "SpotifyClient", FakeClient)
    monkeypatch.setattr(app_module, "attach_features", fake_features)
    app_module._playlist_cache.clear()
    flask_app = app_module.create_app()
    flask_app.config["TESTING"] = True
    c = flask_app.test_client()
    with c.session_transaction() as s:
        s["token_info"] = {"access_token": "x", "refresh_token": "y", "expires_at": time.time() + 3600}
        s["user_id"] = "me"
    return c


def test_bpm_sort_page(client):
    resp = client.get(f"/playlist?url=https://open.spotify.com/playlist/{PLAYLIST_ID}&strategy=bpm_asc")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert html.index("Song 1") < html.index("Song 2") < html.index("Song 0")
    assert "8A" in html and "8B" in html  # Camelot codes rendered


def test_export_uses_sorted_order(client):
    client.get(f"/playlist?url={PLAYLIST_ID}&strategy=bpm_desc")
    resp = client.post("/export", data={"playlist_id": PLAYLIST_ID, "strategy": "bpm_desc", "name": "X"})
    assert resp.status_code == 200
    assert FakeClient.created["uris"] == ["spotify:track:t0", "spotify:track:t2", "spotify:track:t1"]


def test_unconfigured_redirects_to_setup(monkeypatch):
    monkeypatch.setattr(app_module, "load_settings", lambda: Settings("", "", "http://127.0.0.1:8000/callback", "k", "auto"))
    resp = app_module.create_app().test_client().get("/")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/setup")


def test_manual_override_fills_missing_track(client, tmp_path, monkeypatch):
    from playlist_sorter import overrides
    monkeypatch.setattr(overrides, "OVERRIDES_PATH", tmp_path / "overrides.json")

    def partial_features(tracks, c, p):  # provider knows nothing about t0
        fake_features(tracks, c, p)
        tracks[0].tempo = tracks[0].key = tracks[0].mode = tracks[0].energy = tracks[0].valence = None
        return "Fake"
    monkeypatch.setattr(app_module, "attach_features", partial_features)
    base = {"track_id": "t0", "playlist_url": PLAYLIST_ID, "strategy": "bpm_asc"}

    # An invalid Camelot code is rejected and nothing is saved.
    client.post("/override", data={**base, "bpm": "100", "key": "99Z"})
    assert overrides.load_all() == {}

    # Valid values are stored: 5A = C minor (pitch class 0); percentages become 0-1.
    client.post("/override", data={**base, "bpm": "70", "key": "5a", "energy": "40", "valence": ""})
    assert overrides.load_all() == {"t0": {"tempo": 70.0, "key": 0, "mode": 0, "energy": 0.4}}

    # The track now sorts by its manual BPM (70 is slowest) and is marked as edited.
    html = client.get(f"/playlist?url={PLAYLIST_ID}&strategy=bpm_asc").get_data(as_text=True)
    assert html.index("Song 0") < html.index("Song 1")
    assert "5A" in html and "✎" in html

    client.post("/override", data={**base, "action": "clear"})
    assert overrides.load_all() == {}
