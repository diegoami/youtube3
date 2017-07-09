from youtube3.main import *
from oauth2client.tools import argparser

if __name__ == "__main__":
    argparser.add_argument('--videoId')
    args = argparser.parse_args()
    youtube = get_authenticated_service(args)
    videoId = args.videoId
    #videos = get_related_videos(youtube, videoId)
    #recommended = get_recommended(youtube)
    #print(recommended)
    channels = get_channels(youtube)
    print(channels )
    likedchannel  = liked_channel(youtube)
    print(likedchannel)
    videos1 = videos_in_channels(youtube,likedchannel)
    print(videos1)

    videos2 = videos_in_channels(youtube, likedchannel,videos1['nextPageToken'])

    print(videos2)