import re

from backend.utils.logger import logger
from backend.utils.prompt_builder import build_prompt_with_history
from backend.config import CHAT_MODEL
from backend.tools.web_search import WebSearch

# Obvious chitchat that never needs a web search — filtered out before
# spending an LLM call on the decision.
_SMALL_TALK_PATTERN = re.compile(
    r"^(hi|hii+|hello|hey|yo|sup|good\s*(morning|afternoon|evening|night)|"
    r"thanks|thank\s*you|ty|ok|okay|cool|nice|great|bye|goodbye|see\s*ya|"
    r"how\s*are\s*you|what'?s\s*up|lol|haha+)[\s!.,?😀-🙏]*$",
    re.IGNORECASE
)

class GeneralChatAgent:

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.web_search = WebSearch()

    def _plan_web_search(self, user_query):
        """Single LLM call that decides IF a live web search is needed AND
        produces the optimized search query in one round-trip.

        Returns the optimized query string, or None when no search is needed.
        """
        # Cheap heuristic first: greetings/small talk skip the LLM entirely
        stripped = user_query.strip()
        if len(stripped.split()) <= 5 and _SMALL_TALK_PATTERN.match(stripped):
            logger.info(f"[SearchPlanner] Small-talk heuristic → no search: '{stripped[:60]}'")
            return None

        planner_prompt = (
            "You are a web-search planner for an AI assistant. Decide whether the "
            "following user message requires a LIVE internet search to answer properly.\n\n"
            "Reply with EXACTLY one line:\n"
            "- If NO search is needed, reply exactly: NONE\n"
            "- If a search IS needed, reply with ONLY the optimized search engine query "
            "(concise keywords, no question marks, no punctuation, no conversational filler).\n\n"
            "Rules:\n"
            "- Greetings, casual conversation, small talk, or chitchat → NONE\n"
            "- Requests for opinions, jokes, or creative writing → NONE\n"
            "- Follow-up questions that can be answered from conversation context → NONE\n"
            "- Simple math, logic, or general knowledge that doesn't change over time → NONE\n"
            "- Questions about current events, news, real-time data, or recent facts → search query\n"
            "- Questions requiring up-to-date information (prices, weather, scores, etc.) → search query\n"
            "- Research questions, factual look-ups, or technical queries → search query\n"
            "- Questions about specific people, companies, products, or technologies → search query\n\n"
            f"User message: {user_query}\n\n"
            "Answer (NONE or the search query):"
        )
        try:
            result = self.llm_client.generate(planner_prompt, model=CHAT_MODEL)
            first_line = result.strip().splitlines()[0].strip().strip('"\'') if result and result.strip() else ""
            if not first_line or first_line.upper().rstrip(".") in ("NONE", "NO"):
                logger.info(f"[SearchPlanner] Query: '{user_query[:60]}' → no search")
                return None
            logger.info(f"[SearchPlanner] Query: '{user_query[:60]}' → search: '{first_line}'")
            return first_line
        except Exception as e:
            logger.error(f"[SearchPlanner ERROR] {e} — defaulting to NO search", exc_info=True)
            return None

    def run_with_history(self, user_query, history):
        search_results = []

        # Single planning call: decides if a search is needed and returns the
        # optimized query (previously two sequential LLM calls — BUG-03)
        optimized_query = self._plan_web_search(user_query)
        if optimized_query:
            search_results = self.web_search.search(optimized_query)

        search_context = ""
        if search_results:
            search_context = "LIVE INTERNET SEARCH RESULTS FOR CONTEXT (Use this to provide up-to-date answers):\n"
            # Take the top 3-4 snippets to keep it fast and lightweight
            for res in search_results[:4]:
                search_context += f"- [{res['title']}] {res['content']} ({res['url']})\n"
                
        augmented_query = user_query
        if search_context:
            augmented_query = (
                f"{search_context}\n\n"
                f"IMPORTANT: You MUST prioritize the live internet search results above for all factual, "
                f"real-time, or time-sensitive information. If the search results indicate a more recent event "
                f"or fact than your pre-trained knowledge, rely solely on the search results.\n\n"
                f"USER QUESTION: {user_query}"
            )
            
        prompt = build_prompt_with_history(augmented_query, history)

        response = self.llm_client.generate(prompt, model=CHAT_MODEL)

        # Return the actual search results (snippets/URLs) so the frontend can show them
        return response, search_results[:4]