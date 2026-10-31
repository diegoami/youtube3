import pytest


def prepare(fake, *responses):
    service = fake(*responses)
    service.client._channel = {"id": "UCmine", "title": "Mine"}
    return service


def test_preview_never_sends_a_request(fake):
    service = prepare(fake)
    result = service.client.create_playlist("Test")
    assert result == {
        "plan": {"channel": {"id": "UCmine", "title": "Mine"},
                 "body": {"snippet": {"title": "Test", "description": ""},
                          "status": {"privacyStatus": "private"}}},
        "applied": False, "response": None,
    }
    assert service.requests == []


@pytest.mark.parametrize("privacy", ["private", "unlisted", "public"])
def test_apply_creates_exactly_one_playlist(fake, privacy):
    response = {"id": "PLcreated", "status": {"privacyStatus": privacy}}
    service = prepare(fake, response)
    result = service.client.create_playlist("Test", description="Description", privacy=privacy, apply=True)
    assert result["applied"] is True
    assert result["response"] == response
    assert len(service.requests) == 1
    request = service.requests[0]
    assert (request.method, request.path, request.params["part"]) == ("POST", "playlists", "snippet,status")
    assert request.body == {"snippet": {"title": "Test", "description": "Description"},
                            "status": {"privacyStatus": privacy}}


@pytest.mark.parametrize("settings", [
    {"title": ""}, {"title": " \n "}, {"title": None}, {"title": 7},
    {"description": None}, {"privacy": "friends"}, {"privacy": None},
])
def test_invalid_input_fails_before_channel_lookup_or_write(fake, settings):
    service = fake()
    with pytest.raises(ValueError):
        service.client.create_playlist(**({"title": "Test"} | settings), apply=True)
    assert service.requests == []


def test_failed_insert_is_not_retried(fake):
    from googleapiclient.errors import HttpError

    service = prepare(fake, (503, {"error": {"message": "unavailable"}}))
    with pytest.raises(HttpError):
        service.client.create_playlist("Test", apply=True)
    assert len(service.requests) == 1


@pytest.mark.parametrize("apply", [False, True])
def test_installed_command_dispatch_and_result(fake, monkeypatch, capsys, apply):
    import sys
    from youtube3.cli import main

    service = prepare(fake, {"id": "PLcreated"})
    monkeypatch.setattr("youtube3.cli.common.client", lambda args: service.client)
    monkeypatch.setattr(sys, "argv", ["youtube3", "playlist", "create", "Test", "--profile", "test"]
                        + (["--apply"] if apply else []))
    main.main()
    output = capsys.readouterr().out
    assert len(service.requests) == int(apply)
    if apply:
        assert "Playlist ID: PLcreated" in output
        assert "https://www.youtube.com/playlist?list=PLcreated" in output
    else:
        assert "Dry run: no playlist created" in output
        assert '"privacyStatus": "private"' in output


def test_cli_does_not_print_raw_api_error(fake, monkeypatch, capsys):
    import sys
    from youtube3.cli import playlist_create

    service = prepare(fake, (503, {"error": {"message": "RAW_ERROR_SENTINEL"}}))
    monkeypatch.setattr(playlist_create, "client", lambda args: service.client)
    monkeypatch.setattr(sys, "argv", ["create", "Test", "--apply"])
    with pytest.raises(SystemExit) as error:
        playlist_create.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "Inspect the channel" in output.err
    assert "RAW_ERROR_SENTINEL" not in output.err + output.out
    assert len(service.requests) == 1


def test_cli_missing_id_requires_inspection(fake, monkeypatch, capsys):
    import sys
    from youtube3.cli import playlist_create

    service = prepare(fake, {})
    monkeypatch.setattr(playlist_create, "client", lambda args: service.client)
    monkeypatch.setattr(sys, "argv", ["create", "Test", "--apply"])
    with pytest.raises(SystemExit) as error:
        playlist_create.main()
    assert error.value.code == 1
    assert "inspect the channel" in capsys.readouterr().err
    assert len(service.requests) == 1
