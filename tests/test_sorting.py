from playlist_sorter.analysis.mood import cluster_moods
from playlist_sorter.models import Track
from playlist_sorter.sorting import (annotate, bpm_ascending, bpm_descending,
                                     bpm_gap_percent, camelot_harmonic, mood_build)
from playlist_sorter.spotify.client import parse_playlist_id


def make(name, tempo=None, key=None, mode=None, energy=None, valence=None):
    return Track(id=name, uri=f"spotify:track:{name}", name=name, artists=["x"],
                 tempo=tempo, key=key, mode=mode, energy=energy, valence=valence)


def names(tracks):
    return [t.name for t in tracks]


def test_bpm_sorts_and_puts_unknown_last():
    tracks = [make("fast", 140, energy=.5), make("none"), make("slow", 90, energy=.5)]
    assert names(bpm_ascending(tracks)) == ["slow", "fast", "none"]
    assert names(bpm_descending(tracks)) == ["fast", "slow", "none"]


def test_half_time_counts_as_close():
    assert bpm_gap_percent(70, 140) == 0
    assert round(bpm_gap_percent(120, 126)) == 5


def test_camelot_path_prefers_compatible_keys():
    tracks = [
        make("start", 100, key=9, mode=0, energy=.3),   # 8A, slowest -> first
        make("clash", 101, key=3, mode=0, energy=.5),   # 2A, opposite side
        make("fifth", 102, key=4, mode=0, energy=.5),   # 9A, one step from 8A
        make("rel", 101, key=0, mode=1, energy=.5),     # 8B, relative of 8A
    ]
    annotate(tracks)
    order = names(camelot_harmonic(tracks))
    assert order[0] == "start"
    assert order[-1] == "clash"


def test_mood_clusters_follow_quadrants():
    points = [(0.9, 0.9), (0.8, 0.85), (0.1, 0.1), (0.15, 0.2), (0.2, 0.9), (0.8, 0.2)]
    moods = [m.name for m in cluster_moods(points)[0]]
    assert moods == ["Happy", "Happy", "Sad", "Sad", "Intense", "Chill"]


def test_mood_build_goes_calm_to_intense():
    tracks = [make("party", energy=.9, valence=.9), make("ballad", energy=.1, valence=.1),
              make("unknown")]
    annotate(tracks)
    assert names(mood_build(tracks)) == ["ballad", "party", "unknown"]
    assert tracks[2].mood == "Unknown"


def test_parse_playlist_id():
    pid = "37i9dQZF1DXcBWIGoYBM5M"
    assert parse_playlist_id(f"https://open.spotify.com/playlist/{pid}?si=abc123") == pid
    assert parse_playlist_id(f"https://open.spotify.com/intl-es/playlist/{pid}") == pid
    assert parse_playlist_id(f"spotify:playlist:{pid}") == pid
    assert parse_playlist_id(pid) == pid
    assert parse_playlist_id("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC") is None
    assert parse_playlist_id("hello") is None
