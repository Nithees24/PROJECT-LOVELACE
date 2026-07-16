import os
from backend.config import LLM_MODEL, CHAT_MODEL, OLLAMA_SWITCH, OLLAMA_HOST, OLLAMA_HEADERS, TEMPERATURE
from backend.utils.logger import logger
# .env is loaded (root-anchored) by backend.config — no CWD-relative
# load_dotenv() here (BUG-14)

class LLMClient():
    def __init__(self):
        if OLLAMA_SWITCH:
            from ollama import Client
            # Host + auth are aligned in config.py (BUG-20): the default
            # local daemon proxies '-cloud' models itself, so no bearer
            # header; a remote OLLAMA_HOST gets one automatically.
            self.ollama_client = Client(host=OLLAMA_HOST, headers=OLLAMA_HEADERS)
            print(f"[LLMClient] Using Ollama provider at {OLLAMA_HOST}")
        else:
            from google import genai
            google_api_key = os.getenv("GOOGLE_API_KEY")
            self.google_client = genai.Client(api_key=google_api_key)
            print("[LLMClient] Using Google GenAI provider")

    def probe(self):
        """Verify the configured model names exist on the active provider so
        a bad name fails loudly at boot instead of as an unexplained
        mid-request error (BUG-02). Returns True if all names resolve."""
        wanted = {CHAT_MODEL, LLM_MODEL}
        try:
            if OLLAMA_SWITCH:
                available = {m.model for m in self.ollama_client.list().models}
                missing = {m for m in wanted if m not in available}
            else:
                missing = set()
                for name in wanted:
                    try:
                        self.google_client.models.get(model=name)
                    except Exception:
                        missing.add(name)
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

    def generate(self, prompt, model=None):
        active_model = model or LLM_MODEL
        if OLLAMA_SWITCH:
            return self._generate_ollama(prompt, active_model)
        else:
            return self._generate_google(prompt, active_model)

    def _generate_google(self, prompt, model):
        """Generate using Google GenAI."""
        response = self.google_client.models.generate_content(
            model=model,
            contents=prompt,
            config={"temperature": TEMPERATURE}
        )
        return response.text

    def _generate_ollama(self, prompt, model):
        """Generate using Ollama."""
        response = self.ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": TEMPERATURE}
        )
        return response["message"]["content"]
