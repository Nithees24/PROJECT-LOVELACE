from backend.utils.logger import logger
from backend.config import DOC_CONTENT_CHARS
from backend.tools.scraper import Scraper
from backend.tools.web_search import WebSearch
from backend.pipeline.ranker import Ranker
from backend.pipeline.synthesizer import Synthesizer
from backend.pipeline.aggregator import Aggregator
from backend.pipeline.query_generator import QueryGenerator
from concurrent.futures import ThreadPoolExecutor, as_completed


class DeepResearchAgent:
    """
       Orchestrates the full deep research pipeline:
       Generate Queries → Search → Scrape → Rank → Summarize → Aggregate
    """

    def __init__(self, llm_client):
        self.llm = llm_client

        # pipeline
        self.synthesizer = Synthesizer(llm_client)
        self.ranker = Ranker()
        self.aggregator = Aggregator(llm_client)
        self.query_generator = QueryGenerator(self.llm)

        # tools
        self.web_search = WebSearch()
        self.scraper = Scraper()

        # Scrape budget (BUG-19): one authoritative value each, no fallback
        # defaults elsewhere. max_total_docs caps the whole request so
        # (queries × urls) can't fan out unboundedly.
        self.max_urls_per_query = 10
        self.max_total_docs = 40
        self.max_docs_after_ranking = 40

    def run(self, user_query: str):
        """Returns (report_text, sources) where sources is a list of
        {"title", "url"} dicts matching the [n] citations in the report."""
        try:
            queries = self.query_generator.generate(user_query)

            all_docs = self._search_and_scrape(queries)

            if not all_docs:
                return "No relevant data found.", []

            ranked_docs = self._rank(all_docs)

            summaries = self._summarize(ranked_docs)

            if not summaries:
                return "Failed to generate summaries.", []

            return self._aggregate(user_query, summaries)

        except Exception as e:
            logger.error(f"[FATAL ERROR]: {e}", exc_info=True)
            return "Something went wrong during deep research.", []

    # -----------------------------
    # Individual Steps
    # -----------------------------
    def _search_and_scrape(self, queries):
        docs = []
        logger.info("[2] Web search + scraping...")

        if not queries:
            logger.warning("No queries generated")
            return docs

        # ✅ Trusted high-quality domains
        trusted_domains = [
            "arxiv.org",
            "nature.com",
            "sciencedirect.com",
            "nasa.gov",
            "mit.edu",
            "stanford.edu",
            "ibm.com",
            "aws.amazon.com",
            "phys.org",
            "wikipedia.org"
        ]

        # ❌ Weak / noisy domains
        blocked_domains = [
            "medium.com",
            "quora.com",
            "reddit.com",
            "blogspot.com",
            "wordpress.com"
        ]

        # ✅ Deduplication tracker
        seen_contents = set()

        # 🔧 Helper for parallel scraping
        def scrape_single(url):
            try:
                doc = self.scraper.scrape(url)

                if not doc or not isinstance(doc, dict):
                    return None

                content = doc.get("content", "").strip()

                if not content or len(content) < 300:
                    return None

                return {
                    "title": doc.get("title", "Web Document"),
                    "content": content[:DOC_CONTENT_CHARS],
                    "source": "web",
                    "url": url
                }

            except Exception as e:
                logger.error(f"[Scraper ERROR] {url}: {e}")
                return None

        for q in queries:
            # Global cap on collected documents per research request (BUG-19)
            if len(docs) >= self.max_total_docs:
                logger.info(f"[SEARCH] Reached max_total_docs={self.max_total_docs}, stopping early")
                break

            logger.info(f"[SEARCH] Query: {q}")

            # --- Web Search ---
            try:
                results = self.web_search.search(q)
            except Exception as e:
                logger.error(f"[Search ERROR] '{q}': {e}")
                continue

            if not results:
                logger.info(f"No results for query: {q}")
                continue

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
                if any(domain in url for domain in blocked_domains):
                    continue

                # ✅ Allow other domains (ranking handles prioritizing trusted domains later)
                # if not any(domain in url for domain in trusted_domains):
                #     continue

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
                futures = [executor.submit(scrape_single, url) for url in urls_to_scrape]

                for future in as_completed(futures):
                    result = future.result()

                    if not result:
                        continue

                    key = result["content"][:200]
                    if key in seen_contents:
                        continue

                    seen_contents.add(key)
                    docs.append(result)

        logger.info(f"[DONE] Collected {len(docs)} documents")
        return docs

    def _rank(self, documents):
        logger.info("[4] Ranking...")
        return self.ranker.rank(documents, limit=self.max_docs_after_ranking)

    def _summarize(self, documents):
        summaries = []
        logger.info("[5] Summarizing...")

        for doc in documents:
            try:
                summary = self.synthesizer.summarize(doc)
                if summary:
                    summaries.append({
                        "summary": summary,
                        "title": doc.get("title", "Web Document"),
                        "url": doc.get("url", "Unknown")
                    })
            except Exception as e:
                logger.error(f"Summarization failed: {e}", exc_info=True)

        return summaries

    def _aggregate(self, query, summaries):
        try:
            logger.info("[6] Aggregating final report...")
            return self.aggregator.aggregate(query, summaries)
        except Exception as e:
            logger.error(f"Aggregation error: {e}", exc_info=True)
            return "Failed to generate final report.", []
            