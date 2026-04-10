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

BYCRAWL_BASE_URL = "https://api.bycrawl.com"
BYCRAWL_HEADERS = {"x-api-key": BYCRAWL_API_KEY}

DEFAULT_MAX_COMMENTS = 50
DEFAULT_OUTPUT_DIR = "./reports"
DEFAULT_LANG = "zh-TW"
DEFAULT_MODEL = "claude-sonnet-4-6"

RETRY_DELAYS = [5, 15, 30]
