from backend.config import DOC_CONTENT_CHARS, SUMMARY_NUM_CTX
from backend.utils.prompt_builder import UNTRUSTED_RULES, wrap_untrusted


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

        {UNTRUSTED_RULES}

        STRICT INSTRUCTIONS:
        - Do NOT ask for more input
        - Do NOT say "please provide"
        - Directly summarize the content
        - Write a detailed summary of 200-350 words, not one or two lines.
          This summary is raw material for a long report, so detail lost here
          cannot be recovered later.

        Preserve specifics verbatim wherever they appear:
        - concrete numbers, measurements, units, percentages and dates
        - named entities: people, organizations, products, places
        - technical mechanisms, methods and any formulas
        - stated limitations, caveats or disagreements

        Focus on:
        - key ideas
        - important facts
        - technical insights

        DOCUMENT:
        {wrap_untrusted(content)}

        SUMMARY:
        """

        try:
            # DOC_CONTENT_CHARS of input plus a detailed summary out overflows
            # Ollama's default context; size it explicitly so the tail of a
            # long page isn't silently dropped before summarization.
            response = self.llm.generate(prompt, num_ctx=SUMMARY_NUM_CTX)
            return response
        except Exception as e:
            print(f"[Synthesizer ERROR]: {e}")
            return None