"""ccstarter: learn Common Crawl by mapping language tags on .pk pages.

Quick sketch (the complete example is in examples/pakistan_web.py)::

    from ccstarter import latest_crawl, shards, run_sql
    crawl = latest_crawl()
    files = shards(crawl, max_files=8)
    sql = "SELECT url_host_registered_domain, count(*) FROM ccindex " \
          "WHERE url_host_tld = 'pk' GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
    print(run_sql(sql, crawl=crawl, urls=files))

For retrieval, use fetch_record() with the filename, offset, and length from a
URL-index row, then record_to_text() to parse the returned bytes.
"""
from .constants import DATA_HOST, DEFAULT_CRAWL
from .discovery import latest_crawl, shards, warc_files, sample_even, http_get
from .fetcher import fetch_record, FetchError
from .query import run_sql, QueryError
from .warc import parse_record, record_to_text, html_to_text, WarcError

__version__ = "0.1.0"
__all__ = [
    "DATA_HOST", "DEFAULT_CRAWL", "latest_crawl", "shards", "warc_files",
    "sample_even", "http_get", "fetch_record", "FetchError", "run_sql",
    "QueryError", "parse_record", "record_to_text", "html_to_text", "WarcError",
]
