from backend.tools.scraper import Scraper
from backend.tools.paper_fetch import PaperFetch
from backend.tools.pdf_parser import PDFParser
from backend.tools.web_search import WebSearch
from backend.pipeline.ranker import Ranker
from backend.pipeline.synthesizer import Synthesizer
from backend.pipeline.aggregator import Aggregator
from backend.pipeline.planner import Planner
from backend.pipeline.query_generator import QueryGenerator
from concurrent.futures import ThreadPoolExecutor, as_completed


class DeepResearchAgent:
    """
       Orchestrates the full deep research pipeline:
       Plan → Search → Scrape → Fetch Papers → Parse PDFs → Rank → Summarize → Aggregate
    """

    def __init__(self, llm_client):
        self.llm = llm_client

        # pipeline
        self.planner = Planner(llm_client)
        self.synthesizer = Synthesizer(llm_client)
        self.ranker = Ranker()
        self.aggregator = Aggregator(llm_client)
        self.query_generator = QueryGenerator(self.llm)

        # tools
        self.paper_fetch = PaperFetch()
        self.web_search = WebSearch()
        self.scraper = Scraper()
        self.pdf_parser = PDFParser()

        self.max_urls_per_query = 10
        self.max_docs_after_ranking = 40

    def run(self, user_query: str) -> str:
        try:
            queries = self.query_generator.generate(user_query)

            web_docs = self._search_and_scrape(queries)
            # paper_docs = self._fetch_and_parse_papers(user_query)  # disabled for now
            paper_docs = []

            all_docs = web_docs + paper_docs

            if not all_docs:
                return "No relevant data found."

            ranked_docs = self._rank(all_docs)

            summaries = self._summarize(ranked_docs)

            if not summaries:
                return "Failed to generate summaries."

            return self._aggregate(user_query, summaries)

        except Exception as e:
            print(f"[FATAL ERROR]: {e}")
            return "Something went wrong during deep research."

    # -----------------------------
    # Individual Steps
    # -----------------------------
    def _scrape_single(self, url):
        try:
            doc = self.scraper.scrape(url)

            if not doc or not isinstance(doc, dict):
                return None

            content = doc.get("content")
            if not content or len(content) < 300:
                return None

            return {
                "title": doc.get("title", "Web Document"),
                "content": content[:5000],
                "source": "web",
                "url": url
            }

        except Exception as e:
            print(f"[Scraper ERROR] {url}: {e}")
            return None

    def _plan(self, query):
        try:
            print("[1] Planning...")
            plan = self.planner.plan(query)
            return plan.get("steps", [])
        except Exception as e:
            print(f"Planner error: {e}")
            return []

    def _search_and_scrape(self, queries):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        docs = []
        print("[2] Web search + scraping...")

        if not queries:
            print("[WARNING] No queries generated")
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
                    "content": content[:5000],
                    "source": "web",
                    "url": url
                }

            except Exception as e:
                print(f"[Scraper ERROR] {url}: {e}")
                return None

        for q in queries:
            print(f"[SEARCH] Query: {q}")

            # --- Web Search ---
            try:
                results = self.web_search.search(q)
            except Exception as e:
                print(f"[Search ERROR] '{q}': {e}")
                continue

            if not results:
                print(f"[INFO] No results for query: {q}")
                continue

            max_urls = getattr(self, "max_urls_per_query", 3)

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
                        "content": content[:5000],
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

        print(f"[DONE] Collected {len(docs)} documents")
        return docs

    def _fetch_and_parse_papers(self, query):
        docs = []
        print("[3] Paper fetch + parsing...")

        try:
            papers = self.paper_fetch.fetch(query)
        except Exception as e:
            print(f"Paper fetch failed: {e}")
            return docs

        for paper in papers:
            pdf_url = paper.get("pdf_url")
            if not pdf_url:
                continue

            try:
                text = self.pdf_parser.parse(pdf_url)
                if text:
                    docs.append({
                        "title": paper.get("title", "Research Paper"),
                        "content": text,
                        "source": "paper"
                    })
            except Exception as e:
                print(f"PDF parsing failed for {pdf_url}: {e}")

        return docs

    def _rank(self, documents):
        print("[4] Ranking...")

        try:
            # 🔥 Domain priority (higher = better)
            domain_scores = {
                "arxiv.org": 10,
                "nature.com": 10,
                "sciencedirect.com": 9,
                "nasa.gov": 9,
                "mit.edu": 9,
                "stanford.edu": 9,
                "ibm.com": 8,
                "aws.amazon.com": 8,
                "phys.org": 7,
                "wikipedia.org": 6
            }

            def score(doc):
                url = doc.get("url", "")
                content = doc.get("content", "")

                # 🔹 Domain score
                domain_score = 0
                for domain, value in domain_scores.items():
                    if domain in url:
                        domain_score = value
                        break

                # 🔹 Content length score
                length_score = min(len(content) / 1000, 5)

                # 🔹 Source type bonus
                source_bonus = 2 if doc.get("source") == "paper" else 0

                return domain_score + length_score + source_bonus

            # 🔥 Sort documents by score (descending)
            ranked = sorted(documents, key=score, reverse=True)

            limit = getattr(self, "max_docs_after_ranking", 5)
            return ranked[:limit]

        except Exception as e:
            print(f"[Ranking ERROR]: {e}")
            return documents[: getattr(self, "max_docs_after_ranking", 5)]

    def _summarize(self, documents):
        summaries = []
        print("[5] Summarizing...")

        for doc in documents:
            try:
                summary = self.synthesizer.summarize(doc)
                if summary:
                    summaries.append({
                        "summary": summary,
                        "url": doc.get("url", "Unknown")
                    })
            except Exception as e:
                print(f"Summarization failed: {e}")

        return summaries

    def _aggregate(self, query, summaries):
        try:
            print("[6] Aggregating final report...")
            return self.aggregator.aggregate(query, summaries)
        except Exception as e:
            print(f"Aggregation error: {e}")
            return "Failed to generate final report."
            