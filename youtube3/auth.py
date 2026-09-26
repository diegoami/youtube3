import getpass
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube"]
# Where obtain_credentials found the login.
SAVED, REFRESHED, BROWSER = "saved", "refreshed", "browser"
WINDOWS = os.name == "nt"

logger = logging.getLogger("youtube3")


def load_credentials(client_secrets_file, token_file, *, choose_account=False):
    """Return valid credentials for the YouTube scope.

    Uses the saved token when it is valid, refreshes it when it has expired,
    and otherwise runs the browser flow. Any new or refreshed token is saved,
    readable by the owner only.
    """
    credentials, source = obtain_credentials(client_secrets_file, token_file, choose_account=choose_account)
    if source != SAVED:
        save_credentials(credentials, Path(token_file))
    return credentials


def obtain_credentials(client_secrets_file, token_file, *, choose_account=False):
    """(credentials, source) as load_credentials finds them, without saving anything.

    source: SAVED (the saved token, valid as it is), REFRESHED (the saved
    token, refreshed) or BROWSER (the browser flow ran: the saved token was
    missing, unreadable or could not be refreshed). Only SAVED needs no save.
    """
    token_path = Path(token_file)
    credentials = None
    if token_path.exists():
        try:
            credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        # Empty, truncated, missing fields (ValueError), or JSON that is not an
        # object such as [] or null (AttributeError); never log its contents.
        except (ValueError, AttributeError, TypeError):
            logger.info("The saved token could not be read; logging in again")

    if credentials and credentials.valid:
        return credentials, SAVED

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
        # choose_account shows Google's account chooser, where a brand account can be picked.
        extra = {"prompt": "select_account consent"} if choose_account else {}
        return flow.run_local_server(port=0, **extra), BROWSER
    return credentials, REFRESHED


def save_credentials(credentials, token_path):
    """Replace the token file; any failure leaves the previous token as it was.

    The new token is written to a file next to it that is restricted to the
    owner while still empty, then renamed over the old one; the rename keeps
    the new file's permissions.
    """
    token_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=token_path.parent, prefix=f".{token_path.name}.")
    os.close(descriptor)
    try:
        restrict_to_owner(temporary)
        with open(temporary, "w", encoding="utf-8") as token:
            token.write(credentials.to_json())
        os.replace(temporary, token_path)
    except BaseException:
        os.unlink(temporary)
        raise


def restrict_to_owner(path):
    """Make path readable and writable by the current user only."""
    if not WINDOWS:
        os.chmod(path, 0o600)
        return
    # On Windows chmod only sets the read-only flag, and a new file gets its
    # folder's inherited ACL, or the process's default one, either of which
    # can let other accounts read it. Reset the file to inherited entries
    # only, drop those, and grant the current user alone.
    for arguments in (["/reset"], ["/inheritance:r", "/grant:r", f"{windows_user()}:F"]):
        subprocess.run(["icacls", str(path), *arguments], check=True, capture_output=True)


def windows_user():
    domain = os.environ.get("USERDOMAIN")
    user = os.environ.get("USERNAME") or getpass.getuser()
    return f"{domain}\\{user}" if domain else user
