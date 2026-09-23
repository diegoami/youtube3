import logging
import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube"]

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
    descriptor = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as token:
        token.write(credentials.to_json())
    # O_CREAT's mode does not apply to a file that already existed.
    os.chmod(token_path, 0o600)
