import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

PRODUCTION = os.getenv("PRODUCTION", "False").lower() == "true"

# Fast model for general chat — low latency
CHAT_MODEL = "gemini-3.1-flash-lite-preview"

# Powerful model for deep research — higher quality
LLM_MODEL = "gemma-4-31b-it"

TEMPERATURE = 0.2

# Email settings
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
EMAIL_ASSET_BASE_URL = os.getenv("EMAIL_ASSET_BASE_URL", "").strip()
