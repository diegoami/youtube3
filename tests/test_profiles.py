import json
import os
import stat
import subprocess
import sys

import pytest
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence

from youtube3 import YoutubeClient, auth, profiles

CARAMELLA = {"items": [{"id": "UCcaramella", "snippet": {"title": "CaramellaLynx"}}]}
DIEGO = {"items": [{"id": "UCdiego", "snippet": {"title": "Diego Amicabile"}}]}
CHANNEL = {"id": "UCcaramella", "title": "CaramellaLynx"}


def service(*responses):
    http = HttpMockSequence([({"status": "200"}, json.dumps(body)) for body in responses])
    return build("youtube", "v3", http=http, developerKey="test-key"), http


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


# The channel a profile belongs to


def test_the_first_use_remembers_the_channel(tmp_path):
    yt, _ = service(CARAMELLA)

    channel = profiles.verify("caramellalynx", yt, folder=tmp_path, register=True)

    assert channel == {"id": "UCcaramella", "title": "CaramellaLynx"}
    assert profiles.saved_channel("caramellalynx", tmp_path)["id"] == "UCcaramella"


def test_a_later_use_with_the_same_channel_passes(tmp_path):
    profiles.verify("caramellalynx", service(CARAMELLA)[0], folder=tmp_path, register=True)

    assert profiles.verify("caramellalynx", service(CARAMELLA)[0], folder=tmp_path)["title"] == "CaramellaLynx"


def test_a_login_for_another_channel_is_refused_and_changes_nothing(tmp_path):
    profiles.verify("caramellalynx", service(CARAMELLA)[0], folder=tmp_path, register=True)
    before = profiles.channel_path("caramellalynx", tmp_path).read_text()

    with pytest.raises(profiles.ProfileError, match="CaramellaLynx.*Diego Amicabile"):
        profiles.verify("caramellalynx", service(DIEGO)[0], folder=tmp_path)

    assert profiles.channel_path("caramellalynx", tmp_path).read_text() == before


def test_the_check_asks_for_the_signed_in_channel(tmp_path):
    yt, http = service(CARAMELLA)

    profiles.verify("caramellalynx", yt, folder=tmp_path, register=True)

    [(uri, method, _, _)] = http.request_sequence
    assert method == "GET" and "channels" in uri and "mine=true" in uri


def test_profiles_are_listed_with_their_channels(tmp_path):
    for name, answer in (("diego", DIEGO), ("caramellalynx", CARAMELLA)):
        (tmp_path / f"{name}.json").write_text("{}")
        profiles.verify(name, service(answer)[0], folder=tmp_path, register=True)
    (tmp_path / "new.json").write_text("{}")
    (tmp_path / "broken.json").write_text("{}")
    (tmp_path / "broken.channel.json").write_text("{bad json")

    listed = [{key: p[key] for key in ("name", "id", "title")} for p in profiles.list_profiles(tmp_path)]
    assert listed == [
        {"name": "broken", "id": None, "title": None},
        {"name": "caramellalynx", "id": "UCcaramella", "title": "CaramellaLynx"},
        {"name": "diego", "id": "UCdiego", "title": "Diego Amicabile"},
        {"name": "new", "id": None, "title": None},
    ]
    problems = {p["name"]: p.get("problem") for p in profiles.list_profiles(tmp_path)}
    assert problems["broken"] == "its channel file cannot be read" and problems["new"] == "no channel recorded"


# Adopting today's token


def test_adopt_copies_the_token_restricted_and_keeps_the_original(tmp_path):
    original = tmp_path / "token.json"
    original.write_text('{"token": "SECRET"}')
    folder = tmp_path / "profiles"

    target = profiles.adopt("caramellalynx", original, CHANNEL, folder=folder)

    assert target.read_text() == '{"token": "SECRET"}'
    assert original.exists()
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert sorted(p.name for p in folder.iterdir()) == ["caramellalynx.channel.json", "caramellalynx.json"]
    assert profiles.saved_channel("caramellalynx", folder)["id"] == "UCcaramella"


def test_adopt_refuses_an_existing_profile_or_a_missing_token(tmp_path):
    original = tmp_path / "token.json"
    original.write_text("{}")
    profiles.adopt("x", original, CHANNEL, folder=tmp_path / "p")

    with pytest.raises(profiles.ProfileError, match="already exists"):
        profiles.adopt("x", original, CHANNEL, folder=tmp_path / "p")
    with pytest.raises(profiles.ProfileError, match="no such token"):
        profiles.adopt("y", tmp_path / "none.json", CHANNEL, folder=tmp_path / "p")


