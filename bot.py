#!/usr/bin/env python3
"""
Entry point for the X automation bot.

Usage:
    python bot.py                     # Run the scheduler (continuous)
    python bot.py --tweet             # Post a single scheduled tweet now
    python bot.py --thread            # Post the full thread now
    python bot.py --alert milestone   # Post a milestone alert
"""
import argparse
import sys
from x_automation.client import get_client, post_tweet, post_thread
from x_automation.content import get_scheduled_tweet, get_thread, get_alert_tweet
from x_automation.scheduler import start


def main():
    parser = argparse.ArgumentParser(description="X automation bot for BlockChain project")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tweet", action="store_true", help="Post a single tweet now")
    group.add_argument("--thread", action="store_true", help="Post the full thread now")
    group.add_argument("--alert", metavar="TYPE", help="Post an alert tweet (milestone|supply_update|new_transaction)")
    args = parser.parse_args()

    if args.tweet:
        client = get_client()
        text = get_scheduled_tweet()
        print(f"Posting:\n{text}\n")
        post_tweet(client, text)

    elif args.thread:
        client = get_client()
        posts = get_thread()
        print(f"Posting thread ({len(posts)} tweets)...\n")
        post_thread(client, posts)

    elif args.alert:
        client = get_client()
        if args.alert == "milestone":
            text = get_alert_tweet("milestone", milestone_text="1,000 wallets created! 🎉")
        elif args.alert == "supply_update":
            text = get_alert_tweet("supply_update", circulating=8500, remaining=2500)
        elif args.alert == "new_transaction":
            text = get_alert_tweet("new_transaction", sender="0xABC...123", receiver="0xDEF...456", amount=100)
        else:
            print(f"Unknown alert type: {args.alert}", file=sys.stderr)
            sys.exit(1)
        print(f"Posting alert:\n{text}\n")
        post_tweet(client, text)

    else:
        start()


if __name__ == "__main__":
    main()
