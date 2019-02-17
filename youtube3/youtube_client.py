
from googleapiclient import sample_tools
import traceback
from .exceptions import ChannelNotFoundException

class YoutubeClient:
    def __init__(self, client_json_file):
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

    def get_channel_snippet(self, channel_id):
        channel_snippet = None
        if channel_id in self.channel_snippet_map:
            channel_snippet = self.channel_snippet_map[channel_id]
        else:
            channel = self.get_channel(channel_id)
            if channel and 'items' in channel and len(channel['items'] > 0 ) and 'snippet' in  channel['items'][0]:
                channel_snippet = channel['items'][0]['snippet']
                self.channel_snippet_map[channel_id] = channel_snippet
        if not channel_snippet:
            raise ChannelNotFoundException('{} does not exist'.format(channel_id))


    def get_channel(self, channel_id):
      return self.youtube.channels().list(
        id=channel_id,
        part='snippet'
      ).execute()


    def get_channel_title(self, channel_id):
        channel_snippet = self.get_channel_snippet(channel_id)
        channel_title = channel_snippet['title']
        return channel_title


    def get_video(self, video_id):
      return self.youtube.videos().list(
        id=video_id,
        part='snippet'
      ).execute()


    def get_recommended(self):
        return self.youtube.activities().list(
            part='snippet',mine=True
        ).execute()

    def get_channel_id(self, videoId):
        channel_snippet = self.get_channel_snippet(channel_id)
        channel_id = channel_snippet['channel_id']
        return channel_id

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

    def videos_in_channels(self, channelId, nextPageToken=None):

        playlistItems = self.youtube.playlistItems().list(
            part='snippet,contentDetails', playlistId=channelId, pageToken=nextPageToken
        ).execute()
        return playlistItems

    def iterate_videos_in_channel(self, channelId,maxCount=None):
        count = 0
        videos = self.videos_in_channels(channelId)
        yield videos
        count += 1
        while 'nextPageToken' in videos:
            videos = self.videos_in_channels(channelId,videos['nextPageToken'])
            yield videos
            count += 1
            if maxCount and count > int(maxCount):
                break

    def iterate_related_videos(self, videoId,maxCount=None):
        count = 0
        videos = self.get_related_videos(videoId)
        yield videos
        count += 1
        while 'nextPageToken' in videos:
            videos = self.get_related_videos(videoId,videos ['nextPageToken'])
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


