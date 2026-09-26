"""Profiles: one saved login per YouTube channel (brand account).

A YouTube OAuth token belongs to the one channel chosen on Google's consent
screen, and the API cannot list the channels someone manages. So each channel
is logged in once and remembered under a name: its token, and the channel it
was granted for. The channel is recorded only when the login is created (a
fresh browser login, or adopt), never later; every use checks that the token
still belongs to it, so nothing acts on the wrong one.
"""

import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows
    import msvcrt

from .auth import WINDOWS, restrict_to_owner
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
    """The channel a profile was granted for, or None when none is recorded."""
    path = channel_path(name, folder)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as saved:
            channel = json.load(saved)
    except (OSError, ValueError):
        channel = None
    if not (isinstance(channel, dict) and all(isinstance(channel.get(key), str) for key in ("id", "title"))):
        raise ProfileError(
            f"profile {name!r}: its channel file {path} cannot be read: remove it, then log in again "
            f"with profiles.py add {name}"
        )
    return channel


def record(name, channel, folder=None, now=None):
    """Record the channel a profile's login belongs to."""
    now = now or datetime.now(timezone.utc)
    record = {"id": channel["id"], "title": channel["title"], "added_at": now.isoformat(timespec="seconds")}
    write_json_atomically(channel_path(name, folder), record)


def signed_in_channel(service):
    """The channel a token belongs to (1 quota unit)."""
    items = service.channels().list(part="snippet", mine=True).execute().get("items") or []
    if not items:
        raise ProfileError("this login has no YouTube channel")
    return {"id": items[0]["id"], "title": items[0]["snippet"]["title"]}


def verify(name, service, folder=None, now=None, *, register=False):
    """Check that the token belongs to the profile's channel, and return the channel.

    register: the login was just created, so a profile with no channel
    recorded records this one. Otherwise a missing record is refused (#65),
    like a token that belongs to another channel: ProfileError, before
    anything else is done.
    """
    current, new_record = check(name, service, folder, register=register)
    if new_record:
        record(name, current, folder, now)
    return current


def check(name, service, folder=None, *, register=False):
    """verify without writing: (the channel, whether it is still to be recorded)."""
    saved = saved_channel(name, folder)
    current = signed_in_channel(service)
    if saved is None:
        if not register:
            raise ProfileError(
                f"profile {name!r} has a login but no channel recorded: log in again with profiles.py add {name}"
            )
        return current, True
    if saved["id"] != current["id"]:
        raise ProfileError(
            f"profile {name!r} is for {saved['title']} ({saved['id']}), but its login is for "
            f"{current['title']} ({current['id']}): log in again with profiles.py add {name}, "
            f"picking {saved['title']}"
        )
    return current, False


def list_profiles(folder=None):
    folder = Path(folder or config_dir())
    if not folder.exists():
        return []
    names = sorted(path.stem for path in folder.glob("*.json") if not path.name.endswith(".channel.json"))
    return [{"name": name, **_listed_channel(name, folder)} for name in names]


def _listed_channel(name, folder):
    try:
        return saved_channel(name, folder) or {"id": None, "title": None, "problem": "no channel recorded"}
    except ProfileError:
        return {"id": None, "title": None, "problem": "its channel file cannot be read"}


def adopt(name, token_file, channel, folder=None, now=None):
    """Make an existing token (like samples/token.json) a profile, without logging in again.

    channel: {"id", "title"} of the token's channel, from a client built on
    that token (YoutubeClient(..., token_file=token_file).signed_in_channel()).
    The token is copied, restricted to its owner, and the original is kept.
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
        record(name, channel, folder, now)
        os.replace(temporary, target)
    except BaseException:
        os.unlink(temporary)
        raise
    return target


# The logins being replaced in this process: their set-aside copy is not a
# leftover, and their lock is already held.
_REPLACING = set()


def _aside(token):
    return token.with_name(f".{token.name}.previous")


@contextmanager
def _exclusive(token):
    """Hold the profile's lock, across processes, or refuse when another run holds it (#77).

    The operating system releases the lock when its process ends, so a
    crashed run never leaves a profile locked.
    """
    with open(token.with_name(f".{token.name}.lock"), "a+b") as handle:
        handle.seek(0)
        try:
            if WINDOWS:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ProfileError(
                f"profile {token.stem!r} is being logged in again by another run: try again when it is done"
            ) from None
        try:
            yield
        finally:
            if WINDOWS:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _settle(token):
    aside = _aside(token)
    if not aside.exists():
        return
    if token.exists():
        os.unlink(aside)
    else:
        os.replace(aside, token)


def recover(name, folder=None):
    """Settle a login replacement that was interrupted (#70).

    With the login set aside and no new one saved, the old login comes back;
    with a new one saved (it is saved only once its channel checked out),
    the old one is dropped. A replacement still running, in this process or
    another, is left alone: in another, this refuses with ProfileError.
    """
    token = token_path(name, folder)
    if token in _REPLACING or not _aside(token).exists():
        return
    with _exclusive(token):
        _settle(token)


def _restore(path, content):
    """Put a file back as it was: content, or no file when content is None."""
    if content is None:
        path.unlink(missing_ok=True)
    else:
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        with os.fdopen(descriptor, "wb") as restored:
            restored.write(content)
        os.replace(temporary, path)


@contextmanager
def replacing_login(name, folder=None):
    """Set a profile's login aside while a fresh one is made (profiles.py add on an existing profile).

    When the block fails (an abandoned login, one for another channel, or
    any error), the old login comes back with the channel record it had
    (#75). An earlier interrupted replacement is settled first, and another
    run cannot touch the profile meanwhile (#77).
    """
    token = token_path(name, folder)
    if not token.parent.exists():
        yield
        return
    with _exclusive(token):
        _settle(token)
        if not token.exists():
            yield
            return
        channel_file = channel_path(name, folder)
        channel_before = channel_file.read_bytes() if channel_file.exists() else None
        aside = _aside(token)
        os.replace(token, aside)
        _REPLACING.add(token)
        try:
            yield
        except BaseException:
            os.replace(aside, token)
            _restore(channel_file, channel_before)
            raise
        finally:
            _REPLACING.discard(token)
        os.unlink(aside)


def make_folder(folder):
    """The profiles folder, private to its owner."""
    Path(folder).mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(folder, 0o700)


def output_name(stem, suffix, profile=None):
    """liked.json, or liked-<profile>.json with a profile."""
    return f"{stem}-{check_name(profile)}{suffix}" if profile else f"{stem}{suffix}"
