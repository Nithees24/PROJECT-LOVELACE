import os
from dotenv import load_dotenv
from google import genai
from backend.config import LLM_MODEL

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

class LLMClient():
    def __init__(self):
        self.client = genai.Client(api_key=API_KEY)

    def generate(self, prompt, model=None):
        active_model = model or LLM_MODEL
        response = self.client.models.generate_content(model=active_model, contents=prompt)
        return response.text
