"""DocumentAgent — interviews the user, researches, then writes a document.

The mechanism, end to end:

    topic ─► interview (format first, then gaps) ─► web research ─► draft ─► file

Two entry points because the two halves have different transports. `next_step`
is a plain request/response used repeatedly while the interview runs — the brief
travels with every call, so there is no server-side session to expire and a page
reload costs nothing. `run_streaming` is the long half, emitting the same NDJSON
progress events as deep research so the frontend can reuse its reader.

The topic arrives one of two ways. The `+` menu supplies it directly. A plain
chat message that turns out to be a document request arrives through
`brief_from_chat`, which reads the conversation and folds what it already
settled into the brief's answers — the interview then skips whatever the chat
covered. That read is the agent's only contact with history, and it happens
once, before the brief exists; everything downstream still works off the brief
alone, which is what keeps this agent stateless.

The iteration here is the *interview*, not follow-up searches: the user's answers
are what narrow the document, so gathering is a single pass with a small budget
(DOC_GATHER_BUDGET) rather than deep research's multi-round loop.
"""

import time
import uuid

from backend.config import (
    DOC_GATHER_BUDGET,
    DOC_MAX_QUESTION_ROUNDS,
    DOC_ROUTE_FROM_CHAT,
)
from backend.pipeline.document_drafter import DocumentDrafter
from backend.pipeline.document_interviewer import DocumentInterviewer
from backend.pipeline.document_router import DocumentIntentRouter
from backend.pipeline.query_generator import QueryGenerator
from backend.agents.research.events import NullEmitter
from backend.utils.logger import logger


class DocumentAgent:
    """Orchestrates the interview → research → draft pipeline.

    Takes the DeepResearchAgent as its collaborator rather than its own tools:
    `gather()` already owns the scrape budget, URL de-duplication and
    blocked-domain rules, and a second copy of those would drift.
    """

    def __init__(self, llm_client, research_agent):
        self.llm = llm_client
        self.research = research_agent
        self.interviewer = DocumentInterviewer(llm_client)
        self.drafter = DocumentDrafter(llm_client)
        self.query_generator = QueryGenerator(llm_client)
        self.router = DocumentIntentRouter(llm_client)
        self.gather_budget = DOC_GATHER_BUDGET
        self.max_rounds = DOC_MAX_QUESTION_ROUNDS

    # -----------------------------
    # Entry from chat (request/response)
    # -----------------------------
    def brief_from_chat(self, message, history=None):
        """A brief if this chat turn is asking for a document, else None.

        The seam where conversation becomes a brief. Callers pass history
        because they own the database session; from here on the brief is
        self-contained and no further history is read.
        """
        if not DOC_ROUTE_FROM_CHAT:
            return None
        return self.router.route(message, history)

    # -----------------------------
    # Interview (request/response)
    # -----------------------------
    def next_step(self, brief):
        """Return {"ready", "questions", "round"} for the brief so far.

        The round cap is enforced here rather than in the interviewer: the
        interviewer reports what it sees, this decides when to stop asking and
        start writing. Without it a model that never returns ready=true would
        interview forever.
        """
        round_num = int(brief.get("round") or 1)
        if round_num > self.max_rounds:
            logger.info(
                f"[DocumentAgent] round cap ({self.max_rounds}) reached — drafting "
                f"with {len(brief.get('answers') or [])} answers"
            )
            return {"ready": True, "questions": [], "round": round_num}

        result = self.interviewer.next_questions(brief)
        result["round"] = round_num
        return result

    # -----------------------------
    # Research + draft (streaming)
    # -----------------------------
    def run(self, brief):
        """Non-streaming entry point. Returns (markdown, sources)."""
        return self.run_streaming(brief, NullEmitter())

    def run_streaming(self, brief, emitter, run_id=None):
        """Gather source material and write the document, emitting progress.

        Returns (markdown, sources). Always closes the emitter — the streaming
        endpoint's drain loop ends on that close, so an early return that
        skipped it would hang the request.
        """
        run_id = run_id or uuid.uuid4().hex
        started = time.time()
        topic = (brief.get("topic") or "").strip()

        try:
            emitter.run_started(run_id, topic)

            # 1) Search queries from the topic + what the interview settled —
            # "for engineers, 5+ pages" yields sharper queries than the bare
            # topic, which is why gathering waits for the interview.
            emitter.activity("planning", "Planning what to research", "started")
            queries = self.query_generator.generate(self._research_query(brief))
            emitter.activity(
                "planning", "Planning what to research", "ok",
                detail=f"{len(queries)} queries",
            )

            # 2) One gathering pass, small budget.
            summaries, sources = self.research.gather(
                queries, self.gather_budget, emitter
            )
            if not summaries:
                # Not fatal: the drafter falls back to general knowledge and is
                # told not to invent specifics.
                logger.info("[DocumentAgent] no research gathered — drafting unsourced")
                emitter.activity(
                    "reflect", "No usable sources found — writing from general knowledge",
                    "failed",
                )

            # 3) Write it.
            emitter.activity("write", "Writing the document", "started")
            markdown = self.drafter.draft(brief, summaries, sources)
            emitter.activity("write", "Writing the document", "ok")

            emitter.emit(
                "document",
                markdown=markdown,
                sources=sources,
                format=(brief.get("format") or "md"),
            )
            emitter.run_finished({
                "sources": len(sources),
                "questions": len(brief.get("answers") or []),
                "elapsed_s": round(time.time() - started, 1),
            })
            return markdown, sources

        except Exception as e:
            logger.error(f"[DocumentAgent FATAL]: {e}", exc_info=True)
            message = "Something went wrong while generating the document."
            emitter.error(message)
            emitter.emit("document", markdown=f"# Document\n\n{message}", sources=[],
                         format=(brief.get("format") or "md"))
            return message, []
        finally:
            emitter.close()

    # -----------------------------
    # Helpers
    # -----------------------------
    @staticmethod
    def _research_query(brief):
        """Fold the interview answers into the topic so query generation sees
        the specifics the user chose, not just the original one-liner."""
        topic = (brief.get("topic") or "").strip()
        parts = [
            (a.get("answer") or "").strip()
            for a in (brief.get("answers") or [])
            # The format answer describes the file, not the subject — including
            # it would pull "pdf" into the search queries.
            if a.get("id") != "format" and (a.get("answer") or "").strip()
        ]
        return f"{topic} ({', '.join(parts)})" if parts else topic
