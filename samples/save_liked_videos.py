from youtube3.youtube import *
import json
from oauth2client.tools import argparser


def update_liked_files(youtube, max_count, work_dir):
    likedchannel = youtube.liked_channel()
    print(likedchannel)
    count = 0
    liked = {}
    for videos in youtube.iterate_videos_in_channel(likedchannel, max_count):
        for item in videos['items']:
            print(item['contentDetails']['videoId'], item['snippet']['title'])
            liked[item['contentDetails']['videoId']] = item['snippet']['title']
        count = count + 1
    with open(work_dir + '/liked.json', 'w', encoding="utf-8") as f:
        json.dump(liked, f, ensure_ascii=False)


if __name__ == "__main__":
    argparser.add_argument('--workDir')
    argparser.add_argument('--maxCount')
    args = argparser.parse_args()
    youtube = Youtube(get_authenticated_service(args))

    update_liked_files(youtube=youtube, max_count=args.maxCount, work_dir=args.workDir)