def test_adopt_restricts_the_file_before_the_token_is_in_it(tmp_path, monkeypatch):
    original = tmp_path / "token.json"
    original.write_text('{"token": "SECRET"}')
    seen = []
    monkeypatch.setattr(profiles, "restrict_to_owner", lambda path: seen.append(open(path).read()))

    profiles.adopt("x", original, CHANNEL, folder=tmp_path / "p")

    assert seen == [""]


# The client


def test_a_client_with_a_profile_checks_its_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    profiles.verify("caramellalynx", service(CARAMELLA)[0], register=True)

    with pytest.raises(profiles.ProfileError):
        YoutubeClient(service=service(DIEGO)[0], profile="caramellalynx")
    client = YoutubeClient(service=service(CARAMELLA)[0], profile="caramellalynx")
    assert client.signed_in_channel() == {"id": "UCcaramella", "title": "CaramellaLynx"}


def test_a_profile_logs_in_to_its_own_token_with_the_account_chooser(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    calls = []
    monkeypatch.setattr("youtube3.youtube_client.obtain_credentials", lambda s, t, **o: calls.append((t, o)) or (Login("T"), auth.BROWSER))
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(DIEGO)[0])

    client = YoutubeClient("client_secrets.json", profile="diego")

    assert calls == [(tmp_path / "diego.json", {"choose_account": True})]
    assert client.signed_in_channel()["title"] == "Diego Amicabile"


def test_a_profile_and_a_token_file_together_are_refused():
    with pytest.raises(ValueError):
        YoutubeClient("client_secrets.json", token_file="t.json", profile="diego")


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

            class Credentials:
                def to_json(self):
                    return "{}"

            return Credentials()

    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", lambda *a: Flow())
    auth.load_credentials(tmp_path / "s.json", tmp_path / "t.json", choose_account=True)

    assert runs == [{"port": 0, "prompt": "select_account consent"}]


# From the v2.6.0 review: the channel is recorded only with a new login (#65),
# a broken record is a clear error (#66), and add logs in again (#67)


def test_a_profile_with_no_channel_recorded_is_refused_not_rebound(tmp_path):
    profiles.verify("work", service(CARAMELLA)[0], folder=tmp_path, register=True)
    profiles.channel_path("work", tmp_path).unlink()

    with pytest.raises(profiles.ProfileError, match="no channel recorded.*profiles.py add work"):
        profiles.verify("work", service(DIEGO)[0], folder=tmp_path)

    assert not profiles.channel_path("work", tmp_path).exists()


@pytest.mark.parametrize("content", ["{bad json", "[]", '{"id": "UCx"}', '{"id": 1, "title": "x"}', ""])
def test_an_unreadable_channel_file_is_a_profile_error(tmp_path, content):
    profiles.channel_path("work", tmp_path).write_text(content)

    with pytest.raises(profiles.ProfileError, match="cannot be read.*profiles.py add work"):
        profiles.verify("work", service(CARAMELLA)[0], folder=tmp_path, register=True)


def test_a_client_records_the_channel_of_a_new_login_only(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    monkeypatch.setattr("youtube3.youtube_client.obtain_credentials", fake_login("TOKEN"))
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(CARAMELLA)[0])

    YoutubeClient("client_secrets.json", profile="caramellalynx")
    assert profiles.saved_channel("caramellalynx")["id"] == "UCcaramella"

    profiles.channel_path("caramellalynx").unlink()
    with pytest.raises(profiles.ProfileError, match="no channel recorded"):
        YoutubeClient("client_secrets.json", profile="caramellalynx")
    assert profiles.token_path("caramellalynx").read_text() == "TOKEN"


def test_a_new_login_for_another_channel_is_not_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    profiles.verify("caramellalynx", service(CARAMELLA)[0], register=True)
    monkeypatch.setattr("youtube3.youtube_client.obtain_credentials", fake_login("WRONG"))
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(DIEGO)[0])

    with pytest.raises(profiles.ProfileError, match="picking CaramellaLynx"):
        YoutubeClient("client_secrets.json", profile="caramellalynx")

    assert not profiles.token_path("caramellalynx").exists()
    assert profiles.saved_channel("caramellalynx")["id"] == "UCcaramella"


