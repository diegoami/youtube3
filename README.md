# DESCRIPTION

A wrapper around youtube Apis:

- https://developers.google.com/resources/api-libraries/documentation/youtube/v3/python/latest/
- https://developers.google.com/youtube/v3/docs/


## GOAL

I created this package to simplify some typical tasks related to the Youtube API.
See the `samples` directory for examples.

## USAGE

Create a youtube object
```
from youtube3 import YoutubeClient 
youtube = YoutubeClient(<location of your client_secrets.json>)
```

the available methods are all in youtube3.youtube_client

