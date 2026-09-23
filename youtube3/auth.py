import getpass
import logging
import os
import subprocess
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube"]
WINDOWS = os.name == "nt"

logger = logging.getLogger("youtube3")


def load_credentials(client_secrets_file, token_file):
    """Return valid credentials for the YouTube scope.

    Uses the saved token when it is valid, refreshes it when it has expired,
    and otherwise runs the browser flow. Any new or refreshed token is saved,
    readable by the owner only.
    """
    token_path = Path(token_file)
    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except RefreshError:
            logger.info("The saved token could not be refreshed; logging in again")
            credentials = None
    else:
        credentials = None

    if credentials is None:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_file), SCOPES)
        # port=0 takes any free port; the URL is printed when no browser opens (WSL).
        credentials = flow.run_local_server(port=0)

    save_credentials(credentials, token_path)
    return credentials


def save_credentials(credentials, token_path):
    token_path.parent.mkdir(parents=True, exist_ok=True)
    # Empty the file and restrict it before the token is written into it.
    descriptor = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.close(descriptor)
    restrict_to_owner(token_path)
    with open(token_path, "w", encoding="utf-8") as token:
        token.write(credentials.to_json())


def restrict_to_owner(path):
    """Make path readable and writable by the current user only."""
    if not WINDOWS:
        # O_CREAT's mode does not apply to a file that already existed.
        os.chmod(path, 0o600)
        return
    # On Windows chmod only sets the read-only flag, and a new file inherits
    # its folder's ACL, which can let other accounts read it. Drop the
    # inherited entries and grant the current user alone.
    subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"{windows_user()}:F"],
        check=True,
        capture_output=True,
    )


def windows_user():
    domain = os.environ.get("USERDOMAIN")
    user = os.environ.get("USERNAME") or getpass.getuser()
    return f"{domain}\\{user}" if domain else user
