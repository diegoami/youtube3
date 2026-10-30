"""Plan/set a playlist's own hero image using the playlistImages API."""

from googleapiclient.errors import HttpError

from .publish import thumbnail_upload
from .thumbnail_batch import checked_image

MAX_COVER_BYTES = 50 * 1024 * 1024


class PlaylistCoverError(ValueError):
    """Invalid or refused playlist-cover change."""


def _resource(client):
    root = getattr(client.youtube, "_rootDesc", {})
    methods = root.get("resources", {}).get("playlistImages", {}).get("methods", {})
    if not all(name in methods for name in ("list", "insert", "update")) or not all(
            methods[name].get("supportsMediaUpload") for name in ("insert", "update")):
        raise PlaylistCoverError("Playlist covers need google-api-python-client>=2.201.0 with playlistImages media support")
    params = methods["list"].get("parameters", {})
    # The 2026-10-29 discovery uses parent; the prose reference says playlistId.
    key = "parent" if "parent" in params else "playlistId" if "playlistId" in params else None
    if key is None:
        raise PlaylistCoverError("Unsupported playlistImages list discovery; upgrade google-api-python-client")
    return client.youtube.playlistImages(), key


def list_playlist_images(client, playlist_id):
    """List all image resources for a playlist, following pagination."""
    resource, key = _resource(client)
    result, token, seen = [], None, set()
    while True:
        response = resource.list(part="snippet", **{key: playlist_id}, maxResults=50, pageToken=token).execute()
        result.extend(response.get("items", []))
        token = response.get("nextPageToken")
        if not token:
            return result
        if token in seen:
            raise PlaylistCoverError("Playlist image pagination repeated a page token")
        seen.add(token)


def plan_playlist_cover(client, playlist_id, image):
    """Read ownership/existing cover and decode a square image; never writes."""
    _resource(client)
    image = checked_image(image, square=True, max_bytes=MAX_COVER_BYTES)
    channel = client.signed_in_channel()
    playlists = client.youtube.playlists().list(id=playlist_id, part="snippet").execute().get("items", [])
    if not playlists or playlists[0].get("snippet", {}).get("channelId") != channel["id"]:
        raise PlaylistCoverError("Playlist is missing or belongs to another channel")
    images = list_playlist_images(client, playlist_id)
    heroes = [item for item in images if item.get("snippet", {}).get("type") == "hero"]
    if len(heroes) > 1:
        raise PlaylistCoverError("Multiple hero images returned; choose/reconcile the cover explicitly")
    if heroes and not heroes[0].get("id"):
        raise PlaylistCoverError("Existing cover has no resource ID; cannot safely replace it")
    for item in heroes:
        if item.get("snippet", {}).get("playlistId") != playlist_id:
            raise PlaylistCoverError("Returned image belongs to another playlist")
    return {"playlist_id": playlist_id, "channel_id": channel["id"], "image": image,
            "image_id": heroes[0]["id"] if heroes else None, "action": "update" if heroes else "insert", "cost": 50}


def apply_playlist_cover(client, plan):
    """Revalidate the selected cover and replace only its hero image."""
    current = plan_playlist_cover(client, plan["playlist_id"], plan["image"]["path"])
    if current != plan:
        raise PlaylistCoverError("Image, channel or existing cover changed after planning; preview again")
    resource, _ = _resource(client)
    body = {"snippet": {"playlistId": plan["playlist_id"], "type": "hero",
                        "width": plan["image"]["width"], "height": plan["image"]["height"]}}
    if plan["action"] == "update":
        body["id"] = plan["image_id"]
    try:
        return getattr(resource, plan["action"])(part="snippet", body=body,
            media_body=thumbnail_upload(plan["image"]["path"])).execute()
    except HttpError as error:
        raise PlaylistCoverError(
            f"Playlist cover refused (HTTP {error.resp.status}); check ownership, authorization and cover eligibility"
        ) from None
