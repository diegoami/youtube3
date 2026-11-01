"""Owned-video subtitle plans and explicit, single-attempt media writes."""

import hashlib
from io import BytesIO
from pathlib import Path
import re

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

MAX_BYTES = 100 * 1024 * 1024
LANGUAGE = re.compile(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*\Z')
FILE_KEYS = {'path', 'bytes', 'sha256'}


class CaptionError(ValueError):
    """A safe caption error with a conservative account-write outcome."""

    def __init__(self, message, *, outcome='not_started'):
        self.outcome = outcome
        super().__init__(message)


def _time(value, *, srt):
    pattern = r'(\d{2,}):(\d{2}):(\d{2}),(\d{3})' if srt else r'(?:(\d{2,}):)?(\d{2}):(\d{2})\.(\d{3})'
    match = re.fullmatch(pattern, value)
    if not match:
        raise ValueError('Caption cue needs a valid timestamp')
    hours, minutes, seconds, millis = (int(part or 0) for part in match.groups())
    if minutes >= 60 or seconds >= 60:
        raise ValueError('Caption timestamp minutes/seconds must be below 60')
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def _content(path):
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() not in ('.srt', '.vtt'):
        raise ValueError('Captions must be timed UTF-8 .srt or .vtt files')
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError('Caption file must be non-empty and at most 100 MiB')
    with path.open('rb') as source:
        data = source.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Caption file exceeds 100 MiB')
    try:
        text = data.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    except UnicodeError:
        raise ValueError('Caption file must use UTF-8') from None
    srt = path.suffix.lower() == '.srt'
    if '\x00' in text:
        raise ValueError('Caption file contains invalid text')
    blocks = re.split(r'\n[ \t]*\n', text.strip())
    if not srt:
        if not re.fullmatch(r'WEBVTT(?:[ \t].*)?(?:\n[^\n]*)*', blocks.pop(0)):
            raise ValueError('VTT file needs a WEBVTT header')
    cues = 0
    for block in blocks:
        lines = block.splitlines()
        if not lines:
            continue
        if not srt and (lines[0] in ('STYLE', 'REGION') or re.match(r'NOTE(?:[ \t]|$)', lines[0])):
            continue
        if '-->' not in lines[0]:
            if srt and not lines[0].isdigit():
                raise ValueError('SRT cue needs a numeric index')
            lines = lines[1:]
        if len(lines) < 2 or not any(line.strip() for line in lines[1:]):
            raise ValueError('Caption cue needs timing and text')
        match = re.fullmatch(r'(\S+)\s+-->\s+(\S+)(?:[ \t]+.*)?', lines[0])
        if not match or _time(match[1], srt=srt) >= _time(match[2], srt=srt):
            raise ValueError('Caption cue must end after it starts')
        cues += 1
    if not cues:
        raise ValueError('Caption file needs at least one timed cue')
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}, data


def check_caption(path):
    """Validate basic timed SRT/VTT and fingerprint the exact upload bytes."""
    return _content(path)[0]


def validate_settings(settings):
    """Validate one declarative track; no file reads or API calls."""
    if not isinstance(settings, dict) or set(settings) - {'file', 'language', 'name', 'draft', 'caption_id'}:
        raise ValueError('Invalid subtitle settings fields')
    if not isinstance(settings.get('file'), str) or not settings['file']:
        raise ValueError('Subtitle file must be a non-empty path')
    if settings.get('caption_id') is not None:
        if not isinstance(settings['caption_id'], str) or not settings['caption_id']:
            raise ValueError('Caption ID must be non-empty')
        if settings.get('language') is not None or settings.get('name') is not None:
            raise ValueError('Replacement keeps its existing language/name; specify only caption_id, file and optional draft')
    else:
        if not isinstance(settings.get('language'), str) or not LANGUAGE.fullmatch(settings['language']):
            raise ValueError('Caption language must be a language code such as en or pt-BR')
        if not isinstance(settings.get('name', ''), str) or len(settings.get('name', '')) > 150:
            raise ValueError('Caption name must be a string of at most 150 characters')
    if settings.get('draft') is not None and not isinstance(settings['draft'], bool):
        raise ValueError('Caption draft must be true or false')
    return settings


