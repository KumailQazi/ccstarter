"""Build a fake Common Crawl file in memory, so tests need no network.

A real .warc.gz is a concatenation of independent gzip members. We reproduce
that property exactly, because every offset trick in this repo depends on it.
"""
from __future__ import annotations

import gzip
from typing import List, Tuple


def gzip_member(payload: bytes, mtime: int = 0) -> bytes:
    import io
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=mtime) as fh:
        fh.write(payload)
    return buf.getvalue()


def http_record(
    url: str,
    html: str,
    *,
    status: int = 200,
    content_type: str = "text/html; charset=UTF-8",
    extra_http_headers: str = "",
) -> bytes:
    body = html.encode("utf-8")
    head = (
        f"HTTP/1.1 {status} OK\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"{extra_http_headers}"
        "\r\n"
    ).encode("utf-8")
    payload = head + body
    warc_headers = (
        "WARC/1.0\r\n"
        "WARC-Type: response\r\n"
        f"WARC-Target-URI: {url}\r\n"
        "WARC-Date: 2026-10-12T00:00:00Z\r\n"
        "WARC-Record-ID: <urn:uuid:019f4e23-0ae1-7128-99c9-625a3048e3b1>\r\n"
        "Content-Type: application/http; msgtype=response\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "\r\n"
    ).encode("utf-8")
    return warc_headers + payload


def build_warc_file(records: List[bytes]) -> Tuple[bytes, List[Tuple[int, int]]]:
    """Concatenate gzip members; return the bytes and each record's (offset, length)."""
    out = b""
    spans: List[Tuple[int, int]] = []
    for rec in records:
        member = gzip_member(rec)
        spans.append((len(out), len(member)))
        out += member
    return out, spans


SAMPLE_HTML = """
<!doctype html><html><head><title>Karachi Ports</title>
<script>var tracking = "do not include me";</script>
<style>.x{color:red}</style></head>
<body><h1>Karachi</h1><p>Karachi is the largest city in Pakistan.</p>
<p>Population figures are contested.</p><noscript>ignore me</noscript></body></html>
"""
