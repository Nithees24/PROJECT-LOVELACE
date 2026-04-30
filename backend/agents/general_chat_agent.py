from backend.utils.prompt_builder import build_prompt_with_history
from backend.config import CHAT_MODEL
from backend.tools.web_search import WebSearch

class GeneralChatAgent:

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.web_search = WebSearch()

    def _needs_web_search(self, user_query):
        """Use a fast LLM call to decide if this query needs a live web search."""
        classifier_prompt = (
            "You are a query classifier. Your ONLY job is to decide whether the "
            "following user message requires a live internet search to answer properly.\n\n"
            "Reply with EXACTLY one word: YES or NO.\n\n"
            "Rules:\n"
            "- Greetings (hi, hello, hey, good morning, etc.) → NO\n"
            "- Casual conversation, small talk, or chitchat → NO\n"
            "- Requests for opinions, jokes, or creative writing → NO\n"
            "- Follow-up questions that can be answered from conversation context → NO\n"
            "- Simple math, logic, or general knowledge that doesn't change over time → NO\n"
            "- Questions about current events, news, real-time data, or recent facts → YES\n"
            "- Questions requiring up-to-date information (prices, weather, scores, etc.) → YES\n"
            "- Research questions, factual look-ups, or technical queries → YES\n"
            "- Questions about specific people, companies, products, or technologies → YES\n\n"
            f"User message: {user_query}\n\n"
            "Answer (YES or NO):"
        )
        try:
            result = self.llm_client.generate(classifier_prompt, model=CHAT_MODEL)
            decision = result.strip().upper()
            print(f"[SearchClassifier] Query: '{user_query[:60]}...' → {decision}")
            return decision.startswith("YES")
        except Exception as e:
            print(f"[SearchClassifier ERROR] {e} — defaulting to NO search")
            return False

    def run_with_history(self, user_query, history):
        search_results = []

        # Only perform web search if the query actually needs it
        if self._needs_web_search(user_query):
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