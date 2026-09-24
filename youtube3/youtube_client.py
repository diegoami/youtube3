import logging
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .auth import load_credentials
from .exceptions import ChannelNotFoundException
from .likes import LIKES_PLAYLIST, liked_record
from .publish import WRITABLE_STATUS, thumbnail_upload, writable

logger = logging.getLogger("youtube3")

# The largest page the list endpoints return, which saves quota and requests.
PAGE_SIZE = 50


class YoutubeClient:
    def __init__(self, client_json_file=None, debug=False, *, token_file=None, service=None):
        """Log in and build the YouTube client.

        client_json_file: the OAuth client secrets file from the Google Cloud
        console. token_file: where the login is saved; by default token.json
        next to the client secrets. service: an already-built client, used
        instead of logging in. debug is kept for compatibility and unused.
        """
        if service is None:
            if client_json_file is None:
                raise ValueError("client_json_file is required unless a service is passed")
            service = self.login(client_json_file, token_file)
        self.youtube = service
        self.channel_snippet_map = {}

    def login(self, client_json_file, token_file=None):
        if token_file is None:
            token_file = Path(client_json_file).parent / "token.json"
        credentials = load_credentials(client_json_file, token_file)
        # The bundled discovery document is used; the file cache needs oauth2client.
        return build("youtube", "v3", credentials=credentials, cache_discovery=False)

    def list_channels(self, id):
        return self.youtube.channels().list(part="contentDetails", id=id).execute()

    def like_video(self, video_id):
        self.youtube.videos().rate(id=video_id, rating="like").execute()

    def update_snippet(self, video_id, video_snippet):
        update_snippet = {"id": video_id, "snippet": video_snippet}
        return self.youtube.videos().update(part="snippet", body=update_snippet).execute()

    def get_channel_snippet(self, channel_id):
        channel_snippet = None
        if channel_id in self.channel_snippet_map:
            channel_snippet = self.channel_snippet_map[channel_id]
        else:
            channel = self.get_channel(channel_id)
            if channel and channel.get("items") and "snippet" in channel["items"][0]:
                channel_snippet = channel["items"][0]["snippet"]
                self.channel_snippet_map[channel_id] = channel_snippet
        if not channel_snippet:
            raise ChannelNotFoundException(f"{channel_id} does not exist")
        return channel_snippet

    def get_channel(self, channel_id):
        return self.youtube.channels().list(id=channel_id, part="snippet").execute()

    def get_channel_name(self, channel_id):
        return self.get_channel_snippet(channel_id)["title"]

    def get_video(self, video_id):
        return self.youtube.videos().list(id=video_id, part="snippet").execute()

    def get_video_content_details(self, video_id):
        video_content_details = self.youtube.videos().list(
            id=video_id, part="contentDetails"
        ).execute()
        return video_content_details["items"][0]["contentDetails"]

    def upload_thumbnail(self, videoId, thumbnailUrl):
        """Set a video's custom thumbnail; thumbnailUrl is the path of a local PNG or JPEG."""
        return self.youtube.thumbnails().set(videoId=videoId, media_body=thumbnail_upload(thumbnailUrl)).execute()

    def get_video_snippet(self, video_id):
        video_info = self.get_video(video_id)
        return video_info["items"][0]["snippet"]

    def get_channel_id(self, videoId):
        video_snippet = self.get_video(videoId)
        if video_snippet and video_snippet.get("items") and "snippet" in video_snippet["items"][0]:
            return video_snippet["items"][0]["snippet"]["channelId"]
        raise ChannelNotFoundException(f"{videoId} has no channel")

    def get_subscriptions_channel_ids(self, nextPageToken=None):
        subscriptions = self.youtube.subscriptions().list(
            part="snippet,contentDetails", mine=True, maxResults=PAGE_SIZE, pageToken=nextPageToken
        ).execute()
        nextPageToken = subscriptions.get("nextPageToken", None)
        items = [
            {"id": item["snippet"]["resourceId"]["channelId"], "title": item["snippet"]["title"]}
            for item in subscriptions["items"]
        ]
        return items, nextPageToken

    def get_channels(self):
        return self.youtube.channels().list(part="contentDetails", mine=True).execute()

    def iterate_subscriptions_in_channel(self):
        items, nextPageToken = self.get_subscriptions_channel_ids()
        yield from items
        while nextPageToken:
            items, nextPageToken = self.get_subscriptions_channel_ids(nextPageToken)
            yield from items

    def liked_channel(self):
        channels = self.youtube.channels().list(part="snippet,contentDetails", mine=True).execute()
        try:
            return channels["items"][0]["contentDetails"]["relatedPlaylists"]["likes"]
        except (KeyError, IndexError):
            return None

    def iterate_liked_videos(self):
        """Yield a record per liked video, newest like first (youtube3.likes)."""
        for page in self.iterate_videos_in_playlist(LIKES_PLAYLIST):
            for item in page["items"]:
                yield liked_record(item)

    def playlist_snippet(self, playlistId):
        playlist_result = self.youtube.playlists().list(part="snippet", id=playlistId).execute()
        playlist_items = playlist_result["items"]
        if playlist_items:
            return playlist_items[0]["snippet"]
        return None

    def playlist_name(self, playlistId):
        playlist_snippet = self.playlist_snippet(playlistId=playlistId)
        if playlist_snippet:
            return playlist_snippet["localized"]["title"]
        return None

    def videos_in_playlist(self, playlistId, nextPageToken=None):
        return self.youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlistId,
            maxResults=PAGE_SIZE,
            pageToken=nextPageToken,
        ).execute()

    def update_status(self, video_id, privacy_status):
        if privacy_status not in ["private", "unlisted", "public"]:
            raise ValueError("privacy_status must be private, unlisted or public")

        # The status part is replaced whole: send the current fields, or YouTube
        # resets embeddable, license, public stats and made-for-kids.
        current = self.youtube.videos().list(id=video_id, part="status").execute()["items"][0]["status"]
        status = writable(current, WRITABLE_STATUS)
        status["privacyStatus"] = privacy_status
        if privacy_status != "private":
            status.pop("publishAt", None)
        self.youtube.videos().update(part="status", body={"id": video_id, "status": status}).execute()

    def iterate_videos_in_playlist(self, playlistId, maxCount=None):
        """Yield the playlist one page at a time; at most maxCount pages when given."""
        # None, 0 and "0" all mean no limit, as 0 did before 2.0.0.
        max_pages = int(maxCount) if maxCount not in (None, "") else None
        if max_pages is not None and max_pages <= 0:
            max_pages = None
        videos = self.videos_in_playlist(playlistId)
        yield videos
        pages = 1
        while "nextPageToken" in videos and (max_pages is None or pages < max_pages):
            videos = self.videos_in_playlist(playlistId, videos["nextPageToken"])
            yield videos
            pages += 1

    def _items_in_range(self, playlistId, start, end):
        """The playlist items at positions start (inclusive) to end (exclusive)."""
        position = 0
        for page in self.iterate_videos_in_playlist(playlistId):
            for item in page["items"]:
                if position >= end:
                    return
                if position >= start:
                    yield item
                position += 1
            # Stop before the next page is fetched when the range ends here.
            if position >= end:
                return

    def delete_from_playlist(self, playlist_source, start, end, *, apply=True):
        """Remove positions start..end-1; with apply=False, only list them.

        Returns the video ids removed, or that would be.
        """
        # Collect first: deleting while paging would shift the positions.
        items = list(self._items_in_range(playlist_source, start, end))
        for item in items if apply else []:
            video_id = item["contentDetails"]["videoId"]
            logger.info("Removing video %s from %s", video_id, playlist_source)
            self.youtube.playlistItems().delete(id=item["id"]).execute()
            logger.info("Removed video %s from %s", video_id, playlist_source)
        return [item["contentDetails"]["videoId"] for item in items]

    def copy_to_playlist(self, playlist_source, playlist_target, start, end, *, apply=True):
        """Copy positions start..end-1 to another playlist; with apply=False, only list them.

        Returns the video ids copied, or that would be.
        """
        video_ids = []
        for item in self._items_in_range(playlist_source, start, end):
            video_id = item["contentDetails"]["videoId"]
            video_ids.append(video_id)
            if not apply:
                continue
            insert_snippet = {
                "snippet": {
                    "playlistId": playlist_target,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            }
            self.youtube.playlistItems().insert(part="snippet", body=insert_snippet).execute()
            logger.info("Copied video %s from %s to %s", video_id, playlist_source, playlist_target)
        return video_ids

    def subscribe_channel(self, channelId):
        self.youtube.subscriptions().insert(
            part="snippet",
            body={"snippet": {"resourceId": {"channelId": channelId}}},
        ).execute()

    def verify_video(self, video_id, country="DE"):
        """True when the video exists and can be watched in the country."""
        try:
            videos = self.youtube.videos().list(id=video_id, part="contentDetails").execute()
        except HttpError:
            logger.exception("Could not look up video %s", video_id)
            return False
        video_items = videos.get("items")
        if not video_items or not video_items[0] or "contentDetails" not in video_items[0]:
            return False
        restriction = video_items[0]["contentDetails"].get("regionRestriction", {})
        if "allowed" in restriction and country not in restriction["allowed"]:
            return False
        return country not in restriction.get("blocked", [])