def _owner(client, video_id):
    if not isinstance(video_id, str) or not video_id:
        raise ValueError('Video ID must be non-empty')
    channel_id = client.signed_in_channel()['id']
    if client.video_details([video_id]).get(video_id, {}).get('snippet', {}).get('channelId') != channel_id:
        raise ValueError('Video is missing or belongs to another channel')
    return channel_id


def list_captions(client, video_id):
    """Return only track identity/status fields; never caption contents or raw errors."""
    try:
        _owner(client, video_id)
        response = client.youtube.captions().list(part='snippet', videoId=video_id).execute(num_retries=0)
    except (HttpError, OSError):
        raise CaptionError('Caption lookup failed; check channel permissions and OAuth consent') from None
    return [{'id': item['id'], 'snippet': {key: value for key, value in item.get('snippet', {}).items()
             if key in {'videoId', 'language', 'name', 'isDraft', 'status', 'failureReason', 'trackKind'}}}
            for item in response.get('items', []) if isinstance(item.get('id'), str)]


def plan_caption(client, video_id, file, *, language=None, name=None, draft=None, caption_id=None):
    settings = {'file': str(file), 'language': language, 'name': name, 'draft': draft, 'caption_id': caption_id}
    if caption_id is None and name is None:
        settings['name'] = name = ''
    validate_settings(settings)
    spec = check_caption(file)
    tracks = list_captions(client, video_id)
    prior = None
    if caption_id is not None:
        prior = next((item for item in tracks if item['id'] == caption_id), None)
        if prior is None:
            raise ValueError('Caption track is missing from this video')
        draft = prior['snippet'].get('isDraft', False) if draft is None else draft
        body = {'id': caption_id, 'snippet': {'isDraft': draft}}
    else:
        if any(item['snippet'].get('language') == language and item['snippet'].get('name', '') == name for item in tracks):
            raise ValueError('Caption track already exists; select its ID explicitly to replace it')
        body = {'snippet': {'videoId': video_id, 'language': language, 'name': name, 'isDraft': draft if draft is not None else False}}
    return {'video_id': video_id, 'channel_id': client.signed_in_channel()['id'], 'profile': client.profile,
            'file': spec, 'body': body, 'prior': prior, 'quota': 450 if caption_id is not None else 400}


def apply_caption(client, plan):
    """Recheck a preview and upload one snapshot, with no automatic retry."""
    if client.profile != plan['profile'] or client.signed_in_channel()['id'] != plan['channel_id']:
        raise ValueError('Selected channel/profile differs from the caption plan')
    spec, data = _content(plan['file']['path'])
    if spec != plan['file']:
        raise ValueError('Caption file changed after planning')
    body = plan['body']
    options = {'caption_id': body['id'], 'draft': body['snippet']['isDraft']} if 'id' in body else {
        'language': body['snippet']['language'], 'name': body['snippet']['name'], 'draft': body['snippet']['isDraft']}
    current = plan_caption(client, plan['video_id'], spec['path'], **options)
    if current != plan:
        raise ValueError('Caption track changed after planning; preview again')
    media = MediaIoBaseUpload(BytesIO(data), mimetype='application/octet-stream', resumable=False)
    try:
        resource = client.youtube.captions()
        method = resource.update if 'id' in body else resource.insert
        response = method(part='snippet', body=body, media_body=media).execute(num_retries=0)
    except (Exception, KeyboardInterrupt) as error:
        known_failure = isinstance(error, HttpError) and 400 <= error.resp.status < 500 and error.resp.status != 408
        outcome = 'not_started' if known_failure else 'unknown'
        raise CaptionError('Caption write failed; inspect tracks before retrying. Check permissions/OAuth consent if refused.', outcome=outcome) from None
    if not isinstance(response.get('id'), str) or not response['id'] or ('id' in body and response['id'] != body['id']):
        raise CaptionError('Caption write returned no matching ID; inspect tracks before retrying', outcome='unknown')
    return {'id': response['id']}
