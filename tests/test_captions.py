"""Offline caption behavior over the bundled discovery document."""

import json
import sys
from email import policy
from email.parser import BytesParser

import pytest

from youtube3 import captions
from youtube3.cli import main

SRT = '1\n00:00:00,000 --> 00:00:01,500\nHello world\n'
VTT = 'WEBVTT\n\n00:00.000 --> 00:01.500\nHello world\n'
VIDEO = {"items": [{"id": "vid", "snippet": {"channelId": "mine"}}]}
TRACK = {"id": "track", "snippet": {"videoId": "vid", "language": "en", "name": "English", "isDraft": True, "status": "serving"}}


def prepared(fake, *responses):
    service = fake(*responses)
    service.client._channel = {"id": "mine", "title": "Mine"}
    return service


@pytest.fixture
def subtitle(tmp_path):
    path = tmp_path / 'test.srt'
    path.write_bytes(SRT.encode('utf-8'))
    return path


def media_parts(request):
    message = BytesParser(policy=policy.default).parsebytes(
        b'Content-Type: ' + request.headers['content-type'].encode() + b'\r\n\r\n' + request.raw)
    return [part.get_payload(decode=True) for part in message.iter_parts()]


def test_list_tracks_uses_owned_video_and_safe_metadata(fake):
    service = prepared(fake, VIDEO, {"items": [TRACK | {"secret": "omit"}]})
    assert service.client.list_captions('vid') == [TRACK]
    assert [(r.method, r.path) for r in service.requests] == [('GET', 'videos'), ('GET', 'captions')]
    assert service.requests[-1].params['videoId'] == 'vid'


def test_preview_has_quota_fingerprint_and_no_write(fake, subtitle):
    service = prepared(fake, VIDEO, {"items": []})
    result = service.client.upload_caption('vid', subtitle, language='en', name='English')
    assert result['applied'] is False and result['result'] is None
    assert result['plan']['quota'] == 400
    assert result['plan']['file']['sha256']
    assert all(r.method == 'GET' for r in service.requests)


@pytest.mark.parametrize('replace', [False, True])
def test_exact_caption_media_and_target(fake, subtitle, replace):
    tracks = {"items": [TRACK]} if replace else {"items": []}
    service = prepared(fake, VIDEO, tracks, VIDEO, tracks, TRACK)
    if replace:
        result = service.client.replace_caption('vid', 'track', subtitle, apply=True)
    else:
        result = service.client.upload_caption('vid', subtitle, language='en', name='English', apply=True)
    assert result['result']['id'] == 'track'
    writes = [r for r in service.requests if r.method != 'GET']
    assert len(writes) == 1
    request = writes[0]
    assert (request.method, request.path, request.params['part']) == ('PUT' if replace else 'POST', 'captions', 'snippet')
    body, media = media_parts(request)
    expected = {'id': 'track', 'snippet': {'isDraft': True}} if replace else {'snippet': {'videoId': 'vid', 'language': 'en', 'name': 'English', 'isDraft': False}}
    assert json.loads(body) == expected
    assert media == subtitle.read_bytes()
    assert 'sync' not in request.params


@pytest.mark.parametrize('text,suffix', [(SRT, '.srt'), (SRT.replace('\n', '\r\n'), '.srt'), (VTT, '.vtt'), ('\ufeff' + SRT, '.srt')])
def test_timed_utf8_formats(tmp_path, text, suffix):
    path = tmp_path / ('test' + suffix)
    path.write_bytes(text.encode('utf-8'))
    assert captions.check_caption(path)['bytes'] == len(text.encode())


@pytest.mark.parametrize('text,suffix', [('plain transcript', '.srt'), ('1\n00:00:02,000 --> 00:00:01,000\nText', '.srt'), ('WEBVTT\n\n00:60.000 --> 00:61.000\nText', '.vtt'), ('WEBVTT\n\n00:00.000 --> 00:01.000\n', '.vtt'), (SRT, '.txt')])
def test_reject_invalid_timing_and_transcripts(tmp_path, text, suffix):
    path = tmp_path / ('bad' + suffix)
    path.write_bytes(text.encode('utf-8'))
    with pytest.raises(ValueError):
        captions.check_caption(path)


