import time
import random
import sqlite3
import csv
import os
from datetime import datetime
from config import DB_PATH, LEADS_CSV, JOBS_CSV


def human_delay(range_tuple=(2, 5)):
    """Sleep for a random duration to mimic human behavior."""
    delay = random.uniform(*range_tuple)
    time.sleep(delay)
    return delay


def type_like_human(page, selector, text):
    """Type text character by character with random delays."""
    page.click(selector)
    for char in text:
        page.keyboard.type(char)
        time.sleep(random.uniform(0.05, 0.15))


def init_database():
    """Initialize SQLite database for tracking automation data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            title TEXT,
            company TEXT,
            location TEXT,
            profile_url TEXT UNIQUE,
            connected INTEGER DEFAULT 0,
            messaged INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applied_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_title TEXT,
            company TEXT,
            location TEXT,
            job_url TEXT UNIQUE,
            status TEXT DEFAULT 'applied',
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT DEFAULT CURRENT_DATE,
            profile_views INTEGER DEFAULT 0,
            connections_sent INTEGER DEFAULT 0,
            messages_sent INTEGER DEFAULT 0,
            jobs_applied INTEGER DEFAULT 0,
            posts_made INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def get_today_stats():
    """Get today's automation usage stats."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT * FROM daily_stats WHERE date = ?", (today,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"profile_views": 0, "connections_sent": 0,
                "messages_sent": 0, "jobs_applied": 0, "posts_made": 0}
    return {
        "profile_views": row[2],
        "connections_sent": row[3],
        "messages_sent": row[4],
        "jobs_applied": row[5],
        "posts_made": row[6],
    }


def increment_stat(stat_name, amount=1):
    """Increment a daily stat counter."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT id FROM daily_stats WHERE date = ?", (today,))
    row = cursor.fetchone()
    if row:
        cursor.execute(
            f"UPDATE daily_stats SET {stat_name} = {stat_name} + ? WHERE date = ?",
            (amount, today)
        )
    else:
        cursor.execute(
            f"INSERT INTO daily_stats (date, {stat_name}) VALUES (?, ?)",
            (today, amount)
        )
    conn.commit()
    conn.close()


def save_lead(name, title, company, location, profile_url):
    """Save a scraped lead to database and CSV."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO leads (name, title, company, location, profile_url)
            VALUES (?, ?, ?, ?, ?)
        """, (name, title, company, location, profile_url))
        conn.commit()
        _append_to_csv(LEADS_CSV,
                       ["name", "title", "company", "location", "profile_url"],
                       [name, title, company, location, profile_url])
    except Exception as e:
        print(f"[DB] Error saving lead: {e}")
    finally:
        conn.close()


def save_job(job_title, company, location, job_url):
    """Save an applied job to database and CSV."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO applied_jobs (job_title, company, location, job_url)
            VALUES (?, ?, ?, ?)
        """, (job_title, company, location, job_url))
        conn.commit()
        _append_to_csv(JOBS_CSV,
                       ["job_title", "company", "location", "job_url", "status"],
                       [job_title, company, location, job_url, "applied"])
    except Exception as e:
        print(f"[DB] Error saving job: {e}")
    finally:
        conn.close()


def _append_to_csv(filepath, headers, row_data):
    """Append a row to CSV, creating headers if file is new."""
    file_exists = os.path.isfile(filepath)
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(headers)
        writer.writerow(row_data)


def print_stats():
    """Print today's usage statistics."""
    stats = get_today_stats()
    print("\n📊 Today's Stats:")
    print(f"  Profile Views     : {stats['profile_views']}")
    print(f"  Connection Sent   : {stats['connections_sent']}")
    print(f"  Messages Sent     : {stats['messages_sent']}")
    print(f"  Jobs Applied      : {stats['jobs_applied']}")
    print(f"  Posts Made        : {stats['posts_made']}")
    print()
