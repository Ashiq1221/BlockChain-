import time
from playwright.sync_api import Page
from config import LINKEDIN_EMAIL, LINKEDIN_PASSWORD
from utils import human_delay, type_like_human
from browser import save_session, is_logged_in


def login(page: Page, context, email: str = None, password: str = None) -> bool:
    """
    Log in to LinkedIn. Uses saved session if available, otherwise
    performs fresh login with credentials.
    """
    email = email or LINKEDIN_EMAIL
    password = password or LINKEDIN_PASSWORD

    if not email or not password:
        print("[Auth] ERROR: No credentials provided. Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env")
        return False

    # Try to use existing session first
    if is_logged_in(page):
        print("[Auth] Already logged in via saved session.")
        return True

    print("[Auth] Logging in to LinkedIn...")
    page.goto("https://www.linkedin.com/login")
    human_delay((2, 4))

    # Fill credentials with human-like typing
    type_like_human(page, "#username", email)
    human_delay((0.5, 1.5))
    type_like_human(page, "#password", password)
    human_delay((0.5, 1.0))

    page.click("button[type='submit']")
    human_delay((3, 6))

    # Check for CAPTCHA or verification challenge
    if "checkpoint" in page.url or "challenge" in page.url:
        print("[Auth] ⚠️  Security checkpoint detected.")
        print("[Auth] Please complete the verification manually in the browser window.")
        print("[Auth] Waiting up to 60 seconds...")
        try:
            page.wait_for_url("**/feed/**", timeout=60000)
        except Exception:
            print("[Auth] Verification timed out. Please try again.")
            return False

    # Check for 2FA
    if "two-step" in page.url or "verification" in page.url:
        print("[Auth] ⚠️  Two-factor authentication required.")
        code = input("[Auth] Enter the verification code sent to your email/phone: ").strip()
        page.fill("input[name='pin']", code)
        page.click("button[type='submit']")
        human_delay((3, 5))

    if "feed" in page.url or "mynetwork" in page.url:
        print("[Auth] ✅ Login successful!")
        save_session(context)
        return True

    print(f"[Auth] ❌ Login failed. Current URL: {page.url}")
    return False


def logout(page: Page, context):
    """Log out from LinkedIn and clear session."""
    import os
    page.goto("https://www.linkedin.com/m/logout/")
    human_delay((2, 3))
    if os.path.exists("linkedin_session.json"):
        os.remove("linkedin_session.json")
    print("[Auth] Logged out and session cleared.")
