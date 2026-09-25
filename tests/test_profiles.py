import json
import os
import stat

import pytest
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence

from youtube3 import YoutubeClient, auth, profiles

CARAMELLA = {"items": [{"id": "UCcaramella", "snippet": {"title": "CaramellaLynx"}}]}
DIEGO = {"items": [{"id": "UCdiego", "snippet": {"title": "Diego Amicabile"}}]}


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

    channel = profiles.verify("caramellalynx", yt, folder=tmp_path)

    assert channel == {"id": "UCcaramella", "title": "CaramellaLynx"}
    assert profiles.saved_channel("caramellalynx", tmp_path)["id"] == "UCcaramella"


def test_a_later_use_with_the_same_channel_passes(tmp_path):
    profiles.verify("caramellalynx", service(CARAMELLA)[0], folder=tmp_path)

    assert profiles.verify("caramellalynx", service(CARAMELLA)[0], folder=tmp_path)["title"] == "CaramellaLynx"


def test_a_login_for_another_channel_is_refused_and_changes_nothing(tmp_path):
    profiles.verify("caramellalynx", service(CARAMELLA)[0], folder=tmp_path)
    before = profiles.channel_path("caramellalynx", tmp_path).read_text()

    with pytest.raises(profiles.ProfileError, match="CaramellaLynx.*Diego Amicabile"):
        profiles.verify("caramellalynx", service(DIEGO)[0], folder=tmp_path)

    assert profiles.channel_path("caramellalynx", tmp_path).read_text() == before


def test_the_check_asks_for_the_signed_in_channel(tmp_path):
    yt, http = service(CARAMELLA)

    profiles.verify("caramellalynx", yt, folder=tmp_path)

    [(uri, method, _, _)] = http.request_sequence
    assert method == "GET" and "channels" in uri and "mine=true" in uri


def test_profiles_are_listed_with_their_channels(tmp_path):
    for name, answer in (("diego", DIEGO), ("caramellalynx", CARAMELLA)):
        (tmp_path / f"{name}.json").write_text("{}")
        profiles.verify(name, service(answer)[0], folder=tmp_path)
    (tmp_path / "new.json").write_text("{}")

    listed = [{key: p[key] for key in ("name", "id", "title")} for p in profiles.list_profiles(tmp_path)]
    assert listed == [
        {"name": "caramellalynx", "id": "UCcaramella", "title": "CaramellaLynx"},
        {"name": "diego", "id": "UCdiego", "title": "Diego Amicabile"},
        {"name": "new", "id": None, "title": None},
    ]


# Adopting today's token


def test_adopt_copies_the_token_restricted_and_keeps_the_original(tmp_path):
    original = tmp_path / "token.json"
    original.write_text('{"token": "SECRET"}')
    folder = tmp_path / "profiles"

    target = profiles.adopt("caramellalynx", original, folder=folder)

    assert target.read_text() == '{"token": "SECRET"}'
    assert original.exists()
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert [p.name for p in folder.iterdir()] == ["caramellalynx.json"]


def test_adopt_refuses_an_existing_profile_or_a_missing_token(tmp_path):
    original = tmp_path / "token.json"
    original.write_text("{}")
    profiles.adopt("x", original, folder=tmp_path / "p")

    with pytest.raises(profiles.ProfileError, match="already exists"):
        profiles.adopt("x", original, folder=tmp_path / "p")
    with pytest.raises(profiles.ProfileError, match="no such token"):
        profiles.adopt("y", tmp_path / "none.json", folder=tmp_path / "p")


def test_adopt_restricts_the_file_before_the_token_is_in_it(tmp_path, monkeypatch):
    original = tmp_path / "token.json"
    original.write_text('{"token": "SECRET"}')
    seen = []
    monkeypatch.setattr(profiles, "restrict_to_owner", lambda path: seen.append(open(path).read()))

    profiles.adopt("x", original, folder=tmp_path / "p")

    assert seen == [""]


# The client


def test_a_client_with_a_profile_checks_its_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    profiles.verify("caramellalynx", service(CARAMELLA)[0])

    with pytest.raises(profiles.ProfileError):
        YoutubeClient(service=service(DIEGO)[0], profile="caramellalynx")
    client = YoutubeClient(service=service(CARAMELLA)[0], profile="caramellalynx")
    assert client.signed_in_channel() == {"id": "UCcaramella", "title": "CaramellaLynx"}


def test_a_profile_logs_in_to_its_own_token_with_the_account_chooser(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "config_dir", lambda *a, **k: tmp_path)
    calls = []
    monkeypatch.setattr("youtube3.youtube_client.load_credentials", lambda s, t, **o: calls.append((t, o)) or "c")
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
