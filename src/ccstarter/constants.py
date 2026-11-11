"""Facts about where Common Crawl lives. Keep them in one place."""
from __future__ import annotations

#: HTTP mirror of the S3 bucket. Free, no AWS account, no keys.
DATA_HOST = "https://data.commoncrawl.org"

#: Where the URL index (Parquet) lives, bucket-relative.
INDEX_TABLE = "cc-index/table/cc-main/warc"

#: A polite User-Agent. Common Crawl asks you not to hammer their servers.
USER_AGENT = "ccstarter/0.1 (student teaching project; +https://commoncrawl.org)"

#: The crawl the exercises use. Any id from collinfo.json works.
DEFAULT_CRAWL = "CC-MAIN-2026-43"

#: Retry policy for every network call in this package.
RETRIES = 5
TIMEOUT = 90
