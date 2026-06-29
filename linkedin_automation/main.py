#!/usr/bin/env python3
"""
LinkedIn Automation Suite
Covers: Job Search, Auto-Apply, Lead Generation, Messaging, Content Posting
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from playwright.sync_api import sync_playwright
from browser import create_browser, create_context
from auth import login
from utils import init_database, print_stats
from config import (DEFAULT_JOB_KEYWORDS, DEFAULT_JOB_LOCATION,
                    LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN)


def print_banner():
    print("""
╔══════════════════════════════════════════════╗
║       LinkedIn Automation Suite              ║
║  Job Search | Leads | Messaging | Posting    ║
╚══════════════════════════════════════════════╝
    """)


def print_menu():
    print("""
  [1] Job Search & Auto-Apply
  [2] Lead Generation (Scrape Profiles)
  [3] Send Connection Requests (Outreach)
  [4] Post Content to LinkedIn
  [5] View Today's Stats
  [6] Run Scheduled Automation
  [7] Exit
""")


def run_job_search_flow(page, context):
    print("\n── Job Search & Auto-Apply ──")
    keywords = input(f"  Keywords [{DEFAULT_JOB_KEYWORDS}]: ").strip() or DEFAULT_JOB_KEYWORDS
    location = input(f"  Location [{DEFAULT_JOB_LOCATION}]: ").strip() or DEFAULT_JOB_LOCATION
    remote = input("  Remote only? (y/n) [n]: ").strip().lower() == "y"
    max_apply = int(input("  Max applications [10]: ").strip() or "10")
    resume_path = input("  Resume file path (optional, press Enter to skip): ").strip() or None

    if resume_path and not os.path.isfile(resume_path):
        print(f"  ⚠️  Resume file not found: {resume_path}. Continuing without it.")
        resume_path = None

    from job_search import run_job_automation
    run_job_automation(page, keywords, location, max_apply, resume_path, remote)


def run_lead_gen_flow(page, context):
    print("\n── Lead Generation ──")
    keywords = input("  Search keywords (e.g. 'software engineer'): ").strip()
    title = input("  Job title filter (optional): ").strip()
    company = input("  Company filter (optional): ").strip()
    location = input("  Location filter (optional): ").strip()
    max_profiles = int(input("  Max profiles to scrape [50]: ").strip() or "50")

    from lead_gen import run_lead_gen
    run_lead_gen(page, keywords, title, company, location, max_profiles)


def run_outreach_flow(page, context):
    print("\n── Connection Outreach ──")
    print("  Available templates:")
    print("    1. connect_default  — General connection")
    print("    2. connect_recruiter — For recruiters")
    print("    3. connect_peer      — For peers/colleagues")
    print("    4. job_inquiry       — Job opportunity inquiry")

    choice = input("  Choose template [1]: ").strip() or "1"
    template_map = {
        "1": "connect_default",
        "2": "connect_recruiter",
        "3": "connect_peer",
        "4": "job_inquiry",
    }
    template_name = template_map.get(choice, "connect_default")

    max_outreach = int(input("  Max connections to send [20]: ").strip() or "20")

    # Collect template variables
    template_vars = {}
    industry = input("  Industry (e.g. 'tech', 'finance'): ").strip()
    if industry:
        template_vars["industry"] = industry
    role = input("  Role/Position: ").strip()
    if role:
        template_vars["role"] = role
    topic = input("  Shared topic/interest: ").strip()
    if topic:
        template_vars["topic"] = topic

    from messaging import run_outreach_campaign
    run_outreach_campaign(page, template_name, max_outreach, **template_vars)


def run_post_flow(page, context):
    print("\n── Post Content ──")
    print("  Enter your post content (type END on a new line when done):")
    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    post_text = "\n".join(lines)

    if not post_text.strip():
        print("  No content provided. Cancelled.")
        return

    image_path = input("  Image path (optional, press Enter to skip): ").strip() or None
    if image_path and not os.path.isfile(image_path):
        print(f"  ⚠️  Image file not found. Posting without image.")
        image_path = None

    use_api = bool(LINKEDIN_ACCESS_TOKEN and LINKEDIN_PERSON_URN)
    if use_api:
        print("  Using LinkedIn API for posting (recommended).")
    else:
        print("  API credentials not found. Using browser method.")

    from content_post import run_content_poster
    run_content_poster(post_text, image_path, use_api=use_api, page=page)


def run_scheduler_flow():
    print("\n── Scheduled Automation ──")
    from scheduler import (schedule_job_search, schedule_lead_gen,
                            schedule_outreach, schedule_content_post,
                            run_scheduler)

    keywords = input(f"  Job keywords [{DEFAULT_JOB_KEYWORDS}]: ").strip() or DEFAULT_JOB_KEYWORDS
    location = input(f"  Location [{DEFAULT_JOB_LOCATION}]: ").strip() or DEFAULT_JOB_LOCATION

    # Schedule all tasks
    schedule_job_search(keywords, location, time_str="09:00", max_apply=10)
    schedule_lead_gen(keywords, time_str="10:30", max_profiles=30)
    schedule_outreach("connect_default", time_str="11:30", max_outreach=20,
                      industry="tech", role="developer")

    sample_posts = [
        "Excited to share insights on the latest trends in #AI and #MachineLearning! "
        "The future of tech is incredibly promising. What are your thoughts?",
    ]
    schedule_content_post(sample_posts, ["14:00"])
    run_scheduler()


def main():
    print_banner()
    init_database()

    # Check for credentials
    email = os.getenv("LINKEDIN_EMAIL", "")
    password = os.getenv("LINKEDIN_PASSWORD", "")

    if not email or not password:
        print("⚠️  Credentials not set. Please create a .env file:")
        print("   LINKEDIN_EMAIL=your@email.com")
        print("   LINKEDIN_PASSWORD=yourpassword")
        print()
        email = input("Enter LinkedIn email: ").strip()
        password = input("Enter LinkedIn password: ").strip()

    with sync_playwright() as p:
        browser = create_browser(p)
        context = create_context(browser)
        page = context.new_page()

        if not login(page, context, email, password):
            print("❌ Login failed. Please check your credentials.")
            browser.close()
            return

        while True:
            print_menu()
            choice = input("  Select option: ").strip()

            if choice == "1":
                run_job_search_flow(page, context)
            elif choice == "2":
                run_lead_gen_flow(page, context)
            elif choice == "3":
                run_outreach_flow(page, context)
            elif choice == "4":
                run_post_flow(page, context)
            elif choice == "5":
                print_stats()
            elif choice == "6":
                browser.close()
                run_scheduler_flow()
                return
            elif choice == "7":
                print("\nGoodbye!")
                break
            else:
                print("  Invalid option. Try again.")

        browser.close()


if __name__ == "__main__":
    main()
