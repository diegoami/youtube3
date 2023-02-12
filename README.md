# DESCRIPTION

A wrapper around youtube Apis:

- https://developers.google.com/resources/api-libraries/documentation/youtube/v3/python/latest/
- https://developers.google.com/youtube/v3/docs/


## GOAL

I created this package to simplify some typical tasks related to the Youtube API.
See the `samples` directory for examples.

## USAGE

Create a youtube object
```
from youtube3 import YoutubeClient 
youtube = YoutubeClient(<location of your client_secrets.json>)
```

## YOUTUBECLEINT

The `YoutubeClient` class provides a set of methods for interacting with the YouTube API. The methods include:

-   `login`: Initialize the YouTube API client and return a service object and flags.
-   `list_channels`: Retrieve information about YouTube channels using their IDs.
-   `like_video`: Like a video by providing its ID.
-   `update_snippet`: Update the snippet information of a video using its ID and the new snippet.
-   `get_channel_snippet`: Retrieve the snippet information of a channel using its ID.
-   `get_channel`: Retrieve information about a channel using its ID.
-   `get_channel_name`: Retrieve the title of a channel using its ID.
-   `get_video`: Retrieve information about a video using its ID.
-   `upload_thumbnail`: Upload a thumbnail for a video using its ID and the URL of the thumbnail.
-   `get_video_snippet`: Retrieve the snippet information of a video using its ID.
-   `get_recommended`: Retrieve recommended videos for the authenticated user.
-   `get_channel_id`: Retrieve the ID of a channel that a video belongs to using the video's ID.
-   `get_related_videos`: Retrieve related videos to a video using its ID.
-   `get_subscriptions_channel_ids`: Retrieve the IDs and titles of channels that the authenticated user is subscribed to.
-   `get_channels`: Retrieve information about channels that the authenticated user is subscribed to.
-   `iterate_subscriptions_in_channel`: Iterate over the subscriptions in a channel.
-   `liked_channel`: Retrieve the ID of a playlist of liked videos for the authenticated user.
-   `playlist_snippet`: Retrieve the snippet information of a playlist using its ID.
-   `playlist_name`: Retrieve the title of a playlist using its ID.
-   `videos_in_playlist`: Retrieve videos in a playlist using its ID.
-   `iterate_videos_in_playlist`: Iterate over videos in a playlist.
-   `delete_from_playlist`: Remove videos from a playlist using its ID, start, and end indices.
-   `copy_to_playlist`: Copy videos from a playlist to another using the IDs of the source and target playlists, as well as start and end indices.
-   `iterate_related_videos`: Iterate over related videos to a video using its ID.
-   `subscribe_channel`: Subscribe to a channel using its ID.
-   `verify_video`: Verify if a video is available in a specific country using its ID.