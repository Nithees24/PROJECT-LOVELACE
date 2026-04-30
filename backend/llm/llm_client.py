import os
from dotenv import load_dotenv
from backend.config import LLM_MODEL, OLLAMA_SWITCH

load_dotenv()

class LLMClient():
    def __init__(self):
        if OLLAMA_SWITCH:
            from ollama import Client
            ollama_api_key = os.getenv("OLLAMA_API_KEY")
            self.ollama_client = Client(
                host="http://localhost:11434",
                headers={"Authorization": f"Bearer {ollama_api_key}"}
            )
            print("[LLMClient] Using Ollama Cloud provider")
        else:
            from google import genai
            google_api_key = os.getenv("GOOGLE_API_KEY")
            self.google_client = genai.Client(api_key=google_api_key)
            print("[LLMClient] Using Google GenAI provider")

    def generate(self, prompt, model=None):
        active_model = model or LLM_MODEL
        if OLLAMA_SWITCH:
            return self._generate_ollama(prompt, active_model)
        else:
            return self._generate_google(prompt, active_model)

    def _generate_google(self, prompt, model):
        """Generate using Google GenAI."""
        response = self.google_client.models.generate_content(model=model, contents=prompt)
        return response.text

    def _generate_ollama(self, prompt, model):
        """Generate using Ollama Cloud."""
        response = self.ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response["message"]["content"]
