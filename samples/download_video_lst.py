from youtube3.youtube import *
from oauth2client.tools import argparser
import json

if __name__ == "__main__":
    argparser.add_argument('--videoLst')
    argparser.add_argument('--outDir')
    args = argparser.parse_args()
    if args.videoLst == None:
        print("required argument --videoLst <videoId>")
    elif args.outDir == None:
        print("required argument --outDir <outDir>")
    else:
        with open(args.videoLst, 'r', encoding="utf-8") as f:
            video_lst = json.load(f)
            video_key_lst = [k for k,v in video_lst.items() ]
            youtube = Youtube(get_authenticated_service(args))
            youtube.download_list(video_key_lst, args.outDir)