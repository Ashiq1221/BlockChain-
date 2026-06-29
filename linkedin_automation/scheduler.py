import schedule
import time
from datetime import datetime


_jobs = []


def schedule_job_search(keywords: str, location: str, time_str: str = "09:00",
                         max_apply: int = 10):
    """Schedule daily job search and auto-apply."""
    def job():
        from playwright.sync_api import sync_playwright
        from browser import create_browser, create_context
        from auth import login
        from job_search import run_job_automation

        print(f"\n[Scheduler] Running job search at {datetime.now()}")
        with sync_playwright() as p:
            browser = create_browser(p)
            context = create_context(browser)
            page = context.new_page()
            if login(page, context):
                run_job_automation(page, keywords, location, max_apply)
            browser.close()

    schedule.every().day.at(time_str).do(job)
    print(f"[Scheduler] Job search scheduled daily at {time_str}")


def schedule_lead_gen(keywords: str, time_str: str = "10:00",
                       max_profiles: int = 50):
    """Schedule daily lead generation."""
    def job():
        from playwright.sync_api import sync_playwright
        from browser import create_browser, create_context
        from auth import login
        from lead_gen import run_lead_gen

        print(f"\n[Scheduler] Running lead gen at {datetime.now()}")
        with sync_playwright() as p:
            browser = create_browser(p)
            context = create_context(browser)
            page = context.new_page()
            if login(page, context):
                run_lead_gen(page, keywords=keywords, max_profiles=max_profiles)
            browser.close()

    schedule.every().day.at(time_str).do(job)
    print(f"[Scheduler] Lead generation scheduled daily at {time_str}")


def schedule_outreach(template_name: str, time_str: str = "11:00",
                       max_outreach: int = 20, **template_vars):
    """Schedule daily outreach campaign."""
    def job():
        from playwright.sync_api import sync_playwright
        from browser import create_browser, create_context
        from auth import login
        from messaging import run_outreach_campaign

        print(f"\n[Scheduler] Running outreach at {datetime.now()}")
        with sync_playwright() as p:
            browser = create_browser(p)
            context = create_context(browser)
            page = context.new_page()
            if login(page, context):
                run_outreach_campaign(page, template_name, max_outreach, **template_vars)
            browser.close()

    schedule.every().day.at(time_str).do(job)
    print(f"[Scheduler] Outreach campaign scheduled daily at {time_str}")


def schedule_content_post(posts: list, times: list):
    """
    Schedule content posts at specific times.
    posts = ["Post 1 text", "Post 2 text", ...]
    times = ["09:00", "14:00", ...]
    """
    for post_text, time_str in zip(posts, times):
        def make_job(text):
            def job():
                from content_post import run_content_poster
                print(f"\n[Scheduler] Posting content at {datetime.now()}")
                run_content_poster(text)
            return job

        schedule.every().day.at(time_str).do(make_job(post_text))
        print(f"[Scheduler] Post scheduled at {time_str}: '{post_text[:50]}...'")


def run_scheduler():
    """Start the scheduler loop."""
    print("\n[Scheduler] Starting scheduler. Press Ctrl+C to stop.")
    print(f"[Scheduler] Pending jobs: {len(schedule.jobs)}")
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n[Scheduler] Stopped.")
