"""Unit tests for WARC parsing. No network, no AWS, no excuses."""
from __future__ import annotations

import gzip
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from _fixtures import SAMPLE_HTML, build_warc_file, gzip_member, http_record  # noqa: E402

from ccstarter.warc import (  # noqa: E402
    WarcError,
    html_to_text,
    parse_record,
    record_to_text,
)


class TestParseRecord(unittest.TestCase):
    def setUp(self):
        self.data, self.spans = build_warc_file(
            [
                http_record("https://example.pk/", SAMPLE_HTML),
                http_record("https://example.pk/missing", "<html>gone</html>", status=404),
            ]
        )

    def _slice(self, i):
        offset, length = self.spans[i]
        return self.data[offset : offset + length]

    def test_offset_length_pairs_land_on_gzip_members(self):
        for i, (offset, length) in enumerate(self.spans):
            self.assertEqual(self.data[offset : offset + 2], b"\x1f\x8b")
            self.assertEqual(self._slice(i)[:0], b"")  # sliceable
            # each member inflates on its own
            gzip.decompress(self._slice(i))

    def test_warc_headers_and_status(self):
        rec = parse_record(self._slice(0))
        self.assertEqual(rec["type"], "response")
        self.assertEqual(rec["target_uri"], "https://example.pk/")
        self.assertEqual(rec["status"], 200)
        self.assertIn("text/html", rec["http_headers"]["content-type"])

    def test_status_404_is_read_not_raised(self):
        self.assertEqual(parse_record(self._slice(1))["status"], 404)

    def test_truncated_range_is_loud(self):
        offset, length = self.spans[0]
        with self.assertRaises(WarcError) as ctx:
            parse_record(self.data[offset : offset + length - 40])
        self.assertIn("truncated", str(ctx.exception).lower())

    def test_short_range_starts_mid_member_and_is_rejected(self):
        offset, _ = self.spans[1]
        with self.assertRaises(WarcError):
            parse_record(self.data[offset + 12 : offset + 400])

    def test_empty_range_message_is_actionable(self):
        with self.assertRaises(WarcError):
            parse_record(b"")

    def test_ngram_headers_are_lowercased(self):
        rec = parse_record(self._slice(0))
        self.assertIn("warc-target-uri", rec["warc_headers"])


class TestHtmlToText(unittest.TestCase):
    def test_script_and_style_are_dropped(self):
        text = html_to_text(SAMPLE_HTML)
        self.assertIn("Karachi is the largest city", text)
        self.assertNotIn("tracking", text)
        self.assertNotIn("color:red", text)
        self.assertNotIn("ignore me", text)

    def test_record_to_text_end_to_end(self):
        data, spans = build_warc_file([http_record("https://example.pk/", SAMPLE_HTML)])
        rec = record_to_text(data)
        self.assertEqual(rec["status"], 200)
        self.assertIn("Karachi", rec["text"])

    def test_chunked_transfer_encoding_is_decoded(self):
        body = b"<html><body><p>chunked body</p></body></html>"
        chunks = b""
        for i in range(0, len(body), 7):
            piece = body[i : i + 7]
            chunks += b"%x\r\n" % len(piece) + piece + b"\r\n"
        chunks += b"0\r\n\r\n"
        head = (
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
        )
        payload = head + chunks
        warc = (
            b"WARC/1.0\r\nWARC-Type: response\r\nWARC-Target-URI: https://x.pk/\r\n"
            b"Content-Type: application/http; msgtype=response\r\n"
            b"Content-Length: %d\r\n\r\n" % len(payload)
        )
        rec = record_to_text(gzip_member(warc + payload))
        self.assertIn("chunked body", rec["text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
