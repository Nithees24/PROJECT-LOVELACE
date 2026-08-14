import os
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlsplit

# Repo root — anchor for .env and all on-disk RAG state, independent of the
# launch CWD (BUG-14).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from the repo root regardless of the launch CWD (BUG-14)
load_dotenv(PROJECT_ROOT / ".env")

PRODUCTION = os.getenv("PRODUCTION", "False").lower() == "true"

# ──────────────────────────────────────────────
# CLOUD — the single switch for the entire application.
# True  → CLOUD pipeline: Google GenAI models for general chat AND deep
#         research, HuggingFace serverless embeddings + Pinecone vector DB
#         for RAG.
# False → LOCAL pipeline: local Ollama models for general chat AND deep
#         research, local Ollama embeddings (bge-m3) + on-disk Chroma vector
#         DB for RAG. Offline except the daemon.
# Both pipelines run hybrid retrieval (dense semantic + BM25 keyword).
# NOTE: the two RAG stores are separate — documents uploaded under one mode
# are not visible in the other; treat this as a deploy-time choice.
# ──────────────────────────────────────────────
CLOUD = False

if CLOUD:
    # Google GenAI models
    CHAT_MODEL = "gemini-3.1-flash-lite-preview"   # Fast model for general chat
    LLM_MODEL  = "gemma-4-31b-it"                  # Powerful model for deep research
else:
    # Local daemon: a locally-pulled model for general chat, proxied to
    # Ollama Cloud for deep research (needs no OLLAMA_API_KEY when
    # OLLAMA_HOST is the default local daemon — see the Ollama connection
    # note below).
    CHAT_MODEL = "gemma4:31b-cloud"         # local model for general chat
    LLM_MODEL  = "gemma4:31b-cloud"    # Ollama Cloud model for deep research

TEMPERATURE = 0.2

# ──────────────────────────────────────────────
# Deep-research report generation limits.
# The aggregator writes a long, multi-section report (target ~4 pages), which
# needs a high output cap and — on Ollama — an explicitly enlarged context
# window. Ollama's default num_ctx (2k–4k) is the real reason reports came out
# short: it silently truncates BOTH the stacked source summaries going in and
# the report coming out, so no amount of prompt wording could lengthen them.
# num_ctx must comfortably hold (all summaries + the report), not just one.
# ──────────────────────────────────────────────
REPORT_MAX_TOKENS = int(os.getenv("REPORT_MAX_TOKENS", "8192"))
REPORT_NUM_CTX = int(os.getenv("REPORT_NUM_CTX", "32768"))

# Per-document summarization needs a smaller window: DOC_CONTENT_CHARS of page
# text in, a few hundred words out. Still above the Ollama default so the tail
# of a long page isn't dropped before it is ever summarized.
SUMMARY_NUM_CTX = int(os.getenv("SUMMARY_NUM_CTX", "8192"))

# General chat. Normally a small prompt, but an artifact conversation carries
# the full previous artifact source (8-13k chars) back in as history so the
# model can edit rather than rebuild — plus the new artifact it writes out.
CHAT_NUM_CTX = int(os.getenv("CHAT_NUM_CTX", "16384"))

# ──────────────────────────────────────────────
# Artifacts. Writing a complete, working mini-app is code generation — closer to
# research than to chat in difficulty — so an explicitly requested artifact gets
# the stronger model rather than the fast chat one. Under CLOUD=True that is the
# difference between a lite model and a full one; locally the two names are the
# same and this changes nothing.
#
# The output ceiling is explicit because an artifact cut off mid-code used to be
# lost entirely (no closing fence to parse). The extractor now recovers a
# truncated block, but the real fix is not truncating: observed artifacts run
# 9-15k chars (~4k tokens), so this leaves substantial headroom. num_ctx must
# hold the prompt AND the generated output, hence double the token cap.
# ──────────────────────────────────────────────
ARTIFACT_MODEL = LLM_MODEL
ARTIFACT_MAX_TOKENS = int(os.getenv("ARTIFACT_MAX_TOKENS", "16384"))
ARTIFACT_NUM_CTX = int(os.getenv("ARTIFACT_NUM_CTX", "32768"))

