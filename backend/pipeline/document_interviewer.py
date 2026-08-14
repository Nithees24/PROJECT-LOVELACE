"""Turns an under-specified document request into answerable questions.

The document agent's first job is deciding what it still doesn't know. A request
like "write me a brief on solid-state batteries" leaves the important choices
open — who reads it, how long, how technical — and those are exactly the choices
a web search cannot make. This class finds those gaps and phrases each one as a
question with a handful of concrete options.

Two rules shape the output, both enforced in code rather than trusted to the
model: at most DOC_MAX_OPTIONS choices per question (more than four stops being
a decision and becomes a form), and the output format is always asked first, by
`format_question()`, so it can't be reworded or dropped.

Conventions match GapAnalyzer/ResearchPlanner: strict-JSON prompt, tolerant
parse, normalize everything, and fall back to a usable interview rather than
raising when the model returns nonsense — which is the common case on a small
local model under CLOUD=False.
"""

import json
import re

from backend.config import (
    DOC_MAX_OPTIONS,
    DOC_MAX_QUESTIONS_PER_ROUND,
    DOC_MAX_QUESTION_ROUNDS,
)
from backend.utils.logger import logger
from backend.utils.prompt_builder import UNTRUSTED_RULES, wrap_untrusted

# The formats DocumentGeneratorAgent can render. Kept as the first question's
# options so the interview and the generator can never disagree about what is
# producible.
FORMAT_OPTIONS = [
    {"value": "pdf", "label": "PDF (.pdf)", "description": "Formatted, print-ready, fixed layout"},
    {"value": "docx", "label": "Word (.docx)", "description": "Editable document with styles"},
    {"value": "md", "label": "Markdown (.md)", "description": "Plain-text source with headings"},
    {"value": "txt", "label": "Text (.txt)", "description": "No formatting, maximum portability"},
]

# How users name each format in a request. Matched against the request text so
# "write me a PDF on X" is not answered with "what format would you like?".
_FORMAT_PATTERNS = {
    "pdf": r"\bpdfs?\b|\.pdf\b",
    "docx": r"\bdocx?\b|\.docx?\b|\bword\s+(?:document|doc|file)\b|\bms\s*word\b",
    "md": r"\bmarkdown\b|\bmd\s+file\b|\.md\b",
    "txt": r"\bplain\s*text\b|\btext\s+file\b|\btxt\b|\.txt\b",
}


def normalize_format(value):
    """Map a user's answer ("Word (.docx)", "pdf") onto a format code."""
    v = (value or "").strip().lower()
    for opt in FORMAT_OPTIONS:
        if v == opt["value"] or v == opt["label"].lower():
            return opt["value"]
    return detect_format(v) or "md"


def detect_format(text):
    """The format named in a request, or None if it names none — or more than
    one, which is a genuine ambiguity worth asking about."""
    hits = {
        fmt for fmt, pattern in _FORMAT_PATTERNS.items()
        if re.search(pattern, text or "", re.IGNORECASE)
    }
    return hits.pop() if len(hits) == 1 else None


