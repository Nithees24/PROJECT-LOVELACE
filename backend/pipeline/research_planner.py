import json

from backend.utils.logger import logger


class ResearchPlanner:
    """Decomposes a research question into a structured, user-approvable plan.

    Output shape (also the wire shape sent to the frontend's left pane):
        {
          "title": "Research: <topic>",
          "sections": [
            {"id": "s1", "title": "...", "question": "...", "queries": ["..", ".."]},
            ...
          ]
        }

    The plan is shown to the user for approval/editing BEFORE any gathering, and
    then drives execution section-by-section (each section's `queries` seed the
    search). Mirrors QueryGenerator's tolerant-JSON + fallback conventions.
    """

    def __init__(self, llm_client, max_sections=5, queries_per_section=3):
        self.llm = llm_client
        self.max_sections = max_sections
        self.queries_per_section = queries_per_section

    def generate_plan(self, user_query: str):
        prompt = f"""
You are an expert research planner. Break the user's question into a structured
research plan: a set of focused sections that together fully cover the topic.

STRICT RULES:
- Return ONLY valid JSON, no prose.
- Shape:
  {{
    "title": "a concise title for the whole research",
    "sections": [
      {{
        "title": "short section name",
        "question": "the specific sub-question this section answers",
        "queries": ["specific web search query", "another distinct query"]
      }}
    ]
  }}
- Produce {self.max_sections} sections at most, ordered logically
  (e.g. background → core → comparisons → challenges → outlook).
- Each section: up to {self.queries_per_section} specific, information-rich
  search queries (NOT generic like "explain X").
- Sections must be distinct and non-overlapping.

USER QUESTION:
{user_query}
"""
        try:
            response = self.llm.generate(prompt)
        except Exception as e:
            logger.error(f"[ResearchPlanner] LLM call failed: {e}", exc_info=True)
            return self._fallback(user_query)

        try:
            parsed = self._parse_response(response)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(
                f"[ResearchPlanner] LLM output was not valid JSON ({e}); "
                f"using fallback plan. Raw output: {response[:200]!r}"
            )
            return self._fallback(user_query)

        return self._normalize(parsed, user_query)

    # -----------------------------
    # Helpers
    # -----------------------------
    def _normalize(self, parsed, user_query):
        if not isinstance(parsed, dict):
            return self._fallback(user_query)

        title = (parsed.get("title") or f"Research: {user_query[:80]}").strip()
        raw_sections = parsed.get("sections")
        if not isinstance(raw_sections, list):
            return self._fallback(user_query)

        sections = []
        for s in raw_sections[:self.max_sections]:
            if not isinstance(s, dict):
                continue
            sec_title = (s.get("title") or "").strip()
            question = (s.get("question") or "").strip()
            if not sec_title and not question:
                continue

            queries = []
            for q in (s.get("queries") or []):
                if isinstance(q, str) and len(q.strip()) >= 5:
                    queries.append(q.strip())
            queries = list(dict.fromkeys(queries))[:self.queries_per_section]
            if not queries:
                queries = [question or sec_title]

            sections.append({
                "id": f"s{len(sections) + 1}",
                "title": sec_title or question[:60],
                "question": question or sec_title,
                "queries": queries,
            })

        if not sections:
            return self._fallback(user_query)

        return {"title": title, "sections": sections}

    def _fallback(self, user_query):
        logger.info("[ResearchPlanner] using fallback plan")
        return {
            "title": f"Research: {user_query[:80]}",
            "sections": [
                {
                    "id": "s1",
                    "title": "Overview & fundamentals",
                    "question": f"What are the fundamentals of: {user_query}?",
                    "queries": [user_query, f"{user_query} overview"],
                },
                {
                    "id": "s2",
                    "title": "Latest developments",
                    "question": f"What are the latest developments in: {user_query}?",
                    "queries": [f"{user_query} latest research", f"{user_query} recent advances"],
                },
                {
                    "id": "s3",
                    "title": "Challenges & outlook",
                    "question": f"What are the challenges and future outlook for: {user_query}?",
                    "queries": [f"{user_query} challenges", f"{user_query} future outlook"],
                },
            ],
        }

    def _parse_response(self, response):
        try:
            return json.loads(response)
        except (json.JSONDecodeError, TypeError):
            start = response.find("{")
            end = response.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON object found in LLM response")
            return json.loads(response[start:end])
