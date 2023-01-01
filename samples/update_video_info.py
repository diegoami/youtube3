from youtube3 import YoutubeClient
from oauth2client.tools import argparser
import os

if __name__ == "__main__":
    argparser.add_argument('--videoId')
    args = argparser.parse_args()
    if args.videoId == None:
        print("required argument --videoId <videoId>")
    else:
        youtube = YoutubeClient(os.path.join(os.path.dirname(__file__), 'client_secrets.json'))
        videoInfo = youtube.get_video(args.videoId)
        video_snippet = youtube.get_video_snippet(args.videoId)

        video_snippet["title"] = video_snippet["title"]+ " - X"
        video_snippet["description"] = video_snippet["description"] + "\n XXXXXX"

        youtube.update_snippet(video_id=args.videoId, video_snippet=video_snippet)