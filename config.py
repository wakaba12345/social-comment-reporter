import os
from dotenv import load_dotenv

load_dotenv(override=True)

def _get(key: str) -> str:
    """Read from env first, fallback to Streamlit secrets."""
    val = os.getenv(key, "")
    if not val:
        try:
            import streamlit as st
            val = st.secrets.get(key, "")
        except Exception:
            pass
    return val

BYCRAWL_API_KEY = _get("BYCRAWL_API_KEY")
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
APIFY_API_TOKEN = _get("APIFY_API_TOKEN")
ADMIN_API = _get("ADMIN_API")
GOOGLE_CLIENT_ID = _get("GOOGLE_CLIENT_ID")
GOOGLE_API_KEY = _get("GOOGLE_API_KEY")
GOOGLE_APP_ID = _get("GOOGLE_APP_ID")

BYCRAWL_BASE_URL = "https://api.bycrawl.com"  # used for X/generic fallback only

DEFAULT_MAX_COMMENTS = 50
DEFAULT_OUTPUT_DIR = "./reports"
DEFAULT_LANG = "zh-TW"
DEFAULT_MODEL = "claude-sonnet-4-6"

RETRY_DELAYS = [5, 15, 30]
