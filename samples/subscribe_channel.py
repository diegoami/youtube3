from youtube3.youtube_client import *
from oauth2client.tools import argparser
import os

if __name__ == "__main__":
    argparser.add_argument('--channelId')
    args = argparser.parse_args()
    youtube = YoutubeClient(os.path.join(os.path.dirname(__file__), 'client_secrets.json'))
    youtube.subscribe_channel(args.channelId)
