from youtube3.youtube_client import *
from oauth2client.tools import argparser
import os

if __name__ == "__main__":
    argparser.add_argument('--videoId')
    args = argparser.parse_args()
    if args.videoId == None:
        print("required argument --videoId <videoId>")
    else:
        youtube_client = YoutubeClient(os.path.join(os.path.dirname(__file__), 'client_secrets.json'))
        print(youtube_client.verify_video(args.videoId))
