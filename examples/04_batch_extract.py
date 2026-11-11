"""STEP 4 -- turn the sample into a corpus, with a budget and a log.

    python examples/04_batch_extract.py --tld pk --max-records 200 --out pk_sample.jsonl

Design decisions worth explaining to students, in this order:
  1. --workers 8, not 500. Common Crawl is a non-profit on donated AWS; a
     greedy crawler is both rude and slower (429s, then backoff).
  2. Every record is wrapped in try/except and every failure is counted.
     A pipeline that dies on record 3,000 of 5,000 is not a pipeline.
  3. The output is JSONL, one line per page, with provenance fields. Anyone
     can re-fetch any line later and get byte-identical content.

Requires: pip install duckdb
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from ccstarter import fetch_record, latest_crawl, record_to_text, run_sql, shards
from ccstarter.query import lit

PICK = """
SELECT url, warc_filename, warc_record_offset, warc_record_length, content_languages
FROM ccindex
WHERE url_host_tld = {tld} AND fetch_status = 200
  AND content_mime_type LIKE '%html%'
  AND warc_record_length BETWEEN 2000 AND 300000
ORDER BY url_host_registered_domain
LIMIT {n}
"""


def work(row, min_chars: int):
    try:
        raw = fetch_record(row.warc_filename, row.warc_record_offset, row.warc_record_length)
        rec = record_to_text(raw)
        text = rec["text"]
        if len(text) < min_chars:
            return None, "too_short"
        return {
            "url": rec["target_uri"] or row.url,
            "status": rec["status"],
            "languages": row.content_languages,
            "warc_filename": row.warc_filename,
            "warc_record_offset": int(row.warc_record_offset),
            "warc_record_length": int(row.warc_record_length),
            "chars": len(text),
            "text": text,
        }, "ok"
    except Exception as exc:
        return None, type(exc).__name__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tld", default="pk")
    ap.add_argument("--max-records", type=int, default=200)
    ap.add_argument("--min-chars", type=int, default=200)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--crawl", default=None)
    ap.add_argument("--shards", type=int, default=8)
    ap.add_argument("--out", default="sample.jsonl")
    args = ap.parse_args()

    crawl = args.crawl or latest_crawl()
    urls = shards(crawl, max_files=args.shards)
    print(f"crawl {crawl}, {len(urls)} shards, target {args.max_records} records")

    plan = run_sql(
        PICK.format(tld=lit(args.tld), n=max(args.max_records * 2, 50)),
        crawl=crawl,
        urls=urls,
    )
    print(f"candidate rows: {len(plan):,}")
    rows = list(plan.itertuples())

    counts: Counter = Counter()
    kept = 0
    started = time.time()
    with open(args.out, "w", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(work, r, args.min_chars) for r in rows]
            for fut in as_completed(futures):
                record, status = fut.result()
                counts[status] += 1
                if record and kept < args.max_records:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    kept += 1
                    if kept % 50 == 0:
                        print(f"  kept {kept} ...")

    elapsed = time.time() - started
    print(f"\nkept {kept} records in {elapsed:.1f}s  ({kept / max(elapsed, 1e-9):.2f} rec/s)")
    print("outcomes:", dict(counts))
    print(f"wrote {args.out}")
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())
