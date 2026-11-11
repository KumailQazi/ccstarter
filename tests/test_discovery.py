"""Manifest + sampling tests, using local files instead of the real bucket."""
from __future__ import annotations

import gzip
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ccstarter import discovery  # noqa: E402

PATHS = "\n".join(
    [f"cc-index/table/cc-main/warc/crawl=CC-MAIN-2026-43/subset=warc/part-{i:05d}.c000.gz.parquet" for i in range(100)]
    + [f"cc-index/table/cc-main/warc/crawl=CC-MAIN-2026-43/subset=robotstxt/part-{i:05d}.c000.gz.parquet" for i in range(3)]
) + "\n"


class TestSampling(unittest.TestCase):
    def test_even_spacing_not_head(self):
        picked = discovery.sample_even(list(range(100)), 5)
        self.assertEqual(len(picked), 5)
        self.assertEqual(picked, [0, 20, 40, 60, 80])
        self.assertGreater(picked[-1], 50)  # proves we are not taking the head

    def test_none_returns_everything(self):
        self.assertEqual(discovery.sample_even([1, 2, 3], None), [1, 2, 3])

    def test_n_larger_than_list(self):
        self.assertEqual(discovery.sample_even([1, 2], 10), [1, 2])


class TestManifest(unittest.TestCase):
    def test_gzip_manifest_parsed_and_filtered_by_subset(self):
        blob = gzip.compress(PATHS.encode())
        with mock.patch.object(discovery, "http_get", return_value=blob):
            urls = discovery.shards("CC-MAIN-2026-43", subset="warc", max_files=4)
        self.assertEqual(len(urls), 4)
        self.assertTrue(all("/subset=warc/" in u for u in urls))
        self.assertTrue(all(u.startswith("https://data.commoncrawl.org/") for u in urls))

    def test_plain_text_manifest_also_works(self):
        with mock.patch.object(discovery, "http_get", return_value=PATHS.encode()):
            urls = discovery.shards("CC-MAIN-2026-43", subset="robotstxt", max_files=10)
        self.assertTrue(all("/subset=robotstxt/" in u for u in urls))
        self.assertEqual(len(urls), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