@pytest.mark.parametrize('options', [{'language': ''}, {'language': 'english words'}, {'name': 'x' * 151}, {'draft': 'yes'}])
def test_invalid_metadata_before_api(fake, subtitle, options):
    service = prepared(fake)
    with pytest.raises(ValueError):
        service.client.upload_caption('vid', subtitle, **({'language': 'en', 'name': 'English'} | options))
    assert not service.requests


def test_wrong_owner_and_duplicate_tracks_refused(fake, subtitle):
    service = prepared(fake, {"items": [{"id": "vid", "snippet": {"channelId": "other"}}]})
    with pytest.raises(ValueError, match='channel'):
        service.client.upload_caption('vid', subtitle, language='en')
    assert len(service.requests) == 1
    service = prepared(fake, VIDEO, {'items': [TRACK]})
    with pytest.raises(ValueError, match='already'):
        service.client.upload_caption('vid', subtitle, language='en', name='English')
    assert all(r.method == 'GET' for r in service.requests)


def test_wrong_track_is_not_replaced(fake, subtitle):
    service = prepared(fake, VIDEO, {'items': [TRACK]})
    with pytest.raises(ValueError, match='track'):
        service.client.replace_caption('vid', 'other-track', subtitle)


@pytest.mark.parametrize('change', ['file', 'profile', 'channel', 'tracks'])
def test_plan_is_bound_to_original_input_and_destination(fake, subtitle, change):
    service = prepared(fake, VIDEO, {'items': []}, VIDEO, {'items': [TRACK] if change == 'tracks' else []})
    plan = captions.plan_caption(service.client, 'vid', subtitle, language='en', name='English')
    if change == 'file':
        subtitle.write_text(SRT.replace('Hello', 'Other'), encoding='utf-8')
    elif change == 'profile':
        service.client.profile = 'different'
    elif change == 'channel':
        service.client._channel['id'] = 'other'
    with pytest.raises(ValueError):
        captions.apply_caption(service.client, plan)
    assert all(r.method == 'GET' for r in service.requests)


@pytest.mark.parametrize('status,outcome', [(400, 'not_started'), (403, 'not_started'), (503, 'unknown')])
def test_failed_write_is_safe_and_not_retried(fake, subtitle, status, outcome):
    service = prepared(fake, VIDEO, {'items': []}, VIDEO, {'items': []}, (status, {'error': {'message': 'PRIVATE_SENTINEL'}}))
    with pytest.raises(captions.CaptionError) as error:
        service.client.upload_caption('vid', subtitle, language='en', apply=True)
    assert error.value.outcome == outcome
    assert 'PRIVATE_SENTINEL' not in str(error.value)
    assert len([r for r in service.requests if r.method == 'POST']) == 1


def test_cli_dispatch_preview(fake, subtitle, monkeypatch, capsys):
    service = prepared(fake, VIDEO, {'items': []})
    monkeypatch.setattr('youtube3.cli.common.client', lambda args: service.client)
    monkeypatch.setattr(sys, 'argv', ['youtube3', 'captions', 'upload', 'vid', str(subtitle), '--language', 'en'])
    main.main()
    assert 'Dry run' in capsys.readouterr().out
    assert all(r.method == 'GET' for r in service.requests)


@pytest.mark.parametrize('response', [{}, {'id': 'wrong'}])
def test_replacement_missing_or_wrong_id_is_uncertain(fake, subtitle, response):
    service = prepared(fake, VIDEO, {'items': [TRACK]}, VIDEO, {'items': [TRACK]}, response)
    with pytest.raises(captions.CaptionError) as error:
        service.client.replace_caption('vid', 'track', subtitle, apply=True)
    assert error.value.outcome == 'unknown'
    assert len([r for r in service.requests if r.method == 'PUT']) == 1


def test_cli_errors_are_safe(fake, subtitle, monkeypatch, capsys):
    service = prepared(fake, VIDEO, {'items': []}, VIDEO, {'items': []},
                       (503, {'error': {'message': 'PRIVATE_SENTINEL'}}))
    monkeypatch.setattr('youtube3.cli.common.client', lambda args: service.client)
    monkeypatch.setattr(sys, 'argv', ['youtube3', 'captions', 'upload', 'vid', str(subtitle), '--language', 'en', '--apply'])
    with pytest.raises(SystemExit) as error:
        main.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert 'inspect tracks' in output.err
    assert 'PRIVATE_SENTINEL' not in output.out + output.err
