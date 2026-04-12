from backend.utils.prompt_builder import build_prompt_with_history
from backend.config import CHAT_MODEL

class GeneralChatAgent:

    def __init__(self, llm_client):

        self.llm_client = llm_client

    def run_with_history(self, user_query, history):
        prompt = build_prompt_with_history(user_query, history)

        response = self.llm_client.generate(prompt, model=CHAT_MODEL)

        return response