@pytest.mark.parametrize("answer, kept", [(CARAMELLA, "NEW"), (DIEGO, "OLD")])
def test_logging_in_again_keeps_the_new_login_only_for_the_profiles_channel(tmp_path, monkeypatch, answer, kept):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    profiles.verify("caramellalynx", service(CARAMELLA)[0], register=True)
    profiles.token_path("caramellalynx").write_text("OLD")
    monkeypatch.setattr("youtube3.youtube_client.obtain_credentials", fake_login("NEW"))
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(answer)[0])

    try:
        with profiles.replacing_login("caramellalynx"):
            YoutubeClient("client_secrets.json", profile="caramellalynx")
    except profiles.ProfileError:
        assert kept == "OLD"

    assert profiles.token_path("caramellalynx").read_text() == kept
    assert files(tmp_path) == ["caramellalynx.channel.json", "caramellalynx.json"]
    assert profiles.saved_channel("caramellalynx")["id"] == "UCcaramella"


def test_logging_in_again_with_no_channel_recorded_records_the_new_one(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    profiles.token_path("work").write_text("OLD")
    monkeypatch.setattr("youtube3.youtube_client.obtain_credentials", fake_login("NEW"))
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(DIEGO)[0])

    with profiles.replacing_login("work"):
        YoutubeClient("client_secrets.json", profile="work")

    assert profiles.token_path("work").read_text() == "NEW"
    assert profiles.saved_channel("work")["id"] == "UCdiego"


def files(folder):
    """The folder's files, without the profile locks, which stay once made."""
    return sorted(p.name for p in folder.iterdir() if not p.name.endswith(".lock"))


class Login:
    """Credentials whose saved form is token."""

    def __init__(self, token):
        self.token = token

    def to_json(self):
        return self.token


def fake_login(token):
    """obtain_credentials: a saved token is used as it is, and a missing one is a fresh browser login."""

    def login(secrets, token_file, **options):
        from pathlib import Path

        return Login(token), auth.SAVED if Path(token_file).exists() else auth.BROWSER

    return login


# From the v2.6.0 review, round 2: a login is saved only once its channel
# checks out (#69), and an interrupted replacement is settled (#70)


class Flow:
    def run_local_server(self, **kwargs):
        return Login("FRESH")


@pytest.mark.parametrize("answer, saved", [(DIEGO, "{unreadable"), (CARAMELLA, "FRESH")])
def test_a_fresh_login_replaces_the_saved_one_only_for_the_profiles_channel(tmp_path, monkeypatch, answer, saved):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    profiles.verify("work", service(CARAMELLA)[0], register=True)
    profiles.token_path("work").write_text("{unreadable")
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", lambda *a: Flow())
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(answer)[0])

    try:
        YoutubeClient(tmp_path / "s.json", profile="work")
    except profiles.ProfileError as error:
        assert "picking CaramellaLynx" in str(error) and answer is DIEGO

    assert profiles.token_path("work").read_text() == saved
    assert profiles.saved_channel("work")["id"] == "UCcaramella"


def test_an_interrupted_replacement_gives_the_old_login_back(tmp_path):
    (tmp_path / ".work.json.previous").write_text("OLD")

    profiles.recover("work", tmp_path)

    assert profiles.token_path("work", tmp_path).read_text() == "OLD"
    assert files(tmp_path) == ["work.json"]


def test_a_replacement_interrupted_after_saving_keeps_the_new_login(tmp_path):
    profiles.token_path("work", tmp_path).write_text("NEW")
    (tmp_path / ".work.json.previous").write_text("OLD")

    profiles.recover("work", tmp_path)

    assert profiles.token_path("work", tmp_path).read_text() == "NEW"
    assert files(tmp_path) == ["work.json"]


def test_logging_in_again_after_an_interruption_leaves_no_backup(tmp_path):
    (tmp_path / ".work.json.previous").write_text("OLD")

    with profiles.replacing_login("work", tmp_path):
        assert not profiles.token_path("work", tmp_path).exists()
        profiles.token_path("work", tmp_path).write_text("NEW")

    assert files(tmp_path) == ["work.json"]


def test_a_client_settles_an_interrupted_replacement_before_logging_in(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    profiles.verify("work", service(CARAMELLA)[0], register=True)
    (tmp_path / ".work.json.previous").write_text("OLD")
    monkeypatch.setattr("youtube3.youtube_client.obtain_credentials", fake_login("OLD"))
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(CARAMELLA)[0])

    YoutubeClient("client_secrets.json", profile="work")

    assert profiles.token_path("work").read_text() == "OLD"
    assert not (tmp_path / ".work.json.previous").exists()


def test_the_first_browser_login_of_a_profile_records_its_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    monkeypatch.setattr(auth.InstalledAppFlow, "from_client_secrets_file", lambda *a: Flow())
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(CARAMELLA)[0])

    YoutubeClient(tmp_path / "s.json", profile="new")

    assert profiles.saved_channel("new")["id"] == "UCcaramella"
    assert profiles.token_path("new").read_text() == "FRESH"


