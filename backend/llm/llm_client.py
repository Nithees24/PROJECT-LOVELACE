import os
from backend.config import LLM_MODEL, CHAT_MODEL, CLOUD, OLLAMA_HOST, OLLAMA_HEADERS, TEMPERATURE
from backend.utils.logger import logger
# .env is loaded (root-anchored) by backend.config — no CWD-relative
# load_dotenv() here (BUG-14)

class LLMClient():
    def __init__(self):
        if CLOUD:
            from google import genai
            google_api_key = os.getenv("GOOGLE_API_KEY")
            self.google_client = genai.Client(api_key=google_api_key)
            print("[LLMClient] CLOUD pipeline — Google GenAI provider")
        else:
            from ollama import Client
            # Host + auth are aligned in config.py (BUG-20): no bearer
            # header for the local daemon; a remote OLLAMA_HOST gets one
            # automatically.
            self.ollama_client = Client(host=OLLAMA_HOST, headers=OLLAMA_HEADERS)
            print(f"[LLMClient] LOCAL pipeline — Ollama at {OLLAMA_HOST}")

    def probe(self):
        """Verify the configured model names exist on the active provider so
        a bad name fails loudly at boot instead of as an unexplained
        mid-request error (BUG-02). Returns True if all names resolve."""
        wanted = {CHAT_MODEL, LLM_MODEL}
        try:
            if CLOUD:
                missing = set()
                for name in wanted:
                    try:
                        self.google_client.models.get(model=name)
                    except Exception:
                        missing.add(name)
            else:
                available = {m.model for m in self.ollama_client.list().models}
                missing = {m for m in wanted if m not in available}
            if missing:
                logger.error(
                    f"[LLMClient] Configured model(s) NOT available on the "
                    f"provider: {sorted(missing)}. Generation will fail — "
                    f"check backend/config.py."
                )
                return False
            logger.info(f"[LLMClient] Model probe OK: {sorted(wanted)}")
            return True
        except Exception as e:
            logger.error(f"[LLMClient] Model probe could not reach the provider: {e}")
            return False

    def generate(self, prompt, model=None, max_tokens=None, num_ctx=None,
                 temperature=None):
        """Text-in/text-out generation. ``max_tokens`` optionally caps the
        output length — pass it for short, bounded outputs (e.g. a thread
        title) so the provider stops early instead of generating far more
        tokens than are kept, or for long ones (the research report) to raise
        the ceiling above the provider default.

        ``num_ctx`` enlarges the Ollama context window for calls whose prompt
        plus output won't fit the daemon's small default; it is ignored by the
        Google provider, which sizes its own context.

        ``temperature`` overrides the global default for one call. Pass 0 for
        routing/classification calls, where the same input returning different
        answers on different turns is a bug rather than variety — prose calls
        should keep the default."""
        active_model = model or LLM_MODEL
        if CLOUD:
            return self._generate_google(prompt, active_model, max_tokens,
                                         temperature)
        else:
            return self._generate_ollama(prompt, active_model, max_tokens,
                                         num_ctx, temperature)

    def _generate_google(self, prompt, model, max_tokens=None, temperature=None):
        """Generate using Google GenAI."""
        # `or` would swallow an explicit 0, which is the value that matters most
        # to pass through here.
        config = {"temperature": TEMPERATURE if temperature is None else temperature}
        if max_tokens:
            config["max_output_tokens"] = max_tokens
        response = self.google_client.models.generate_content(
            model=model,
            contents=prompt,
            config=config
        )
        return response.text

    def _generate_ollama(self, prompt, model, max_tokens=None, num_ctx=None,
                         temperature=None):
        """Generate using Ollama."""
        options = {"temperature": TEMPERATURE if temperature is None else temperature}
        if max_tokens:
            options["num_predict"] = max_tokens
        if num_ctx:
            options["num_ctx"] = num_ctx
        response = self.ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options=options,
            # Keep the model resident between calls so a title/greeting doesn't
            # pay a cold model-load cost on the next request.
            keep_alive="30m",
        )
        return response["message"]["content"]
