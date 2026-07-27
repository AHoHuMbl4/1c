# IVF index build on 1536-dim vectors: sharp threshold between 5 000 and 6 000 rows

Bug report prepared 2026-07-27. All numbers below are measurements on a live instance,
not estimates. Reproduction script at the end is verified to run.

---

## Environment

```
SELECT version();  ->  PostgreSQL 18.3 (SereneDB 26.07.3)
```

Linux x86-64, 63 GB RAM, no other load on the box.

Settings — **all at their defaults**, nothing was tuned before the runs:

```
memory_limit                   = 50.0 GiB
threads                        = 6
sdb_ivf_posting_size           = 1024
sdb_ivf_sample_factor          = 0
sdb_nprobe                     = 8
sdb_rerank_factor              = 4
sdb_scored_terms_limit         = 1024
sdb_disable_top_k_optimization = off
sdb_strict_ddl                 = off
```

---

## What we are doing

Building an IVF index over a `FLOAT[1536]` column (text embeddings, cosine). The table
holds nothing but a key and the vector:

```sql
CREATE TABLE t (row_key VARCHAR, emb FLOAT[1536]);
CREATE INDEX t_idx ON t USING inverted(row_key, emb ivf (metric = 'cosine'));
```

`quant` is not specified, so it defaults to `none` — in 26.07.3 quantization is
rejected for `cosine` anyway:

```
metric='cosine', quant='sq8' -> ERROR: ivf quantization supports only metric 'l2' or 'ip'
```

---

## Observed behaviour: a sharp threshold, not gradual growth

Same table shape, same settings, only the row count differs. Memory column is the
increase in system-wide used memory during the build.

| Rows | Result | Time | Memory increase |
|---|---|---|---|
| 1 000 | `CREATE INDEX` | **1 s** | **0 MB** |
| 5 000 | `CREATE INDEX` | **1 s** | **0 MB** |
| 6 000 | did not finish | 90 s (timeout) | +4 473 MB |
| 7 000 | did not finish | 90 s (timeout) | +4 324 MB |
| 8 000 | did not finish | 90 s (timeout) | +5 653 MB |
| 10 000 | did not finish | 400 s (timeout) | +12 494 MB |
| 20 000 | did not finish | 400 s (timeout) | +13 476 MB |

**The transition between 5 000 and 6 000 rows is abrupt.** Below it the build is
instant and allocates nothing measurable; above it the build does not complete and
memory grows without bound. Left running longer, a single build reached ~30 GB.

For scale: 10 000 × 1536 × 4 bytes = **61 MB of vector data**. Peak memory exceeds the
payload by roughly **two orders of magnitude**.

### `sdb_ivf_posting_size` does not move the threshold

At 10 000 rows, varying the posting size changes nothing:

| `sdb_ivf_posting_size` | Result | Memory increase |
|---|---|---|
| 128 | did not finish (90 s) | +4 529 MB |
| 256 | did not finish (90 s) | +4 255 MB |
| 1024 (default) | did not finish (400 s) | +12 494 MB |

---

## Hypotheses we checked against the source, and ruled out

We read `libs/iresearch/include/iresearch/formats/ivf/` in the public `main`
(commit `722c929`, 2026-07-26 — same generation as our build) looking for an
explanation. Three candidates did not survive:

**1. Training sample size.** With `sample_factor = 0` the adaptive formula is
`(rows / posting_size) * kTrainPointsPerLeaf` = `(10000 / 1024) * 64` ≈ **625 vectors**
≈ 3.7 MB. Too small to matter, and it grows smoothly across the threshold.

**2. `kMaxTrainSample`.** The 4 194 304 cap is capped again by
`sample_size = min(sample_size, rows)` on the next line, so it is unreachable at these
row counts.

**3. Clustering algorithm switch.** `SuperKMeansGate(d, k, min_k)` requires **both**
`d >= 32` **and** `k >= min_k` (512, or 4096 for angular metrics). With
`posting_size = 1024` the cluster count is on the order of ten. The gate does not fire
on either side of the threshold, so the same `RunLloyd` path runs in both cases.

