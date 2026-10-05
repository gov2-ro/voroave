> Historical research note. Archived on 2026-10-05. Neither frequency screen feeds the live ranking.
> Current workflow: [scripts guide](../scripts-guide.md). Evaluation: [F09](../fixes/F09-evaluation.md).

# wordfreq recipe — the pragmatic path

> **Status (2026-08-11): this screen feeds nothing.** The `rare_in_use` tab it filled was
> removed. wordfreq's Romanian list has no resolution at the low end — measured over 60,000
> candidates, **99.6% score exactly 0.00** because the library has never heard of them, so
> its lowest real scores are ordinary words (`haz` 3.31, `bețiv` 3.22) while `zapciu`,
> `vornic` and `logofăt` are all 0.00 and indistinguishable. A tier defined on that band
> could only ever hold common words, at any threshold. The idea it was reaching for is now
> the `urme azi` filter, measured on CulturaX. The script still runs standalone; do not wire
> it back into `ui.db`. See docs/BACKLOG.md and CLAUDE.md.

For this project's actual goal — *produce a defensible list of Romanian
dictionary words that aren't in common modern use* — `wordfreq` plus
lemmatization probably collapses Phase 2 into a one-line lookup. This doc
explains why and how.

Companion to `docs/corpus-options.md` (which is mostly about going beyond
this) and `docs/methodology-v2.md` (which is mostly aspirational).

## What `wordfreq` is

[`wordfreq`](https://github.com/rspeer/wordfreq) by Robyn Speer is a
Python library for word frequencies in 40+ languages. It is not
itself a corpus — it is the **aggregated frequency tables** built from a
mix of corpora.

### How it's built

For each supported language, wordfreq combines up to **eight** sources:

- **Wikipedia** — encyclopedic
- **OpenSubtitles 2018 + SUBTLEX** — conversational / spoken
- **NewsCrawl 2014 + GlobalVoices** — news
- **Google Books Ngrams 2012** — books, where available
- **OSCAR** — web text
- **Twitter** — social
- **Reddit** — social

Romanian has **three** of these (Wikipedia, Subtitles, Web; plus some
Twitter), and only the **small** wordlist — no "large" tier.

### The figure-skating metric

For each word, wordfreq drops the **highest** and **lowest** per-source
frequency estimates, then averages the rest. The effect: any single
corpus's bias (Wikipedia's encyclopedic skew, Twitter's hashtag noise) is
trimmed. Robust by construction.

This is the **single most important methodological lesson** to learn from
wordfreq: don't trust any individual corpus, and don't try to weight them
manually — drop the outliers and average.

### Zipf scale

Output is on the **Zipf scale** = `log10(frequency_per_billion)`. So:

| Zipf | Frequency | Intuition |
|------|-----------|-----------|
| 7    | 1 per 100  | extremely common (the, and, …) |
| 6    | 1 per 1000 | common content word |
| 5    | 1 per 10K  | reasonably frequent |
| 4    | 1 per 100K | uncommon but known |
| 3    | 1 per million | rare; **wordfreq's reliability floor for small lists** |
| < 3  | below floor | returned as default; not real estimates |

For Romanian's small list, **anything with Zipf < 3 is "below the floor"**
— wordfreq returns 0 (or its default) rather than a real frequency, because
the underlying counts are too noisy at that level.

### Maintenance status

The project is in **sunset since around 2021** (Twitter killing its
academic API broke the rebuild). Data is frozen but stable. **For our
purposes that's a feature**: we want a stable reference baseline, not a
moving target.

## Why this nearly solves the project's problem

The project's framing is "find dictionary words not in common modern use."
The current Phase 2 builds a custom corpus to count occurrences. wordfreq
already aggregated 8 corpora across many registers and made the answer a
function call.

Reframe:

> Instead of building a corpus to find rare words, use `wordfreq` to
> filter out the words that *aren't* rare.

For each DEX low-frequency candidate:

- **Zipf ≥ 3** → modern signal across multiple corpora; **not forgotten**;
  filter out.
- **Zipf < 3 / 0 / below floor** → no modern signal in 8 aggregated
  corpora; **high-confidence forgotten**; keep.

## The recipe

```python
from wordfreq import zipf_frequency
import simplemma

THRESHOLD = 3.0  # wordfreq's small-list reliability floor for Romanian

def is_forgotten(word: str) -> bool:
    """True if a DEX candidate has no detectable modern usage signal."""
    lemma = simplemma.lemmatize(word, lang='ro')
    return zipf_frequency(lemma, 'ro') < THRESHOLD
```

That's it. Apply over `forgotten_words_curated.csv` (or directly over the
DEX low-frequency band from `lexemes.db`), keep the rows where
`is_forgotten` is true.

