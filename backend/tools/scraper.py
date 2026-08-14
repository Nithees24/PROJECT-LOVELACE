import ipaddress
import socket
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

# SSRF guard limits (SEC-10). Redirects are followed manually so every hop
# is re-validated; the byte cap stops a hostile page from ballooning memory
# (only 5000 chars are kept anyway).
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _check_public_http_url(url):
    """Validate that a URL is http(s) and its host resolves only to public
    addresses (SEC-10). Returns (ok, reason). Rejecting on resolution rather
    than on the hostname string blocks localhost/127.x, RFC-1918, link-local
    (incl. 169.254.169.254 cloud metadata) and DNS names pointing at them.
    Note: validation happens just before connecting, so a DNS-rebinding TOCTOU
    window remains; scraped URLs come from search results, not raw user input,
    which bounds that residual risk.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"scheme '{parsed.scheme or '(none)'}' not allowed"
    if not parsed.hostname:
        return False, "URL has no hostname"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        return False, f"DNS resolution failed: {e}"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            return False, f"host resolves to non-public address {ip}"
    return True, ""


class Scraper:
    def __init__(self):
        pass

    def scrape(self, url):
        print(f"[Scraper] Scraping: {url}")

        try:
            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            # Follow redirects manually so each hop is re-validated — a
            # public site must not be able to bounce us to an internal
            # address (SEC-10).
            current_url = url
            response = None
            for _ in range(MAX_REDIRECTS + 1):
                ok, reason = _check_public_http_url(current_url)
                if not ok:
                    print(f"[Scraper BLOCKED] {current_url}: {reason}")
                    return None

                response = requests.get(
                    current_url,
                    headers=headers,
                    timeout=10,
                    allow_redirects=False,
                    stream=True,
                )
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    response.close()
                    if not location:
                        return None
                    current_url = urljoin(current_url, location)
                    continue
                break
            else:
                print(f"[Scraper ERROR] Too many redirects for {url}")
                return None

            if response.status_code != 200:
                print(f"[Scraper ERROR] Status code: {response.status_code}")
                response.close()
                return None

            # Size-capped read: never buffer an unbounded body.
            body = b""
            for chunk in response.iter_content(chunk_size=65536):
                body += chunk
                if len(body) >= MAX_RESPONSE_BYTES:
                    break
            response.close()
            html = body.decode(response.encoding or "utf-8", errors="replace")

            soup = BeautifulSoup(html, "html.parser")

            # Extract paragraphs
            paragraphs = soup.find_all("p")
            text = " ".join(p.get_text() for p in paragraphs)

            if not text.strip():
                return None

            return {
                "title": url,
                "content": text[:5000]  # limit size
            }

        except Exception as e:
            print(f"[Scraper ERROR]: {e}")
            return None