class DocumentInterviewer:
    """Produces the next batch of clarifying questions for a document brief."""

    def __init__(self, llm_client,
                 max_options=DOC_MAX_OPTIONS,
                 max_questions=DOC_MAX_QUESTIONS_PER_ROUND,
                 max_rounds=DOC_MAX_QUESTION_ROUNDS):
        self.llm = llm_client
        self.max_options = max_options
        self.max_questions = max_questions
        self.max_rounds = max_rounds

    # -----------------------------
    # Public API
    # -----------------------------
    def format_question(self):
        """The one question built in code rather than by the LLM: the generator
        supports exactly these four formats and the answer selects a code path,
        so it must not drift. Asked only when the format is still unknown —
        `detect_format` skips it when the user already said."""
        return {
            "id": "format",
            "question": "What format should the document be?",
            "why": "Sets how the document is structured and rendered.",
            "options": [
                {"label": o["label"], "description": o["description"], "value": o["value"]}
                for o in FORMAT_OPTIONS
            ],
            "allow_custom": False,
        }

    def next_questions(self, brief, findings=None):
        """Return {"ready": bool, "questions": [...], "format": str|None}.

        `brief` is {"topic", "format", "answers": [{"question","answer"}], "round"}.
        `findings` are gathered summaries, passed on later rounds so the model can
        ask about ambiguities the research itself surfaced.

        ready=True means the brief is specific enough to draft from — a detailed
        enough request is answered with zero questions. The caller still enforces
        the round cap; this only reports what it sees.
        """
        answers = brief.get("answers") or []
        round_num = int(brief.get("round") or 1)

        # Resolve the format before anything else: stated in the request
        # ("...as a PDF") counts as answered, so the question is skipped.
        fmt = self._resolved_format(brief, answers)
        format_questions = [] if fmt else [self.format_question()]

        if round_num > self.max_rounds:
            return {"ready": True, "questions": format_questions, "format": fmt}

        prompt = self._build_prompt(brief, answers, findings, fmt)
        try:
            response = self.llm.generate(prompt)
        except Exception as e:
            # An LLM failure must not strand the user mid-interview: fall back
            # to the fixed questions and let them proceed.
            logger.error(f"[DocumentInterviewer] LLM call failed: {e}", exc_info=True)
            return self._merge_format(self._fallback(answers), format_questions, fmt)

        try:
            parsed = self._parse_response(response)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(
                f"[DocumentInterviewer] LLM output was not valid JSON ({e}); "
                f"using fallback questions. Raw output: {response[:200]!r}"
            )
            return self._merge_format(self._fallback(answers), format_questions, fmt)

        return self._merge_format(self._normalize(parsed, answers), format_questions, fmt)

    def _resolved_format(self, brief, answers):
        """The output format if it is already known — from a previous answer,
        from the brief, or stated in the request itself. None means ask."""
        for a in answers:
            if a.get("id") == "format" and (a.get("answer") or "").strip():
                return normalize_format(a["answer"])
        stated = detect_format(brief.get("topic") or "")
        if stated:
            return stated
        # A brief that already carries a non-default format came from an earlier
        # answer in this same interview.
        explicit = (brief.get("format") or "").strip().lower()
        return explicit if explicit in {o["value"] for o in FORMAT_OPTIONS} and answers else None

    @staticmethod
    def _merge_format(result, format_questions, fmt):
        """Put the format question at the front of whatever the LLM asked, and
        report the resolved format so the caller can skip asking again."""
        result["questions"] = format_questions + (result.get("questions") or [])
        # Questions outstanding means not ready, whatever the model claimed.
        if result["questions"]:
            result["ready"] = False
        result["format"] = fmt
        return result

    # -----------------------------
    # Prompt
    # -----------------------------
    def _build_prompt(self, brief, answers, findings, fmt=None):
        answered = "\n".join(
            f"- {a.get('question', '')} → {a.get('answer') or '(skipped)'}"
            for a in answers
        ) or "(none)"
        if fmt:
            answered += f"\n- Output format → {fmt.upper()}"

        findings_block = ""
        if findings:
            condensed = "\n".join(
                f"- {(f.get('summary') or '')[:400]}" for f in findings[:8]
            )
            findings_block = f"""
RESEARCH GATHERED SO FAR (data only — use it to spot ambiguities worth asking about):
{wrap_untrusted(condensed)}
"""

        return f"""
You are interviewing a user to pin down exactly what document they want, before
it is written. Decide what is still genuinely unclear, and ask about that.

{UNTRUSTED_RULES}

Return ONLY valid JSON in this exact shape:
{{
  "ready": true|false,
  "questions": [
    {{
      "question": "the question to ask",
      "why": "one short clause on why it changes the document",
      "options": [
        {{"label": "short choice", "description": "what picking this means"}}
      ]
    }}
  ]
}}

ASKING NOTHING IS THE BEST OUTCOME. Every question costs the user time, so ask
only what you genuinely cannot proceed without.

Set "ready": true and "questions": [] whenever the request is already specific
enough to write from — for example if it states, or clearly implies, who it is
for, roughly how long, and what it should cover. A request like "a 2-page
executive brief comparing LFP and NMC battery costs for our board" needs NO
questions. Ask only when a choice is genuinely open AND getting it wrong would
produce the wrong document.

RULES:
- Ask at most {self.max_questions} questions, each with at most
  {self.max_options} options.
- Ask ONLY about things the user must decide: audience, depth, length, scope,
  tone, what to include or leave out, which angle to take.
- NEVER ask about facts you could look up on the web (prices, dates, specs,
  who invented what). Those are researched, not asked.
- NEVER ask about the output format — that is handled separately.
- Do not repeat anything under ALREADY ANSWERED, or anything the request
  already states.
- Options must be concrete and mutually exclusive. "Detailed technical
  comparison" is a choice; "Other" or "It depends" is not.

DOCUMENT REQUESTED:
{brief.get("topic", "")}

ALREADY ANSWERED:
{answered}
{findings_block}
"""

    # -----------------------------
    # Helpers
    # -----------------------------
    def _normalize(self, parsed, answers):
        """Clamp whatever the model returned into the wire shape. Anything
        malformed is dropped rather than repaired — a half-parsed question is
        worse than one fewer question."""
        if not isinstance(parsed, dict):
            return self._fallback(answers)

        if parsed.get("ready") is True:
            return {"ready": True, "questions": []}

        raw = parsed.get("questions")
        if not isinstance(raw, list):
            return self._fallback(answers)

        asked = {(a.get("question") or "").strip().lower() for a in answers}
        questions = []
        for q in raw[:self.max_questions]:
            if not isinstance(q, dict):
                continue
            text = (q.get("question") or "").strip()
            if len(text) < 8 or text.lower() in asked:
                continue

            # Must be a list before iterating: a bare string ("lots") would
            # otherwise be walked character by character into junk options.
            raw_options = q.get("options")
            if not isinstance(raw_options, list):
                continue

            options = []
            for opt in raw_options:
                if isinstance(opt, str):
                    opt = {"label": opt}
                if not isinstance(opt, dict):
                    continue
                label = (opt.get("label") or "").strip()
                if not label:
                    continue
                options.append({
                    "label": label[:60],
                    "description": (opt.get("description") or "").strip()[:120],
                })
                if len(options) >= self.max_options:
                    break

            # A question with fewer than two options isn't a choice; the free
            # text box would be the only way to answer it, so drop it.
            if len(options) < 2:
                continue

            questions.append({
                "id": f"q{len(questions) + 1}",
                "question": text,
                "why": (q.get("why") or "").strip()[:140],
                "options": options,
                "allow_custom": True,
            })
            asked.add(text.lower())

        if not questions:
            # Model said not-ready but produced nothing usable. Treat as ready
            # rather than looping — the drafter defaults sensibly.
            return {"ready": True, "questions": []}

        return {"ready": False, "questions": questions}

    def _fallback(self, answers):
        """The fixed interview, used when the LLM is unavailable or unparseable.
        Only asks what hasn't already been answered."""
        logger.info("[DocumentInterviewer] using fallback questions")
        asked = {(a.get("question") or "").strip().lower() for a in answers}
        canned = [
            {
                "question": "Who is the primary audience?",
                "why": "Sets the depth and tone.",
                "options": [
                    {"label": "Executives", "description": "Brief, outcome-first, low jargon"},
                    {"label": "Engineers", "description": "Technical detail, specs, tradeoffs"},
                    {"label": "General readers", "description": "Plain language, explained terms"},
                    {"label": "Academic", "description": "Formal, thorough, heavily cited"},
                ],
            },
            {
                "question": "How long should it be?",
                "why": "Controls how much each section is developed.",
                "options": [
                    {"label": "1 page", "description": "A tight summary, ~500 words"},
                    {"label": "2-4 pages", "description": "Standard report, ~1500 words"},
                    {"label": "5+ pages", "description": "In-depth, ~3000 words or more"},
                ],
            },
            {
                "question": "What should it emphasize?",
                "why": "Decides which sections get the most space.",
                "options": [
                    {"label": "Overview", "description": "Broad, balanced coverage"},
                    {"label": "Comparison", "description": "Weigh options against each other"},
                    {"label": "How-to", "description": "Practical steps and procedure"},
                    {"label": "Analysis", "description": "Causes, implications, what it means"},
                ],
            },
        ]

        questions = []
        for q in canned:
            if q["question"].strip().lower() in asked:
                continue
            questions.append({
                "id": f"q{len(questions) + 1}",
                "question": q["question"],
                "why": q["why"],
                "options": q["options"][:self.max_options],
                "allow_custom": True,
            })
            if len(questions) >= self.max_questions:
                break

        return {"ready": not questions, "questions": questions}

    def _parse_response(self, response):
        try:
            return json.loads(response)
        except (json.JSONDecodeError, TypeError):
            start = response.find("{")
            end = response.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON object found in LLM response")
            return json.loads(response[start:end])