# ──────────────────────────────────────────────
# Document agent (backend/agents/document_agent.py).
# The interview is a real cost to the user — every question is a round trip they
# have to answer — so it is capped in two directions: how many batches may be
# asked, and how many questions each batch may contain. DOC_MAX_OPTIONS is the
# hard ceiling the interviewer normalizes to; more than four choices stops being
# a decision and starts being a form.
# ──────────────────────────────────────────────
DOC_MAX_QUESTION_ROUNDS = int(os.getenv("DOC_MAX_QUESTION_ROUNDS", "3"))
DOC_MAX_QUESTIONS_PER_ROUND = int(os.getenv("DOC_MAX_QUESTIONS_PER_ROUND", "3"))
DOC_MAX_OPTIONS = int(os.getenv("DOC_MAX_OPTIONS", "4"))

# Gathering is deliberately far smaller than deep research's 40: a document is
# shaped by the interview answers, not by exhaustive coverage, and the user is
# already waiting through the interview before this starts.
DOC_GATHER_BUDGET = int(os.getenv("DOC_GATHER_BUDGET", "8"))
DOC_MAX_TOKENS = int(os.getenv("DOC_MAX_TOKENS", "8192"))
DOC_NUM_CTX = int(os.getenv("DOC_NUM_CTX", "32768"))

# Routing a plain chat message into the document agent
# (backend/pipeline/document_router.py). Off switch included because this is the
# one path that can turn an ordinary question into a minutes-long research run:
# if the router ever misfires on a given deployment, the `+` menu still works.
DOC_ROUTE_FROM_CHAT = os.getenv("DOC_ROUTE_FROM_CHAT", "true").lower() == "true"
# How much conversation the router reads. Enough to see what a "turn that into a
# report" refers to, bounded so one long turn can't crowd out the rest.
DOC_ROUTE_HISTORY_TURNS = int(os.getenv("DOC_ROUTE_HISTORY_TURNS", "10"))
DOC_ROUTE_TURN_CHARS = int(os.getenv("DOC_ROUTE_TURN_CHARS", "600"))

# ──────────────────────────────────────────────
# Ollama connection (BUG-20) — used only by the LOCAL pipeline (CLOUD=False).
# Default: the local daemon at localhost, no bearer auth (local Ollama
# ignores it anyway). A remote OLLAMA_HOST + OLLAMA_API_KEY gets the bearer
# header attached automatically.
# NOTE: local RAG embeddings (bge-m3) require the model to be available on
# this host; with the default local host it is pulled locally.
# ──────────────────────────────────────────────
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
_OLLAMA_IS_LOCAL = ("localhost" in OLLAMA_HOST) or ("127.0.0.1" in OLLAMA_HOST)
OLLAMA_HEADERS = (
    {"Authorization": f"Bearer {OLLAMA_API_KEY}"}
    if (OLLAMA_API_KEY and not _OLLAMA_IS_LOCAL)
    else None
)

# Verification links expire after this many hours (SEC-13). The email
# template's "expire in N hours" wording uses the same constant, so the
# claim and the enforcement can't drift apart.
VERIFICATION_TOKEN_TTL_HOURS = int(os.getenv("VERIFICATION_TOKEN_TTL_HOURS", "24"))

# Email settings
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
EMAIL_ASSET_BASE_URL = os.getenv("EMAIL_ASSET_BASE_URL", "").strip()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX")

# ──────────────────────────────────────────────
# Rate limits (SEC-12)
# Baseline per-IP limit on all /api/* routes, a tighter one on the
# unauthenticated auth endpoints, and account lockout after repeated
# failed logins. In-memory (single uvicorn process) — see
# backend/utils/rate_limiter.py.
#
# The global limit is only a coarse DoS backstop, so it's set generously —
# a real interactive session fires only a handful of calls per minute, and
# too low a ceiling (the old 120 = 2 req/s) locks the user out on a normal
# burst. The meaningful brute-force protection lives on the auth endpoints
# below (AUTH_RATE_LIMIT_PER_MINUTE + login lockout), not here.
# ──────────────────────────────────────────────
GLOBAL_RATE_LIMIT_PER_MINUTE = int(os.getenv("GLOBAL_RATE_LIMIT_PER_MINUTE", "600"))
AUTH_RATE_LIMIT_PER_MINUTE = int(os.getenv("AUTH_RATE_LIMIT_PER_MINUTE", "10"))
LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
LOGIN_FAILURE_WINDOW_SECONDS = int(os.getenv("LOGIN_FAILURE_WINDOW_SECONDS", "900"))
LOGIN_LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))

