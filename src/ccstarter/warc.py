"""Turn one record's bytes into text -- with the standard library only.

Why hand-roll this when `warcio` and `fastwarc` exist? Because a student who
has taken one WARC record apart by hand understands every failure mode they
will later hit. Use FastWARC in production; use this to learn.

A Common Crawl .warc.gz is a *concatenation of independent gzip members*, one
per record. That is why a byte range works at all: the offset in the index
points at the start of a gzip member, not at the start of the file.
"""
from __future__ import annotations

import gzip
import io
import re
import zlib
from html.parser import HTMLParser
from typing import Dict

GZIP_MAGIC = b"\x1f\x8b"


class WarcError(ValueError):
    pass


def decompress_member(raw: bytes) -> bytes:
    """Inflate a single gzip member. Refuses to return half a record."""
    if not raw:
        raise WarcError("empty range: the offset/length pair is wrong")
    if not raw.startswith(GZIP_MAGIC):
        # Some ranges start mid-member; a plain record is also tolerated.
        return raw
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = d.decompress(raw) + d.flush()
    except zlib.error as exc:
        raise WarcError(f"gzip inflate failed: {exc}") from exc
    if not d.eof:
        raise WarcError(
            "gzip member is truncated: ask for a slightly longer range "
            "(the index 'length' is the record length; try length + 64)"
        )
    return out


def parse_headers(block: bytes) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for line in block.decode("utf-8", "replace").split("\r\n"):
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return headers


def _dechunk(body: bytes) -> bytes:
    out, rest = bytearray(), body
    while rest:
        line_end = rest.find(b"\r\n")
        if line_end < 0:
            break
        try:
            size = int(rest[:line_end].split(b";")[0], 16)
        except ValueError:
            break
        if size == 0:
            break
        start = line_end + 2
        out += rest[start : start + size]
        rest = rest[start + size + 2 :]
    return bytes(out)


def _maybe_gunzip(body: bytes, headers: Dict[str, str]) -> bytes:
    if headers.get("content-encoding", "").lower() == "gzip" or body[:2] == GZIP_MAGIC:
        try:
            return gzip.decompress(body)
        except OSError:
            return body
    return body


def parse_record(raw: bytes) -> Dict:
    """Split one WARC record into WARC headers, HTTP headers and payload."""
    data = decompress_member(raw)
    if not data.startswith(b"WARC/"):
        preview = data[:40].decode("utf-8", "replace")
        raise WarcError(f"not a WARC record (starts with {preview!r})")

    split = data.find(b"\r\n\r\n")
    if split < 0:
        raise WarcError("no header/body separator found")
    warc_headers = parse_headers(data[:split])
    body_start = split + 4
    try:
        content_length = int(warc_headers.get("content-length", "-1"))
    except ValueError:
        content_length = -1
    content = data[body_start:] if content_length < 0 else data[body_start : body_start + content_length]

    record: Dict = {
        "type": warc_headers.get("warc-type", ""),
        "target_uri": warc_headers.get("warc-target-uri", ""),
        "warc_headers": warc_headers,
        "http_headers": {},
        "status": None,
        "payload": content,
    }
    ctype = warc_headers.get("content-type", "").lower()
    if "application/http" in ctype or content.startswith(b"HTTP/"):
        head_end = content.find(b"\r\n\r\n")
        if head_end > 0:
            head, payload = content[:head_end], content[head_end + 4 :]
            record["http_headers"] = parse_headers(head)
            match = re.match(rb"HTTP/\d(?:\.\d)?\s+(\d{3})", head)
            if match:
                record["status"] = int(match.group(1))
            if record["http_headers"].get("transfer-encoding", "").lower() == "chunked":
                payload = _dechunk(payload)
            record["payload"] = _maybe_gunzip(payload, record["http_headers"])
    return record


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.parts.append(data)


def html_to_text(html: bytes | str) -> str:
    """Readable text from HTML, no dependencies, no boilerplate magic."""
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def record_to_text(raw: bytes) -> Dict:
    """Convenience: bytes from fetch_record() -> headers + plain text."""
    record = parse_record(raw)
    ctype = record["http_headers"].get("content-type", "") or ""
    payload = record["payload"]
    if "html" in ctype.lower() or payload[:200].lstrip().lower().startswith((b"<!doctype", b"<html")):
        record["text"] = html_to_text(payload)
    else:
        record["text"] = payload.decode("utf-8", "replace")
    return record
