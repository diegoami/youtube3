from youtube3.youtube_client import *
from oauth2client.tools import argparser
import os

if __name__ == "__main__":
    args = argparser.parse_args()
    youtube = YoutubeClient(os.path.join(os.path.dirname(__file__), 'client_secrets.json'))

    recommended = youtube.get_recommended()
    print(recommended)