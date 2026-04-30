import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

PRODUCTION = os.getenv("PRODUCTION", "False").lower() == "true"

# ──────────────────────────────────────────────
# LLM Provider Switch
# Set to True  → Ollama Cloud
# Set to False → Google GenAI
# ──────────────────────────────────────────────
OLLAMA_SWITCH = True

if OLLAMA_SWITCH:
    # Ollama Cloud models
    CHAT_MODEL = "gemma4:31b-cloud"    # Gemma 4 cloud model for general chat
    LLM_MODEL  = "gemma4:31b-cloud"    # Gemma 4 cloud model for deep research
else:
    # Google GenAI models
    CHAT_MODEL = "gemini-3.1-flash-lite-preview"   # Fast model for general chat
    LLM_MODEL  = "gemma-4-31b-it"                  # Powerful model for deep research

TEMPERATURE = 0.2

# Email settings
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
EMAIL_ASSET_BASE_URL = os.getenv("EMAIL_ASSET_BASE_URL", "").strip()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX")
