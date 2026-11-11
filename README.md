# ccstarter

**Read Common Crawl without downloading Common Crawl.**

A one-weekend teaching kit for university students and meetup engineers. By the
end, every participant has pulled real pages out of a petabyte-scale web
archive, for free, from a laptop, using tools they can explain to a friend.

```
Common Crawl   ->   2.16 billion pages per monthly crawl, ~109 TiB compressed
this repo      ->   reads the index, then fetches *only the bytes you asked for*
```

---

## The one idea

Common Crawl's archive is not a database you download. It is a pile of ~100,000
gzipped WARC files, each hundreds of megabytes. The naive approach — "download
the WARC, find the page" — is why people give up on Common Crawl in week one.

The whole trick is two lines:

1. Ask the **URL index** (plain Parquet, free to query) which file holds your page,
   and at what byte offset and length.
2. Ask the server for **exactly those bytes** with an HTTP `Range` request.

You get a few kilobytes instead of a gigabyte, in about a second.

```
Range: bytes=250975924-250982845     ->     206 Partial Content, 6,922 bytes
```

Everything else in this repo is exercise material around that one idea.

---

## Why a sample, not a crawl (read this before you quote a number)

The exercises query **8 shards sampled evenly** across one crawl's ~900 index
shards. That is a sample of the *snapshot files*, not a random sample of the web,
and the difference matters when you write up results. Say "in this sample", not
"on the web". The honest upgrade path is one SQL statement in Athena over the
full partition — and comparing your DuckDB number to the Athena number is the
best five-minute lesson on sampling error a student will ever get.

---

## Setup (5 minutes, no AWS account)

```bash
git clone <this repo> ccstarter && cd ccstarter
python -m venv .venv && source .venv/bin/activate
pip install duckdb            # the only dependency
python -m unittest discover -s tests -p 'test_*.py' -v   # works offline (43 tests)
```

You do **not** need AWS credentials. `https://data.commoncrawl.org` serves the
data anonymously. Costs are zero unless you choose to use Athena or move data
out of `us-east-1`.

Requirements: Python 3.10+, ~50 MB of disk for the exercises, a normal internet
connection.

---

## Five steps, in order

| Step | Command | What it proves |
|---|---|---|
| 1 | `python examples/01_probe_a_record.py dawn.com` | one page, one byte range, ~6 KB instead of ~800 MB |
| 2 | `python examples/02_urdu_coverage.py` | what languages actually appear on `.pk` sites, in the sample |
| 3 | `python examples/03_own_passage.py` | the student writes their own SQL and reads five real pages |
| 4 | `python examples/04_batch_extract.py --max-records 200` | a small corpus with a failure log, not a crash |
| 5 | `python examples/05_ai_crawler_blocking_nov2026.py --tld com --sample 500` | who is blocking AI crawlers in November 2026: robots.txt + llms.txt audit |

Each script prints more than it needs to, on purpose. The output *is* the lesson.

### Step 5: AI Crawler Blocking Audit (robots.txt + llms.txt)

Audit which domains block major AI crawlers (`CCBot`, `GPTBot`, `ClaudeBot`, etc.) and inspect adoption of `llms.txt` policy files on the November 2026 web (`CC-MAIN-2026-43`).

**Compare multiple TLDs side by side:**
```bash
python examples/05_ai_crawler_blocking_nov2026.py --compare-tlds com,pk,de,uk,fr --sample 300
```

**Compare multiple TLDs for one specific bot:**
```bash
python examples/05_ai_crawler_blocking_nov2026.py --compare-tlds com,pk,de --bot GPTBot --sample 200
```

**Single TLD, single bot:**
```bash
python examples/05_ai_crawler_blocking_nov2026.py --tld com --bot ClaudeBot --sample 300
```

The `--compare-tlds` flag runs the full audit across each TLD and prints a cross-jurisdictional comparison table plus a blog-ready paragraph. The `--bot` flag filters every output to one crawler, so the CSV, summary, and comparison all focus on that single bot.

**Available values for `--bot`:**
`CCBot`, `GPTBot`, `ClaudeBot`, `OAI-SearchBot`, `PerplexityBot`, `Google-Extended`, `FacebookBot`, `Applebot`, `Amazonbot`, `Bytespider`.

