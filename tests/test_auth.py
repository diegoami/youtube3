import json
import stat

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


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


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
    assert mode(token) == 0o600


def test_without_a_token_the_browser_flow_runs_and_the_token_is_saved(login, tmp_path):
    credentials, token = login()

    [(secrets_file, kwargs)] = FakeFlow.runs
    assert secrets_file == str(tmp_path / "my_secrets.json")
    assert kwargs == {"port": 0}
    assert token.read_text() == credentials.to_json()
    assert mode(token) == 0o600


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

    assert mode(token) == 0o600


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
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *args, **kwargs: "service")

    client = YoutubeClient(tmp_path / "secrets" / "client_secrets.json")

    assert client.youtube == "service"
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
