"""Artifact extraction (Artifacts module, Phase 1).

An *artifact* is a self-contained deliverable the model produces alongside its
prose — a runnable mini-app or a code file — which the frontend renders in the
document canvas rather than inline in the chat bubble.

The model signals one with a fenced block carrying a dedicated info string:

    ```artifact:html title="Compound Interest Calculator"
    <!DOCTYPE html> ...
    ```

A dedicated `artifact:` prefix (rather than a bare ```html) is deliberate: it
keeps "show me some HTML syntax" from being turned into a running app. Anything
that fails to parse is left untouched in the reply, so the worst case is the
user seeing an ordinary code block — never a broken message.
"""
import re

from backend.utils.logger import logger

# Types the frontend knows how to render. `html` is executed in a sandboxed
# iframe; everything else is shown as highlighted, copyable source.
ARTIFACT_TYPES = {
    "html": {"kind": "runnable", "language": "html"},
    "code": {"kind": "code", "language": ""},
    "python": {"kind": "code", "language": "python"},
    "javascript": {"kind": "code", "language": "javascript"},
    "css": {"kind": "code", "language": "css"},
    "json": {"kind": "code", "language": "json"},
    "sql": {"kind": "code", "language": "sql"},
    "markdown": {"kind": "document", "language": "markdown"},
}

# ```artifact:<type> [title="..."] \n <content> \n ```
# DOTALL so the body may span lines; non-greedy so two artifacts in one reply
# don't collapse into a single match.
_ARTIFACT_RE = re.compile(
    r"```artifact:([a-zA-Z0-9_+-]+)[ \t]*(.*?)\r?\n(.*?)```",
    re.DOTALL,
)

# Same block, but running to end-of-string instead of a closing fence. A
# generation that hits the output ceiling stops mid-code with no fence to match,
# and the strict pattern then discarded the whole artifact — dumping raw HTML
# into the chat bubble, which is the worst possible outcome for the user. An
# incomplete app they can see, copy and ask to finish is strictly better.
_ARTIFACT_TRUNCATED_RE = re.compile(
    r"```artifact:([a-zA-Z0-9_+-]+)[ \t]*(.*?)\r?\n(.*)\Z",
    re.DOTALL,
)

# Storage APIs are unavailable in the artifact sandbox: it runs with
# allow-scripts but deliberately WITHOUT allow-same-origin, so the frame has an
# opaque origin and touching localStorage/sessionStorage/cookies throws
# SecurityError. The frontend installs an in-memory shim so these degrade to
# session-only state instead of a dead panel; this flags them so the UI can say
# the data won't survive reopening.
_STORAGE_RE = re.compile(
    r"\b(localStorage|sessionStorage|indexedDB)\b|document\s*\.\s*cookie",
    re.IGNORECASE,
)

# title="..." or title='...' in the info string.
_TITLE_RE = re.compile(r"""title\s*=\s*["']([^"']+)["']""")

# Hard ceiling so a runaway generation can't push a multi-MB payload into the
# DB row and the JSON response.
MAX_ARTIFACT_CHARS = 100_000


def _slug(text):
    """Filesystem-safe stem for the artifact's download filename."""
    s = re.sub(r"[^\w\s-]", "", (text or "").lower()).strip()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:60] or "artifact"


def extract_artifact(reply):
    """Split an assistant reply into (cleaned_text, artifact | None).

    Only the FIRST artifact block is extracted — one deliverable per message
    keeps the canvas unambiguous about what it is showing. Any further blocks
    are left in place and render as ordinary code.

    The returned artifact is a plain dict (JSON-serializable for the DB column
    and the API response):
        {"type", "kind", "language", "title", "content", "filename"}
    """
    if not reply or "```artifact:" not in reply:
        return reply, None

    truncated = False
    match = _ARTIFACT_RE.search(reply)
    if not match:
        # No closing fence. Almost always a generation that hit the output
        # ceiling, so salvage what was written rather than discarding it.
        match = _ARTIFACT_TRUNCATED_RE.search(reply)
        if not match:
            logger.warning("[Artifact] 'artifact:' marker found but no block parsed")
            return reply, None
        truncated = True
        logger.warning(
            "[Artifact] unclosed block — recovering as truncated artifact"
        )

    raw_type = (match.group(1) or "").lower()
    info = match.group(2) or ""
    content = (match.group(3) or "").strip()

    if not content:
        return reply, None

    spec = ARTIFACT_TYPES.get(raw_type)
    if not spec:
        # Unknown type: treat as generic code so the content still reaches the
        # user in the canvas instead of being silently dropped.
        logger.info(f"[Artifact] unknown type '{raw_type}' — falling back to code")
        spec = ARTIFACT_TYPES["code"]
        language = raw_type
    else:
        language = spec["language"]

    if len(content) > MAX_ARTIFACT_CHARS:
        logger.warning(
            f"[Artifact] content {len(content)} chars exceeds "
            f"{MAX_ARTIFACT_CHARS} — truncated"
        )
        content = content[:MAX_ARTIFACT_CHARS]
        truncated = True

    uses_storage = bool(_STORAGE_RE.search(content))

    title_match = _TITLE_RE.search(info)
    title = title_match.group(1).strip() if title_match else "Untitled artifact"

    ext = {"html": "html", "python": "py", "javascript": "js",
           "css": "css", "json": "json", "sql": "sql",
           "markdown": "md"}.get(raw_type, "txt")

    artifact = {
        "type": raw_type,
        "kind": spec["kind"],
        "language": language,
        "title": title,
        "content": content,
        "filename": f"{_slug(title)}.{ext}",
        # Both drive a notice on the card rather than changing what runs: the
        # user should know why an app stops mid-feature or forgets its data.
        "truncated": truncated,
        "uses_storage": uses_storage,
    }

    # Remove the block from the prose so the chat bubble doesn't duplicate what
    # the canvas is already showing. Collapse the blank lines left behind.
    cleaned = (reply[:match.start()] + reply[match.end():])
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    # A reply that was ONLY an artifact block leaves nothing behind. Never
    # return empty text: the chat bubble would render blank, and the frontend
    # treats an empty reply as a backend error.
    if not cleaned:
        cleaned = f"I've created **{title}** — open it from the card below."

    logger.info(
        f"[Artifact] extracted type={raw_type} kind={spec['kind']} "
        f"title='{title[:50]}' chars={len(content)} "
        f"truncated={truncated} storage={uses_storage}"
    )
    return cleaned, artifact
