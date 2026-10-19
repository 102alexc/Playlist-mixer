"""
Flask web layer: routes, sessions and templates.

This file deliberately contains no music logic. It only:
  * guards routes (setup done? user logged in?)
  * calls the Spotify client / features / sorting modules
  * renders templates

Request flow for the main feature:

  /                 paste a playlist link, pick a strategy
  /playlist?url=..  fetch tracks + features (cached), sort, show table
  /export  (POST)   create a new Spotify playlist in the shown order
"""
from __future__ import annotations

import functools
import logging
import time
from typing import Dict, Tuple

from flask import (Flask, current_app, flash, redirect, render_template,
                   request, session, url_for)

from .config import Settings, load_settings, write_env_file
from .features import attach_features
from .models import Track
from .overrides import OverrideInputError, apply_overrides, clear_override, parse_form, set_override
from .sorting import STRATEGIES, annotate, apply_strategy
from .spotify import auth
from .spotify.client import SpotifyAPIError, SpotifyClient, parse_playlist_id

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# A tiny in-memory cache so switching strategies doesn't re-download the
# playlist. Key: (spotify user id, playlist id). It lives in this process
# only, which is fine for a local single-user app; a real deployment would
# use Redis or similar. (The session cookie is too small: ~4 KB max.)
# --------------------------------------------------------------------------
CACHE_TTL_SECONDS = 30 * 60
_playlist_cache: Dict[Tuple[str, str], dict] = {}


def _settings() -> Settings:
    return current_app.config["SETTINGS"]


# --------------------------------------------------------------------------
# Auth helpers
# --------------------------------------------------------------------------

