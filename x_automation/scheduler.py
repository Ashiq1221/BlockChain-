import schedule
import time
import logging
from datetime import datetime
from . import config
from .client import get_client, post_tweet, post_thread
from .content import get_scheduled_tweet, get_thread

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def job_scheduled_tweet():
    try:
        client = get_client()
        text = get_scheduled_tweet()
        tweet_id = post_tweet(client, text)
        log.info(f"Scheduled tweet posted: {tweet_id}")
    except Exception as e:
        log.error(f"Failed to post scheduled tweet: {e}")


def job_weekly_thread():
    try:
        client = get_client()
        posts = get_thread()
        ids = post_thread(client, posts)
        log.info(f"Thread posted: {len(ids)} tweets")
    except Exception as e:
        log.error(f"Failed to post thread: {e}")


def start():
    log.info(f"X Automation bot starting — interval: every {config.POST_INTERVAL_HOURS}h")

    schedule.every(config.POST_INTERVAL_HOURS).hours.do(job_scheduled_tweet)
    schedule.every().monday.at("09:00").do(job_weekly_thread)

    # Post immediately on start
    job_scheduled_tweet()

    log.info("Scheduler running. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(60)
