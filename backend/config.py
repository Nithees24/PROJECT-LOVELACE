import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from the repo root regardless of the launch CWD (BUG-14)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

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

# ──────────────────────────────────────────────
# Ollama connection (BUG-20)
# Default mode: the LOCAL daemon at localhost proxies '-cloud' model names
# to ollama.com using its own signed-in credentials, so no bearer auth is
# sent (local Ollama ignores it anyway).
# Direct-cloud mode: set OLLAMA_HOST=https://ollama.com and provide
# OLLAMA_API_KEY — the bearer header is attached only for a remote host.
# NOTE: RAG embeddings (bge-m3) require the model to be available on this
# host; with the default local host it is pulled locally.
# ──────────────────────────────────────────────
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
_OLLAMA_IS_LOCAL = ("localhost" in OLLAMA_HOST) or ("127.0.0.1" in OLLAMA_HOST)
OLLAMA_HEADERS = (
    {"Authorization": f"Bearer {OLLAMA_API_KEY}"}
    if (OLLAMA_API_KEY and not _OLLAMA_IS_LOCAL)
    else None
)

# Email settings
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
EMAIL_ASSET_BASE_URL = os.getenv("EMAIL_ASSET_BASE_URL", "").strip()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX")

# Minimum cosine-similarity score a retrieved RAG chunk must reach to be
# injected into the prompt (BUG-13). Below this, chunks are considered
# unrelated to the question and skipped. Tune empirically via env.
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.5"))

# Single per-document content budget for the deep-research pipeline
# (BUG-21): the scraper stores this many chars and the synthesizer
# summarizes ALL of them — previously it silently read only the first 2000
# of 5000, so ranking rewarded length that was never used.
DOC_CONTENT_CHARS = 5000
