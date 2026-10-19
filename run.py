"""
Start the development server:   python run.py

The host/port come from SPOTIFY_REDIRECT_URI, because Spotify will send the
browser back to exactly that address after login. Port 8000 is the default
since macOS uses 5000 for AirPlay Receiver.
"""
import logging
from urllib.parse import urlparse

from playlist_sorter.app import create_app

logging.basicConfig(level=logging.INFO)

app = create_app()

if __name__ == "__main__":
    redirect = urlparse(app.config["SETTINGS"].redirect_uri)
    host = redirect.hostname or "127.0.0.1"
    port = redirect.port or 8000
    print(f"\n  Open http://{host}:{port} in your browser\n")
    app.run(host=host, port=port, debug=True)
