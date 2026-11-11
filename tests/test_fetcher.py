"""Test HTTP Range fetching against a local server. Still no internet.

The server here can misbehave on purpose -- ignore Range, answer 503, answer
the wrong range -- because real servers do all three and the retry logic is
exactly what students must learn to write.
"""
from __future__ import annotations

import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from _fixtures import build_warc_file, http_record  # noqa: E402

from ccstarter.fetcher import FetchError, fetch_record  # noqa: E402

BLOB, SPANS = build_warc_file(
    [http_record(f"https://example.pk/{i}", f"<html><body>page {i}</body></html>") for i in range(4)]
)

STATE = {"ignore_range": False, "fail_first": 0, "wrong_range": False}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silence
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(BLOB)))
        self.end_headers()

    def do_GET(self):
        if STATE["fail_first"] > 0:
            STATE["fail_first"] -= 1
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        rng = self.headers.get("Range", "")
        if STATE["ignore_range"] or not rng:
            self.send_response(200)
            self.send_header("Content-Length", str(len(BLOB)))
            self.end_headers()
            self.wfile.write(BLOB)
            return

        start, end = rng.split("=")[1].split("-")
        start, end = int(start), int(end)
        if STATE["wrong_range"]:
            start, end = 0, 99
        if start >= len(BLOB):
            self.send_response(416)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        chunk = BLOB[start : min(end, len(BLOB) - 1) + 1]
        self.send_response(206)
        self.send_header("Content-Range", f"bytes {start}-{start + len(chunk) - 1}/{len(BLOB)}")
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)


class TestRangeFetch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.host = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        STATE.update(ignore_range=False, fail_first=0, wrong_range=False)

    def test_exact_bytes_for_every_record(self):
        for i, (offset, length) in enumerate(SPANS):
            got = fetch_record("crawl-data/fake.warc.gz", offset, length, host=self.host, retries=2)
            self.assertEqual(got, BLOB[offset : offset + length], f"record {i}")
            self.assertEqual(got[:2], b"\x1f\x8b")

    def test_retries_after_transient_503(self):
        STATE["fail_first"] = 2
        offset, length = SPANS[1]
        got = fetch_record("f.warc.gz", offset, length, host=self.host, retries=5)
        self.assertEqual(got, BLOB[offset : offset + length])

    def test_server_ignoring_range_is_rejected_safely(self):
        STATE["ignore_range"] = True
        offset, length = SPANS[2]
        with self.assertRaisesRegex(FetchError, "ignored Range"):
            fetch_record("f.warc.gz", offset, length, host=self.host, retries=2)

    def test_wrong_content_range_is_rejected(self):
        STATE["wrong_range"] = True
        offset, length = SPANS[3]
        with self.assertRaises(FetchError):
            fetch_record("f.warc.gz", offset, length, host=self.host, retries=2)

    def test_out_of_bounds_offset_raises(self):
        with self.assertRaises(FetchError):
            fetch_record("f.warc.gz", len(BLOB) + 10, 100, host=self.host, retries=1)

    def test_head_returns_object_size(self):
        from ccstarter.discovery import http_head_length
        self.assertEqual(http_head_length(f"{self.host}/fake.warc.gz"), len(BLOB))

    def test_head_on_missing_url_returns_none(self):
        from ccstarter.discovery import http_head_length
        self.assertIsNone(http_head_length("http://127.0.0.1:1/nope", timeout=1))

    def test_bad_arguments_rejected_locally(self):
        with self.assertRaises(FetchError):
            fetch_record("f.warc.gz", 10, 0, host=self.host, retries=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
