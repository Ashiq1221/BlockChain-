from playwright.sync_api import sync_playwright, Browser, Page
import os
import json
from config import HEADLESS, SLOW_MO

SESSION_FILE = "linkedin_session.json"


def create_browser(playwright):
    """Launch a stealth Chromium browser."""
    browser = playwright.chromium.launch(
        headless=HEADLESS,
        slow_mo=SLOW_MO,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--start-maximized",
        ]
    )
    return browser


def create_context(browser: Browser):
    """Create a browser context with stealth settings."""
    context_args = {
        "viewport": {"width": 1366, "height": 768},
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "locale": "en-US",
        "timezone_id": "America/New_York",
    }

    # Load saved session cookies if available
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            storage_state = json.load(f)
        context_args["storage_state"] = storage_state
        print("[Browser] Loaded saved session.")

    context = browser.new_context(**context_args)

    # Inject stealth JS to hide automation fingerprints
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)

    return context


def save_session(context):
    """Save browser cookies/session for reuse."""
    storage = context.storage_state()
    with open(SESSION_FILE, "w") as f:
        json.dump(storage, f)
    print("[Browser] Session saved.")


def is_logged_in(page: Page) -> bool:
    """Check if user is currently logged in to LinkedIn."""
    try:
        page.goto("https://www.linkedin.com/feed/", timeout=15000)
        return "feed" in page.url
    except Exception:
        return False
