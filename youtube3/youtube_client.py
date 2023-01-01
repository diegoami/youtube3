
from googleapiclient import sample_tools
import traceback
from .exceptions import ChannelNotFoundException

class YoutubeClient:
    def __init__(self, client_json_file, debug=False):
        service, flags = self.login(client_json_file)
        self.youtube = service
        self.channel_snippet_map = {}



    def login(self, client_json_file):
        service, flags = sample_tools.init(
            ['--noauth_local_webserver'], 'youtube', 'v3', __doc__, client_json_file,
            scope='https://www.googleapis.com/auth/youtube')
        return service, flags

    def list_channels(self, id):
        return self.youtube.channels().list(part="contentDetails", id=id).execute()

    def like_video(self, video_id):
        self.youtube.videos().rate(
        id=video_id,
        rating="like"
      ).execute()

    def update_snippet(self, video_id, video_snippet):
        update_snippet = {
            "id": video_id,
            "snippet": video_snippet
        }
        return self.youtube.videos().update(
            part='snippet',
            body=update_snippet

        ).execute()


    def get_channel_snippet(self, channel_id):
        channel_snippet = None
        if channel_id in self.channel_snippet_map:
            channel_snippet = self.channel_snippet_map[channel_id]
        else:
            channel = self.get_channel(channel_id)
            if channel and 'items' in channel and len(channel['items']) > 0  and 'snippet' in  channel['items'][0]:
                channel_snippet = channel['items'][0]['snippet']
                self.channel_snippet_map[channel_id] = channel_snippet
        if not channel_snippet:
            raise ChannelNotFoundException('{} does not exist'.format(channel_id))
        return channel_snippet

    def get_channel(self, channel_id):
        return self.youtube.channels().list(
            id=channel_id,
            part='snippet'
        ).execute()

    def get_channel_name(self, channel_id):
        channel_snippet = self.get_channel_snippet(channel_id)
        channel_title = channel_snippet['title']
        return channel_title

    def get_video(self, video_id):
      return self.youtube.videos().list(
        id=video_id,
        part='snippet'
      ).execute()

    def upload_thumbnail(self, videoId, thumbnailUrl):
        return self.youtube.thumbnails().set(
            videoId = videoId,
            media_body = thumbnailUrl
        ).execute()

    def get_video_snippet(self, video_id):
        video_info = self.get_video(video_id)
        return video_info['items'][0]['snippet']

    def get_recommended(self):
        return self.youtube.activities().list(
            part='snippet',mine=True
        ).execute()

    def get_channel_id(self, videoId):
        video_snippet = self.get_video(videoId)
        if video_snippet and 'items' in video_snippet and len(video_snippet['items']) > 0 and 'snippet' in video_snippet['items'][0]:
            channel_id = video_snippet['items'][0]['snippet']['channelId']
            return channel_id
        else:
            raise ChannelNotFoundException('{} has no channel'.format(videoId))

    def get_related_videos(self, videoId,nextPageToken=None):
        return self.youtube.search().list(
            part='snippet', type="video", relatedToVideoId=videoId, pageToken=nextPageToken
        ).execute()

    def get_subscriptions_channel_ids(self, nextPageToken=None):
        subscriptions = self.youtube.subscriptions().list(
            part='snippet, contentDetails', mine="true", pageToken=nextPageToken
        ).execute()
        nextPageToken = subscriptions.get('nextPageToken', None)
        items = [{'id': item['snippet']['resourceId']['channelId'], 'title' : item['snippet']['title'] }
                 for item in subscriptions['items']]
        return items, nextPageToken

    def get_channels(self):
        return self.youtube.channels().list(
            part='contentDetails', mine="true"
        ).execute()

    def iterate_subscriptions_in_channel(self):
        items, nextPageToken = self.get_subscriptions_channel_ids()
        yield from items
        while nextPageToken:
            items, nextPageToken = self.get_subscriptions_channel_ids(nextPageToken )
            yield from items

    def liked_channel(self):
        channels = self.youtube.channels().list(
            part='snippet,contentDetails', mine="true"
        ).execute()
        try:
            return channels['items'][0]['contentDetails']['relatedPlaylists']['likes']
        except:
            return None

    def playlist_snippet(self, playlistId):
        playlist_result = self.youtube.playlists().list(
            part='snippet', id=playlistId).execute()
        playlist_items = playlist_result["items"]
        if playlist_items:
            playlist_snippet = playlist_items[0]["snippet"]
        else:
            playlist_snippet = None
        return playlist_snippet

    def playlist_name(self, playlistId):
        playlist_snippet = self.playlist_snippet(playlistId=playlistId)
        if playlist_snippet:
            return playlist_snippet["localized"]["title"]
        else:
            return None

    def videos_in_playlist(self, playlistId, nextPageToken=None):

        playlistItems = self.youtube.playlistItems().list(
            part='snippet,contentDetails', playlistId=playlistId, pageToken=nextPageToken
        ).execute()
        return playlistItems


    def iterate_videos_in_playlist(self, playlistId, maxCount=None):
        count = 0
        videos = self.videos_in_playlist(playlistId)
        yield videos
        count += 1
        while 'nextPageToken' in videos:
            videos = self.videos_in_playlist(playlistId, videos['nextPageToken'])
            yield videos
            count += 1
            if maxCount and count > int(maxCount):
                break

    def delete_from_playlist(self, playlist_source, start, end):
        counter = 0
        ids_to_delete = []
        for video_items in self.iterate_videos_in_playlist(playlist_source):
            for item in video_items["items"]:
                if (start <= counter < end):
                    id = item["id"]
                    videoId = item["contentDetails"]["videoId"]
                    ids_to_delete.append(id)
                    counter += 1
        for id in ids_to_delete:
            print(f"Trying to remove video {videoId} from {playlist_source}")
            self.youtube.playlistItems().delete(id=id).execute()
            print(f"Successfully removed video {videoId} from {playlist_source}")

    def copy_to_playlist(self, playlist_source, playlist_target, start, end):
        counter = 0
        for video_items in self.iterate_videos_in_playlist(playlist_source):
            for item in video_items["items"]:
                if (start <= counter < end):
                    videoId = item["contentDetails"]["videoId"]
                    insert_snippet = {
                        "snippet": {
                            "playlistId" : playlist_target,
                            "resourceId" : {
                                "kind" : "youtube#video",
                                "videoId" : videoId
                            }
                        }
                    }
                    self.youtube.playlistItems().insert(part="snippet", body=insert_snippet).execute()
                    print(f"Copied video {videoId} from {playlist_source} to {playlist_target}")
                    counter += 1

    def iterate_related_videos(self, videoId,maxCount=None):
        count = 0
        videos = self.get_related_videos(videoId)
        yield videos
        count += 1
        while 'nextPageToken' in videos:
            videos = self.get_related_videos(videoId, videos ['nextPageToken'])
            yield videos
            count  += 1
            if maxCount and count > int(maxCount):
                break

    def subscribe_channel(self, channelId):
        self.youtube.subscriptions().insert(
            part='snippet',
            body=dict(
                snippet=dict(
                    resourceId=dict(
                        channelId=channelId
                    )
                )
            )).execute()

    def verify_video(self, video_id, country='DE'):
        try:
            videos = self.youtube.videos().list(
                id=video_id,
                part='contentDetails'
            ).execute()
            if 'items' in videos:
                video_items = videos['items']
                if video_items:
                    if video_items[0]:
                        if 'contentDetails' in video_items[0]:
                            contentDetails = video_items[0]['contentDetails']
                            if 'regionRestriction' in contentDetails and 'blocked' in contentDetails[
                                'regionRestriction'] and country in contentDetails['regionRestriction']['blocked']:
                                return False
                            else:
                                return True
                        else:
                            return False
                    else:
                        return False
                else:
                    return False
            else:
                return False
        except:
            traceback.print_exc()
            return False


