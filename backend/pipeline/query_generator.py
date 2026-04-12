import json


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
            parsed = self._parse_response(response)
            return parsed.get("queries", [])
        except Exception as e:
            print(f"[QueryGenerator LLM ERROR]: {e}")
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
        except:
            start = response.find("{")
            end = response.rfind("}") + 1
            cleaned = response[start:end]
            return json.loads(cleaned)