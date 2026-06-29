import os
from dotenv import load_dotenv

load_dotenv()

# LinkedIn Credentials
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")

# LinkedIn API (for content posting)
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_PERSON_URN = os.getenv("LINKEDIN_PERSON_URN", "")

# Browser settings
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
SLOW_MO = int(os.getenv("SLOW_MO", "50"))  # ms between actions

# Safe daily limits
LIMITS = {
    "profile_views": 80,
    "connection_requests": 25,
    "messages": 15,
    "job_applications": 20,
    "posts_per_day": 2,
}

# Delays (seconds) — randomized for human-like behavior
DELAY_SHORT = (1, 3)
DELAY_MEDIUM = (3, 6)
DELAY_LONG = (5, 10)

# Job search defaults
DEFAULT_JOB_KEYWORDS = os.getenv("JOB_KEYWORDS", "Python Developer")
DEFAULT_JOB_LOCATION = os.getenv("JOB_LOCATION", "Remote")

# Data storage
DB_PATH = "linkedin_data.db"
LEADS_CSV = "leads.csv"
JOBS_CSV = "applied_jobs.csv"
