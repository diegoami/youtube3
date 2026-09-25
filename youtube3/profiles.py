"""Profiles: one saved login per YouTube channel (brand account).

A YouTube OAuth token belongs to the one channel chosen on Google's consent
screen, and the API cannot list the channels someone manages. So each channel
is logged in once and remembered under a name: its token, and the channel it
was granted for. Every later use checks that the token still belongs to that
channel, so nothing acts on the wrong one.
"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .auth import restrict_to_owner
from .likes import write_json_atomically

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


class ProfileError(Exception):
    pass


def check_name(name):
    if not NAME.match(name or ""):
        raise ProfileError(f"{name!r}: a profile name is 1 to 40 lowercase letters, digits, - or _")
    return name


def config_dir(environ=None, windows=None):
    """Where profiles live: outside any repository, in the user's config folder."""
    environ = os.environ if environ is None else environ
    windows = os.name == "nt" if windows is None else windows
    if windows:
        base = Path(environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "youtube3" / "profiles"


def token_path(name, folder=None):
    return Path(folder or config_dir()) / f"{check_name(name)}.json"


def channel_path(name, folder=None):
    return Path(folder or config_dir()) / f"{check_name(name)}.channel.json"


def saved_channel(name, folder=None):
    """The channel a profile was granted for, or None before its first use."""
    path = channel_path(name, folder)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as saved:
        return json.load(saved)


def signed_in_channel(service):
    """The channel a token belongs to (1 quota unit)."""
    items = service.channels().list(part="snippet", mine=True).execute().get("items") or []
    if not items:
        raise ProfileError("this login has no YouTube channel")
    return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}


def verify(name, service, folder=None, now=None):
    """Check that the token belongs to the profile's channel; remember it on first use.

    Returns the channel. Raises ProfileError, before anything else is done,
    when the token belongs to another channel.
    """
    current = signed_in_channel(service)
    saved = saved_channel(name, folder)
    if saved is None:
        now = now or datetime.now(timezone.utc)
        write_json_atomically(channel_path(name, folder), {**current, "added_at": now.isoformat(timespec="seconds")})
        return current
    if saved["id"] != current["id"]:
        raise ProfileError(
            f"profile {name!r} is for {saved['title']} ({saved['id']}), but its login is for "
            f"{current['title']} ({current['id']}): log in again with profiles.py add {name}"
        )
    return current


def list_profiles(folder=None):
    folder = Path(folder or config_dir())
    if not folder.exists():
        return []
    names = sorted(path.stem for path in folder.glob("*.json") if not path.name.endswith(".channel.json"))
    return [{"name": name, **(saved_channel(name, folder) or {"id": None, "title": None})} for name in names]


def adopt(name, token_file, folder=None):
    """Make an existing token (like samples/token.json) a profile, without logging in again.

    The token is copied, restricted to its owner, and the original is kept;
    the channel is recorded on the profile's first use.
    """
    target = token_path(name, folder)
    if target.exists():
        raise ProfileError(f"profile {name!r} already exists")
    if not Path(token_file).exists():
        raise ProfileError(f"{token_file}: no such token file")
    make_folder(target.parent)
    token = Path(token_file).read_bytes()
    # Restricted while still empty, then filled: the token is never readable by others.
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    os.close(descriptor)
    try:
        restrict_to_owner(temporary)
        Path(temporary).write_bytes(token)
        os.replace(temporary, target)
    except BaseException:
        os.unlink(temporary)
        raise
    return target


def make_folder(folder):
    """The profiles folder, private to its owner."""
    Path(folder).mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(folder, 0o700)


def output_name(stem, suffix, profile=None):
    """liked.json, or liked-<profile>.json with a profile."""
    return f"{stem}-{check_name(profile)}{suffix}" if profile else f"{stem}{suffix}"
