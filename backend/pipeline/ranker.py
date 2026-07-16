from backend.utils.logger import logger


class Ranker:
    """Scores and orders scraped documents by source quality.

    Heuristic: domain reputation + content length. Moved here from
    DeepResearchAgent._rank so the class actually does the job its name
    implies (BUG-09).
    """

    DOMAIN_SCORES = {
        "arxiv.org": 10,
        "nature.com": 10,
        "sciencedirect.com": 9,
        "nasa.gov": 9,
        "mit.edu": 9,
        "stanford.edu": 9,
        "ibm.com": 8,
        "aws.amazon.com": 8,
        "phys.org": 7,
        "wikipedia.org": 6,
    }

    def rank(self, documents, limit=None):
        """Returns documents sorted by score (best first), truncated to limit."""
        try:
            ranked = sorted(documents, key=self._score, reverse=True)
        except Exception as e:
            logger.error(f"[Ranking ERROR]: {e}", exc_info=True)
            ranked = documents
        return ranked[:limit] if limit else ranked

    def _score(self, doc):
        url = doc.get("url", "")
        content = doc.get("content", "")

        domain_score = 0
        for domain, value in self.DOMAIN_SCORES.items():
            if domain in url:
                domain_score = value
                break

        length_score = min(len(content) / 1000, 5)

        return domain_score + length_score
