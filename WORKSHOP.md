# Workshop: "Read the Web Without Downloading It"

**Audience** university students or meetup engineers, 15–40 people
**Length** 150 minutes, one break
**Prerequisites** Python basics (loops, functions, dicts). No cloud experience.
**Materials** this repo, laptops, one shared screen, average wifi

**Learning outcomes** — by the end, each participant can:
1. Explain why Common Crawl is not downloaded but *addressed*.
2. Query a petabyte-scale Parquet index locally with DuckDB.
3. Fetch one archived page in under two seconds with an HTTP `Range` header.
4. State the sampling limitation of their own result, unprompted.

---

## Run of show

| Time | Segment | Format |
|---|---|---|
| 0:00–0:10 | The problem: 109 TiB and no patience | talk |
| 0:10–0:35 | Anatomy of a WARC + the offset trick | talk + live demo |
| 0:35–0:55 | Lab 1: fetch one page | pairs, hands-on |
| 0:55–1:15 | The URL index: SQL over 2 billion rows | talk + live demo |
| 1:15–1:25 | break | |
| 1:25–1:50 | Lab 2: map languages on `.pk` | pairs, hands-on |
| 1:50–2:10 | Lab 3: your own question | groups of 3 |
| 2:10–2:25 | Show-and-tell: three groups, 3 min each | plenary |
| 2:25–2:30 | Where to go next | talk |

---

## 0:00–0:10 — The problem

Open with numbers, not definitions.

> "Common Crawl's October crawl: 2.16 billion pages, 109 TiB compressed.
> A WARC file in that archive is about 800 MB. You want one article."

Write on the board:

```
naive:    download 800 MB   ->  find 6 KB
actual:   ask for   6 KB    ->  get  6 KB
```

Ask the room: what would the naive version cost if you wanted 10,000 pages?
(Answer: ~8 TB of transfer, and a ban from the nice people who host it.)

## 0:10–0:35 — Anatomy of a WARC

Live, on the shared screen. Do not show slides; show a terminal.

```bash
python examples/01_probe_a_record.py example.com --chars 200
```

Walk through four artefacts, in this order:

1. **`.warc.gz` is a concatenation of independent gzip members** — one per record.
   That is *why* an offset works: the index points at a member boundary.
2. **`warc_record_offset` / `warc_record_length`** — the two numbers the entire
   industry runs on.
3. **The `Range` header and `206 Partial Content`** — demonstrate with `curl -r`.
4. **Why the fetcher refuses a `200`** — a proxy strips a header and now you are
   downloading 800 MB. Show the code that raises.

Key line to say out loud: *"the index is a phone book, not a copy of the book."*

## 0:35–0:55 — Lab 1: fetch one page

Pairs. Each pair picks a Pakistani domain they actually use.

```bash
pip install duckdb
python examples/01_probe_a_record.py <their-domain>
```

