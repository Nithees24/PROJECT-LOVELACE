# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Project Lovelace is an agentic AI research assistant. A **Planner** LLM classifies each query into one of two modes, and the backend routes accordingly:

- **Chat Agent** (`normal`) → `GeneralChatAgent`: stateful, conversation-history-aware answers, with optional live web search when the query needs current info.
- **Deep Research** (`deep_research`) → `DeepResearchAgent`: stateless multi-step pipeline (generate queries → web search + parallel scrape → rank → summarize → aggregate into a report with structured sources).

The stack is a **FastAPI** backend + a **vanilla HTML/CSS/JS** frontend (no build step, no framework). A PostgreSQL database stores users, conversations, and messages, all connected by enforced foreign keys (`users` ← `conversations` ← `messages`, cascade delete). Pinecone provides per-conversation RAG over uploaded documents.

## Running the App

There is **no build step and no test suite**. All imports are absolute from the `backend` package (`from backend.x.y import ...`), so modules must be run as packages, not as files. The app is CWD-independent — every filesystem path (`.env`, RAG markers/temp files, the frontend static mount) is anchored to a `PROJECT_ROOT` computed from `__file__`, so it can be launched from any working directory.

**Python environment**: this project uses the **`LOVELACE` conda environment**, which already has all required packages installed. Activate it before running anything:

```powershell
conda activate LOVELACE

# API server (FastAPI + Uvicorn) — this is the real entry point for the web app
python -m backend.app        # serves on http://0.0.0.0:8000

# CLI REPL mode — for quick agent testing, persists to a real "CLI Session" conversation
python -m backend.main
```

Startup work (DB migrations, LLM client + agent construction, a model-name probe) runs in a FastAPI **lifespan handler**, not at import time — importing `backend.app` is side-effect-free and safe without a live DB.

The frontend is served **by the backend itself**: `app.py` mounts `frontend/` at `/` via `StaticFiles`, and `/` redirects to `/login.html`. Open `http://127.0.0.1:8000/login.html`. Opening the HTML files directly from disk will break API calls (the frontend hardcodes `http://127.0.0.1:8000`).

- Frontend API base is set in `frontend/script.js` and `frontend/login.js` (`API_ENDPOINT` / `API_BASE`, overridable via `window.LOVELACE_CONFIG`). If you change the backend port, update these.
- `PRODUCTION=true` in `.env` disables uvicorn's auto-reloader.

## LLM Provider Switch (important)

`backend/config.py` has a single hard-coded boolean `OLLAMA_SWITCH` that flips the entire app between two providers:

- `True` → **Ollama** (default). `LLMClient` talks to a local Ollama daemon (`OLLAMA_HOST`, default `http://localhost:11434`). The daemon proxies `-cloud` model names to Ollama Cloud using **its own** signed-in credentials — no bearer header is sent to a local host. A bearer header (`OLLAMA_API_KEY`) is only attached when `OLLAMA_HOST` points at a genuinely remote host.
- `False` → **Google GenAI** (`GOOGLE_API_KEY`).

`TEMPERATURE` (config.py) is threaded through both providers' generation calls.

`OllamaEmbeddings` in `backend/rag/vector_store.py` **always** uses local Ollama (`bge-m3`, 1024-dim) for RAG embeddings regardless of this switch, so the Ollama daemon must be running for document upload/RAG search even when using Google for generation. (This replaced a HuggingFace-Hub-backed embedder that needed network access to `huggingface.co` even when the model was cached.)

All generation goes through `LLMClient.generate(prompt, model=...)` — a single synchronous, non-streaming text-in/text-out method. Add provider logic there, not in agents. `LLMClient.probe()` checks the configured `CHAT_MODEL`/`LLM_MODEL` actually exist on the active provider and is called once at startup (lifespan / CLI `main()`), logging loudly if a model name is misconfigured.

## Architecture

### Request flow (`POST /api/chat`)
`backend/app.py` `chat()` is the core endpoint. Per request it: auto-generates a conversation title (LLM call, run in a background thread in parallel with the main answer — not on the blocking request path), saves the user message, checks for a RAG marker file and injects retrieved document context (only chunks meeting `RAG_SCORE_THRESHOLD`), then dispatches to `deep_agent.run()` (stateless) or `general_agent.run_with_history()` (stateful, last 20 messages via `message_repo.get_conversation_history`, DB-limited not Python-sliced). Both agents return `(reply, sources)` — the assistant reply is saved with `sources` serialized as a JSON string, and both chat modes return structured, titled sources to the frontend.

