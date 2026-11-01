"""Subtitle progress, identity and uncertain-write recovery in publishing jobs."""

from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from youtube3 import publishing_job as jobs, publishing_config as config, publishing_batch as batch, publishing_queue as queue

TEXT = '1\n00:00:00,000 --> 00:00:01,000\nHello\n'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    path = tmp_path / 'captions.srt'
    path.write_text(TEXT, encoding='utf-8')
    tracks, calls = [], []
    resource = Mock()
    resource.list.return_value.execute.side_effect = lambda **kw: {'items': deepcopy(tracks)}

    def insert(**kwargs):
        def execute(**kw):
            calls.append('subtitle')
            track = {'id': 'track-' + str(len(tracks)), 'snippet': deepcopy(kwargs['body']['snippet']) | {'status': 'serving'}}
            tracks.append(track)
            return deepcopy(track)
        return SimpleNamespace(execute=execute)

    resource.insert.side_effect = insert
    resource.update.side_effect = lambda **kw: SimpleNamespace(execute=lambda **opts: calls.append('replace') or {'id': kw['body']['id']})
    client = SimpleNamespace(profile=None, signed_in_channel=lambda: {'id': 'mine', 'title': 'Mine'},
        video_details=lambda ids: {vid: {'id': vid, 'snippet': {'channelId': 'mine'}} for vid in ids},
        youtube=SimpleNamespace(captions=lambda: resource))
    monkeypatch.setattr(jobs.publish, 'plan_publish', lambda *a, **kw: {'errors': [], 'options': kw})
    monkeypatch.setattr(jobs.publish, 'apply_publish', lambda client, plan: calls.append('publication' if 'privacy' in plan['options'] else 'metadata'))
    return SimpleNamespace(path=path, file={'file': str(path), 'language': 'en', 'name': 'English'},
                           client=client, tracks=tracks, calls=calls, resource=resource, job_path=tmp_path / 'job.json')


def plan(setup, **kw):
    return jobs.plan_publishing_job(setup.client, video_id='vid', subtitles=[setup.file], **kw)


def test_subtitles_precede_publication_and_checkpoint_each_track(setup):
    job = plan(setup, title='Title', privacy='public')
    assert setup.calls == [] and not setup.job_path.exists()
    complete = jobs.apply_publishing_job(setup.client, job, setup.job_path)
    assert setup.calls == ['metadata', 'subtitle', 'publication']
    assert complete['subtitles'][0]['caption_id'] == 'track-0'
    assert complete['subtitles'][0]['state'] == 'successful'
    assert jobs.load_job(setup.job_path) == complete
    setup.path.unlink()
    jobs.apply_publishing_job(setup.client, complete, setup.job_path, resume=True)
    assert setup.calls == ['metadata', 'subtitle', 'publication']


