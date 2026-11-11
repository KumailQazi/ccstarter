"""STEP 3 -- the students' turn: write your own query, then read real pages.

    python examples/03_own_passage.py --tld pk --limit 5

Edit QUESTION at the top. That is the assignment: a question the index can
answer, the SQL that answers it, and five real pages to justify it.

Requires: pip install duckdb
"""
from __future__ import annotations

import argparse
import sys

from ccstarter import fetch_record, latest_crawl, record_to_text, run_sql, shards
from ccstarter.query import lit

# EDIT ME: pick something you actually want to know.
# Ideas: which domains publish in Urdu; how many .pk pages are PDFs;
# the biggest news domains; average page size by domain.
QUESTION = """
SELECT url_host_registered_domain AS domain,
       count(*) AS pages,
       round(avg(warc_record_length)) AS avg_bytes
FROM ccindex
WHERE url_host_tld = {tld} AND fetch_status = 200
GROUP BY 1
ORDER BY pages DESC
LIMIT {n}
"""

PICK_ONE = """
SELECT url, warc_filename, warc_record_offset, warc_record_length
FROM ccindex
WHERE url_host_registered_domain = {domain} AND fetch_status = 200
  AND content_mime_type LIKE '%html%' AND warc_record_length > 0
LIMIT {n}
"""

ANY_RECORD = PICK_ONE.replace("AND content_mime_type LIKE '%html%'", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tld", default="pk")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--crawl", default=None)
    ap.add_argument("--shards", type=int, default=8)
    args = ap.parse_args()

    crawl = args.crawl or latest_crawl()
    urls = shards(crawl, max_files=args.shards)

    print("== your question ==")
    top = run_sql(
        QUESTION.format(tld=lit(args.tld), n=10), crawl=crawl, urls=urls
    )
    print(top.to_string(index=False) if len(top) else "(no rows)")
    if top.empty:
        return 1

    domain = top.domain.iloc[0]
    print(f"\n== reading real pages from {domain} ==")
    picks = run_sql(
        PICK_ONE.format(domain=lit(domain), n=args.limit * 3), crawl=crawl, urls=urls
    )
    if picks.empty:
        picks = run_sql(
            ANY_RECORD.format(domain=lit(domain), n=args.limit * 3), crawl=crawl, urls=urls
        )

    shown = 0
    for _, row in picks.iterrows():
        try:
            raw = fetch_record(row.warc_filename, row.warc_record_offset, row.warc_record_length)
            rec = record_to_text(raw)
        except Exception as exc:      # one bad record must never stop class
            print(f"  skip {row.url}: {type(exc).__name__}")
            continue
        text = " ".join(rec["text"].split())[:300]
        if not text:
            continue
        shown += 1
        print(f"\n--- {rec['target_uri']}  [{rec['status']}]")
        print(text)
        if shown >= args.limit:
            break
    print(f"\n{shown} pages read from byte ranges.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
