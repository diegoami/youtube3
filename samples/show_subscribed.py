from _common import client, parser

if __name__ == "__main__":
    args = parser("List the channels you are subscribed to.").parse_args()

    for subscription in client(args).iterate_subscriptions_in_channel():
        print(subscription)
