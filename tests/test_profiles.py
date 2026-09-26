import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence

from youtube3 import YoutubeClient, auth, profiles

CARAMELLA = {"items": [{"id": "UCcaramella", "snippet": {"title": "CaramellaLynx"}}]}
DIEGO = {"items": [{"id": "UCdiego", "snippet": {"title": "Diego Amicabile"}}]}
CHANNEL = {"id": "UCcaramella", "title": "CaramellaLynx"}
OTHER = {"id": "UCdiego", "title": "Diego Amicabile"}


def service(*responses):
    http = HttpMockSequence([({"status": "200"}, json.dumps(body)) for body in responses])
    return build("youtube", "v3", http=http, developerKey="test-key"), http


class Login:
    """Credentials whose saved form is {"token": token}."""

    def __init__(self, token):
        self.token = token

    def to_json(self):
        return json.dumps({"token": self.token})


def credentials_from(token, source=None):
    """credentials_from_info: a saved login is used as it is; none, or browser=True, is a browser login."""

    def login(secrets, info, **options):
        if info is None or options.get("browser"):
            return Login(token), auth.BROWSER
        return Login(info["token"]), source or auth.SAVED

    return login


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Profiles in tmp_path; answer(response) sets the channel the next login belongs to."""
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)

    def answer(response, token="NEW", source=None):
        monkeypatch.setattr("youtube3.youtube_client.credentials_from_info", credentials_from(token, source))
        monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(response)[0])

    return answer


def on_disk(name, folder):
    """(channel id, token) as the profile file holds them."""
    data = json.loads(profiles.profile_path(name, folder).read_text())
    return data["channel"]["id"], data["credentials"]["token"]


def files(folder):
    return sorted(p.name for p in Path(folder).iterdir())


# Names and places


@pytest.mark.parametrize("name", ["caramellalynx", "diego", "lynx-2", "a_b", "x"])
def test_good_names(name):
    assert profiles.check_name(name) == name


@pytest.mark.parametrize("name", ["", "Diego", "../x", "a/b", "a b", "-x", "x" * 41, None])
def test_bad_names_are_refused(name):
    with pytest.raises(profiles.ProfileError):
        profiles.check_name(name)


def test_profiles_live_in_the_user_config_folder():
    assert profiles.config_dir({"XDG_CONFIG_HOME": "/home/me/.cfg"}, windows=False).as_posix() == "/home/me/.cfg/youtube3/profiles"
    assert profiles.config_dir({"APPDATA": r"C:\Users\me\AppData\Roaming"}, windows=True).parts[-2:] == ("youtube3", "profiles")
    assert profiles.config_dir({}, windows=False).parts[-3:] == (".config", "youtube3", "profiles")


def test_output_names_carry_the_profile():
    assert profiles.output_name("liked", ".json") == "liked.json"
    assert profiles.output_name("liked", ".html", "diego") == "liked-diego.html"
    with pytest.raises(profiles.ProfileError):
        profiles.output_name("liked", ".json", "../x")


# One file: the channel and the login together


def test_a_profile_is_one_file_with_its_channel_and_login_for_the_owner_only(tmp_path):
    path = profiles.write("work", CHANNEL, {"token": "T"}, tmp_path)

    assert files(tmp_path) == ["work.json"]
    assert on_disk("work", tmp_path) == ("UCcaramella", "T")
    assert profiles.saved_channel("work", tmp_path)["title"] == "CaramellaLynx"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700


def test_a_profile_is_written_in_one_step(tmp_path, monkeypatch):
    # From the v2.6.1 review (#75, #79): the channel and the login are never
    # written apart, so no interruption can leave them disagreeing.
    replaced = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda src, dst: replaced.append((Path(src).read_text(), Path(dst).name)) or real(src, dst))

    profiles.write("work", CHANNEL, {"token": "T"}, tmp_path)

    [(content, target)] = replaced
    assert target == "work.json"
    assert json.loads(content)["channel"]["id"] == "UCcaramella" and json.loads(content)["credentials"] == {"token": "T"}


@pytest.mark.parametrize("content", ["{bad json", "[]", "", '{"channel": {"id": 1}, "credentials": {}}', '{"channel": null, "credentials": []}'])
def test_an_unreadable_profile_is_a_profile_error(tmp_path, content):
    # From the v2.6.0 review (#66).
    (tmp_path / "work.json").write_text(content)

    with pytest.raises(profiles.ProfileError, match="cannot be read.*profiles.py add work"):
        profiles.read("work", tmp_path)


def test_profiles_are_listed_with_their_channels(tmp_path):
    profiles.write("diego", OTHER, {"token": "D"}, tmp_path)
    profiles.write("caramellalynx", CHANNEL, {"token": "C"}, tmp_path)
    (tmp_path / "broken.json").write_text("{bad json")
    (tmp_path / "bare.json").write_text('{"token": "B"}')

    listed = {p["name"]: p.get("problem") or p["id"] for p in profiles.list_profiles(tmp_path)}
    assert listed == {
        "bare": "no channel recorded",
        "broken": "its file cannot be read",
        "caramellalynx": "UCcaramella",
        "diego": "UCdiego",
    }


# The channel check


def test_the_check_asks_for_the_signed_in_channel(tmp_path):
    profiles.write("work", CHANNEL, {"token": "T"}, tmp_path)
    yt, http = service(CARAMELLA)

    assert profiles.verify("work", yt, tmp_path) == CHANNEL

    [(uri, method, _, _)] = http.request_sequence
    assert method == "GET" and "channels" in uri and "mine=true" in uri


def test_a_login_for_another_channel_is_refused_and_changes_nothing(tmp_path):
    profiles.write("work", CHANNEL, {"token": "T"}, tmp_path)
    before = profiles.profile_path("work", tmp_path).read_text()

    with pytest.raises(profiles.ProfileError, match="CaramellaLynx.*Diego Amicabile.*picking CaramellaLynx"):
        profiles.verify("work", service(DIEGO)[0], tmp_path)

    assert profiles.profile_path("work", tmp_path).read_text() == before


def test_a_client_with_a_profile_and_a_service_checks_its_channel(home, tmp_path):
    profiles.write("caramellalynx", CHANNEL, {"token": "T"})

    with pytest.raises(profiles.ProfileError):
        YoutubeClient(service=service(DIEGO)[0], profile="caramellalynx")
    assert YoutubeClient(service=service(CARAMELLA)[0], profile="caramellalynx").signed_in_channel() == CHANNEL


def test_a_profile_and_a_token_file_together_are_refused():
    with pytest.raises(ValueError):
        YoutubeClient("client_secrets.json", token_file="t.json", profile="diego")


# Logging in with a profile


def test_the_first_login_records_the_channel_with_the_login(home, tmp_path):
    home(CARAMELLA, token="FIRST")

    client = YoutubeClient("client_secrets.json", profile="new")

    assert client.signed_in_channel() == CHANNEL
    assert on_disk("new", tmp_path) == ("UCcaramella", "FIRST")


def test_a_profile_logs_in_with_the_account_chooser(home, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "youtube3.youtube_client.credentials_from_info", lambda s, info, **o: calls.append((info, o)) or (Login("T"), auth.BROWSER)
    )
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(DIEGO)[0])

    YoutubeClient("client_secrets.json", profile="diego")

    assert calls == [(None, {"choose_account": True, "browser": False})]


def test_a_saved_login_for_its_channel_is_used_and_not_rewritten(home, tmp_path, monkeypatch):
    # From the v2.6.1 review (#76).
    profiles.write("work", CHANNEL, {"token": "OLD"})
    home(CARAMELLA)

    def refuse(*args):
        raise PermissionError("read-only folder")

    monkeypatch.setattr(profiles, "write_private", refuse)

    assert YoutubeClient("client_secrets.json", profile="work").signed_in_channel() == CHANNEL
    assert on_disk("work", tmp_path) == ("UCcaramella", "OLD")


def test_a_refreshed_login_is_saved_with_its_channel(home, tmp_path):
    profiles.write("work", CHANNEL, {"token": "OLD"})
    home(CARAMELLA, source=auth.REFRESHED)

    YoutubeClient("client_secrets.json", profile="work")

    assert on_disk("work", tmp_path) == ("UCcaramella", "OLD")
    assert json.loads(profiles.profile_path("work").read_text())["channel"]["added_at"]


def test_a_profile_with_no_channel_recorded_is_refused_not_rebound(home, tmp_path):
    # From the v2.6.0 review (#65).
    (tmp_path / "work.json").write_text('{"token": "OLD"}')
    home(DIEGO)

    with pytest.raises(profiles.ProfileError, match="no channel recorded.*profiles.py add work"):
        YoutubeClient("client_secrets.json", profile="work")

    assert (tmp_path / "work.json").read_text() == '{"token": "OLD"}'


def test_an_automatic_browser_login_for_another_channel_never_replaces_the_profile(home, tmp_path, monkeypatch):
    # From the v2.6.0 review (#69): the saved login expired or was revoked,
    # the browser opened by itself, and another channel was picked.
    profiles.write("work", CHANNEL, {"token": "OLD"})
    before = profiles.profile_path("work").read_text()
    home(DIEGO)
    monkeypatch.setattr("youtube3.youtube_client.credentials_from_info", lambda s, info, **o: (Login("WRONG"), auth.BROWSER))

    with pytest.raises(profiles.ProfileError, match="picking CaramellaLynx"):
        YoutubeClient("client_secrets.json", profile="work")

    assert profiles.profile_path("work").read_text() == before


# profiles.py add: logging in again


@pytest.mark.parametrize("answer, kept", [(CARAMELLA, "NEW"), (DIEGO, "OLD")])
def test_logging_in_again_keeps_the_new_login_only_for_the_profiles_channel(home, tmp_path, answer, kept):
    # From the v2.6.0 review (#67).
    profiles.write("work", CHANNEL, {"token": "OLD"})
    home(answer, token="NEW")

    try:
        YoutubeClient("client_secrets.json", profile="work", new_login=True)
    except profiles.ProfileError:
        assert kept == "OLD"

    assert on_disk("work", tmp_path) == ("UCcaramella", kept)
    assert files(tmp_path) == ["work.json"]


def test_logging_in_again_repairs_a_profile_with_no_channel_or_an_unreadable_file(home, tmp_path):
    (tmp_path / "bare.json").write_text('{"token": "OLD"}')
    (tmp_path / "broken.json").write_text("{bad json")
    home(DIEGO, token="NEW")

    for name in ("bare", "broken"):
        YoutubeClient("client_secrets.json", profile=name, new_login=True)
        assert on_disk(name, tmp_path) == ("UCdiego", "NEW")


def test_a_failed_or_interrupted_login_leaves_the_profile_as_it_was(home, tmp_path, monkeypatch):
    # From the v2.6.0 and v2.6.1 reviews (#70, #75, #79): nothing is written
    # before the one replacement, so any stop before it changes nothing.
    profiles.write("work", CHANNEL, {"token": "OLD"})
    before = profiles.profile_path("work").read_text()
    home(CARAMELLA, token="NEW")
    for failure in (OSError("disk full"), KeyboardInterrupt()):

        def fail(*args, error=failure):
            raise error

        monkeypatch.setattr(profiles, "write_private", fail)
        with pytest.raises(type(failure)):
            YoutubeClient("client_secrets.json", profile="work", new_login=True)
        assert profiles.profile_path("work").read_text() == before
    assert files(tmp_path) == ["work.json"]


def test_a_run_killed_while_logging_in_leaves_the_profile_as_it_was(tmp_path):
    profiles.write("work", CHANNEL, {"token": "OLD"}, tmp_path)
    before = profiles.profile_path("work", tmp_path).read_text()
    code = (
        "import os, pathlib\n"
        "from youtube3 import auth\n"
        "real = auth.restrict_to_owner\n"
        "def killed(path):\n"
        "    real(path)\n"
        "    pathlib.Path(path).write_text('half')\n"
        "    os._exit(9)\n"
        "auth.restrict_to_owner = killed\n"
        "from youtube3 import profiles\n"
        f"profiles.write('work', {{'id': 'UCdiego', 'title': 'D'}}, {{'token': 'NEW'}}, pathlib.Path({str(tmp_path)!r}))\n"
    )
    run = subprocess.run([sys.executable, "-c", code], timeout=60)

    assert run.returncode == 9
    assert profiles.profile_path("work", tmp_path).read_text() == before
    assert on_disk("work", tmp_path) == ("UCcaramella", "OLD")


def test_concurrent_first_logins_leave_one_whole_profile(tmp_path):
    # From the v2.6.1 review (#77, #80): with no lock, two runs that write at
    # once each replace the whole file, so the last one wins, never a mix.
    code = (
        "import pathlib, sys\n"
        "from youtube3 import profiles\n"
        "channel, token = sys.argv[1], sys.argv[2]\n"
        "for _ in range(200):\n"
        "    try:\n"
        f"        profiles.write('work', {{'id': channel, 'title': channel}}, {{'token': token}}, pathlib.Path({str(tmp_path)!r}))\n"
        "    except PermissionError:\n"
        "        pass  # Windows refuses a replace racing another one: loud, and the file stays whole\n"
    )
    runs = [subprocess.Popen([sys.executable, "-c", code, f"UC{who}", who]) for who in ("A", "B")]
    for run in runs:
        assert run.wait(timeout=120) == 0

    channel, token = on_disk("work", tmp_path)
    assert (channel, token) in {("UCA", "A"), ("UCB", "B")}
    assert files(tmp_path) == ["work.json"]


# The v2.6.0 layout: a bare token, its channel beside it


def test_a_v260_profile_is_used_and_rewritten_as_one_file(home, tmp_path):
    (tmp_path / "work.json").write_text('{"token": "OLD"}')
    (tmp_path / "work.channel.json").write_text(json.dumps({**CHANNEL, "added_at": "2026-09-25T10:00:00+00:00"}))
    home(CARAMELLA)

    assert profiles.saved_channel("work")["id"] == "UCcaramella"
    YoutubeClient("client_secrets.json", profile="work")

    assert files(tmp_path) == ["work.json"]
    assert on_disk("work", tmp_path) == ("UCcaramella", "OLD")
    assert json.loads((tmp_path / "work.json").read_text())["channel"]["added_at"] == "2026-09-25T10:00:00+00:00"


def test_a_v260_profile_for_another_channel_is_refused_and_left_alone(home, tmp_path):
    (tmp_path / "work.json").write_text('{"token": "OLD"}')
    (tmp_path / "work.channel.json").write_text(json.dumps(CHANNEL))
    home(DIEGO)

    with pytest.raises(profiles.ProfileError, match="picking CaramellaLynx"):
        YoutubeClient("client_secrets.json", profile="work")

    assert files(tmp_path) == ["work.channel.json", "work.json"]


# Adopting today's token


def test_adopt_copies_the_token_with_its_channel_and_keeps_the_original(tmp_path):
    original = tmp_path / "token.json"
    original.write_text('{"token": "SECRET"}')
    folder = tmp_path / "profiles"

    target = profiles.adopt("caramellalynx", original, CHANNEL, folder=folder)

    assert on_disk("caramellalynx", folder) == ("UCcaramella", "SECRET")
    assert original.read_text() == '{"token": "SECRET"}'
    assert files(folder) == ["caramellalynx.json"]
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700


def test_adopt_refuses_an_existing_profile_a_missing_token_or_not_a_token(tmp_path):
    original = tmp_path / "token.json"
    original.write_text('{"token": "T"}')
    profiles.adopt("x", original, CHANNEL, folder=tmp_path / "p")
    (tmp_path / "list.json").write_text("[]")

    with pytest.raises(profiles.ProfileError, match="already exists"):
        profiles.adopt("x", original, CHANNEL, folder=tmp_path / "p")
    with pytest.raises(profiles.ProfileError, match="no such token"):
        profiles.adopt("y", tmp_path / "none.json", CHANNEL, folder=tmp_path / "p")
    with pytest.raises(profiles.ProfileError, match="not a saved login"):
        profiles.adopt("z", tmp_path / "list.json", CHANNEL, folder=tmp_path / "p")


def test_the_profile_file_is_restricted_before_the_login_is_in_it(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(auth, "restrict_to_owner", lambda path: seen.append(open(path).read()))

    profiles.write("x", CHANNEL, {"token": "SECRET"}, tmp_path)

    assert seen == [""]


# Without a profile, nothing changes


def test_without_a_profile_the_login_is_unchanged(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("youtube3.youtube_client.load_credentials", lambda s, t, **o: calls.append(o) or "c")
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: "service")

    YoutubeClient(tmp_path / "client_secrets.json")

    assert calls == [{"choose_account": False}]


def test_the_account_chooser_is_asked_for_on_first_login(monkeypatch, tmp_path):
    runs = []

    class Flow:
        def run_local_server(self, **kwargs):
            runs.append(kwargs)
            return Login("T")

    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", lambda *a: Flow())
    auth.load_credentials(tmp_path / "s.json", tmp_path / "t.json", choose_account=True)

    assert runs == [{"port": 0, "prompt": "select_account consent"}]
