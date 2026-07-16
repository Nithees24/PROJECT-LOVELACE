import json

from backend.utils.logger import logger


class Planner:
    def __init__(self, llm_client):
        self.llm_client = llm_client

    def plan(self, user_query):
        prompt = self._build_planner_prompt(user_query)
        response = self.llm_client.generate(prompt)
        return self._parse_response(response)


    def _build_planner_prompt(self, user_query):
        return f"""
        You are an intelligent AI planner.
        
        Your job:
        1. Understand the user query
        2. Decide the mode:
           - normal → simple/general questions
           - deep_research → requires latest info, papers, or detailed analysis
        3. Break the problem into steps
        
        STRICT RULES:
        - Return ONLY valid JSON
        - No explanation, no extra text
        - Follow this format exactly
        
        {{
          "mode": "normal or deep_research",
          "steps": ["step 1", "step 2", "step 3"]
        }}
        
        User Query:
        {user_query}
        """

    def _parse_response(self, response):
        # Only JSON-shaped failures fall back; anything else should surface
        # instead of being silently swallowed (BUG-16)
        try:
            return json.loads(response)
        except (json.JSONDecodeError, TypeError):
            try:
                start = response.find("{")
                end = response.rfind("}") + 1

                if start == -1 or end == 0:
                    raise ValueError("No JSON object found in LLM response")

                cleaned = response[start:end]
                return json.loads(cleaned)

            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(
                    f"[Planner] Could not parse LLM output as JSON ({e}); "
                    f"defaulting to normal mode. Raw output: {response[:200]!r}"
                )
                return {
                    "mode": "normal",
                    "steps": []
                }