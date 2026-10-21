"""Minimal HTTP client with retries and exponential backoff (stdlib only)."""
import time
import urllib.error
import urllib.request

USER_AGENT = "Mozilla/5.0 (compatible; BRIEF-by-ProMedia/0.2; +https://brief.promedia.report/)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    def __init__(self, url, message, status=None):
        super().__init__(f"{url}: {message}")
        self.url = url
        self.status = status


def fetch(url, data=None, timeout=25, retries=3, backoff=2.0, max_bytes=5_000_000, sleep=time.sleep, opener=None,
          headers=None):
    """GET (or POST when data is given). Retries only transient failures.

    4xx responses other than 429 are not retried: they mean access is denied or the
    resource is missing, and we never try to work around access restrictions.
    """
    open_ = opener or urllib.request.urlopen
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
            with open_(req, timeout=timeout) as r:
                return r.read(max_bytes)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read(300).decode("utf-8", "replace")
            except Exception:
                pass
            last = FetchError(url, f"HTTP {e.code} {detail}".strip(), e.code)
            if e.code not in RETRY_STATUS:
                raise last from e
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = FetchError(url, str(getattr(e, "reason", e)))
        if attempt < retries:
            sleep(backoff * (2 ** attempt))
    raise last