**We could not find the cause in the code.** That is the main question.

---

## Two related problems found along the way

### The build cannot be cancelled

`pg_cancel_backend()` returns `t`, the `psql` client can be killed, and the server-side
work **continues** and keeps allocating. The only way to stop it is restarting the
engine. We found no interrupt-check point anywhere along the IVF build path
(`centroids.cpp`, `clustering.cpp`, `ivf_writer.cpp`, `quantizer.cpp`).

This makes the failure mode expensive: an accidental build on a slightly-too-large
table takes the whole instance down until restart.

### `SET memory_limit` does not stop it either

We set `memory_limit = '4GB'` and `'6GB'` on the session as a safety net before the
build. The build still went past 12 GB. Whatever allocates during IVF construction
appears not to go through the engine's memory accounting.

---

## Reproduction

Verified to run on 26.07.3 — the vector-generating expression is checked and returns
1536.

```sql
-- builds in ~1 second, no measurable memory growth
CREATE TABLE t5 AS
  SELECT i::VARCHAR AS k,
         array_transform(range(1536), x -> random()::FLOAT)::FLOAT[1536] AS emb
  FROM range(5000) s(i);
CREATE INDEX t5_idx ON t5 USING inverted(k, emb ivf (metric = 'cosine'));

-- same statement, 6000 rows: does not complete, memory grows without bound
CREATE TABLE t6 AS
  SELECT i::VARCHAR AS k,
         array_transform(range(1536), x -> random()::FLOAT)::FLOAT[1536] AS emb
  FROM range(6000) s(i);
CREATE INDEX t6_idx ON t6 USING inverted(k, emb ivf (metric = 'cosine'));
-- expect to restart the engine to recover
```

---

## Questions

1. **Is this expected at `d = 1536` with default settings, or a defect?** In
   `tests/sqllogic` the largest dimension exercised at volume is `FLOAT[8]` (50 000
   rows); the only test above that is `FLOAT[384]` on four rows. Do you have
   measurements for IVF at production dimensions — build time, peak memory, on-disk
   size, recall?

2. **What configuration do you recommend for ~100 000 rows × 1536, cosine?**
   Specifically `quant`, `pq_m`, `sdb_ivf_posting_size`, `sdb_ivf_sample_factor`,
   `sdb_nprobe`, `sdb_rerank_factor`.

3. **Quantization and cosine.** 26.07.3 rejects `quant` with `metric='cosine'`, while
   `main` already defaults to `sq8` and allows it for cosine
   (`server/catalog/index.cpp:343-347`). Which release carries that change?

4. **Is cancellation of an IVF build planned**, and is its memory expected to be
   covered by `memory_limit`?

5. **Would splitting the data help?** Since 5 000 rows build instantly, is building
   several smaller IVF indexes over partitions and querying them together
   (`UNION ALL` over per-partition top-k) a supported pattern, or is there a reason it
   would degrade recall or performance?

---

## Two unrelated observations, in case they are useful

**`examples/demo4` and `demo5` do not run.** Both use the `hnsw` opclass:

```sql
embedding hnsw (metric = 'cosine', m = 32, ef_construction = 64)
```

which fails on our build and, as far as we can tell, on current `main` as well:

```
ERROR: Unknown built-in opclass 'hnsw' on 'embedding' (known: included, ivf)
```

`kKnownOpclassTypes` in `server/catalog/index.cpp:110-113` holds exactly
`{included, ivf}`; there is no `columnstore/` directory, although
`scripts/perf/sweep_hnsw.sh:16` still points at `columnstore/hnsw.cpp`. These are the
only two demos covering production-scale dimensions (1536 and 3072), so they are
exactly what a new user reaches for first.

**Unknown opclass is silently swallowed by `USING secondary`.**

```sql
CREATE INDEX i ON t USING secondary (v bogus_opclass);
-- succeeds; duckdb_indexes() then shows:
--   CREATE INDEX i ON public.t USING secondary ();      <- no columns
```

The same DDL through `USING inverted` correctly raises an error. We hit this while
testing and it cost us time before we noticed the index had no columns.
