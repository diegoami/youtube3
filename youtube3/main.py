#!/usr/bin/python

import httplib2
import os
import sys



from apiclient import discovery
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import run_flow

# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret. You can acquire an OAuth 2.0 client ID and client secret from
# the {{ Google Cloud Console }} at
# {{ https://cloud.google.com/console }}.
# Please ensure that you have enabled the YouTube Data API for your project.
# For more information about using OAuth2 to access the YouTube Data API, see:
#   https://developers.google.com/youtube/v3/guides/authentication
# For more information about the client_secrets.json file format, see:
#   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
CLIENT_SECRETS_FILE = "client_secrets_yt.json"

# This variable defines a message to display if the CLIENT_SECRETS_FILE is
# missing.
MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

   %s

with information from the {{ Cloud Console }}
{{ https://cloud.google.com/console }}

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % os.path.abspath(os.path.join(os.path.dirname(__file__),
                                   CLIENT_SECRETS_FILE))

# This OAuth 2.0 access scope allows for full read/write access to the
# authenticated user's account.
YOUTUBE_READ_WRITE_SCOPE = "https://www.googleapis.com/auth/youtube"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

def get_authenticated_service(args):
  flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
    scope=YOUTUBE_READ_WRITE_SCOPE,
    message=MISSING_CLIENT_SECRETS_MESSAGE)

  storage = Storage("%s-oauth2.json" % sys.argv[0])
  credentials = storage.get()

  if credentials is None or credentials.invalid:
    credentials = run_flow(flow, storage, args)

  return discovery.build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
        http=credentials.authorize(httplib2.Http()))

def list_channels(youtube,id):
    return youtube.channels().list(part="contentDetails",id=id).execute()

def like_video(youtube, video_id):
  youtube.videos().rate(
    id=video_id,
    rating="like"
  ).execute()


def get_video(youtube, video_id):
  return youtube.videos().list(
    id=video_id,
    part='snippet'
  ).execute()

def get_recommended(youtube):

    return youtube.activities().list(
        part='snippet',mine=True
    ).execute()

def get_channel_id(youtube, videoId):
    result = get_video(youtube, videoId)
    channelId= result['items'][0]['snippet']['channelId']
    return channelId

def get_related_videos(youtube, videoId):
    return youtube.search().list(
        part='snippet', type="video", relatedToVideoId=videoId
    ).execute()


def get_channels(youtube):
    return youtube.channels().list(
        part='contentDetails', mine="true"
    ).execute()

def liked_channel(youtube):
    channels = youtube.channels().list(
        part='contentDetails', mine="true"
    ).execute()
    return channels['items'][0]['contentDetails']['relatedPlaylists']['likes']

def videos_in_channels(youtube, channelid, nextPageToken=None):
    playlistItems = youtube.playlistItems().list(
        part='snippet', playlistId=channelid, pageToken=nextPageToken
    ).execute()
    return playlistItems

def subscribe_channel(youtube, channelId):
    print('Subscribing to channel '+channelId)
    youtube.subscriptions().insert(
        part='snippet',
        body=dict(
            snippet=dict(
                resourceId=dict(
                    channelId=channelId
                )
            )
        )).execute()