# From the v2.6.1 review: a record is written only after its login is saved,
# and rolled back with it (#75); a valid login is not rewritten (#76); another
# run cannot touch a replacement in progress (#77)


def test_an_add_that_fails_to_save_leaves_the_old_login_and_no_new_record(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    profiles.token_path("work").write_text("OLD")
    monkeypatch.setattr("youtube3.youtube_client.obtain_credentials", fake_login("NEW"))
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(DIEGO)[0])

    def disk_full(*args):
        raise OSError("disk full")

    monkeypatch.setattr("youtube3.youtube_client.save_credentials", disk_full)

    with pytest.raises(OSError):
        with profiles.replacing_login("work"):
            YoutubeClient("client_secrets.json", profile="work")

    assert profiles.token_path("work").read_text() == "OLD"
    assert profiles.saved_channel("work") is None
    assert files(tmp_path) == ["work.json"]


@pytest.mark.parametrize("recorded", [None, CARAMELLA])
def test_an_add_stopped_after_its_record_puts_the_old_record_back(tmp_path, monkeypatch, recorded):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    if recorded:
        profiles.verify("work", service(recorded)[0], register=True)
    before = profiles.channel_path("work").read_bytes() if recorded else None
    profiles.token_path("work").write_text("OLD")
    monkeypatch.setattr("youtube3.youtube_client.obtain_credentials", fake_login("NEW"))
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(recorded or DIEGO)[0])

    with pytest.raises(KeyboardInterrupt):
        with profiles.replacing_login("work"):
            YoutubeClient("client_secrets.json", profile="work")
            assert profiles.token_path("work").read_text() == "NEW"
            raise KeyboardInterrupt

    assert profiles.token_path("work").read_text() == "OLD"
    path = profiles.channel_path("work")
    assert (path.read_bytes() if path.exists() else None) == before


def test_the_record_is_written_only_after_the_login_is_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    monkeypatch.setattr("youtube3.youtube_client.obtain_credentials", fake_login("NEW"))
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(CARAMELLA)[0])
    seen = []
    real_record = profiles.record
    monkeypatch.setattr(profiles, "record", lambda *a, **k: seen.append(profiles.token_path("new").read_text()) or real_record(*a, **k))

    YoutubeClient("client_secrets.json", profile="new")

    assert seen == ["NEW"]


def test_a_valid_profile_login_is_not_rewritten(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    profiles.verify("work", service(CARAMELLA)[0], register=True)
    profiles.token_path("work").write_text("OLD")
    monkeypatch.setattr("youtube3.youtube_client.obtain_credentials", fake_login("OLD"))
    monkeypatch.setattr("youtube3.youtube_client.build", lambda *a, **k: service(CARAMELLA)[0])

    def refuse(*args):
        raise PermissionError("read-only folder")

    monkeypatch.setattr("youtube3.youtube_client.save_credentials", refuse)

    assert YoutubeClient("client_secrets.json", profile="work").signed_in_channel()["id"] == "UCcaramella"


def another_run(folder, then):
    """A second Python process inside replacing_login("work"), stopped until told to go on."""
    code = (
        "import os, sys, pathlib\n"
        "from youtube3 import profiles\n"
        f"with profiles.replacing_login('work', pathlib.Path({str(folder)!r})):\n"
        "    print('ready', flush=True)\n"
        "    sys.stdin.readline()\n"
        f"    {then}\n"
    )
    run = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert run.stdout.readline().strip() == "ready"
    return run


def test_another_run_cannot_touch_a_replacement_in_progress(tmp_path):
    profiles.token_path("work", tmp_path).write_text("OLD")
    run = another_run(tmp_path, "(pathlib.Path(%r) / 'work.json').write_text('NEW')" % str(tmp_path))

    with pytest.raises(profiles.ProfileError, match="another run"):
        profiles.recover("work", tmp_path)
    with pytest.raises(profiles.ProfileError, match="another run"):
        with profiles.replacing_login("work", tmp_path):
            pass
    run.communicate("go\n", timeout=30)

    assert run.returncode == 0
    assert profiles.token_path("work", tmp_path).read_text() == "NEW"
    assert files(tmp_path) == ["work.json"]


def test_a_run_killed_mid_replacement_leaves_the_profile_recoverable(tmp_path):
    profiles.token_path("work", tmp_path).write_text("OLD")
    run = another_run(tmp_path, "os._exit(9)")
    run.communicate("go\n", timeout=30)
    assert run.returncode == 9 and not profiles.token_path("work", tmp_path).exists()

    profiles.recover("work", tmp_path)

    assert profiles.token_path("work", tmp_path).read_text() == "OLD"
    assert files(tmp_path) == ["work.json"]
