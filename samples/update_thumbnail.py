from youtube3 import YoutubeClient
from oauth2client.tools import argparser
import os

if __name__ == "__main__":
    argparser.add_argument('--videoId')
    argparser.add_argument('--thumbnail')
    args = argparser.parse_args()
    if args.videoId == None:
        print("required argument --videoId <videoId>")
    if args.thumbnail == None:
        print("required argument --thumbnail <thumbnailUrl>")

    else:
        youtube = YoutubeClient(os.path.join(os.path.dirname(__file__), 'client_secrets.json'))
        videoInfo = youtube.get_video(args.videoId)
        youtube.upload_thumbnail(args.videoId, args.thumbnail)
