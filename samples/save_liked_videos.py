from youtube3.youtube import *
import json
from oauth2client.tools import argparser

if __name__ == "__main__":
    argparser.add_argument('--workDir')
    argparser.add_argument('--maxCount')
    args = argparser.parse_args()
    youtube = Youtube(get_authenticated_service(args))

    likedchannel  = youtube.liked_channel()
    print(likedchannel)
    #videos1 = youtube.videos_in_channels(likedchannel)
    #print(videos1)
    #videos2 = youtube.videos_in_channels(likedchannel,videos1['nextPageToken'])
    #print(videos2)
    count = 0
    liked = {}
    for videos in youtube.iterate_videos_in_channel(likedchannel,args.maxCount):
        for item in videos['items']:
            print(item['contentDetails']['videoId'],item['snippet']['title'])
            liked[item['contentDetails']['videoId']] = item['snippet']['title']
        count = count + 1

    with open(args.workDir+'/liked.json','w',encoding="utf-8") as f:
        json.dump(liked,f,ensure_ascii=False )