# ──────────────────────────────────────────────
# Upload limits (SEC-09)
# Enforced server-side while streaming to disk — the client checks are UX
# only. The doc cap bounds Pinecone/embedding load per conversation.
# ──────────────────────────────────────────────
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_DOCS_PER_CONVERSATION = int(os.getenv("MAX_DOCS_PER_CONVERSATION", "20"))

# ──────────────────────────────────────────────
# CORS allowlist (SEC-08)
# The frontend is served by this backend, so same-origin traffic needs no
# CORS at all; the allowlist only covers the dev host mismatch (page opened
# at localhost:8000 while the frontend hardcodes 127.0.0.1:8000) plus the
# deployed BASE_URL. Add extra origins via comma-separated
# CORS_ALLOWED_ORIGINS in .env. Never a wildcard here — "*" together with
# allow_credentials=True is invalid per the CORS spec and would expose
# credentialed responses to any site if a browser honored it.
# ──────────────────────────────────────────────
def _origin_of(url: str):
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else None

_extra_origins = [
    o.strip().rstrip("/")
    for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
CORS_ALLOWED_ORIGINS = sorted({
    o for o in (
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        _origin_of(BASE_URL),
        *_extra_origins,
    ) if o
})

# Minimum cosine-similarity score a retrieved RAG chunk must reach to be
# injected into the prompt (BUG-13). Below this, chunks are considered
# unrelated to the question and skipped. Tune empirically via env.
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.5"))

# ──────────────────────────────────────────────
# RAG embeddings & vector stores (see CLOUD above)
# ──────────────────────────────────────────────
# Cloud RAG — HuggingFace serverless embeddings via the Inference router.
# NOTE: Qwen/Qwen3-Embedding-0.6B is NOT served on the free serverless API
# (returns 404 for feature-extraction), so the default is BAAI/bge-m3 — a
# 1024-dim model that matches both the existing Pinecone index dimension and
# the local Ollama bge-m3 model. Override with HF_EMBED_MODEL in .env.
HF_TOKEN = os.getenv("HF_TOKEN")
HF_EMBED_MODEL = os.getenv("HF_EMBED_MODEL", "BAAI/bge-m3")
# Embed chunks in batches (one HTTP call per batch) so a big document doesn't
# fire hundreds of serial requests at HF's free-tier rate limit. Transient
# failures (429 rate-limit, 503 model-loading, timeouts) are retried with
# exponential backoff, then the batch is retried item-by-item as a last resort.
HF_EMBED_BATCH_SIZE = int(os.getenv("HF_EMBED_BATCH_SIZE", "32"))
HF_EMBED_MAX_RETRIES = int(os.getenv("HF_EMBED_MAX_RETRIES", "4"))

# Local RAG — local Ollama embedding model + an on-disk Chroma store.
LOCAL_EMBED_MODEL = os.getenv("LOCAL_EMBED_MODEL", "bge-m3")
CHROMA_DIR = PROJECT_ROOT / "backend" / "rag" / "chroma_db"

# Hybrid retrieval — a BM25 keyword index persisted per conversation next to
# whichever dense store is active, fused with the dense results. Set
# RAG_HYBRID=false to fall back to dense-only search.
KEYWORD_INDEX_DIR = PROJECT_ROOT / "backend" / "rag" / "keyword_index"
RAG_HYBRID = os.getenv("RAG_HYBRID", "true").lower() == "true"

# Single per-document content budget for the deep-research pipeline
# (BUG-21): the scraper stores this many chars and the synthesizer
# summarizes ALL of them — previously it silently read only the first 2000
# of 5000, so ranking rewarded length that was never used.
DOC_CONTENT_CHARS = 5000
