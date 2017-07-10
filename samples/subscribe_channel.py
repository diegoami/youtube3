from youtube3.youtube import *
from oauth2client.tools import argparser

if __name__ == "__main__":
    argparser.add_argument('--channelId')
    args = argparser.parse_args()
    if args.channelId == None:
        print("required argument --channelId <channelId>")
    else:
        youtube = Youtube(args)
        youtube.subscribe_channel(args.channelId)