**Checkpoints** (walk the room and ask these, don't wait for raised hands):
- What is your `saved:` ratio? (Expect 10,000×–300,000×.)
- Did anyone get "no rows"? Why — small domain, or too few shards?
- Does `--shards 30` fix it? What did that cost in seconds?

**Common failures and what to say**
| Symptom | Real cause | Line to use |
|---|---|---|
| `no rows` | domain isn't in the 8 sampled shards | "we sampled; we didn't read everything" |
| `ImportError: duckdb` | venv not active | fix quietly, move on |
| `ModuleNotFoundError: ccstarter` | not installed; run from repo root | `PYTHONPATH=src` |
| slow first query | DuckDB is fetching Parquet over HTTPS | "watch the second query, it's instant" |

## 0:55–1:15 — SQL over 2 billion rows

This is the intellectual peak. Build the query on the screen *one clause at a time*.

```sql
SELECT url_host_registered_domain AS domain, count(*) AS pages
FROM ccindex
WHERE url_host_tld = 'pk'
GROUP BY 1 ORDER BY pages DESC LIMIT 10;
```

Then the three questions that turn a query into an understanding:

1. **"How many bytes did that scan?"** Explain column pruning: we read three
   columns, not the 26-column, 300 GB table.
2. **"Why `WHERE` before `GROUP BY`?"** Partition and predicate pruning: `tld='pk'`
   lets the engine skip most row groups before it reads anything.
3. **"Is this the whole web?"** No. Eight shards out of ~900, evenly spaced.
   Ask what would change if the shards were the *first* eight. (Answer: very
   different domains, very different language mix — bias you cannot see in the
   output.)

## 1:25–1:50 — Lab 2: map languages on `.pk`

```bash
python examples/02_urdu_coverage.py --shards 8 --out pk_languages.csv
```

Have each pair write one sentence on the whiteboard from their table. Then run
the same query with `--shards 30` and compare. The numbers move. That is the
lesson: **a sample supports a statement about the sample.**

Prompts for stronger groups:
- Why is a large share of rows `content_languages IS NULL`? (Detection failures,
  short pages, non-HTML payloads.)
- Is `content_languages` a language *of the page* or *of the URL*? (Of the
  detected content — say so precisely.)
- What is the `.pk` share of the whole crawl? Compare against another TLD.

## 1:50–2:10 — Lab 3: your own question

Groups of three. Every group edits `QUESTION` in `examples/03_own_passage.py`,
runs it, and reads five real pages to justify the answer.

Rules that make this work:
- **The question must be answerable by the index alone.** Not "what do Pakistanis
  think about X" — that needs text, and gets Lab 4 territory.
- **Five pages or it isn't finished.** Anyone can print a table.
- **One sentence of caveat required**, naming the sample.

Question bank (hand out if a group is stuck):
- Which `.pk` domains publish most, and are they news or government?
- What fraction of `.pk` pages are PDFs, and are they bigger than HTML?
- Which domains appear in Urdu-tagged rows but never English-tagged?
- Do `.pk` pages get truncated (`content_truncated IS NOT NULL`) more than
  average? Why might that be?
- What is the median page size by TLD? Does `pk` differ from `com`?

## 2:10–2:25 — Show-and-tell

Three groups, three minutes each, three questions to answer:
**what did you ask, what did you get, what can't you claim?**

The third question is the assessment. Cut anyone who skips it — gently, and
publicly, so the norm sticks.

## 2:25–2:30 — Where to go next

Point at four doors, briefly:
- **Capstone: AI Crawler Blocking Audit (Step 5)** → Run `examples/05_ai_crawler_blocking_nov2026.py` to audit which domains block CCBot, GPTBot, ClaudeBot, and others via robots.txt and inspect llms.txt adoption in the November 2026 crawl (`CC-MAIN-2026-43`).
- **Exact numbers** → Athena over the full partition, ~$1.50 worst case.
- **Throughput** → FastWARC, and keep the byte-range fetch.
- **Text, not HTML** → WET files; no offsets, so stream them.
- **A real project** → PK government portal link-rot monitor; low-resource
  language corpus for Urdu; or ship an MCP server over this index so an agent
  can browse the archive.

---

## Step 5 / Capstone — Who is Blocking AI Crawlers Right Now?

This is the capstone: students have learned the byte-range trick, the index query, and the parsing pipeline. Now they apply it to a real, timely question — *"who is blocking AI crawlers right now?"* — and get a publishable result in one command:

```bash
# Compare multiple TLDs side by side:
python examples/05_ai_crawler_blocking_nov2026.py --compare-tlds com,pk,de,uk,fr --sample 300

# Compare multiple TLDs for one specific bot:
python examples/05_ai_crawler_blocking_nov2026.py --compare-tlds com,pk,de --bot GPTBot --sample 200

# Single TLD, single bot:
python examples/05_ai_crawler_blocking_nov2026.py --tld com --bot ClaudeBot --sample 300

# Standard run:
python examples/05_ai_crawler_blocking_nov2026.py --tld com --sample 500 --out com_ai_blocking_nov2026.csv
```

The `--compare-tlds` flag runs the full audit across each TLD and prints a cross-jurisdictional comparison table plus a blog-ready paragraph. The `--bot` flag filters every output to one crawler, so the CSV, summary, and comparison all focus on that single bot.

**Available values for `--bot`:** `CCBot`, `GPTBot`, `ClaudeBot`, `OAI-SearchBot`, `PerplexityBot`, `Google-Extended`, `FacebookBot`, `Applebot`, `Amazonbot`, `Bytespider`.

*(Pass `--demo` to any command for instant offline operation if conference/classroom wifi drops).*

What it demonstrates:
- Index querying at scale (DuckDB over Parquet for `robots.txt` and `llms.txt`)
- Byte-range fetching of policy files without full WARC downloads
- Parsing robots.txt directives across 10 major bots with wildcard fallback
- Detecting template markers and prompt-injection strings in `llms.txt`
- Exporting a structured CSV plus a blog-ready summary paragraph

Leave them with the repo link and one sentence: *"you now know how to read a
petabyte without downloading it."*

---

## Facilitator notes

**Wifi is the only real risk.** Run Lab 1 yourself before the session and cache
the shard list. If the room's connection dies, `run_tests.sh` still works offline
and every example can be re-read from the code — that is why the test suite is
offline-first.

**Keep `--shards 8`.** Bigger numbers feel impressive and take four minutes each.
The point is the trick, not the volume.

**Do not fix students' SQL for them.** Ask "what does `GROUP BY 1` mean?" and
walk away. Coming back to a working query they wrote beats watching one you wrote.

**The ethics five minutes.** Common Crawl honours robots opt-outs and is built on
donated infrastructure; extracted text is not automatically yours to redistribute.
Say it once, plainly, and point at the Terms of Use. Students remember the
sentence about being a good citizen more than the one about `Content-Range`.

---

## Assessment (optional, if this is for credit)

One page, three sections:
1. Your SQL, and what it answers.
2. Your table, with the sample size stated in the caption.
3. One paragraph: *"what this cannot tell us, and how I would find out."*

Section 3 is worth half the marks. It is the difference between someone who ran a
query and someone who can be trusted with a number.
