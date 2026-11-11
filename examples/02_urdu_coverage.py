"""STEP 2 -- map the languages present on .pk websites.

    python examples/02_urdu_coverage.py
    python examples/02_urdu_coverage.py --tld pk --shards 12 --out pk_languages.csv

This is the students' analysis template: one SQL query, one CSV, one claim.

Honesty note, and make them read it aloud in the session:
the shards are an evenly spaced *sample*, not the whole crawl. So the output
is "in the sample", not "on the web". The fix is one line: run the same query
in Athena over the full partition. Compare the two numbers, and you have
taught sampling error better than any slide.

Requires: pip install duckdb
"""
from __future__ import annotations

import argparse
import sys

from ccstarter import latest_crawl, run_sql, shards
from ccstarter.query import lit

TOTAL_SQL = """
SELECT count(*) AS pages,
       count(DISTINCT url_host_registered_domain) AS domains
FROM ccindex
WHERE url_host_tld = {tld} AND fetch_status = 200
"""

LANG_SQL = """
SELECT content_languages AS languages, count(*) AS pages
FROM ccindex
WHERE url_host_tld = {tld} AND fetch_status = 200 AND content_languages IS NOT NULL
GROUP BY 1
ORDER BY pages DESC
LIMIT 25
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Language mix of a country-code TLD.")
    ap.add_argument("--tld", default="pk")
    ap.add_argument("--crawl", default=None)
    ap.add_argument("--shards", type=int, default=8)
    ap.add_argument("--out", default=None, help="write the language table to CSV")
    args = ap.parse_args()

    crawl = args.crawl or latest_crawl()
    urls = shards(crawl, max_files=args.shards)
    print(f"crawl {crawl}, {len(urls)} shards sampled\n")

    tld = lit(args.tld)
    totals = run_sql(TOTAL_SQL.format(tld=tld), crawl=crawl, urls=urls)
    langs = run_sql(LANG_SQL.format(tld=tld), crawl=crawl, urls=urls)

    pages = int(totals.pages.iloc[0]) if len(totals) else 0
    domains = int(totals.domains.iloc[0]) if len(totals) else 0
    print(f".{args.tld} in sample: {pages:,} pages from {domains:,} domains\n")
    if langs.empty:
        print("no language tags; try more shards")
        return 1

    langs = langs.copy()
    langs["share"] = (langs.pages / max(pages, 1) * 100).round(2)
    print(f"{'languages':<24}{'pages':>10}{'share %':>10}")
    print("-" * 44)
    for _, r in langs.iterrows():
        print(f"{str(r.languages):<24}{int(r.pages):>10,}{r.share:>10}")

    tagged = int(langs.pages.sum())
    print("-" * 44)
    print(f"{'tagged rows':<24}{tagged:>10,}{tagged / max(pages, 1) * 100:>9.1f}%")
    print(f"{'untagged rows':<24}{pages - tagged:>10,}")

    if args.out:
        langs.to_csv(args.out, index=False)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
