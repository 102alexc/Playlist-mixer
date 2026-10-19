"""
Spotify OAuth 2.0 — the "Authorization Code" flow, written by hand so you
can see every step (libraries like spotipy hide this).

The flow in four steps:

  1. We redirect the browser to Spotify's /authorize page with our client
     ID, the scopes we want, our redirect URI and a random `state` value.
  2. The user logs in and approves. Spotify redirects back to our
     redirect URI with `?code=...&state=...`.
  3. Our server checks `state` (CSRF protection) and swaps the short-lived
     `code` for an access token + refresh token by POSTing to /api/token,
     authenticating with client ID + secret. The secret never touches the
     browser, which is why this flow needs a backend.
  4. Access tokens expire after ~1 hour. When that happens we POST the
     refresh token to /api/token to get a new access token without
     bothering the user.

Tokens are kept in the Flask session (a signed cookie), as a plain dict:
    {"access_token": ..., "refresh_token": ..., "expires_at": <unix time>}
"""
from __future__ import annotations

import secrets
import time
from urllib.parse import urlencode

import requests

from ..config import SPOTIFY_SCOPES, Settings

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

# Refresh a little before the real expiry so a request never goes out
# with a token that dies mid-flight.
EXPIRY_MARGIN_SECONDS = 60


class AuthError(Exception):
    """Raised when Spotify rejects a token exchange or refresh."""


def new_state() -> str:
    """Random, unguessable value we store in the session and compare on callback."""
    return secrets.token_urlsafe(16)


def build_authorize_url(settings: Settings, state: str) -> str:
    """Step 1: the URL we send the user's browser to."""
    params = {
        "client_id": settings.client_id,
        "response_type": "code",
        "redirect_uri": settings.redirect_uri,
        "scope": SPOTIFY_SCOPES,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _token_request(settings: Settings, data: dict) -> dict:
    """POST to /api/token using HTTP Basic auth (client_id:client_secret)."""
    resp = requests.post(
        TOKEN_URL,
        data=data,
        auth=(settings.client_id, settings.client_secret),
        timeout=15,
    )
    if resp.status_code != 200:
        # Spotify returns {"error": ..., "error_description": ...}
        try:
            body = resp.json()
            detail = body.get("error_description") or body.get("error")
        except ValueError:
            detail = resp.text
        raise AuthError(f"Spotify token endpoint said: {detail}")
    return resp.json()


def _to_token_info(payload: dict, previous_refresh_token: str | None = None) -> dict:
    """Normalise Spotify's token response into what we keep in the session."""
    return {
        "access_token": payload["access_token"],
        # A refresh response may omit refresh_token: keep the old one then.
        "refresh_token": payload.get("refresh_token") or previous_refresh_token,
        "expires_at": int(time.time()) + int(payload.get("expires_in", 3600)),
    }


def exchange_code(settings: Settings, code: str) -> dict:
    """Step 3: trade the one-time `code` for tokens."""
    payload = _token_request(
        settings,
        {
            "grant_type": "authorization_code",
            "code": code,
            # Must be identical to the one used in step 1.
            "redirect_uri": settings.redirect_uri,
        },
    )
    return _to_token_info(payload)


def refresh(settings: Settings, token_info: dict) -> dict:
    """Step 4: get a fresh access token using the refresh token."""
    payload = _token_request(
        settings,
        {"grant_type": "refresh_token", "refresh_token": token_info["refresh_token"]},
    )
    return _to_token_info(payload, previous_refresh_token=token_info["refresh_token"])


def ensure_fresh(settings: Settings, token_info: dict) -> dict:
    """Return a token_info that is valid right now, refreshing if needed."""
    if token_info["expires_at"] - EXPIRY_MARGIN_SECONDS > time.time():
        return token_info
    return refresh(settings, token_info)
