from youtube3.youtube_client import *
from oauth2client.tools import argparser
import os

if __name__ == "__main__":
    argparser.add_argument('--playlistId')
    args = argparser.parse_args()
    youtube = YoutubeClient(os.path.join(os.path.dirname(__file__), 'client_secrets.json'))
    args = argparser.parse_args()
    playlist_id = args.playlistId
    playlist_name = youtube.playlist_name(playlist_id)
    print("Playlist_name: {}".format(playlist_name))
    for video_items in youtube.iterate_videos_in_playlist(playlist_id):
        for item in video_items['items']:
            snippet = item['snippet']
            content_details = item['contentDetails']
            video_id = content_details['videoId']
            title = snippet['title']
            print(video_id, title)
