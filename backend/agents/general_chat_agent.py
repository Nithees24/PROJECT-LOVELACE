from backend.utils.prompt_builder import build_prompt_with_history
from backend.config import CHAT_MODEL
from backend.tools.web_search import WebSearch

class GeneralChatAgent:

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.web_search = WebSearch()

    def run_with_history(self, user_query, history):
        # Perform a quick internet search to augment the prompt with up-to-date knowledge
        search_results = self.web_search.search(user_query)
        
        search_context = ""
        if search_results:
            search_context = "LIVE INTERNET SEARCH RESULTS FOR CONTEXT (Use this to provide up-to-date answers):\n"
            # Take the top 3-4 snippets to keep it fast and lightweight
            for res in search_results[:4]:
                search_context += f"- [{res['title']}] {res['content']} ({res['url']})\n"
                
        augmented_query = user_query
        if search_context:
            augmented_query = f"{search_context}\n\nUSER QUESTION: {user_query}"
            
        prompt = build_prompt_with_history(augmented_query, history)

        response = self.llm_client.generate(prompt, model=CHAT_MODEL)

        # Return the actual search results (snippets/URLs) so the frontend can show them
        return response, search_results[:4]