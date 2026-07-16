import json

from backend.utils.logger import logger


class QueryGenerator:
    def __init__(self, llm_client):
        self.llm = llm_client
        self.max_queries = 10

    # -----------------------------
    # Public Method
    # -----------------------------
    def generate(self, user_query: str):
        # Step 1: Try LLM generation
        queries = self._generate_with_llm(user_query)

        # Step 2: Validate & clean
        queries = self._validate_queries(queries)

        # Step 3: Fallback if needed
        if not queries:
            queries = self._fallback(user_query)

        return queries[:self.max_queries]

    # -----------------------------
    # LLM Generation
    # -----------------------------
    def _generate_with_llm(self, user_query: str):
        prompt = f"""
You are an expert research assistant.

Generate high-quality search queries for deep research.

STRICT RULES:
- Return ONLY valid JSON
- Format: {{ "queries": ["query1", "query2", ...] }}
- Each query must be:
  • specific
  • information-rich
  • different from others
- Avoid generic queries like "explain topic"
- Focus on:
  • latest research
  • comparisons
  • technical depth
- Maximum 10 queries

User Query:
{user_query}
"""

        try:
            response = self.llm.generate(prompt)
        except Exception as e:
            # LLM/network failure — fall back to template queries
            logger.error(f"[QueryGenerator] LLM call failed: {e}", exc_info=True)
            return []

        try:
            parsed = self._parse_response(response)
            return parsed.get("queries", [])
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(
                f"[QueryGenerator] LLM output was not valid JSON ({e}); "
                f"falling back. Raw output: {response[:200]!r}"
            )
            return []

    # -----------------------------
    # Validation & Cleaning
    # -----------------------------
    def _validate_queries(self, queries):
        if not isinstance(queries, list):
            return []

        cleaned = []

        for q in queries:
            if not isinstance(q, str):
                continue

            q = q.strip()

            # Basic filters
            if len(q) < 10:
                continue
            if len(q.split()) < 3:
                continue

            cleaned.append(q)

        # Remove duplicates
        cleaned = list(dict.fromkeys(cleaned))

        return cleaned

    # -----------------------------
    # Fallback Strategy
    # -----------------------------
    def _fallback(self, user_query: str):
        print("[QueryGenerator] Using fallback queries")

        return [
            user_query,
            f"{user_query} latest developments",
            f"{user_query} research papers",
            f"{user_query} advantages and challenges"
        ]

    # -----------------------------
    # Safe JSON Parsing
    # -----------------------------
    def _parse_response(self, response):
        try:
            return json.loads(response)
        except (json.JSONDecodeError, TypeError):
            start = response.find("{")
            end = response.rfind("}") + 1
            if start == -1 or end == 0:
                # Previously json.loads ran on an empty slice here and raised
                # a masked error (BUG-16) — fail with a clear message instead
                raise ValueError("No JSON object found in LLM response")
            return json.loads(response[start:end])