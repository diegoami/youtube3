import json
import os
import stat
import subprocess

import pytest
from google.auth.exceptions import RefreshError

from youtube3 import YoutubeClient, auth

TOKEN_JSON = json.dumps({"token": "SECRET-ACCESS", "refresh_token": "SECRET-REFRESH"})
FRESH_JSON = json.dumps({"token": "SECRET-FRESH", "refresh_token": "SECRET-REFRESH"})


class FakeCredentials:
    def __init__(self, valid=True, expired=False, refresh_token="SECRET-REFRESH", refresh_error=False):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.refresh_error = refresh_error
        self.refreshed = False

    def refresh(self, request):
        if self.refresh_error:
            raise RefreshError("token revoked")
        self.refreshed = True
        self.valid = True
        self.expired = False

    def to_json(self):
        return FRESH_JSON if self.refreshed else TOKEN_JSON


class FakeFlow:
    runs = []

    def __init__(self, secrets_file):
        self.secrets_file = secrets_file

    def run_local_server(self, **kwargs):
        FakeFlow.runs.append((self.secrets_file, kwargs))
        return FakeCredentials()


@pytest.fixture
def login(monkeypatch, tmp_path):
    """login(saved=None) -> (credentials, token path); saved is the credentials on disk."""
    FakeFlow.runs = []
    monkeypatch.setattr(
        auth.InstalledAppFlow, "from_client_secrets_file", lambda path, scopes: FakeFlow(path)
    )

    def run(saved=None):
        token = tmp_path / "token.json"
        if saved is not None:
            token.write_text(TOKEN_JSON)
            monkeypatch.setattr(
                auth.Credentials, "from_authorized_user_file", lambda path, scopes: saved
            )
        credentials = auth.load_credentials(tmp_path / "my_secrets.json", token)
        return credentials, token

    return run


def owner_only(path):
    """True when only the current user can open path, by the platform's own rules."""
    if os.name != "nt":
        return stat.S_IMODE(path.stat().st_mode) == 0o600
    listing = subprocess.run(
        ["icacls", str(path)], capture_output=True, text=True, errors="replace", check=True
    ).stdout
    # "<path> DOMAIN\user:(F)", one entry per line, then a blank line and a summary.
    entries = listing.split("\n\n")[0].replace(str(path), "", 1).split()
    return [e.lower() for e in entries] == [f"{auth.windows_user()}:(F)".lower()]


def test_a_valid_saved_token_is_used_without_a_login(login):
    saved = FakeCredentials(valid=True)

    credentials, _ = login(saved)

    assert credentials is saved
    assert FakeFlow.runs == []


def test_an_expired_token_is_refreshed_and_saved_for_the_owner_only(login):
    saved = FakeCredentials(valid=False, expired=True)

    credentials, token = login(saved)

    assert credentials is saved and saved.refreshed
    assert FakeFlow.runs == []
    assert token.read_text() == FRESH_JSON
    assert owner_only(token)


def test_without_a_token_the_browser_flow_runs_and_the_token_is_saved(login, tmp_path):
    credentials, token = login()

    [(secrets_file, kwargs)] = FakeFlow.runs
    assert secrets_file == str(tmp_path / "my_secrets.json")
    assert kwargs == {"port": 0}
    assert token.read_text() == credentials.to_json()
    assert owner_only(token)


def test_a_token_that_cannot_be_refreshed_falls_back_to_the_browser_flow(login):
    saved = FakeCredentials(valid=False, expired=True, refresh_error=True)

    credentials, _ = login(saved)

    assert credentials is not saved
    assert len(FakeFlow.runs) == 1


def test_an_expired_token_without_a_refresh_token_falls_back_to_the_browser_flow(login):
    saved = FakeCredentials(valid=False, expired=True, refresh_token=None)

    login(saved)

    assert len(FakeFlow.runs) == 1


def test_a_token_file_readable_by_others_is_tightened(login, tmp_path):
    token = tmp_path / "token.json"
    token.write_text("{}")
    token.chmod(0o644)

    login(FakeCredentials(valid=False, expired=True))

    assert owner_only(token)


def test_no_token_reaches_the_logs_or_the_terminal(login, caplog, capsys):
    with caplog.at_level("DEBUG"):
        login(FakeCredentials(valid=False, expired=True, refresh_error=True))

    printed = capsys.readouterr()
    assert "SECRET" not in caplog.text + printed.out + printed.err


def test_the_token_defaults_to_token_json_next_to_the_secrets(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        "youtube3.youtube_client.load_credentials",
        lambda secrets, token: calls.append((secrets, token)) or "credentials",
    )
    builds = []
    monkeypatch.setattr(
        "youtube3.youtube_client.build", lambda *args, **kwargs: builds.append(kwargs) or "service"
    )

    client = YoutubeClient(tmp_path / "secrets" / "client_secrets.json")

    assert client.youtube == "service"
    # Without it, every login logs "file_cache is only supported with oauth2client<4.0.0".
    assert builds == [{"credentials": "credentials", "cache_discovery": False}]
    assert calls == [(tmp_path / "secrets" / "client_secrets.json", tmp_path / "secrets" / "token.json")]


def test_an_explicit_token_file_is_used(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        "youtube3.youtube_client.load_credentials",
        lambda secrets, token: calls.append(token) or "credentials",
    )
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *args, **kwargs: "service")

    YoutubeClient("client_secrets.json", token_file=tmp_path / "mine.json")

    assert calls == [tmp_path / "mine.json"]


@pytest.fixture
def windows(monkeypatch):
    """Take the Windows branch on any OS, recording each icacls call."""
    calls = []

    def run(args, **kwargs):
        target = args[1]
        calls.append({"args": args, "kwargs": kwargs, "content": open(target).read()})
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(auth, "WINDOWS", True)
    monkeypatch.setattr(auth.subprocess, "run", run)
    monkeypatch.setenv("USERDOMAIN", "PC")
    monkeypatch.setenv("USERNAME", "diego")
    return calls


def test_on_windows_the_token_file_is_cut_off_from_its_folder_before_the_token_is_written(
    windows, tmp_path
):
    token = tmp_path / "token.json"
    token.write_text("an earlier token")

    auth.save_credentials(FakeCredentials(), token)

    [call] = windows
    assert call["args"] == ["icacls", str(token), "/inheritance:r", "/grant:r", "PC\\diego:F"]
    assert call["kwargs"]["check"] is True
    assert call["content"] == ""
    assert token.read_text() == TOKEN_JSON


def test_on_windows_a_failed_icacls_leaves_no_token_on_disk(monkeypatch, tmp_path):
    def fail(args, **kwargs):
        raise subprocess.CalledProcessError(5, args)

    monkeypatch.setattr(auth, "WINDOWS", True)
    monkeypatch.setattr(auth.subprocess, "run", fail)
    token = tmp_path / "token.json"

    with pytest.raises(subprocess.CalledProcessError):
        auth.save_credentials(FakeCredentials(), token)

    assert "SECRET" not in token.read_text()


def test_the_windows_user_without_a_domain_is_the_user_name(monkeypatch):
    monkeypatch.delenv("USERDOMAIN", raising=False)
    monkeypatch.setenv("USERNAME", "diego")

    assert auth.windows_user() == "diego"
