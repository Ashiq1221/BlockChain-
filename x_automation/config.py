import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("X_API_KEY")
API_SECRET = os.getenv("X_API_SECRET")
ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")
BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")

BLOCKCHAIN_NAME = os.getenv("BLOCKCHAIN_NAME", "BlockChain")
TOTAL_SUPPLY = int(os.getenv("TOTAL_SUPPLY", "11000"))
POST_INTERVAL_HOURS = int(os.getenv("POST_INTERVAL_HOURS", "6"))
TIMEZONE = os.getenv("TIMEZONE", "UTC")

def validate():
    required = {
        "X_API_KEY": API_KEY,
        "X_API_SECRET": API_SECRET,
        "X_ACCESS_TOKEN": ACCESS_TOKEN,
        "X_ACCESS_TOKEN_SECRET": ACCESS_TOKEN_SECRET,
        "X_BEARER_TOKEN": BEARER_TOKEN,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")
