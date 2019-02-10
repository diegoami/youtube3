from youtube3.youtube_client import *
from oauth2client.tools import argparser

if __name__ == "__main__":
    argparser.add_argument('--channelId')
    args = argparser.parse_args()


    youtube = YoutubeClient(get_authenticated_service(args))
    youtube.subscribe_channel(args.channelId)
