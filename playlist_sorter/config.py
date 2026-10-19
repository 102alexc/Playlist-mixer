"""
Configuration loading.

All settings live in a `.env` file at the project root (see `.env.example`).
We read them once at startup into a small dataclass so the rest of the code
never touches `os.environ` directly. That makes it obvious which settings
exist and lets the app detect "not configured yet" and show the setup page.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root = the folder that contains this package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

DEFAULT_REDIRECT_URI = "http://127.0.0.1:8000/callback"

# OAuth scopes = the permissions we ask the user for.
#   playlist-read-*   -> read the playlist the user pastes in
#   playlist-modify-* -> create the new, reordered playlist
SPOTIFY_SCOPES = " ".join(
    [
        "playlist-read-private",
        "playlist-read-collaborative",
        "playlist-modify-private",
        "playlist-modify-public",
    ]
)


@dataclass
class Settings:
    client_id: str
    client_secret: str
    redirect_uri: str
    secret_key: str
    features_provider: str

    @property
    def is_configured(self) -> bool:
        """True once real Spotify credentials have been entered."""
        placeholders = {"", "your-client-id", "your-client-secret"}
        return self.client_id not in placeholders and self.client_secret not in placeholders


def load_settings() -> Settings:
    """Read `.env` (if present) and return a Settings object."""
    # override=True so that saving new values from the setup page and
    # reloading picks them up instead of keeping stale process env vars.
    load_dotenv(ENV_PATH, override=True)
    return Settings(
        client_id=os.getenv("SPOTIFY_CLIENT_ID", "").strip(),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET", "").strip(),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip(),
        # Without a stable key, sessions would reset every restart; we
        # generate one on first save (see write_env_file).
        secret_key=os.getenv("FLASK_SECRET_KEY", "") or secrets.token_hex(32),
        features_provider=os.getenv("FEATURES_PROVIDER", "auto").strip().lower(),
    )


def write_env_file(client_id: str, client_secret: str, redirect_uri: str,
                   features_provider: str = "auto") -> None:
    """
    Persist credentials to `.env`. Used by both the web setup page and the
    `setup_credentials.py` CLI so there is a single source of truth.
    Keeps an existing FLASK_SECRET_KEY so logged-in sessions survive.
    """
    load_dotenv(ENV_PATH, override=True)
    secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
    if secret_key == "change-me":
        secret_key = secrets.token_hex(32)

    lines = [
        f"SPOTIFY_CLIENT_ID={client_id.strip()}",
        f"SPOTIFY_CLIENT_SECRET={client_secret.strip()}",
        f"SPOTIFY_REDIRECT_URI={redirect_uri.strip() or DEFAULT_REDIRECT_URI}",
        f"FLASK_SECRET_KEY={secret_key}",
        f"FEATURES_PROVIDER={features_provider.strip() or 'auto'}",
    ]
    ENV_PATH.write_text("\n".join(lines) + "\n")
    # The file holds a secret: make it readable by the owner only.
    os.chmod(ENV_PATH, 0o600)
