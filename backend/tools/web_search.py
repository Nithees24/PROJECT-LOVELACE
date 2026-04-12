from ddgs import DDGS


class WebSearch:
    def __init__(self):
        self.ddgs = DDGS()

    def search(self, query):
        print(f"[WebSearch] Searching for: {query}")

        try:
            results = self.ddgs.text(
                query,
                max_results=10
            )

            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "content": r.get("body", "")
                }
                for r in results
            ]

        except Exception as e:
            print(f"[WebSearch ERROR]: {e}")
            return []