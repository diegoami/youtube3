from youtube3.youtube_client import *

import os

if __name__ == "__main__":
    youtube = YoutubeClient(os.path.join(os.path.dirname(__file__), 'client_secrets.json'))
    for subscription_id in youtube.iterate_subscriptions_in_channel():
        print(subscription_id)
