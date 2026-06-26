import tweepy
from . import config


def get_client() -> tweepy.Client:
    config.validate()
    return tweepy.Client(
        bearer_token=config.BEARER_TOKEN,
        consumer_key=config.API_KEY,
        consumer_secret=config.API_SECRET,
        access_token=config.ACCESS_TOKEN,
        access_token_secret=config.ACCESS_TOKEN_SECRET,
        wait_on_rate_limit=True,
    )


def post_tweet(client: tweepy.Client, text: str) -> str:
    response = client.create_tweet(text=text)
    tweet_id = response.data["id"]
    print(f"[POST] Tweet posted: https://x.com/i/web/status/{tweet_id}")
    return tweet_id


def post_thread(client: tweepy.Client, posts: list[str]) -> list[str]:
    ids = []
    reply_to = None
    for i, text in enumerate(posts):
        kwargs = {"text": text}
        if reply_to:
            kwargs["in_reply_to_tweet_id"] = reply_to
        response = client.create_tweet(**kwargs)
        tweet_id = response.data["id"]
        ids.append(tweet_id)
        reply_to = tweet_id
        print(f"[THREAD {i+1}/{len(posts)}] https://x.com/i/web/status/{tweet_id}")
    return ids