def test_failed_second_track_does_not_reinsert_first(setup):
    second = setup.file | {'language': 'de', 'name': 'German'}
    job = jobs.plan_publishing_job(setup.client, video_id='vid', subtitles=[setup.file, second], privacy='public')
    original = setup.resource.insert.side_effect
    attempts = 0

    # Raise a real HTTP refusal so apply_caption can classify it.
    from googleapiclient.errors import HttpError
    import httplib2
    def fail_request(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            return SimpleNamespace(execute=lambda **kw: (_ for _ in ()).throw(HttpError(httplib2.Response({'status': '400'}), b'{}')))
        return original(**kwargs)
    setup.resource.insert.side_effect = fail_request
    with pytest.raises(jobs.PublishingJobError):
        jobs.apply_publishing_job(setup.client, job, setup.job_path)
    saved = jobs.load_job(setup.job_path)
    assert saved['subtitles'][0]['state'] == 'successful'
    assert saved['subtitles'][1]['state'] == 'failed'
    assert 'publication' not in setup.calls
    setup.resource.insert.side_effect = original
    complete = jobs.apply_publishing_job(setup.client, saved, setup.job_path, resume=True)
    assert complete['state'] == 'completed'
    assert [t['snippet']['language'] for t in setup.tracks] == ['en', 'de']


def test_unknown_insert_requires_explicit_id_recovery(setup):
    job = plan(setup, privacy='public')
    original = setup.resource.insert.side_effect

    def lost_response(**kwargs):
        request = original(**kwargs)
        def execute(**kw):
            request.execute(**kw)
            raise OSError('lost response')
        return SimpleNamespace(execute=execute)

    setup.resource.insert.side_effect = lost_response
    with pytest.raises(jobs.PublishingJobError):
        jobs.apply_publishing_job(setup.client, job, setup.job_path)
    saved = jobs.load_job(setup.job_path)
    assert saved['state'] == 'recovery_required'
    assert saved['subtitles'][0]['state'] == 'unknown'
    assert saved['stages']['publication'] == 'pending'
    with pytest.raises(jobs.PublishingJobError):
        jobs.apply_publishing_job(setup.client, saved, setup.job_path, resume=True)
    assert setup.calls == ['subtitle']
    recovered = jobs.recover_subtitle(setup.client, jobs.load_job(setup.job_path), 1, caption_id='track-0')
    jobs._persist(recovered, setup.job_path, overwrite=True)
    complete = jobs.apply_publishing_job(setup.client, recovered, setup.job_path, resume=True)
    assert complete['state'] == 'completed'
    assert setup.calls == ['subtitle', 'publication']


def test_changed_caption_stops_before_write_and_publication(setup):
    job = plan(setup, privacy='public')
    setup.path.write_text(TEXT.replace('Hello', 'Other'), encoding='utf-8')
    with pytest.raises(jobs.PublishingJobError):
        jobs.apply_publishing_job(setup.client, job, setup.job_path)
    assert setup.calls == []


def test_checkpoint_cannot_overwrite_subtitle(setup):
    job = plan(setup)
    with pytest.raises(jobs.PublishingJobError, match='inputs'):
        jobs.apply_publishing_job(setup.client, job, setup.path)
    assert setup.path.read_text() == TEXT
    assert setup.calls == []


def test_relative_subtitle_paths_and_layer_replacement(setup, tmp_path):
    document = tmp_path / 'video.json'
    document.write_text(json.dumps({'schema': config.VIDEO_SCHEMA, 'video_id': 'vid',
                                    'settings': {'subtitles': [setup.file | {'file': 'captions.srt'}]}}))
    result = config.resolve_video_config(document)
    assert result['settings']['subtitles'][0]['file'] == str(setup.path)
    assert config.resolve_settings(result['settings'], {'subtitles': []})['subtitles'] == []
    assert config.resolve_settings(result['settings'], {'subtitles': None})['subtitles'] is None


@pytest.mark.parametrize('subtitles', ['en.srt', [{}], [{'file': 'x', 'language': 'en', 'extra': 1}], [{'file': 'x', 'language': 'en', 'draft': 'yes'}]])
def test_invalid_subtitle_configuration(subtitles):
    with pytest.raises(ValueError):
        config.validate_settings({'subtitles': subtitles})


def test_legacy_job_keeps_original_schema_and_stages(setup):
    job = jobs.plan_publishing_job(setup.client, video_id='vid')
    assert job['schema'] == 'youtube3.publishing-job.v1'
    assert set(job['stages']) == {'upload', 'thumbnail', 'metadata', 'publication'}
    assert 'subtitles' not in job
    assert jobs.apply_publishing_job(setup.client, job, setup.job_path)['state'] == 'completed'


def test_duplicate_track_specs_rejected(setup):
    with pytest.raises(ValueError, match='Duplicate'):
        jobs.plan_publishing_job(setup.client, video_id='vid', subtitles=[setup.file, setup.file])


def test_batch_and_queue_cannot_overwrite_subtitle(setup):
    entries = [{'id': 'one', 'file': None, 'video_id': 'vid', 'settings': {'subtitles': [setup.file]}, 'playlists': []}]
    saved_plan = batch.plan_batch(setup.client, entries)
    with pytest.raises(ValueError, match='inputs|media'):
        batch.save_plan(saved_plan, setup.path)
    with pytest.raises(ValueError, match='inputs|media'):
        queue.initialize_queue(saved_plan, setup.path, ledger_path=setup.job_path)
    assert setup.path.read_text() == TEXT


def test_checkpoint_failure_after_caption_acceptance_exposes_id_without_reinsert(setup, monkeypatch):
    job = plan(setup, privacy='public')
    original = jobs.artwork.save_bytes

    def disk_failure(path, data, **kw):
        document = json.loads(data)
        if document.get('subtitles', [{}])[0].get('state') == 'successful':
            raise OSError('disk full')
        return original(path, data, **kw)

    monkeypatch.setattr(jobs.artwork, 'save_bytes', disk_failure)
    with pytest.raises(jobs.PublishingJobError) as error:
        jobs.apply_publishing_job(setup.client, job, setup.job_path)
    assert error.value.job['subtitles'][0]['caption_id'] == 'track-0'
    assert jobs.load_job(setup.job_path)['subtitles'][0]['state'] == 'running'
    assert setup.calls == ['subtitle']
    monkeypatch.setattr(jobs.artwork, 'save_bytes', original)
    with pytest.raises(jobs.PublishingJobError):
        jobs.apply_publishing_job(setup.client, jobs.load_job(setup.job_path), setup.job_path, resume=True)
    assert setup.calls == ['subtitle']
    complete = jobs.apply_publishing_job(setup.client, jobs.load_job(setup.job_path), setup.job_path, resume=True,
                                        recover_subtitle_index=1, recover_caption_id='track-0')
    assert complete['state'] == 'completed'
    assert setup.calls == ['subtitle', 'publication']


def uncertain_job(setup):
    job = plan(setup, privacy='public')
    job['subtitles'][0]['state'] = 'unknown'
    job['stages']['subtitles'] = 'unknown'
    job['state'], job['failed_stage'] = 'recovery_required', 'subtitles'
    return job


@pytest.mark.parametrize('change', ['wrong_id', 'wrong_language', 'failed', 'draft', 'profile', 'channel'])
def test_recovered_id_must_match_intended_track(setup, change):
    job = uncertain_job(setup)
    track = {'id': 'accepted', 'snippet': {'videoId': 'vid', 'language': 'en', 'name': 'English', 'isDraft': False, 'status': 'serving'}}
    if change == 'wrong_language':
        track['snippet']['language'] = 'de'
    elif change == 'failed':
        track['snippet']['status'] = 'failed'
    elif change == 'draft':
        track['snippet']['isDraft'] = True
    elif change == 'profile':
        setup.client.profile = 'different'
    elif change == 'channel':
        setup.client.signed_in_channel = lambda: {'id': 'different'}
    setup.tracks.append(track)
    with pytest.raises(ValueError):
        jobs.recover_subtitle(setup.client, job, 1, caption_id='absent' if change == 'wrong_id' else 'accepted')
    assert setup.calls == []


def test_confirm_missing_requires_absence_and_cannot_reset_success(setup):
    job = uncertain_job(setup)
    setup.tracks.append({'id': 'exists', 'snippet': {'language': 'en', 'name': 'English'}})
    with pytest.raises(ValueError, match='visible'):
        jobs.recover_subtitle(setup.client, job, 1, confirm_missing=True)
    setup.tracks.clear()
    recovered = jobs.recover_subtitle(setup.client, job, 1, confirm_missing=True)
    assert recovered['subtitles'][0]['state'] == 'pending'
    jobs._persist(recovered, setup.job_path, overwrite=False)
    complete = jobs.apply_publishing_job(setup.client, recovered, setup.job_path, resume=True)
    assert complete['state'] == 'completed'
    with pytest.raises(ValueError, match='recovery'):
        jobs.recover_subtitle(setup.client, complete, 1, confirm_missing=True)


def test_queue_recovery_reuses_track_and_unblocks_publication(setup):
    entries = [{'id': 'one', 'file': None, 'video_id': 'vid', 'settings': {'subtitles': [setup.file], 'privacy': 'public'}, 'playlists': []}]
    saved_plan = batch.plan_batch(setup.client, entries)
    queue.initialize_queue(saved_plan, setup.job_path, ledger_path=setup.job_path.with_name('ledger.json'))
    original = setup.resource.insert.side_effect

    def lost_response(**kwargs):
        request = original(**kwargs)
        def execute(**kw):
            request.execute(**kw)
            raise OSError('lost response')
        return SimpleNamespace(execute=execute)

    setup.resource.insert.side_effect = lost_response
    stopped = queue.run_queue(setup.client, setup.job_path)
    assert stopped['entries']['one']['state'] == 'blocked'
    assert setup.calls == ['subtitle']
    queue.recover_entry(setup.client, setup.job_path, 'one', subtitle_index=1, caption_id='track-0')
    completed = queue.run_queue(setup.client, setup.job_path, resume=True)
    assert completed['state'] == 'completed'
    assert setup.calls == ['subtitle', 'publication']


def test_cli_publishing_config_previews_subtitles_without_checkpoint(setup, monkeypatch, capsys):
    import sys
    from youtube3.cli import publish_job
    document = setup.job_path.with_name('video.json')
    document.write_text(json.dumps({'schema': config.VIDEO_SCHEMA, 'video_id': 'vid', 'settings': {'subtitles': [setup.file]}}))
    monkeypatch.setattr(publish_job, 'client', lambda args: setup.client)
    monkeypatch.setattr(sys, 'argv', ['publishing', '--config', str(document), '--job', str(setup.job_path)])
    publish_job.main()
    output = capsys.readouterr().out
    assert 'Dry run' in output and 'subtitles' in output
    assert not setup.job_path.exists() and setup.calls == []


def test_new_upload_cannot_replace_old_track_and_preflights_caption_before_upload(setup):
    media = setup.path.with_suffix('.mp4')
    media.write_bytes(b'synthetic media')
    with pytest.raises(ValueError, match='new video'):
        jobs.plan_publishing_job(setup.client, file=media, title='Test', subtitles=[{'file': str(setup.path), 'caption_id': 'old-track'}])
    setup.path.write_text('plain transcript', encoding='utf-8')
    with pytest.raises(ValueError):
        jobs.plan_publishing_job(setup.client, file=media, title='Test', subtitles=[setup.file])
    assert setup.calls == []


def test_subtitle_job_rejects_skipping_unfinished_tracks_and_extra_checkpoint_fields(setup):
    job = plan(setup)
    job['stages']['subtitles'] = 'skipped'
    with pytest.raises(ValueError):
        jobs.validate_job(job)
    job['stages']['subtitles'] = 'pending'
    job['subtitles'][0]['credentials'] = {}
    with pytest.raises(ValueError):
        jobs.validate_job(job)


def test_pause_is_honored_between_subtitle_writes(setup):
    job = jobs.plan_publishing_job(setup.client, video_id='vid', privacy='public',
                                   subtitles=[setup.file, setup.file | {'language': 'de'}])
    paused = jobs.apply_publishing_job(setup.client, job, setup.job_path,
        before_stage=lambda stage, current: not (stage == 'subtitles' and len(setup.tracks) == 1))
    assert paused['state'] == 'paused'
    assert [row['state'] for row in paused['subtitles']] == ['successful', 'pending']
    assert setup.calls == ['subtitle']
    complete = jobs.apply_publishing_job(setup.client, paused, setup.job_path, resume=True)
    assert complete['state'] == 'completed'
    assert setup.calls == ['subtitle', 'subtitle', 'publication']


def test_unknown_without_visible_track_never_retries_automatically(setup):
    job = plan(setup, privacy='public')
    original = setup.resource.insert.side_effect
    setup.resource.insert.side_effect = lambda **kw: SimpleNamespace(execute=lambda **opts: (_ for _ in ()).throw(OSError('connection closed')))
    with pytest.raises(jobs.PublishingJobError):
        jobs.apply_publishing_job(setup.client, job, setup.job_path)
    saved = jobs.load_job(setup.job_path)
    assert saved['state'] == 'recovery_required'
    setup.resource.insert.side_effect = original
    with pytest.raises(jobs.PublishingJobError):
        jobs.apply_publishing_job(setup.client, saved, setup.job_path, resume=True)
    assert setup.calls == [] and setup.tracks == []
    assert jobs.load_job(setup.job_path)['state'] == 'recovery_required'


def test_new_video_stays_private_until_subtitles_complete(setup, monkeypatch):
    media = setup.path.with_suffix('.mp4')
    media.write_bytes(b'synthetic media')
    job = jobs.plan_publishing_job(setup.client, file=media, title='Test', subtitles=[setup.file], privacy='public')
    assert job['upload']['body']['status']['privacyStatus'] == 'private'
    monkeypatch.setattr(jobs.upload, 'apply_video_upload', lambda client, spec: setup.calls.append('upload') or {'video_id': 'new-video'})
    complete = jobs.apply_publishing_job(setup.client, job, setup.job_path)
    assert complete['state'] == 'completed'
    assert setup.calls == ['upload', 'metadata', 'subtitle', 'publication']
    assert setup.tracks[0]['snippet']['videoId'] == 'new-video'


def test_replacement_job_preserves_draft_and_never_inserts(setup):
    setup.tracks.append({'id': 'existing', 'snippet': {'videoId': 'vid', 'language': 'en', 'name': 'Original', 'isDraft': True}})
    job = jobs.plan_publishing_job(setup.client, video_id='vid', subtitles=[{'file': str(setup.path), 'caption_id': 'existing'}])
    assert job['subtitles'][0]['settings']['draft'] is True
    complete = jobs.apply_publishing_job(setup.client, job, setup.job_path)
    assert complete['subtitles'][0]['caption_id'] == 'existing'
    assert setup.calls == ['replace']
    assert not setup.resource.insert.called


def test_cli_recovery_uses_index_and_id_from_saved_job(setup, monkeypatch, capsys):
    import sys
    from youtube3.cli import publish_job
    job = uncertain_job(setup)
    jobs._persist(job, setup.job_path, overwrite=False)
    setup.tracks.append({'id': 'existing', 'snippet': {'videoId': 'vid', 'language': 'en', 'name': 'English', 'isDraft': False}})
    monkeypatch.setattr(publish_job, 'client', lambda args: setup.client)
    monkeypatch.setattr(sys, 'argv', ['publishing', '--resume', str(setup.job_path), '--recover-subtitle', '1', '--recover-caption-id', 'existing', '--apply'])
    publish_job.main()
    assert jobs.load_job(setup.job_path)['state'] == 'completed'
    assert setup.calls == ['publication']
    assert 'completed' in capsys.readouterr().out


@pytest.mark.parametrize('via_cli', [False, True])
def test_missing_subtitle_recovery_checkpoint_refuses_without_changes(setup, monkeypatch, capsys, via_cli):
    import sys
    from youtube3.cli import publishing_batch as cli

    entries = [{'id': 'one', 'file': None, 'video_id': 'vid',
                'settings': {'subtitles': [setup.file]}, 'playlists': []}]
    saved_plan = batch.plan_batch(setup.client, entries)
    ledger = setup.job_path.with_name('ledger.json')
    queue.initialize_queue(saved_plan, setup.job_path, ledger_path=ledger)
    original = setup.resource.insert.side_effect

    def lost_response(**kwargs):
        request = original(**kwargs)
        def execute(**kw):
            request.execute(**kw)
            raise OSError('lost response')
        return SimpleNamespace(execute=execute)

    setup.resource.insert.side_effect = lost_response
    stopped = queue.run_queue(setup.client, setup.job_path)
    assert stopped['entries']['one']['state'] == 'blocked'
    child = queue._job_path(setup.job_path, 'one')
    assert child.exists()
    child.unlink()
    before_queue = setup.job_path.read_bytes()
    before_ledger = ledger.read_bytes() if ledger.exists() else None
    before_lookups = setup.resource.list.return_value.execute.call_count
    if via_cli:
        monkeypatch.setattr(cli, 'client', lambda args: setup.client)
        monkeypatch.setattr(sys, 'argv', ['publishing-batch', 'recover', str(setup.job_path), '--entry', 'one',
                                        '--subtitle-index', '1', '--caption-id', 'track-0', '--apply'])
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 1
        output = capsys.readouterr()
        assert 'Subtitle checkpoint is missing' in output.err
        assert 'Traceback' not in output.err + output.out
    else:
        with pytest.raises(queue.QueueError, match='Subtitle checkpoint is missing') as error:
            queue.recover_entry(setup.client, setup.job_path, 'one', subtitle_index=1, caption_id='track-0')
        assert error.value.queue == queue.load_queue(setup.job_path)
    assert setup.job_path.read_bytes() == before_queue
    assert (ledger.read_bytes() if ledger.exists() else None) == before_ledger
    assert not child.exists()
    assert setup.calls == ['subtitle']
    assert setup.resource.list.return_value.execute.call_count == before_lookups
    with queue.locked(str(ledger) + '.lock'), queue.locked(str(setup.job_path) + '.lock'):
        pass