def login_required(view):
    """Decorator: send the user to Spotify login if we have no token."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if "token_info" not in session:
            session["next_url"] = request.full_path
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def get_client() -> SpotifyClient:
    """A SpotifyClient with a guaranteed-fresh token (refreshes transparently)."""
    token_info = auth.ensure_fresh(_settings(), session["token_info"])
    session["token_info"] = token_info  # persist a refreshed token
    return SpotifyClient(token_info["access_token"])


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------

def load_playlist(client: SpotifyClient, playlist_id: str, force: bool = False) -> dict:
    """Fetch playlist + tracks + audio features, using the cache when possible."""
    cache_key = (session.get("user_id", ""), playlist_id)
    cached = _playlist_cache.get(cache_key)
    if cached and not force and time.time() - cached["fetched_at"] < CACHE_TTL_SECONDS:
        return cached

    meta = client.get_playlist_meta(playlist_id)
    tracks = client.get_playlist_tracks(playlist_id)
    provider = attach_features(tracks, client, _settings().features_provider)

    entry = {
        "meta": meta,
        # Raw provider data only. Manual overrides and the Camelot/mood labels
        # are applied per request (see prepare_tracks) so edits show instantly.
        # Plain dicts so each request works on fresh Track copies.
        "tracks": [t.to_dict() for t in tracks],
        "provider": provider,
        "fetched_at": time.time(),
    }
    _playlist_cache[cache_key] = entry
    return entry


def prepare_tracks(data: dict) -> list:
    """Cached raw tracks -> Tracks with manual overrides applied and labels computed."""
    tracks = [Track.from_dict(d) for d in data["tracks"]]
    apply_overrides(tracks)
    annotate(tracks)  # after overrides, so mood clusters include hand-entered values
    return tracks


def friendly_error(err: SpotifyAPIError) -> str:
    if err.status == 403:
        return ("Spotify refused access to this playlist. Apps in Development Mode can only "
                "read playlists you own or collaborate on, and your Spotify account must be "
                "added under 'User Management' in the developer dashboard. Tip: in the "
                "Spotify app, use 'Add to other playlist' to copy the songs into a playlist "
                "you own, then paste that link.")
    if err.status == 404:
        return "Playlist not found. Check the link, and make sure the playlist isn't private to someone else."
    return str(err)


# --------------------------------------------------------------------------
# App factory
# --------------------------------------------------------------------------

def create_app() -> Flask:
    app = Flask(__name__)
    settings = load_settings()
    app.config["SETTINGS"] = settings
    app.secret_key = settings.secret_key

    @app.before_request
    def require_setup():
        """Until credentials exist, every page redirects to the setup step."""
        if not _settings().is_configured and request.endpoint not in ("setup", "static"):
            return redirect(url_for("setup"))

    @app.context_processor
    def inject_globals():
        return {"logged_in": "token_info" in session, "user_name": session.get("user_name")}

    # ---- configuration step ---------------------------------------------

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        s = _settings()
        if request.method == "POST":
            client_id = request.form.get("client_id", "").strip()
            client_secret = request.form.get("client_secret", "").strip()
            # Leaving the secret empty on a re-config keeps the current one.
            if not client_secret and s.is_configured:
                client_secret = s.client_secret
            if not client_id or not client_secret:
                flash("Client ID and Client Secret are both required.", "error")
            else:
                write_env_file(
                    client_id,
                    client_secret,
                    request.form.get("redirect_uri", "").strip() or s.redirect_uri,
                    request.form.get("features_provider", "auto"),
                )
                app.config["SETTINGS"] = load_settings()
                session.pop("token_info", None)  # old tokens belong to the old app
                flash("Credentials saved to .env. Now log in with Spotify.", "ok")
                return redirect(url_for("index"))
        return render_template("setup.html", settings=s)

    # ---- OAuth ----------------------------------------------------------

    @app.route("/login")
    def login():
        state = auth.new_state()
        session["oauth_state"] = state
        return redirect(auth.build_authorize_url(_settings(), state))

    @app.route("/callback")
    def callback():
        if request.args.get("error"):
            flash(f"Spotify login was cancelled ({request.args['error']}).", "error")
            return redirect(url_for("index"))

        # CSRF check: the state must be the one we generated in /login.
        if request.args.get("state") != session.pop("oauth_state", None):
            flash("Login failed: state mismatch. Please try again.", "error")
            return redirect(url_for("index"))

        try:
            session["token_info"] = auth.exchange_code(_settings(), request.args.get("code", ""))
            me = SpotifyClient(session["token_info"]["access_token"]).me()
        except (auth.AuthError, SpotifyAPIError) as err:
            flash(f"Login failed: {err}", "error")
            return redirect(url_for("index"))

        session["user_id"] = me.get("id", "")
        session["user_name"] = me.get("display_name") or me.get("id")
        return redirect(session.pop("next_url", None) or url_for("index"))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    # ---- main pages -----------------------------------------------------

    @app.route("/")
    def index():
        return render_template("index.html", strategies=STRATEGIES)

    @app.route("/playlist")
    @login_required
    def playlist():
        raw_url = request.args.get("url", "")
        strategy = request.args.get("strategy", "original")
        playlist_id = parse_playlist_id(raw_url)
        if not playlist_id:
            flash("That doesn't look like a Spotify playlist link.", "error")
            return redirect(url_for("index"))

        try:
            data = load_playlist(get_client(), playlist_id, force=bool(request.args.get("refresh")))
        except auth.AuthError:
            session.pop("token_info", None)
            return redirect(url_for("login"))
        except SpotifyAPIError as err:
            if err.status == 401:
                session.pop("token_info", None)
                return redirect(url_for("login"))
            flash(friendly_error(err), "error")
            return redirect(url_for("index"))

        ordered = apply_strategy(strategy, prepare_tracks(data))

        tempos = [t.tempo for t in ordered if t.tempo]
        stats = {
            "count": len(ordered),
            "missing": sum(1 for t in ordered if not t.has_features),
            "avg_bpm": round(sum(tempos) / len(tempos)) if tempos else None,
            "minutes": round(sum(t.duration_ms for t in ordered) / 60000),
        }
        if strategy == "camelot":
            stats["smooth"] = sum(1 for t in ordered if t.extra.get("smooth"))

        return render_template(
            "results.html",
            meta=data["meta"],
            tracks=ordered,
            provider=data["provider"],
            strategies=STRATEGIES,
            strategy=strategy if strategy in STRATEGIES else "original",
            playlist_url=raw_url,
            playlist_id=playlist_id,
            stats=stats,
        )

    @app.route("/override", methods=["POST"])
    @login_required
    def override():
        """Save (or clear) hand-entered BPM/key/energy/valence for one track."""
        track_id = request.form.get("track_id", "")
        playlist_url = request.form.get("playlist_url", "")
        back = url_for("playlist", url=playlist_url, strategy=request.form.get("strategy", "original"))
        if not track_id.isalnum():  # Spotify IDs are base-62; reject anything else
            flash("Invalid track.", "error")
            return redirect(back)

        if request.form.get("action") == "clear":
            clear_override(track_id)
            flash("Manual values removed.", "ok")
            return redirect(back)

        try:
            values = parse_form(request.form.get("bpm", ""), request.form.get("key", ""),
                                request.form.get("energy", ""), request.form.get("valence", ""))
        except OverrideInputError as err:
            flash(str(err), "error")
            return redirect(back)
        set_override(track_id, values)
        flash("Saved. Values are kept in overrides.json.", "ok")
        return redirect(back)

    @app.route("/export", methods=["POST"])
    @login_required
    def export():
        playlist_id = request.form["playlist_id"]
        strategy = request.form.get("strategy", "original")
        name = request.form.get("name", "").strip() or "Sorted playlist"
        public = request.form.get("public") == "on"

        try:
            client = get_client()
            # Re-run the strategy server-side from cached data rather than
            # trusting a list of URIs posted by the browser.
            data = load_playlist(client, playlist_id)
            ordered = apply_strategy(strategy, prepare_tracks(data))
            label = STRATEGIES.get(strategy, STRATEGIES["original"]).label
            new = client.create_playlist(
                name,
                description=f"“{data['meta']['name']}” reordered by {label}. Made with Playlist Sorter.",
                public=public,
            )
            client.add_items(new["id"], [t.uri for t in ordered])
        except SpotifyAPIError as err:
            hint = (" Try logging out and in again so Spotify grants the playlist-modify "
                    "permissions." if err.status in (401, 403) else "")
            flash(f"Export failed: {err.message}.{hint}", "error")
            return redirect(url_for("playlist", url=playlist_id, strategy=strategy))

        return render_template(
            "exported.html",
            name=name,
            url=(new.get("external_urls") or {}).get("spotify", ""),
            count=len(ordered),
        )

    return app