For ranking within the kept set, you can additionally:

```python
zipf = zipf_frequency(lemma, 'ro')
# zipf == 0  → strongest "forgotten" signal
# 0 < zipf < THRESHOLD → marginal; some signal but below reliability floor
```

Sort ascending by `zipf` for a "most forgotten first" ordering.

## What you give up

Honest accounting:

- **No resolution below Zipf 3.0.** wordfreq can't tell you whether a
  below-floor word has Zipf 2.5 or Zipf 0. They're all "rare." If you
  need to *rank* within the forgotten set with high resolution, you'd
  still need a custom corpus pass — but only over the below-floor subset
  (a few thousand words at most), which is much cheaper than a full pass.
- **Frozen at ~2021.** Words that became prominent or died in 2022–2026
  are mis-measured. For "forgotten Romanian dictionary words" this almost
  never matters — the dynamics are decadal at best.
- **No inflection awareness.** Romanian is morphologically rich. Always
  lemmatize before lookup. `simplemma` is one line.
- **Romanian is the small list.** No "large" wordlist exists, so the
  reliability floor is at Zipf 3.0 rather than the more permissive Zipf 1.0
  available for English / French / etc.

## When to add corpora on top

Consider supplementary corpora **only if** wordfreq's Zipf-3 floor proves
too coarse for your use case — i.e., if filtering at Zipf < 3 still leaves
many candidates that are actually common in modern Romanian.

If that happens, the smallest useful addition is:

- **OpenSubtitles RO** (via OPUS, free, no auth) — captures conversational
  register that even wordfreq's small Romanian list under-represents.
  Single-corpus pass, then filter words that appear ≥ N times in
  subtitles. This catches casually-used words that wordfreq missed.

Skip the rest of `docs/corpus-options.md` for the pragmatic goal. CulturaX,
mC4, Wikisource, Project Gutenberg, scraping — all aspirational unless
you're chasing the broader methodology in `docs/methodology-v2.md`.

## What this means for the existing code

If you adopt this recipe, the current Phase 2 pipeline (`process_corpus.py`
+ `validate_forgotten_words.py`) is largely redundant. A reasonable
migration:

1. **New script: `validate_with_wordfreq.py`** — ~30 lines, the recipe
   above, output `forgotten_words_validated.csv` with `zipf_frequency`,
   `is_forgotten`, and a confidence proxy (e.g. `1 - zipf/THRESHOLD`
   clamped).
2. **Demote `process_corpus.py`** to a one-shot reranker: run it only
   over the below-floor subset to get higher-resolution ranking among
   the genuinely forgotten words. This is a small fraction of the
   original workload.
3. **`validate_forgotten_words.py`** becomes redundant unless you want to
   keep the multi-signal confidence score (DEX × wordfreq × custom corpus).

This sidesteps the candidate-set mismatch bug (CLAUDE.md "Known issues"
#1) entirely — the bug only matters because the custom corpus pipeline
exists.

## TL;DR

```
pip install wordfreq simplemma
```

Three lines of Python replace ~600 lines of corpus-streaming code for the
common case. Use the rest of the documented infrastructure only if you
want to go beyond what wordfreq can express.
