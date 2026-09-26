"""Profiles: one saved login per YouTube channel (brand account).

A YouTube OAuth token belongs to the one channel chosen on Google's consent
screen, and the API cannot list the channels someone manages. So each channel
is logged in once and remembered under a name, in one file, <name>.json:

    {"channel": {"id", "title", "added_at"}, "credentials": {...the login...}}

The file is only ever replaced whole, in one atomic step, and only by a login
whose channel checked out. So the channel and the login beside it cannot
disagree, and a login that fails, is interrupted or runs at the same time as
another leaves either the old profile or the new one, never a mix of the two.
Every use checks that the login still belongs to the recorded channel, so
nothing acts on the wrong one.
"""

import json
import os
import re
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

from .auth import write_private

NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

# What a profile file holds: the channel (or None), the login (the dict a
# token file holds, or None), and whether it is still in the v2.6.0 layout.
Saved = namedtuple("Saved", "channel credentials legacy")


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


def profile_path(name, folder=None):
    return Path(folder or config_dir()) / f"{check_name(name)}.json"


def _legacy_channel_path(name, folder=None):
    """Where v2.6.0 kept the channel, beside a bare token in <name>.json."""
    return Path(folder or config_dir()) / f"{check_name(name)}.channel.json"


def _is_channel(channel):
    return isinstance(channel, dict) and all(isinstance(channel.get(key), str) for key in ("id", "title"))


def _unreadable(name, path):
    return ProfileError(f"profile {name!r}: {path} cannot be read: log in again with profiles.py add {name}")


def read(name, folder=None):
    """The profile as saved (Saved), all None when there is none; ProfileError when it cannot be read."""
    path = profile_path(name, folder)
    if not path.exists():
        return Saved(None, None, False)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise _unreadable(name, path) from None
    if not isinstance(data, dict):
        raise _unreadable(name, path)
    if "credentials" not in data:
        # v2.6.0: the file is the bare token, and its channel sits beside it.
        legacy = _legacy_channel_path(name, folder)
        if not legacy.exists():
            return Saved(None, data, True)
        try:
            channel = json.loads(legacy.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            channel = None
        if not _is_channel(channel):
            raise _unreadable(name, legacy)
        return Saved(channel, data, True)
    channel, credentials = data.get("channel"), data.get("credentials")
    if (channel is not None and not _is_channel(channel)) or (credentials is not None and not isinstance(credentials, dict)):
        raise _unreadable(name, path)
    return Saved(channel, credentials, False)


def saved_channel(name, folder=None):
    """The channel a profile was granted for, or None when none is recorded."""
    return read(name, folder).channel


def write(name, channel, credentials, folder=None, now=None):
    """Replace the profile whole, its channel and its login together, readable by the owner only.

    credentials: the dict a token file holds (json.loads(credentials.to_json())).
    """
    now = now or datetime.now(timezone.utc)
    recorded = {
        "id": channel["id"],
        "title": channel["title"],
        "added_at": channel.get("added_at") or now.isoformat(timespec="seconds"),
    }
    path = profile_path(name, folder)
    make_folder(path.parent)
    write_private(path, json.dumps({"channel": recorded, "credentials": credentials}, indent=2))
    # The v2.6.0 channel file, now inside the profile.
    _legacy_channel_path(name, folder).unlink(missing_ok=True)
    return path


def signed_in_channel(service):
    """The channel a token belongs to (1 quota unit)."""
    items = service.channels().list(part="snippet", mine=True).execute().get("items") or []
    if not items:
        raise ProfileError("this login has no YouTube channel")
    return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}


def match(name, saved, current, *, register=False):
    """The channel record to keep for a login of current, or ProfileError.

    saved: the recorded channel, or None. register: the profile is new, or
    is being logged in again on purpose (profiles.py add), so a profile with
    no channel recorded takes this one; otherwise a missing record is refused
    (#65, #82), like a login that belongs to another channel.
    """
    if saved is None:
        if not register:
            raise ProfileError(
                f"profile {name!r} has a login but no channel recorded: log in again with profiles.py add {name}"
            )
        return current
    if saved["id"] != current["id"]:
        raise ProfileError(
            f"profile {name!r} is for {saved['title']} ({saved['id']}), but its login is for "
            f"{current['title']} ({current['id']}): log in again with profiles.py add {name}, "
            f"picking {saved['title']}"
        )
    return saved


def verify(name, service, folder=None):
    """Check that service's login belongs to the profile's channel, and return the channel."""
    current = signed_in_channel(service)
    match(name, read(name, folder).channel, current)
    return current


def list_profiles(folder=None):
    folder = Path(folder or config_dir())
    if not folder.exists():
        return []
    names = sorted(path.stem for path in folder.glob("*.json") if not path.name.endswith(".channel.json"))
    return [{"name": name, **_listed_channel(name, folder)} for name in names]


def _listed_channel(name, folder):
    try:
        channel = read(name, folder).channel
    except ProfileError:
        return {"id": None, "title": None, "problem": "its file cannot be read"}
    return channel or {"id": None, "title": None, "problem": "no channel recorded"}


def adopt(name, token_file, channel, folder=None, now=None):
    """Make an existing token (like samples/token.json) a profile, without logging in again.

    channel: {"id", "title"} of the token's channel, from a client built on
    that token (YoutubeClient(..., token_file=token_file).signed_in_channel()).
    The token is copied into the profile, readable by its owner only, and the
    original is kept.
    """
    target = profile_path(name, folder)
    if target.exists():
        raise ProfileError(f"profile {name!r} already exists")
    if not Path(token_file).exists():
        raise ProfileError(f"{token_file}: no such token file")
    try:
        credentials = json.loads(Path(token_file).read_text(encoding="utf-8"))
    except ValueError:
        credentials = None
    if not isinstance(credentials, dict):
        raise ProfileError(f"{token_file}: not a saved login")
    return write(name, channel, credentials, folder, now)


def make_folder(folder):
    """The profiles folder, private to its owner."""
    Path(folder).mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(folder, 0o700)


def output_name(stem, suffix, profile=None):
    """liked.json, or liked-<profile>.json with a profile."""
    return f"{stem}-{check_name(profile)}{suffix}" if profile else f"{stem}{suffix}"
