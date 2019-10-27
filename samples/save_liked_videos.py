from youtube3.youtube_client import *
import json
from oauth2client.tools import argparser
import os

def update_liked_files(youtube, max_count, work_dir):
    likedchannel = youtube.liked_channel()
    print(likedchannel)
    count = 0
    liked = {}
    for videos in youtube.iterate_videos_in_playlist(likedchannel, max_count):
        for item in videos['items']:
            print(item['contentDetails']['videoId'], item['snippet']['title'])
            liked[item['contentDetails']['videoId']] = item['snippet']['title']
        count = count + 1
    with open(work_dir + '/liked.json', 'w', encoding="utf-8") as f:
        json.dump(liked, f, ensure_ascii=False)


if __name__ == "__main__":
    argparser.add_argument('--workDir', default="test")
    argparser.add_argument('--maxCount')
    args = argparser.parse_args()
    youtube = YoutubeClient(os.path.join(os.path.dirname(__file__), 'client_secrets.json'))
    if not os.path.isdir(args.workDir):
        os.path.mkdir(args.workDir)

    print("Saving to directory: {}".format(args.workDir))

    update_liked_files(youtube=youtube, max_count=args.maxCount, work_dir=args.workDir)
