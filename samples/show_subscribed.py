from youtube3.youtube import *
from oauth2client.tools import argparser

if __name__ == "__main__":
    argparser.add_argument('--channelId')
    args = argparser.parse_args()
    youtube = Youtube(get_authenticated_service(args))
    for subscription_id in youtube.iterate_subscriptions_in_channel():
        print(subscription_id)
