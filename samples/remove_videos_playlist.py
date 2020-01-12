from youtube3.youtube_client import *
from oauth2client.tools import argparser
import os
import logging

if __name__ == "__main__":
    argparser.add_argument('--playlistSource')
    argparser.add_argument('--start')
    argparser.add_argument('--end')

    youtube = YoutubeClient(os.path.join(os.path.dirname(__file__), 'client_secrets.json'), True)

    args = argparser.parse_args()

    playlist_source = args.playlistSource

    start = int(args.start)
    end = int(args.end)


    youtube.delete_from_playlist(playlist_source, start, end)
