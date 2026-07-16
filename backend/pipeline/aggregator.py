class Aggregator:
    def __init__(self, llm_client):
        self.llm = llm_client

    def aggregate(self, query, summaries):
        """Returns (answer_text, sources) where sources is a list of
        {"title", "url"} dicts ordered to match the [n] citation markers."""
        print("[Aggregator] Generating final answer...")

        if not summaries:
            return "No summaries available.", []

        # Create numbered sources (structured, so the frontend can render them)
        sources = []
        formatted_summaries = []

        for i, item in enumerate(summaries, start=1):
            summary_text = item.get("summary", "")
            url = item.get("url", "Unknown")

            sources.append({
                "title": item.get("title", f"Source [{i}]"),
                "url": url,
                "content": summary_text
            })

            # Attach citation marker
            formatted_summaries.append(f"[{i}] {summary_text}")

        combined = "\n\n".join(formatted_summaries)

        prompt = f"""
You are an expert research assistant.

Answer the user query using the information below.

STRICT INSTRUCTIONS:
- Write a well-structured answer
- Use clear sections (Overview, Key Points, etc.)
- Keep it concise but informative
- Naturally incorporate citation numbers like [1], [2] in the answer
- Do NOT list sources inside the answer text (they are shown separately by the app)
- Do NOT ask for more input
- FORMATTING: Use markdown. Use bold section titles like **Overview** (NOT # headers). You may use **bold** for emphasis and simple "- " bullet points. Do NOT use tables, code blocks, or links.

Query:
{query}

Information:
{combined}

FINAL ANSWER:
"""

        try:
            answer = self.llm.generate(prompt)

            # Sources are returned as structured data; the frontend renders
            # them in the 'Sources' dropdown (ordered to match [n] markers).
            return answer, sources

        except Exception as e:
            print(f"[Aggregator ERROR]: {e}")
            return "Failed to generate final answer.", []