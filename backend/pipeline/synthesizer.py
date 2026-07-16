from backend.config import DOC_CONTENT_CHARS


class Synthesizer:
    def __init__(self, llm_client):
        self.llm = llm_client

    def summarize(self, doc):
        print("[Synthesizer] Summarizing document...")

        content = doc.get("content", "")

        if not content.strip():
            return "No content available to summarize."

        # Same budget the scraper stores (BUG-21) — nothing collected is
        # silently discarded before summarization
        content = content[:DOC_CONTENT_CHARS]

        prompt = f"""
        You are an expert research assistant.

        Summarize the following document.

        STRICT INSTRUCTIONS:
        - Do NOT ask for more input
        - Do NOT say "please provide"
        - Directly summarize the content

        Focus on:
        - key ideas
        - important facts
        - technical insights

        DOCUMENT:
        {content}

        SUMMARY:
        """

        try:
            response = self.llm.generate(prompt)
            return response
        except Exception as e:
            print(f"[Synthesizer ERROR]: {e}")
            return None