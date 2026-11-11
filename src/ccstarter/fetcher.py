"""Fetch one WARC record using an HTTP Range request.

The URL index tells you, for every captured page, the file it lives in plus the
byte offset and byte length of its record. So instead of pulling an 800 MiB
WARC file for one page, you ask the server for exactly those bytes.

    Range: bytes=<offset>-<offset + length - 1>

The server answers 206 Partial Content. That is the whole trick.
"""
from __future__ import annotations

import random
import time
import urllib.error
import urllib.request
from typing import Optional

from .constants import DATA_HOST, RETRIES, TIMEOUT, USER_AGENT


class FetchError(RuntimeError):
    pass


def record_url(warc_filename: str, host: str = DATA_HOST) -> str:
    if warc_filename.startswith("http"):
        return warc_filename
    return f"{host}/{warc_filename.lstrip('/')}"


def _range_matches(content_range: str, start: int, end: int) -> bool:
    # "bytes 100-199/12345"
    try:
        span = content_range.split()[1].split("/")[0]
        got_start, got_end = (int(x) for x in span.split("-"))
    except Exception:
        return True  # unparseable header: trust the body
    return got_start == start and got_end == end


def fetch_record(
    warc_filename: str,
    offset: int,
    length: int,
    *,
    host: str = DATA_HOST,
    timeout: int = TIMEOUT,
    retries: int = RETRIES,
) -> bytes:
    """Download exactly one record's bytes. Returns raw (gzipped) bytes."""
    offset, length = int(offset), int(length)
    if offset < 0 or length <= 0:
        raise FetchError(f"bad range offset={offset} length={length}")
    end = offset + length - 1
    url = record_url(warc_filename, host)

    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Range": f"bytes={offset}-{end}",
                    "Accept-Encoding": "identity",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                if status == 206:
                    crange = resp.headers.get("Content-Range", "")
                    if crange and not _range_matches(crange, offset, end):
                        raise FetchError(f"server returned wrong range: {crange}")
                    body = resp.read()
                    if len(body) != length:
                        raise FetchError(f"short range body: got {len(body)}, expected {length}")
                    return body
                if status == 200:
                    # Do not read the body: it may be an 800 MiB WARC file.
                    raise FetchError(f"server ignored Range; refusing full-file download: {url}")
                raise FetchError(f"unexpected HTTP {status} for {url}")
        except urllib.error.HTTPError as exc:
            if exc.code == 416:
                raise FetchError(f"range not satisfiable: {offset}-{end} in {url}") from exc
            if exc.code not in (429, 500, 502, 503, 504):
                raise FetchError(f"HTTP {exc.code} for {url}") from exc
            last = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
        except Exception as exc:
            # IncompleteRead and a few urllib/socket errors can surface as
            # other concrete exception types depending on Python version.
            # Do not swallow our own validation failures.
            if isinstance(exc, FetchError):
                raise
            last = exc
        time.sleep(min(2 ** attempt + random.random(), 30))
    raise FetchError(f"fetch {url} bytes={offset}-{end} failed: {last}")