*(Add `--demo` to any command for 100% offline classroom runs using authentic Common Crawl patterns).*

### Step 1 output, roughly

```
crawl:  CC-MAIN-2026-43
index:  8 shards sampled evenly across the crawl

url:     https://www.dawn.com/...
warc:    crawl-data/CC-MAIN-2026-43/segments/.../CC-MAIN-....warc.gz
range:   bytes=...-...  (6,922 bytes)
got:     6,922 bytes via HTTP Range
file:    847,392,110 bytes if you had downloaded it
saved:   122,410x less data
```

That `saved:` line is the moment the room understands the problem.

---

## What is in the box

```
src/ccstarter/
  constants.py   where the data lives, and the retry policy
  discovery.py   newest crawl, index shard list, even sampling, HEAD sizes
  query.py       DuckDB over the Parquet index, exposed as a view named ccindex
  fetcher.py     HTTP Range fetch with backoff, jitter, and range validation
  warc.py        gzip member -> WARC headers -> HTTP headers -> clean text
examples/        the five teaching steps
tests/           43 offline tests; a fake crawl is built in-memory
BLOG_POST.md     the write-up, with blanks for your own numbers
WORKSHOP.md      a 150-minute session plan
```

### The hand-rolled WARC parser is a feature

`src/ccstarter/warc.py` parses WARC records with the standard library only. That
is deliberate: a student who has taken one record apart by hand — gzip member,
WARC headers, HTTP headers, chunked transfer encoding, payload — understands
every error they will later see in production, and will know exactly why
FastWARC exists. Use FastWARC when you ship; keep this for when you teach.

It also fails loudly and specifically:

```
WarcError: gzip member is truncated: ask for a slightly longer range
           (the index 'length' is the record length; try length + 64)
```

---

## Patterns worth stealing for your own pipeline

**Never trust a range you did not verify.** The fetcher reads back
`Content-Range` and refuses the bytes if the server returned a different window.
A pipeline that silently accepts wrong bytes is worse than one that crashes.

**Refuse the full file.** If a server ignores `Range` and answers `200` with the
whole object, the fetcher raises instead of reading it. Downloading 800 MB
because a proxy stripped a header is the classic self-inflicted bill.

**Sample evenly, not from the head.** `sample_even()` takes items spread across
the manifest. The first eight index shards are not a sample of the web; they are
one corner of it.

**Count your failures.** `04_batch_extract.py` records every exception type and
keeps going. "1,842 ok / 158 too_short / 3 WarcError" is a result; a traceback is
not.

**Find files through the manifest, not the bucket.** Anonymous access cannot
`ListBucket`. Every crawl publishes `cc-index-table.paths.gz`; read that.

**Be a good citizen.** `--workers 8`, a real User-Agent, exponential backoff.
Common Crawl is a non-profit on donated AWS credits, and rate-limit bans hurt
everyone's students, including yours.

---

## Cost table

| Thing | Cost |
|---|---|
| Index queries with DuckDB | **$0** |
| Byte-range record fetches over HTTPS | **$0** |
| Reading data on EC2 in `us-east-1` | $0 for data, you pay for the instance |
| Athena over one full crawl partition | ~$1.50 worst case, usually cents |
| Pulling data *out* of `us-east-1` | where surprise bills come from; stay in-region |

A weekend of these exercises costs nothing. The only thing to watch is running
the pipeline from a home connection at full tilt — that is bandwidth, not money.

---

## When to graduate from this repo

- **You need the whole crawl, not a sample** → Athena, per the
  [URL Index docs](https://commoncrawl.org/url-index).
- **You need throughput** → FastWARC for parsing, plus targeted `Range`
  requests; never `warcio` in a hot loop.
- **You need WET/WAT instead of WARC** → WET is text-only and much smaller;
  WAT carries links and headers. Neither has offsets in the index, so plan on
  streaming those files rather than range-fetching.
- **You need it in a warehouse** → land the extracted JSONL in Parquet, then
  model it wherever you already work.

---

## Licence and attribution

MIT for the code. Common Crawl data is governed by
[their Terms of Use](https://commoncrawl.org/terms-of-use) — attribute the
corpus, respect robots opt-outs, and do not republish content you have no right
to redistribute. A corpus of extracted text is not automatically yours to ship.
