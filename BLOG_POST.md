<!--
HOW TO USE THIS DRAFT
1. Run the four steps. Paste your real numbers into the [BRACKETS].
2. Delete any section you cannot honestly fill. The post is stronger shorter.
3. Do not publish a number you did not run yourself. The whole point of the
   post is that it is repeatable by a reader on a laptop.
4. Suggested title options at the bottom.
-->

# I read 2.16 billion web pages on a laptop for $0

*A one-weekend, one-dependency tour of Common Crawl — and the two lines that make it possible.*

---

I spent a weekend helping a room of students pull live web pages out of Common
Crawl. Nobody downloaded a terabyte. Nobody made an AWS account. Nobody paid for
anything. The whole kit is one dependency (`duckdb`) and about 600 lines of
Python, most of it comments.

Here is the trick, the traps, and what we actually found.

## The thing everybody gets wrong

Common Crawl's October 2026 crawl is **2.16 billion pages, 109 TiB compressed**,
spread over ~100,000 gzipped WARC files.<source-chip title="Common Crawl Archives" url="https://data.commoncrawl.org/crawl-data/index.html" />

The instinct is: find the crawl, download a WARC file, search inside it. That
file is roughly 800 MB. You want one article. You are now spending an afternoon
to read six kilobytes.

The fix is that Common Crawl ships an **index** — and the index already told you
where your page is:

```
https://data.commoncrawl.org/crawl-data/CC-MAIN-2026-43/segments/.../CC-MAIN-....warc.gz
  warc_record_offset: 250975924
  warc_record_length: 6922
```

Two numbers. Ask for exactly those bytes:

```python
requests.get(url, headers={"Range": f"bytes={offset}-{offset+length-1}"})
```

The server answers `206 Partial Content` and hands you 6,922 bytes.

```
naive:   download 800 MB  ->  find 6 KB
actual:  ask for   6 KB   ->  get  6 KB
```

In my run against `dawn.com` in `CC-MAIN-2026-43`, the ratio was
**[INSERT: saved ×]**, and the fetch took **[INSERT: seconds]** on a home
connection. That ratio is the entire argument, and it lands in a room better than
any slide.

### Why the offset works at all

A Common Crawl `.warc.gz` is **a concatenation of independent gzip members**, one
per record. The offset points at a member boundary, so the bytes you requested
inflate on their own. This is not a hack; it is the format, and knowing it is the
difference between "it works" and "I understand why it works."

## The index is just Parquet. Query it locally.

The second half of the trick: the URL index is published as **Apache Parquet**,
partitioned by crawl and subset, at
`s3://commoncrawl/cc-index/table/cc-main/warc/`. That means DuckDB reads it over
HTTPS like a local file, and column + row-group pruning means a filtered query
touches megabytes of a 300 GB index.

```sql
SELECT url_host_registered_domain AS domain, count(*) AS pages
FROM ccindex
WHERE url_host_tld = 'pk'
GROUP BY 1 ORDER BY pages DESC LIMIT 10;
```

That is SQL over two billion rows, run on a laptop, offline from any account,
cost zero.

One trap worth naming: **you cannot list the S3 prefix anonymously.** You can
`GetObject` if you know the exact key, but `ListBucket` needs credentials — which
is why "just glob the Parquet folder" fails in confusing ways. Every crawl
publishes a manifest (`cc-index-table.paths.gz`) listing its index shards. Read
the manifest; it is a few kilobytes and it is the supported path.

## Five traps I hit so you don't have to

**1. Trusting a range you did not verify.** Read back `Content-Range` and compare
it to what you asked for. A pipeline that silently accepts the wrong window
produces plausible garbage.

**2. Accepting a `200`.** If a proxy strips your `Range` header, the server
happily starts sending the whole 800 MB file. My fetcher now *raises* on `200`
instead of reading it. Downloading a gigabyte because of a header is the classic
self-inflicted bill.

**3. Sampling from the head of the manifest.** The first eight index shards of a
crawl are not a sample of the web; they are one corner of it, with a visibly
different domain and language mix. Sample *evenly* across the shard list —
`sample_even()` in the kit does this — and say in your write-up that you sampled.

**4. Assuming WET and WAT have offsets.** They do not. The index gives offsets
into WARC files only. If you want WET (text, much smaller) or WAT (links and
headers), you stream those files rather than range-fetching them.

**5. Dying on record 3,000 of 5,000.** Wrap every record, count every failure by
type, and keep going. "1,842 ok / 158 too_short / 3 WarcError" is a result. A
traceback is not.

## What we actually found

Twenty-something workshop participants, one afternoon, `.pk` domains,
`CC-MAIN-2026-43`, 8 evenly spaced index shards out of ~900:

- **`[INSERT: pages]` pages** from **`[INSERT: domains]`** `.pk` domains, in the sample.
- Language tags: **`[INSERT: top language]`** `[INSERT: %]`, **`urd`** `[INSERT: %]`,
  **`[INSERT: third]`** `[INSERT: %]`.
- **`[INSERT: %]`** of `.pk` rows carry **no** language tag at all — which is
  itself a finding about detection, not about the web.
- Biggest publisher in the sample: **`[INSERT: domain]`**, `[INSERT: pages]` pages.

Every one of those numbers describes **the sample**, not Pakistan. That
distinction is the single most useful thing anyone learned that day, and it is
the first thing I would put in front of any student who quotes a web-scale
figure.

## Reproduce it in 10 minutes

```bash
git clone https://github.com/KumailQazi/ccstarter.git && cd ccstarter
python -m venv .venv && source .venv/bin/activate
pip install duckdb                                    # the only dependency
python -m unittest discover -s tests -p 'test_*.py'    # 43 tests, no internet

python examples/01_probe_a_record.py dawn.com          # one page, one byte range
python examples/02_urdu_coverage.py --shards 8         # language mix on .pk
python examples/04_batch_extract.py --max-records 200  # a small corpus
python examples/05_ai_crawler_blocking_nov2026.py --tld com --sample 500  # AI crawler blocking audit
```

No AWS account. No credentials. No cost. The tests build a fake crawl in memory,
so they pass on a train.

## When you should not use this

- **You need the exact number over a full crawl** → Athena over the full
  partition. Roughly $1.50 worst case for one month's index, usually cents.
- **You need throughput** → FastWARC for parsing (C-backed, 4–8× faster than
  `warcio`), and keep the byte-range fetch. Never put `warcio` in a hot loop.
- **You need to be a good citizen** → `--workers 8`, a real User-Agent,
  exponential backoff. Common Crawl is a non-profit running on donated AWS
  credits. A greedy crawler gets rate-limited, and the ban applies to everyone.

## The lesson I did not expect to teach

I built this thinking the interesting part was the HTTP header. It is not. The
interesting part is that **a petabyte-scale archive is addressable**, and once
students see that, they stop treating big data as something that requires
permission, budget, or a cloud account. Two numbers from an index and a `Range`
header is enough to read the web from a laptop.

The code is MIT-licensed. Take it to your own meetup, swap `.pk` for your TLD,
and put your numbers in the brackets.

---

*Corpus: Common Crawl `CC-MAIN-2026-43`, October 2026. Common Crawl data is
governed by [their Terms of Use](https://commoncrawl.org/terms-of-use) —
attribute the corpus, respect robots opt-outs, and remember that extracted text
is not automatically yours to redistribute.*

<!--
TITLE OPTIONS
- I read 2.16 billion web pages on a laptop for $0
- The index is a phone book, not a copy of the book
- Two numbers and a Range header: reading Common Crawl from a laptop
- How I taught 20 students to read the web without downloading it
-->