### Deep Research pipeline (`backend/agents/deep_research_agent.py`)
`run()` orchestrates: `QueryGenerator` → `_search_and_scrape` (DuckDuckGo via `ddgs`, then parallel scraping with a `ThreadPoolExecutor`, hardcoded trusted/blocked domain lists, content dedup, capped by `max_urls_per_query` and a global `max_total_docs`) → `_rank` (delegates to `Ranker`: domain reputation + content length) → `_summarize` (per-doc via `Synthesizer`, same `DOC_CONTENT_CHARS` budget the scraper used) → `_aggregate` (`Aggregator` returns `(report_text, sources)`, markdown-formatted with `[n]` citations matching the structured `sources` list). There is no paper-fetching path — the old arXiv/PDF stubs were removed as unfinished scaffolding.

### General Chat agent (`backend/agents/general_chat_agent.py`)
`run_with_history()` uses a single planner call (`_plan_web_search`) that decides in one round-trip whether a live search is needed and, if so, returns the optimized query directly (`NONE` otherwise) — this replaced two sequential classifier/optimizer calls. A cheap regex heuristic short-circuits obvious greetings/small talk before spending an LLM call at all. Search snippets are injected into the prompt and the top 4 results are returned to the frontend as `sources`.

### RAG (`backend/rag/`)
Document upload (`POST /api/rag/upload`) extracts + chunks text (`pdf_utils.py`) and indexes into **Pinecone** under namespace `conv_{conversation_id}`. A marker file at `backend/rag/rag_state/{conversation_id}.marker` flags that RAG is active for a conversation; `chat()` checks this file's existence before querying Pinecone, then filters retrieved chunks by similarity score (`RAG_SCORE_THRESHOLD`, config.py) before injecting them — an unrelated question in a RAG-enabled conversation no longer force-injects irrelevant chunks. Deleting a conversation removes the marker and clears the Pinecone namespace in a background task.

### Persistence (`backend/database/`)
SQLAlchemy over PostgreSQL (`DATABASE_URL` env var). `create_tables()` runs `Base.metadata.create_all` **plus** a hand-rolled `_run_migrations()` in `connection.py` — there is no Alembic. Existing migration blocks add the `messages.sources` column, a composite `(conversation_id, timestamp)` index for bounded history reads, and enforce foreign keys (`conversations.user_id → users.id`, `messages.conversation_id → conversations.id`, both `ON DELETE CASCADE`) with orphan-row cleanup baked into the migration. Add new schema changes as further migration blocks here. Models: `User`, `Conversation`, `Message`. `message_repo.py` holds the query helpers, including the single shared `get_conversation_history` used by both `app.py` and `main.py`.

### Auth
Custom email/password auth in `app.py` (`/api/auth/*`). Emails are validated with Pydantic `EmailStr` and normalized to lowercase before storage/lookup (`normalize_email`, `find_user_by_email`) so casing can't create duplicate accounts. Dates of birth are strictly validated (`parse_dob`) — impossible or future dates are rejected with a clear error instead of silently storing a NULL age. Passwords are **SHA-256 hashed** (`hash_password`), no salt, no JWT/session — login returns the raw `user_id` to the frontend. Email verification uses UUID tokens emailed via SMTP (`backend/utils/email_utils.py`), with resend rate-limiting on the `User` row.

## Environment (`.env`, gitignored)

Required keys depend on the provider switch and features in use:
`DATABASE_URL` (Postgres), `OLLAMA_API_KEY` **or** `GOOGLE_API_KEY`, `OLLAMA_HOST` (optional, defaults to local), `PINECONE_API_KEY` + `PINECONE_INDEX` (RAG), `RAG_SCORE_THRESHOLD` (optional, default 0.5), `SMTP_USER` + `SMTP_PASSWORD` (verification email), `BASE_URL` / `EMAIL_ASSET_BASE_URL`, `PRODUCTION` (optional). See `README.md` for the email-asset URL caveat (Gmail can't load `localhost` image URLs).

## Conventions

- **Logging**: use `from backend.utils.logger import logger` (a configured rotating-file + console logger writing to `logs/`). Don't add ad-hoc `print` for anything meant to persist; existing tool modules use `print` but new code should prefer `logger`.
- **Error handling**: endpoints and agents broadly catch exceptions and return `{"error": str(e)}` (endpoints) or a fallback string (agents) rather than raising — follow the surrounding pattern so the frontend keeps working. Exceptions caught for control flow (e.g. LLM JSON parsing) should be narrowed to the specific expected type (`json.JSONDecodeError`, `ValueError`) rather than bare `except:` — see `Planner._parse_response` / `QueryGenerator._parse_response` for the pattern, including a warning log of the raw LLM output on fallback.
- **LLM JSON parsing**: tolerate LLM output that wraps JSON in prose by slicing between the first `{` and last `}`, falling back only on a JSON-shaped failure (not swallowing everything).
- **Dead code**: this codebase went through a full bug-fix pass (see git history / commit messages for `BUG-NN` references) that removed several stubs (`db_operations.py`, `PaperFetch`/`PDFParser`, duplicate helpers). Don't reintroduce unused scaffolding — finish or delete.
