import requests
import json
import time
from playwright.sync_api import Page
from utils import human_delay, increment_stat, get_today_stats
from config import (LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN,
                    LIMITS, DELAY_SHORT, DELAY_MEDIUM)


# ─── Official API Method (Recommended for posting) ────────────────────────────

class LinkedInAPI:
    """LinkedIn Official API client for content operations."""

    BASE_URL = "https://api.linkedin.com/v2"

    def __init__(self, access_token: str, person_urn: str):
        self.access_token = access_token
        self.person_urn = person_urn
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def post_text(self, text: str) -> dict:
        """Post a text update to LinkedIn feed."""
        stats = get_today_stats()
        if stats["posts_made"] >= LIMITS["posts_per_day"]:
            print(f"[API] Daily post limit reached ({LIMITS['posts_per_day']}).")
            return {}

        url = f"{self.BASE_URL}/ugcPosts"
        payload = {
            "author": f"urn:li:person:{self.person_urn}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }

        response = requests.post(url, headers=self.headers, json=payload)
        if response.status_code == 201:
            increment_stat("posts_made")
            print(f"[API] ✅ Post published successfully!")
            return response.json()
        else:
            print(f"[API] ❌ Post failed: {response.status_code} — {response.text}")
            return {}

    def post_with_image(self, text: str, image_path: str) -> dict:
        """Post a text update with an image."""
        # Step 1: Register image upload
        register_url = f"{self.BASE_URL}/assets?action=registerUpload"
        register_payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": f"urn:li:person:{self.person_urn}",
                "serviceRelationships": [{
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent"
                }]
            }
        }

        reg_response = requests.post(register_url, headers=self.headers, json=register_payload)
        if reg_response.status_code != 200:
            print(f"[API] ❌ Failed to register image upload")
            return {}

        reg_data = reg_response.json()
        upload_url = reg_data["value"]["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
        asset_urn = reg_data["value"]["asset"]

        # Step 2: Upload the image
        with open(image_path, "rb") as f:
            img_headers = {"Authorization": f"Bearer {self.access_token}"}
            upload_response = requests.put(upload_url, headers=img_headers, data=f)
            if upload_response.status_code not in (200, 201):
                print(f"[API] ❌ Failed to upload image")
                return {}

        # Step 3: Create post with image
        stats = get_today_stats()
        if stats["posts_made"] >= LIMITS["posts_per_day"]:
            print(f"[API] Daily post limit reached.")
            return {}

        url = f"{self.BASE_URL}/ugcPosts"
        payload = {
            "author": f"urn:li:person:{self.person_urn}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "IMAGE",
                    "media": [{
                        "status": "READY",
                        "description": {"text": "Image"},
                        "media": asset_urn,
                        "title": {"text": "Post Image"}
                    }]
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }

        response = requests.post(url, headers=self.headers, json=payload)
        if response.status_code == 201:
            increment_stat("posts_made")
            print(f"[API] ✅ Post with image published successfully!")
            return response.json()
        else:
            print(f"[API] ❌ Post failed: {response.status_code}")
            return {}

    def get_profile(self) -> dict:
        """Get current user profile info."""
        url = f"{self.BASE_URL}/me"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        return {}

    def schedule_post(self, text: str, delay_seconds: int):
        """Schedule a post after a delay (simple time-based scheduling)."""
        print(f"[API] Post scheduled in {delay_seconds} seconds...")
        time.sleep(delay_seconds)
        return self.post_text(text)


# ─── Browser Method (Fallback — no API token needed) ──────────────────────────

def post_via_browser(page: Page, text: str) -> bool:
    """
    Post content to LinkedIn feed using browser automation.
    Use this if you don't have API access.
    """
    stats = get_today_stats()
    if stats["posts_made"] >= LIMITS["posts_per_day"]:
        print(f"[Post] Daily post limit reached.")
        return False

    print(f"[Post] Posting via browser...")
    page.goto("https://www.linkedin.com/feed/")
    human_delay(DELAY_MEDIUM)

    # Click "Start a post" area
    start_post = page.query_selector("button.share-box-feed-entry__trigger")
    if not start_post:
        start_post = page.query_selector("[data-control-name='share.sharebox_trigger']")

    if not start_post:
        print("[Post] Could not find post button.")
        return False

    start_post.click()
    human_delay(DELAY_MEDIUM)

    # Type in the post content
    post_box = page.query_selector("div.ql-editor")
    if not post_box:
        post_box = page.query_selector("div[role='textbox']")

    if not post_box:
        print("[Post] Could not find post text area.")
        return False

    post_box.click()
    post_box.type(text)
    human_delay(DELAY_SHORT)

    # Click Post button
    post_btn = page.query_selector("button.share-actions__primary-action")
    if not post_btn:
        post_btn = page.query_selector("button:has-text('Post')")

    if post_btn:
        post_btn.click()
        human_delay(DELAY_MEDIUM)
        increment_stat("posts_made")
        print("[Post] ✅ Content posted successfully!")
        return True

    print("[Post] ❌ Could not find Post button.")
    return False


def run_content_poster(post_text: str, image_path: str = None,
                       use_api: bool = True, page: Page = None):
    """
    Main function to post content to LinkedIn.
    Prefers API method, falls back to browser.
    """
    if use_api and LINKEDIN_ACCESS_TOKEN and LINKEDIN_PERSON_URN:
        api = LinkedInAPI(LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN)
        if image_path:
            return api.post_with_image(post_text, image_path)
        return api.post_text(post_text)
    elif page:
        return post_via_browser(page, post_text)
    else:
        print("[Post] No API credentials and no browser page provided.")
        return None
