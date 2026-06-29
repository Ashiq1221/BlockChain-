import sqlite3
from playwright.sync_api import Page
from utils import human_delay, increment_stat, get_today_stats
from config import LIMITS, DELAY_SHORT, DELAY_MEDIUM, DELAY_LONG, DB_PATH


# Message templates
TEMPLATES = {
    "connect_default": (
        "Hi {name}, I came across your profile and would love to connect. "
        "I'm interested in {industry} and think we could have a valuable connection!"
    ),
    "connect_recruiter": (
        "Hi {name}, I noticed you work at {company}. "
        "I'm actively exploring {role} opportunities and would love to connect!"
    ),
    "connect_peer": (
        "Hi {name}, I see we share an interest in {topic}. "
        "Would love to connect and exchange ideas!"
    ),
    "followup": (
        "Hi {name}, thanks for connecting! I'd love to learn more about "
        "your work at {company}. Would you be open to a quick chat?"
    ),
    "job_inquiry": (
        "Hi {name}, I noticed {company} is doing great work in {industry}. "
        "I'm a {role} with {years} years of experience and would love to "
        "explore potential opportunities. Would you be open to connecting?"
    ),
}


def format_message(template_name: str, **kwargs) -> str:
    """Format a message template with given variables."""
    template = TEMPLATES.get(template_name, TEMPLATES["connect_default"])
    try:
        return template.format(**kwargs)
    except KeyError as e:
        print(f"[Messaging] Missing template variable: {e}")
        return template


def send_connection_request(page: Page, profile_url: str,
                             message: str = None, name: str = "") -> bool:
    """
    Send a connection request to a LinkedIn profile.
    Optionally includes a personalized note.
    """
    stats = get_today_stats()
    if stats["connections_sent"] >= LIMITS["connection_requests"]:
        print(f"[Messaging] Daily connection limit reached ({LIMITS['connection_requests']}).")
        return False

    page.goto(profile_url)
    human_delay(DELAY_MEDIUM)

    # Look for Connect button (sometimes behind More menu)
    connect_btn = page.query_selector("button:has-text('Connect')")
    if not connect_btn:
        # Try the "More" dropdown
        more_btn = page.query_selector("button:has-text('More')")
        if more_btn:
            more_btn.click()
            human_delay(DELAY_SHORT)
            connect_btn = page.query_selector("div[role='option']:has-text('Connect')")

    if not connect_btn:
        print(f"[Messaging] Connect button not found for: {profile_url}")
        return False

    connect_btn.click()
    human_delay(DELAY_SHORT)

    if message:
        add_note_btn = page.query_selector("button:has-text('Add a note')")
        if add_note_btn:
            add_note_btn.click()
            human_delay(DELAY_SHORT)
            note_field = page.query_selector("textarea#custom-message")
            if note_field:
                # Enforce LinkedIn's 300-char limit
                note_text = message[:300]
                note_field.fill(note_text)
                human_delay(DELAY_SHORT)

    # Send the request
    send_btn = page.query_selector("button:has-text('Send')")
    if not send_btn:
        send_btn = page.query_selector("button:has-text('Send without a note')")

    if send_btn:
        send_btn.click()
        human_delay(DELAY_SHORT)
        increment_stat("connections_sent")
        print(f"[Messaging] ✅ Connection sent to {name or profile_url}")

        # Mark as connected in DB
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE leads SET connected = 1 WHERE profile_url = ?", (profile_url,))
        conn.commit()
        conn.close()
        return True

    print(f"[Messaging] ❌ Failed to send connection to {name or profile_url}")
    return False


def send_direct_message(page: Page, profile_url: str, message: str,
                        name: str = "") -> bool:
    """
    Send a direct message to an existing connection.
    """
    stats = get_today_stats()
    if stats["messages_sent"] >= LIMITS["messages"]:
        print(f"[Messaging] Daily message limit reached ({LIMITS['messages']}).")
        return False

    page.goto(profile_url)
    human_delay(DELAY_MEDIUM)

    # Click Message button
    msg_btn = page.query_selector("button:has-text('Message')")
    if not msg_btn:
        print(f"[Messaging] Message button not found — may not be a connection yet.")
        return False

    msg_btn.click()
    human_delay(DELAY_MEDIUM)

    # Find message input
    msg_input = page.query_selector("div.msg-form__contenteditable")
    if not msg_input:
        msg_input = page.query_selector("div[role='textbox']")

    if not msg_input:
        print(f"[Messaging] Could not find message input field.")
        return False

    msg_input.click()
    msg_input.type(message)
    human_delay(DELAY_SHORT)

    # Send message
    send_btn = page.query_selector("button.msg-form__send-button")
    if send_btn:
        send_btn.click()
        human_delay(DELAY_SHORT)
        increment_stat("messages_sent")
        print(f"[Messaging] ✅ Message sent to {name or profile_url}")

        # Mark as messaged in DB
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE leads SET messaged = 1 WHERE profile_url = ?", (profile_url,))
        conn.commit()
        conn.close()
        return True

    return False


def run_outreach_campaign(page: Page, template_name: str = "connect_default",
                           max_outreach: int = 20, **template_vars):
    """
    Run a bulk outreach campaign to all uncontacted leads in the database.
    Sends connection requests with personalized messages.
    """
    print(f"\n[Messaging] Starting outreach campaign with template: '{template_name}'")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, profile_url, company FROM leads
        WHERE connected = 0
        ORDER BY created_at DESC
        LIMIT ?
    """, (max_outreach,))
    leads = cursor.fetchall()
    conn.close()

    if not leads:
        print("[Messaging] No uncontacted leads found. Run lead generation first.")
        return

    sent = 0
    failed = 0

    for name, profile_url, company in leads:
        stats = get_today_stats()
        if stats["connections_sent"] >= LIMITS["connection_requests"]:
            print(f"[Messaging] Daily limit reached. Stopping campaign.")
            break

        # Format message with lead-specific data
        msg_vars = {"name": name.split()[0], "company": company, **template_vars}
        message = format_message(template_name, **msg_vars)

        success = send_connection_request(page, profile_url, message, name)
        if success:
            sent += 1
        else:
            failed += 1

        human_delay(DELAY_LONG)  # longer pause between outreach

    print(f"\n[Messaging] Campaign done. Sent: {sent} | Failed: {failed}")
