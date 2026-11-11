"""Find things: the latest crawl, its index shards, its WARC files.

The important idea in this module: you cannot *list* a prefix of the
Common Crawl bucket anonymously, but Common Crawl publishes a manifest for
every crawl that lists the files for you. That manifest is a few KB and it is
the only sane way to find the Parquet shards you want.
"""
from __future__ import annotations

import gzip
import json
import random
import time
import urllib.request
from typing import List, Sequence

from .constants import DATA_HOST, RETRIES, TIMEOUT, USER_AGENT

COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"


class DiscoveryError(RuntimeError):
    pass


def http_get(url: str, timeout: int = TIMEOUT, retries: int = RETRIES) -> bytes:
    """GET with exponential backoff and jitter. Follows redirects."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # URLError, HTTPError, timeouts, resets
            last = exc
            time.sleep(min(2 ** attempt + random.random(), 30))
    raise DiscoveryError(f"GET {url} failed after {retries} attempts: {last}")


def http_head_length(url: str, timeout: int = TIMEOUT) -> int | None:
    """Size of a remote object via HEAD, or None if the server will not say.

    Used to answer the only question that matters to a beginner:
    "how much data did I *not* download?"
    """
    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.headers.get("Content-Length")
            return int(raw) if raw else None
    except Exception:
        return None


def latest_crawl() -> str:
    """Newest crawl id, straight from Common Crawl (never hardcode one)."""
    data = json.loads(http_get(COLLINFO_URL).decode("utf-8"))
    return data[0]["id"]


def index_manifest_url(crawl: str) -> str:
    return f"{DATA_HOST}/crawl-data/{crawl}/cc-index-table.paths.gz"


def warc_manifest_url(crawl: str) -> str:
    return f"{DATA_HOST}/crawl-data/{crawl}/warc.paths.gz"


def _manifest(paths_url: str) -> List[str]:
    raw = http_get(paths_url)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return [line.strip() for line in raw.decode("utf-8").splitlines() if line.strip()]


def sample_even(items: Sequence, n: int | None) -> List:
    """Take n items spread across the list, not the first n.

    The first 8 shards of a crawl are not a random sample of the web; they are
    one corner of it. Even spacing is still a sample, but a much less biased
    one. Say so in your write-up -- that honesty is half the grade.
    """
    items = list(items)
    if not n or n >= len(items):
        return items
    step = len(items) / float(n)
    return [items[int(i * step)] for i in range(n)]


def shards(
    crawl: str,
    subset: str = "warc",
    max_files: int | None = 8,
) -> List[str]:
    """Return HTTPS URLs of URL-index Parquet shards for one crawl.

    Each shard holds millions of rows: one row per captured URL. Eight shards
    is enough for a classroom question and does not melt a laptop.
    """
    paths = _manifest(index_manifest_url(crawl))
    marker = f"subset={subset}/"
    subset_paths = [p for p in paths if marker in p]
    if not subset_paths:                      # older crawls may differ
        subset_paths = paths
    return [f"{DATA_HOST}/{p.lstrip('/')}" for p in sample_even(subset_paths, max_files)]


def warc_files(crawl: str, max_files: int | None = 3) -> List[str]:
    """Return HTTPS URLs of .warc.gz files (only needed for full-file work)."""
    paths = _manifest(warc_manifest_url(crawl))
    return [f"{DATA_HOST}/{p.lstrip('/')}" for p in sample_even(paths, max_files)]
