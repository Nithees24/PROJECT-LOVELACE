import re

from backend.utils.logger import logger
from backend.utils.prompt_builder import build_prompt_with_history, UNTRUSTED_RULES, wrap_untrusted
from backend.config import (
    ARTIFACT_MAX_TOKENS,
    ARTIFACT_MODEL,
    ARTIFACT_NUM_CTX,
    CHAT_MODEL,
    CHAT_NUM_CTX,
)
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

        # The rules are ORDERED and first-match-wins on purpose. An unordered
        # list let "what is rubisco?" satisfy both "general knowledge that
        # doesn't change over time → NONE" and "technical query → search", and
        # the model picked between them at random from one turn to the next.
        # Rule 6 now states outright that being a stable fact is not grounds to
        # skip the search, and the examples pin the rule-5/rule-6 boundary.
        planner_prompt = (
            "You are a web-search planner for an AI assistant. Decide whether the "
            "following user message requires a LIVE internet search to answer properly.\n\n"
            "Reply with EXACTLY one line:\n"
            "- If NO search is needed, reply exactly: NONE\n"
            "- If a search IS needed, reply with ONLY the optimized search engine query "
            "(concise keywords, no question marks, no punctuation, no conversational filler).\n\n"
            "Apply these rules IN ORDER. The FIRST rule that matches decides:\n"
            "1. Greeting, small talk, thanks, or chitchat → NONE\n"
            "2. Opinion, joke, roleplay, or creative writing → NONE\n"
            "3. Rewriting, translating, summarising, or reasoning about text the "
            "user already gave you → NONE\n"
            "4. A follow-up fully answerable from the conversation so far → NONE\n"
            "5. Arithmetic, or a fact virtually everyone already knows (capital "
            "cities, days in a week, who wrote Hamlet) → NONE\n"
            "6. ANY other request for facts → search query. This includes asking "
            "what a named term, organism, chemical, technology, company, person, "
            "disease, law, or concept IS, or HOW it works — even when the answer "
            "is stable and never changes. Being a stable fact is NOT a reason to "
            "skip the search; only rule 5's everyday common knowledge is.\n\n"
            "If rule 5 and rule 6 both seem to fit, choose rule 6 and search.\n\n"
            "Examples:\n"
            "- hey there → NONE\n"
            "- write me a poem about rain → NONE\n"
            "- what is 15% of 240 → NONE\n"
            "- what is the capital of France → NONE\n"
            "- what is rubisco → rubisco enzyme function\n"
            "- what is photosynthesis → photosynthesis process explained\n"
            "- how does CRISPR work → CRISPR gene editing mechanism\n"
            "- explain quantum entanglement → quantum entanglement explained\n"
            "- who is the CEO of OpenAI → OpenAI CEO\n"
            "- latest iPhone price → iPhone latest model price\n\n"
            f"User message: {user_query}\n\n"
            "Answer (NONE or the search query):"
        )
        try:
            # temperature=0: this is a routing decision, so the same question
            # must not search on one turn and answer from memory on the next.
            # max_tokens bounds a model that starts explaining itself instead of
            # emitting the one line asked for.
            result = self.llm_client.generate(planner_prompt, model=CHAT_MODEL,
                                              temperature=0, max_tokens=64)
            first_line = result.strip().splitlines()[0].strip().strip('"\'') if result and result.strip() else ""
            if not first_line or first_line.upper().rstrip(".") in ("NONE", "NO"):
                logger.info(f"[SearchPlanner] Query: '{user_query[:60]}' → no search")
                return None
            logger.info(f"[SearchPlanner] Query: '{user_query[:60]}' → search: '{first_line}'")
            return first_line
        except Exception as e:
            logger.error(f"[SearchPlanner ERROR] {e} — defaulting to NO search", exc_info=True)
            return None

    def run_with_history(self, user_query, history, force_artifact=False):
        search_results = []

        # "Build me X" is a generation task, not a look-up, so artifact mode
        # skips the search-planner round-trip entirely — it would almost always
        # return NONE, and the sandboxed artifact can't fetch live data anyway.
        # (Drop this guard if artifacts should be able to bake in fresh facts.)
        if not force_artifact:
            # Single planning call: decides if a search is needed and returns the
            # optimized query (previously two sequential LLM calls — BUG-03)
            optimized_query = self._plan_web_search(user_query)
            if optimized_query:
                search_results = self.web_search.search(optimized_query)

        search_context = ""
        if search_results:
            # Take the top 3-4 snippets to keep it fast and lightweight.
            # Snippets are third-party web content — wrapped as untrusted
            # data so embedded instructions aren't followed (SEC-11).
            snippets = ""
            for res in search_results[:4]:
                snippets += f"- [{res['title']}] {res['content']} ({res['url']})\n"
            search_context = (
                "LIVE INTERNET SEARCH RESULTS FOR CONTEXT (Use this to provide up-to-date answers):\n"
                f"{wrap_untrusted(snippets)}"
            )

        augmented_query = user_query
        if search_context:
            augmented_query = (
                f"{UNTRUSTED_RULES}\n\n"
                f"{search_context}\n\n"
                f"IMPORTANT: You MUST prioritize the live internet search results above for all factual, "
                f"real-time, or time-sensitive information. If the search results indicate a more recent event "
                f"or fact than your pre-trained knowledge, rely solely on the search results.\n\n"
                f"USER QUESTION: {user_query}"
            )
            
        prompt = build_prompt_with_history(augmented_query, history,
                                           force_artifact=force_artifact)

        # An explicitly requested artifact is a code-generation task, so it gets
        # the stronger model and an output ceiling wide enough that a complete
        # page can't be cut off mid-tag. Ordinary chat keeps the fast model:
        # most turns are prose, and paying research-model latency for "hi" would
        # be a poor trade. A spontaneous artifact inside a normal chat turn
        # still works — the extractor recovers a truncated block.
        if force_artifact:
            response = self.llm_client.generate(
                prompt, model=ARTIFACT_MODEL,
                num_ctx=ARTIFACT_NUM_CTX, max_tokens=ARTIFACT_MAX_TOKENS,
            )
        else:
            response = self.llm_client.generate(prompt, model=CHAT_MODEL,
                                                num_ctx=CHAT_NUM_CTX)

        # Return the actual search results (snippets/URLs) so the frontend can show them
        return response, search_results[:4]