import time
import uuid

from backend.utils.logger import logger
from backend.config import DOC_CONTENT_CHARS
from backend.tools.scraper import Scraper
from backend.tools.web_search import WebSearch
from backend.pipeline.ranker import Ranker
from backend.pipeline.synthesizer import Synthesizer
from backend.pipeline.aggregator import Aggregator
from backend.pipeline.query_generator import QueryGenerator
from backend.pipeline.gap_analyzer import GapAnalyzer
from backend.pipeline.research_planner import ResearchPlanner
from backend.agents.research.events import EventEmitter, NullEmitter
from concurrent.futures import ThreadPoolExecutor, as_completed


class DeepResearchAgent:
    """
       Orchestrates an *iterative* deep research pipeline:

         generate queries
           └─▶ [ROUND] search → scrape → rank → summarize
                 └─▶ gap analysis → follow-up queries ─┐
                       (repeat while gaps remain and budget allows)
           ─▶ aggregate all findings into one cited report

       Iteration re-allocates a FIXED global document budget across rounds
       (rather than multiplying work): the total number of scraped/summarized
       docs stays capped at max_total_docs no matter how many rounds run, so
       the only added cost per round is one gap-analysis LLM call.
    """

    def __init__(self, llm_client):
        self.llm = llm_client

        # pipeline
        self.synthesizer = Synthesizer(llm_client)
        self.ranker = Ranker()
        self.aggregator = Aggregator(llm_client)
        self.query_generator = QueryGenerator(self.llm)
        self.gap_analyzer = GapAnalyzer(self.llm)
        self.research_planner = ResearchPlanner(self.llm)

        # tools
        self.web_search = WebSearch()
        self.scraper = Scraper()

        # Scrape budget (BUG-19): one authoritative value each. max_total_docs
        # is the GLOBAL cap across all iterative rounds so (rounds × queries ×
        # urls) can't fan out unboundedly; max_docs_per_round bounds a single
        # round so early rounds leave budget for gap-driven follow-up rounds.
        self.max_urls_per_query = 10
        self.max_total_docs = 40
        self.max_docs_per_round = 15
        self.max_docs_after_ranking = 40

        # How many gap-filling iterations to run (round 1 + follow-ups).
        self.max_rounds = 3

    def run(self, user_query: str):
        """Non-streaming entry point. Returns (report_text, sources). Delegates
        to run_streaming with a NullEmitter so there is a single code path."""
        return self.run_streaming(user_query, NullEmitter())

    def run_streaming(self, user_query: str, emitter, plan=None, run_id=None):
        """Execute the research pipeline while emitting progress events to
        `emitter` (plan → activities → sources → report). Returns the same
        (report_text, sources) tuple as run(). Always closes the emitter.

        If `plan` is provided (e.g. a user-approved/edited plan) its sections'
        queries seed the search; otherwise a plan is generated first.
        """
        run_id = run_id or uuid.uuid4().hex
        started = time.time()
        try:
            emitter.run_started(run_id, user_query)

            # 1) Plan — generate one unless the caller supplied an approved plan.
            if plan is None:
                emitter.activity("planning", "Planning research approach", "started")
                plan = self.research_planner.generate_plan(user_query)
                emitter.activity(
                    "planning", "Planning research approach", "ok",
                    detail=f"{len(plan.get('sections', []))} sections",
                )
            emitter.plan(plan)

            # Seed the first round from the plan's section queries.
            seed = []
            for section in plan.get("sections", []):
                seed.extend(section.get("queries", []))
            pending = list(dict.fromkeys(seed)) or [user_query]

            # Shared across rounds so follow-up rounds never re-scrape a URL or
            # re-collect duplicate content already gathered earlier.
            seen_urls = set()
            seen_contents = set()
            all_docs = []
            all_summaries = []
            asked_queries = []
            rounds_run = 0

            for round_num in range(1, self.max_rounds + 1):
                budget_left = self.max_total_docs - len(all_docs)
                if not pending or budget_left <= 0:
                    break
                rounds_run = round_num

                asked_queries.extend(pending)
                round_budget = min(self.max_docs_per_round, budget_left)
                logger.info(
                    f"[ROUND {round_num}] {len(pending)} queries, "
                    f"budget {round_budget} (used {len(all_docs)}/{self.max_total_docs})"
                )

                docs = self._search_and_scrape(
                    pending, seen_urls, seen_contents, round_budget, emitter
                )
                if docs:
                    all_docs.extend(docs)
                    ranked = self._rank(docs)
                    all_summaries.extend(self._summarize_streaming(ranked, emitter))

                # Decide follow-up queries for the next round from everything
                # gathered so far — unless this was the last allowed round or
                # the budget is exhausted.
                if round_num >= self.max_rounds or len(all_docs) >= self.max_total_docs:
                    break
                if not all_summaries:
                    break  # nothing to reason about; stop instead of looping dry

                emitter.activity("reflect", "Analyzing gaps in the findings", "started")
                pending = self.gap_analyzer.find_gaps(
                    user_query, all_summaries, asked_queries
                )
                emitter.activity(
                    "reflect", "Analyzing gaps in the findings", "ok",
                    detail=(f"{len(pending)} follow-up queries"
                            if pending else "coverage sufficient"),
                )
                logger.info(
                    f"[ROUND {round_num}] gap analysis → "
                    f"{len(pending)} follow-up queries" if pending
                    else f"[ROUND {round_num}] gap analysis → coverage sufficient, stopping"
                )

            if not all_summaries:
                emitter.report("No relevant data found.", [])
                emitter.run_finished({"sources": 0, "rounds": rounds_run,
                                      "elapsed_s": round(time.time() - started, 1)})
                return "No relevant data found.", []

            emitter.activity("write", "Synthesizing the final report", "started")
            report, sources = self._aggregate(user_query, all_summaries)
            emitter.activity("write", "Synthesizing the final report", "ok")

            emitter.report(report, sources)
            emitter.run_finished({"sources": len(sources), "rounds": rounds_run,
                                  "elapsed_s": round(time.time() - started, 1)})
            return report, sources

        except Exception as e:
            logger.error(f"[FATAL ERROR]: {e}", exc_info=True)
            emitter.error("Something went wrong during deep research.")
            emitter.report("Something went wrong during deep research.", [])
            return "Something went wrong during deep research.", []
        finally:
            emitter.close()

    def gather(self, queries, budget, emitter=None):
        """Single-pass search → scrape → rank → summarize. Returns
        (summaries, sources).

        The public surface over the collection pipeline, for callers that want
        source material without the iterative gap-driven rounds `run_streaming`
        performs — currently DocumentAgent, whose iteration is the user
        interview rather than follow-up searches. Keeping this here (instead of
        letting another agent reach for the underscore methods, or copy them)
        means the scrape budget, URL/content de-duplication and blocked-domain
        rules stay defined exactly once.
        """
        # _summarize_streaming emits unconditionally, so a caller that wants no
        # events gets the null sink rather than an AttributeError.
        emitter = emitter or NullEmitter()
        seen_urls, seen_contents = set(), set()
        docs = self._search_and_scrape(queries, seen_urls, seen_contents, budget, emitter)
        if not docs:
            return [], []
        summaries = self._summarize_streaming(self._rank(docs), emitter)
        sources = [
            {"title": s.get("title", "Source"), "url": s.get("url")}
            for s in summaries if s.get("url")
        ]
        return summaries, sources

    # -----------------------------
    # Individual Steps
    # -----------------------------
    # ❌ Weak / noisy domains (skipped at collection time)
    BLOCKED_DOMAINS = [
        "medium.com",
        "quora.com",
        "reddit.com",
        "blogspot.com",
        "wordpress.com",
    ]

    def _search_and_scrape(self, queries, seen_urls, seen_contents, budget, emitter=None):
        """Collect up to `budget` new documents for `queries`.

        `seen_urls` / `seen_contents` are shared across iterative rounds so a
        follow-up round never re-scrapes a URL or re-collects content already
        gathered. Stops as soon as `budget` new docs are collected. If `emitter`
        is given, search/fetch progress is streamed to it.
        """
        docs = []
        logger.info("[2] Web search + scraping...")

        if not queries or budget <= 0:
            return docs

        # 🔧 Helper for parallel scraping (emits per-URL fetch activity)
        def scrape_single(url):
            try:
                if emitter:
                    emitter.activity("fetch", f"Reading page: {url}", "started")
                doc = self.scraper.scrape(url)

                if not doc or not isinstance(doc, dict):
                    if emitter:
                        emitter.activity("fetch", f"No content: {url}", "failed")
                    return None

                content = doc.get("content", "").strip()

                if not content or len(content) < 300:
                    if emitter:
                        emitter.activity("fetch", f"Too little content: {url}", "failed")
                    return None

                if emitter:
                    emitter.activity("fetch", f"Read page: {url}", "ok",
                                     detail=f"{len(content)} chars")
                return {
                    "title": doc.get("title", "Web Document"),
                    "content": content[:DOC_CONTENT_CHARS],
                    "source": "web",
                    "url": url
                }

            except Exception as e:
                logger.error(f"[Scraper ERROR] {url}: {e}")
                if emitter:
                    emitter.activity("fetch", f"Failed: {url}", "failed", detail=str(e)[:150])
                return None

        for q in queries:
            # Per-round budget: stop once we've collected enough new docs.
            if len(docs) >= budget:
                logger.info(f"[SEARCH] Reached round budget={budget}, stopping early")
                break

            logger.info(f"[SEARCH] Query: {q}")
            if emitter:
                emitter.activity("search", f"Searching the web: {q}", "started")

            # --- Web Search ---
            try:
                results = self.web_search.search(q)
            except Exception as e:
                logger.error(f"[Search ERROR] '{q}': {e}")
                if emitter:
                    emitter.activity("search", f"Search failed: {q}", "failed", detail=str(e)[:150])
                continue

            if not results:
                logger.info(f"No results for query: {q}")
                if emitter:
                    emitter.activity("search", f"No results: {q}", "ok", detail="0 results")
                continue

            if emitter:
                emitter.activity("search", f"Searched: {q}", "ok", detail=f"{len(results)} results")

            max_urls = self.max_urls_per_query

            urls_to_scrape = []

            for r in results[:max_urls]:
                if not isinstance(r, dict):
                    continue

                url = r.get("url") or r.get("link")
                if not url:
                    continue

                # ❌ Skip non-text sources
                if "youtube.com" in url:
                    continue

                # ❌ Block weak domains
                if any(domain in url for domain in self.BLOCKED_DOMAINS):
                    continue

                # ❌ Skip URLs already collected in an earlier round/query
                if url in seen_urls:
                    continue

                # ✅ Try using search snippet first
                content = r.get("content")

                if content:
                    content = content.strip()

                    if len(content) < 300:
                        continue

                    key = content[:200]
                    if key in seen_contents:
                        continue

                    seen_contents.add(key)
                    seen_urls.add(url)

                    docs.append({
                        "title": r.get("title", "Web Document"),
                        "content": content[:DOC_CONTENT_CHARS],
                        "source": "web",
                        "url": url
                    })
                else:
                    urls_to_scrape.append(url)

            # 🚀 Parallel scraping
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_url = {
                    executor.submit(scrape_single, url): url for url in urls_to_scrape
                }

                for future in as_completed(future_to_url):
                    result = future.result()

                    if not result:
                        continue

                    key = result["content"][:200]
                    if key in seen_contents:
                        continue

                    seen_contents.add(key)
                    seen_urls.add(result["url"])
                    docs.append(result)

        logger.info(f"[DONE] Collected {len(docs)} documents this round")
        return docs

    def _rank(self, documents):
        logger.info("[4] Ranking...")
        return self.ranker.rank(documents, limit=self.max_docs_after_ranking)

    def _summarize_streaming(self, documents, emitter):
        """Summarize each document, emitting a read activity + a source event per
        doc so the frontend can show what's being read and cite it live."""
        summaries = []
        logger.info("[5] Summarizing...")

        for doc in documents:
            title = doc.get("title") or "Web Document"
            url = doc.get("url", "Unknown")
            label = title if title != url else url
            try:
                emitter.activity("read", f"Reading & summarizing: {label}", "started", detail=url)
                summary = self.synthesizer.summarize(doc)
                if summary:
                    summaries.append({
                        "summary": summary,
                        "title": title,
                        "url": url,
                    })
                    emitter.source({
                        "title": title,
                        "url": url,
                        "type": doc.get("source", "web"),
                    })
                    emitter.activity("read", f"Summarized: {label}", "ok", detail=url)
                else:
                    emitter.activity("read", f"No summary: {label}", "failed", detail=url)
            except Exception as e:
                logger.error(f"Summarization failed: {e}", exc_info=True)
                emitter.activity("read", f"Failed: {label}", "failed", detail=str(e)[:150])

        return summaries

    def _aggregate(self, query, summaries):
        try:
            logger.info("[6] Aggregating final report...")
            return self.aggregator.aggregate(query, summaries)
        except Exception as e:
            logger.error(f"Aggregation error: {e}", exc_info=True)
            return "Failed to generate final report.", []
            