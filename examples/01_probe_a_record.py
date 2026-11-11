"""STEP 1 -- pull exactly one page out of the web, and prove you saved bandwidth.

    python examples/01_probe_a_record.py example.com
    python examples/01_probe_a_record.py dawn.com --crawl CC-MAIN-2026-43

What to look for in the output:
  * "record bytes" should be a few KB
  * "file size" should be hundreds of MB
  * the ratio is the whole argument for byte-range fetching

Requires: pip install duckdb
"""
from __future__ import annotations

import argparse
import sys

from ccstarter import fetch_record, latest_crawl, record_to_text, run_sql, shards
from ccstarter.discovery import http_head_length
from ccstarter.query import lit

SQL = """
SELECT url, warc_filename, warc_record_offset, warc_record_length,
       fetch_status, content_mime_type, content_languages
FROM ccindex
WHERE url_host_registered_domain = {domain}
  AND fetch_status = 200
  AND warc_record_length > 0
LIMIT 1
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch one Common Crawl record by byte range.")
    ap.add_argument("domain", help="registered domain, e.g. example.com or dawn.com")
    ap.add_argument("--crawl", default=None, help="crawl id (default: newest)")
    ap.add_argument("--shards", type=int, default=8, help="how many index shards to search")
    ap.add_argument("--chars", type=int, default=600, help="how much text to print")
    args = ap.parse_args()

    crawl = args.crawl or latest_crawl()
    print(f"crawl:  {crawl}")
    print(f"index:  {args.shards} shards sampled evenly across the crawl\n")

    urls = shards(crawl, max_files=args.shards)
    df = run_sql(SQL.format(domain=lit(args.domain)), crawl=crawl, urls=urls)
    if df.empty:
        print("no rows: this domain is not in the sampled shards.")
        print("try --shards 30, or pick a bigger/popular domain.")
        return 1

    row = df.iloc[0]
    offset, length = int(row.warc_record_offset), int(row.warc_record_length)
    print(f"url:     {row.url}")
    print(f"warc:    {row.warc_filename}")
    print(f"range:   bytes={offset}-{offset + length - 1}  ({length:,} bytes)")
    print(f"langs:   {row.content_languages}")

    raw = fetch_record(row.warc_filename, offset, length)
    print(f"got:     {len(raw):,} bytes via HTTP Range")

    whole_file = http_head_length(f"https://data.commoncrawl.org/{row.warc_filename}")
    if whole_file:
        print(f"file:    {whole_file:,} bytes if you had downloaded it")
        print(f"saved:   {whole_file / max(len(raw), 1):,.0f}x less data\n")

    rec = record_to_text(raw)
    print(f"status:  {rec['status']}  type: {rec['type']}")
    print(f"target:  {rec['target_uri']}")
    print("-" * 70)
    print(rec["text"][: args.chars])
    print("-" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
