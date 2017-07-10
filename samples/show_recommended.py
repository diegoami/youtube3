from youtube3.youtube import *
from oauth2client.tools import argparser

if __name__ == "__main__":
    args = argparser.parse_args()
    youtube = Youtube(args)
    recommended  = youtube.get_recommended()
    print(recommended)