import json
from urllib.parse import parse_qs, urlparse

import pytest
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence

from youtube3 import YoutubeClient


class Recorded:
    """One request the client sent, parsed for assertions."""

    def __init__(self, uri, method, body):
        parsed = urlparse(uri)
        self.method = method
        self.path = parsed.path.removeprefix("/youtube/v3/")
        self.params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        self.body = json.loads(body) if body else None

    def __repr__(self):
        return f"<{self.method} {self.path} {self.params}>"


class FakeYoutube:
    """A YoutubeClient over canned responses, with no login and no network.

    The service is built from the discovery document bundled with
    google-api-python-client, so the requests are the real ones.
    """

    def __init__(self, responses):
        self.http = HttpMockSequence(
            [
                ({"status": str(status)}, json.dumps(body) if body is not None else "")
                for status, body in responses
            ]
        )
        service = build("youtube", "v3", http=self.http, developerKey="test-key")
        self.client = YoutubeClient(service=service)

    @property
    def requests(self):
        return [Recorded(uri, method, body) for uri, method, body, _ in self.http.request_sequence]


@pytest.fixture
def fake():
    """fake(response, ...) -> FakeYoutube; a response is a body (status 200) or (status, body)."""

    def make(*responses):
        normalised = [r if isinstance(r, tuple) else (200, r) for r in responses]
        return FakeYoutube(normalised)

    return make
