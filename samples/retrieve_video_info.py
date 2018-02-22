from youtube3 import Youtube, get_authenticated_service
from oauth2client.tools import argparser

if __name__ == "__main__":
    argparser.add_argument('--videoId')
    args = argparser.parse_args()
    if args.videoId == None:
        print("required argument --videoId <videoId>")
    else:
        youtube = Youtube(get_authenticated_service(args))
        videoInfo = youtube.get_video(args.videoId )
        channelId = youtube.get_channel_id(args.videoId)
        channelTitle = youtube.get_channel_title(channelId )

        relatedVideos = youtube.get_related_videos(args.videoId )
        print(videoInfo)
        print(channelId)
        print(relatedVideos)
        print(channelTitle)
