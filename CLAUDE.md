# CLAUDE.md

Project Lovelace: agentic AI research assistant. FastAPI backend + vanilla HTML/CSS/JS frontend (no build step). A Planner LLM routes each query to `GeneralChatAgent` (stateful chat, optional web search) or `DeepResearchAgent` (stateless multi-round research → cited report). Either can emit an **artifact** (sandboxed HTML/CSS/JS or code) rendered in a side canvas. PostgreSQL stores users/conversations/messages (FK cascade). Per-conversation RAG over uploads, switchable cloud/local via the `CLOUD` flag.

## Running
No build step, no tests. Imports are absolute (`backend.x.y`); run as packages. Activate `conda activate LOVELACE` first.
- `python -m backend.app` — API server (`0.0.0.0:8000`), serves frontend at `/login.html`. Don't open HTML files directly (API base is hardcoded).
- `python -m backend.main` — CLI REPL.
- Bump `?v=` in `lovelace.html` on any CSS/JS edit (no cache-busting build step).
- `frontend/vendor/` (KaTeX, highlight.js) is committed, not gitignored — no `npm install` step exists.

## CLOUD switch (`config.py`)
One boolean flips chat, research, and RAG together: `True` = Google GenAI + HuggingFace embeddings + Pinecone. `False` (default) = local Ollama + Chroma. RAG stores are separate per setting — docs don't carry over on flip.

## Architecture
- `POST /api/chat` routes by `mode` (Deep Research / Artifact / normal); returns `{reply, sources, artifact, model}`.
- Deep Research: iterative search→rank→summarize→gap-analysis loop (max 3 rounds) → cited markdown report. Streams via `/api/research/plan` + `/api/research/stream` (NDJSON).
- Document agent (`+` menu → Create Document, **or** routed out of plain chat): interview → web research → written document. `POST /api/document/next` returns a batch of ≤3 questions with ≤4 options each — or none at all when the request is already specific enough. The format question is built in code (never by the LLM, since it selects a render path) and is skipped when `detect_format` finds one named in the request; the resolved format comes back as `format` in the response. The brief travels with every call, so the interview is stateless. A normal chat turn can also become a document: `pipeline/document_router.py` gates on a cheap regex, then one strict-JSON LLM call decides — JSON contract, not provider-native tool calling, since `LLMClient.generate` is text-in/text-out on both providers. On a hit `/api/chat` returns `{route: "document", brief}` **instead of** a reply and the frontend runs the same workspace. The router is the agent's only contact with history: what the conversation already settled is folded into `brief.answers` (marked `source: "chat"`), which the interviewer's ALREADY ANSWERED block then suppresses — so a detailed chat yields zero questions without a second notion of "specific enough", and `DocumentAgent` stays stateless. `/api/chat` has already saved the user's turn, hence `skip_user_message` on the stream. Kill switch: `DOC_ROUTE_FROM_CHAT`. `POST /api/document/stream` (NDJSON, same event vocabulary as research, plus a `document` event) gathers via `DeepResearchAgent.gather()` and drafts. Round cap lives in `DocumentAgent.next_step`; the interviewer's `_fallback` keeps a bad LLM round from stranding the user.
- Export (Share & Export menu): `POST /api/documents/export` renders report/document markdown as .md/.txt/.docx/.pdf via `DocumentGeneratorAgent` (`agents/generator_agent.py`) — deterministic, no LLM. Markdown is parsed once into blocks (`utils/markdown_blocks.py`); one writer per format. Prefers `message_id` (re-reads the stored message) over client-sent markdown, which only a live run needs.
- Artifacts: fenced ` ```artifact:<type> ` blocks extracted server-side. Runs in an iframe with `sandbox="allow-scripts"`, **no** `allow-same-origin`, plus strict no-network CSP — never change this pairing. Latest artifact re-attaches to history so follow-ups can edit it.
- RAG: hybrid dense (Pinecone/Chroma) + BM25, merged via Reciprocal Rank Fusion; marker file gates activity per conversation.
- Auth: bearer tokens, Argon2id hashing (legacy SHA-256 auto-upgraded). Never trust `user_id`/`conversation_id` from requests — use `require_owned_conversation`. Routes with broad `except Exception` must re-raise `HTTPException` first.

## Conventions
- Use `logger`, not `print`, in new code.
- Narrow exception handling (e.g. `json.JSONDecodeError`), not bare `except:`.
- Don't reintroduce removed dead code — see `BUG-NN` commits in git history.
