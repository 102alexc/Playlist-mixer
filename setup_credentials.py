"""
Command-line alternative to the web /setup page:   python setup_credentials.py

Asks for your Spotify app credentials and writes them to .env.
"""
import getpass

from playlist_sorter.config import DEFAULT_REDIRECT_URI, ENV_PATH, write_env_file

INSTRUCTIONS = f"""
Spotify credentials setup
-------------------------
1. Go to https://developer.spotify.com/dashboard and create an app.
2. Add this Redirect URI (exactly):  {DEFAULT_REDIRECT_URI}
3. Tick "Web API", save, and add your account under User Management.
4. Copy the Client ID and Client secret from the app's Settings page.
"""


def main() -> None:
    print(INSTRUCTIONS)
    client_id = input("Client ID: ").strip()
    # getpass hides the secret while typing.
    client_secret = getpass.getpass("Client secret (hidden): ").strip()
    redirect_uri = input(f"Redirect URI [{DEFAULT_REDIRECT_URI}]: ").strip() or DEFAULT_REDIRECT_URI
    provider = input("Audio features source: auto / spotify / reccobeats [auto]: ").strip() or "auto"

    if not client_id or not client_secret:
        raise SystemExit("Client ID and secret are required. Nothing was saved.")

    write_env_file(client_id, client_secret, redirect_uri, provider)
    print(f"\nSaved to {ENV_PATH}. Now run:  python run.py")


if __name__ == "__main__":
    main()
