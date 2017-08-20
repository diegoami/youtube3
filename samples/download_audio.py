from youtube3.youtube import *
from oauth2client.tools import argparser

if __name__ == "__main__":
    argparser.add_argument('--videoId')
    argparser.add_argument('--outDir')
    args = argparser.parse_args()
    if args.videoId == None:
        print("required argument --videoId <videoId>")
    elif args.outDir == None:
        print("required argument --outDir <outDir>")
    else:
        youtube = Youtube(get_authenticated_service(args))
        youtube.download(args.videoId, args.outDir, onlyAudio=True)