# DESCRIPTION

A wrapper around youtube Apis:

- https://developers.google.com/resources/api-libraries/documentation/youtube/v3/python/latest/
- https://developers.google.com/youtube/v3/docs/


## GOAL

I created this package to simplify some typical tasks related to the Youtube API.
See the `samples` directory for examples.

## INSTALL

```
pip install youtube3
```

## USAGE

Create an OAuth client of type "Desktop app" in the Google Cloud console,
enable the YouTube Data API v3, and download its client secrets file. Then:

```
from youtube3 import YoutubeClient
youtube = YoutubeClient("path/to/client_secrets.json")
```

The first run opens the browser to log in (on WSL or a headless machine, open
the printed URL yourself). The login is saved as `token.json` next to the
client secrets, readable by you only, and refreshed on later runs; pass
`token_file=` to keep it elsewhere. Never commit either file.

The library logs what it changes through the `youtube3` logger; call
`logging.basicConfig(level=logging.INFO)` to see it.

The `samples` directory has one script per operation, for example:

```
python samples/show_files_in_playlist.py --playlistId <id>
python samples/move_videos_playlist.py --playlistSource <id> --playlistTarget <id> --start 0 --end 10
```

Each takes `--client-secrets` (default `samples/client_secrets.json`) and
`--token-file`.

## YOUTUBECLIENT

The methods of `YoutubeClient`:

-   `login`: Log in with the client secrets and a saved token, and return the API service.
-   `list_channels`: Retrieve information about YouTube channels using their IDs.
-   `like_video`: Like a video by providing its ID.
-   `update_snippet`: Update the snippet information of a video using its ID and the new snippet.
-   `update_status`: Set a video's privacy to private, unlisted or public.
-   `get_channel_snippet`: Retrieve the snippet information of a channel using its ID.
-   `get_channel`: Retrieve information about a channel using its ID.
-   `get_channel_name`: Retrieve the title of a channel using its ID.
-   `get_video`: Retrieve information about a video using its ID.
-   `get_video_content_details`: Retrieve the content details of a video using its ID.
-   `upload_thumbnail`: Set a video's custom thumbnail from a local image file (max 2 MB; the channel must be verified).
-   `get_video_snippet`: Retrieve the snippet information of a video using its ID.
-   `get_channel_id`: Retrieve the ID of a channel that a video belongs to using the video's ID.
-   `get_subscriptions_channel_ids`: Retrieve one page of the IDs and titles of the channels you are subscribed to.
-   `get_channels`: Retrieve your own channel's content details.
-   `iterate_subscriptions_in_channel`: Iterate over all the channels you are subscribed to.
-   `liked_channel`: Retrieve the ID of the playlist of your liked videos.
-   `playlist_snippet`: Retrieve the snippet information of a playlist using its ID.
-   `playlist_name`: Retrieve the title of a playlist using its ID.
-   `videos_in_playlist`: Retrieve one page (up to 50) of the videos in a playlist.
-   `iterate_videos_in_playlist`: Iterate over a playlist page by page, at most `maxCount` pages when given.
-   `delete_from_playlist`: Remove the videos at positions `start` to `end - 1` from a playlist.
-   `copy_to_playlist`: Copy the videos at positions `start` to `end - 1` of a playlist to another.
-   `subscribe_channel`: Subscribe to a channel using its ID.
-   `verify_video`: Say whether a video exists and is not blocked in a country (default `DE`).

Version 2.0.0 removed `get_related_videos`, `iterate_related_videos` and
`get_recommended`: YouTube no longer serves related videos or
recommendations through the API.

## DEVELOPMENT

Python 3.11 or newer. BSD-3-Clause licensed (`LICENSE`).

```
pip install -e ".[dev]"
ruff check
pytest
```

The tests run offline: they build the client over canned responses
(`tests/conftest.py`) and never touch a real account. The process for changes
is in `CLAUDE.md`, the requests in `ROADMAP.md`.
