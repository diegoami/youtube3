from youtube3.youtube import *
from oauth2client.tools import argparser

if __name__ == "__main__":
    args = argparser.parse_args()
    youtube = Youtube(get_authenticated_service(args))

    likedchannel  = youtube.liked_channel()
    print(likedchannel)
    videos1 = youtube.videos_in_channels(likedchannel)
    print(videos1)
    videos2 = youtube.videos_in_channels(likedchannel,videos1['nextPageToken'])
    print(videos2)