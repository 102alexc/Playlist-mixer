# Playlist Sorter

A small Flask app that takes a Spotify playlist link, looks up each track's
tempo, key, mode, energy and valence, and reorders the playlist by:

- **BPM**, ascending or descending
- **Harmonic mixing**: a path around the Camelot wheel where each track moves to a compatible key at a close tempo
- **Mood**: k-means clusters on valence and energy, played calm → intense or intense → calm

Each track shows its BPM, Camelot code and mood label. You can save the new
order back to Spotify as a new playlist.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py            # then open http://127.0.0.1:8000
```

On first launch the app sends you to **/setup**, which walks you through
creating a Spotify app and saves the credentials to `.env`. You can also run
`python setup_credentials.py` in the terminal, or copy `.env.example` to `.env`
and edit it by hand.

Run the tests (offline, no credentials needed):

```bash
python -m pytest
```

## Filling in missing tracks by hand

Some tracks aren't in any free database. Click **Add data** (or **Edit**) at the end of a row, then type the BPM and key (as a Camelot code such as `8A`; Spotify's desktop app shows BPM and key next to each track) and, optionally, energy and valence from 0 to 100. Values are saved to `overrides.json` by track ID, so they persist across restarts and apply in every playlist. Code: `playlist_sorter/overrides.py`.

## Spotify API limits you should know about (as of 2026)

| Limit | What the app does |
|---|---|
| `/audio-features` returns **403** for apps created after 27 Nov 2024 | `FEATURES_PROVIDER=auto` tries Spotify first, then falls back to [ReccoBeats](https://reccobeats.com), a free API with no key that accepts Spotify track IDs. |
| Development Mode apps can only read **playlists you own or collaborate on** | Shows a clear error. To sort someone else's playlist, copy its songs into a playlist you own. |
| Development Mode: owner needs **Premium**, max **5 users**, each added in *User Management* | Explained on the setup page. |
| Redirect URIs can't use `localhost` | Uses `http://127.0.0.1:8000/callback` (port 8000 because macOS uses 5000 for AirPlay). |
| Feb 2026 renames: `/playlists/{id}/tracks` → `/items`, `POST /users/{id}/playlists` → `POST /me/playlists` | Uses the new paths. |

## Suggested reading order

| File | What you'll learn |
|---|---|
| `playlist_sorter/config.py` | Loading settings from `.env`; detecting "not configured yet" |
| `playlist_sorter/spotify/auth.py` | The OAuth Authorization Code flow written by hand: state/CSRF, code exchange, token refresh |
| `playlist_sorter/spotify/client.py` | Calling a REST API with `requests`: pagination, batching, 429 retry |
| `playlist_sorter/overrides.py` | Persisting user edits to a JSON file, and validating form input |
| `playlist_sorter/models.py` | The `Track` dataclass everything passes around |
| `playlist_sorter/features.py` | The provider pattern: two interchangeable data sources with a fallback |
| `playlist_sorter/analysis/camelot.py` | Pitch class + mode → Camelot code, and why it follows the circle of fifths |
| `playlist_sorter/analysis/mood.py` | k-means clustering from scratch on (valence, energy) |
| `playlist_sorter/sorting.py` | The strategy registry, and greedy nearest-neighbour ordering for harmonic mixing |
| `playlist_sorter/app.py` | Flask routes, sessions, the app factory, caching |
| `playlist_sorter/templates/` | Jinja templates (server-rendered; JS is optional) |
| `tests/` | Unit tests for the music logic, plus route tests that use a fake Spotify client |

## Ideas for extending it

- Let the user choose the starting track for the harmonic path.
- Replace greedy ordering with 2-opt improvement to get a smoother mix overall.
- Add a "tempo arc" strategy: build up to a peak BPM, then come back down.
- Store the cache in SQLite so it survives restarts.
