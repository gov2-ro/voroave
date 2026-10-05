# Corpus options beyond Wikipedia

> Historical options catalog. Reconciled 2026-10-05: Wikipedia/OSCAR is archived.
> Wikisource, LUMRO, and CulturaX are already loaded into the production panels.
> Wordfreq proved too coarse for this vocabulary and feeds no production score.
> Use [corpus expansion](corpus-expansion-plan.md) for measured decisions and
> [F09](fixes/F09-evaluation.md) for the next research task. Suggestions below are historical, not an execution queue.

Wikipedia RO was the right choice as a Phase 2 proof-of-concept: a known
HuggingFace dataset, streamable, no auth, well-formed. It's the wrong choice
as the *only* corpus the project ever runs against. This document catalogues
what's available, why it matters, and what to swap in.

Companion to `conceptual-roadmap.md` §3 (diachronic) and §5 (statistical
power).

> The proposed wordfreq shortcut was measured and rejected for the production ranking.
> Its historical rationale is retained in [the archived recipe](archive-obsolete/wordfreq-recipe.md).
> More corpora must improve evidence quality, not just add tokens.

## Why diversify

Wikipedia RO is **~80M tokens**, single-register (encyclopedic-formal),
heavily edited, topic-skewed toward translatable content. Two consequences:

- **Statistical floor.** A word with true rate 1e-7 is expected to appear
  ~0 times in 80M tokens. You cannot distinguish "very rare" from "absent."
  Every confidence claim about rare words is undersampled. Going to 1B+
  tokens shrinks credible intervals roughly with √n.
- **Sociolinguistic ceiling.** A word can be alive in literary,
  conversational, or specialist registers and never appear on Wikipedia.
  "Absent from Wikipedia" ≠ "forgotten." Different registers reveal
  different vocabulary.

The fix is two axes simultaneously: **scale** (more tokens) and
**register / era diversity**. What follows is what's available without
asking anyone for permission.

## Catalog

### Modern, open, large-scale (drop-in OSCAR replacements)

Ranked by quality-per-friction:

| Corpus | Source | Romanian size | Auth | Notes |
|--------|--------|---------------|------|-------|
| **CulturaX** | `uonlp/CulturaX` (HF) | ~40B tokens | None | Cleaned, deduplicated CC + mC4 across 167 languages. Late 2023. Best single OSCAR replacement. |
| **mC4** | `allenai/c4` config `multilingual` filter `ro`, or legacy `mc4` | several B tokens | None | Google's cleaned Common Crawl. Standard multilingual baseline; well-cited. |
| **MADLAD-400** | `allenai/MADLAD-400` | several B tokens | None | Another open, deduplicated CC derivative. Comparable scale to mC4. |
| **CC-100 RO** | FAIR direct download | ~33 GB | None | Older but trusted; lots of academic precedent. Direct HTTPS. |
| **FineWeb-2** | `HuggingFaceFW/fineweb-2` (HF) | sizeable | None | 2024 high-quality multilingual web. Arguably cleanest of this class. |
| **Common Crawl raw** | `commoncrawl.org` | uncapped | None | Underlying source for the above. Use only if cleaned derivatives miss something. |

### Historical / diachronic (the genuine unlock)

These enable the *then* baseline that §3 of the conceptual roadmap calls
for. None require authentication.

| Corpus | Source | Period | Notes |
|--------|--------|--------|-------|
| **Wikisource RO** | `dumps.wikimedia.org` (`rowikisource`) | 19th–early-20th c. | Public-domain Romanian literature: Eminescu, Caragiale, Creangă, Slavici, Rebreanu. **Single highest-leverage corpus** for the project's stated thesis. Same dump format as Wikipedia, so existing tokenizer / streaming code works unchanged. |
| **Project Gutenberg (Romanian)** | `gutenberg.org` | 19th–early-20th c. | ~50 books. Small but cleanly OCR'd, public domain, direct download. Complement to Wikisource. |
| **Biblioteca Digitală Națională (DigiBuc)** | `digibuc.ro` | 19th–20th c. | Romanian National Library digital archive: historical newspapers, books. Bulk download requires scraping. OCR quality varies, period coverage is unmatched. |
| **BCU Cluj / DigiTeca BCU** | `bcucluj.ro` | 19th–20th c. | Cluj University library digital collection. Similar to DigiBuc with a more academic skew. |
| **ROMTEXT / DLR** | Romanian Academy | various | Largely gated / research-only, but derivatives have appeared in open datasets. Worth a Google Scholar pass. |

### Register-diverse modern (counter Wikipedia's encyclopedic bias)

| Corpus | Source | Register | Auth | Notes |
|--------|--------|----------|------|-------|
| **CC-News (RO filter)** | `commoncrawl.org` / HF mirrors | News | None | Common Crawl's news subset. Romanian portion is non-trivial. Differs from Wikipedia: more verbs, more colloquialism, more recency. |
| **OpenSubtitles RO** | OPUS | Conversational / spoken-like | None | Movie subtitles. The closest open thing to Romanian conversational data. Large. |
| **Europarl / DGT / EU Bookshop** | OPUS | Bureaucratic-formal | None | EU translations. Good as a register baseline ("does this word ever appear in any context"). |
| **TED2020** | OPUS | Spoken-prepared | None | TED talk transcripts in Romanian. |
| **Reddit r/Romania archives** | `academictorrents.com` (pre-2023 Pushshift dumps) | Colloquial-online | None (research use) | Pushshift API is restricted now, but archived dumps are accessible for academic use. The missing register in nearly every Romanian NLP corpus. DIY tooling. |
| **HPLT v2** | `hplt-project.org` | Web mixed | None | Open EU project, multilingual web crawl. Public datasets, downloadable. |

### Specialized / curated (high quality, some friction)

| Corpus | Source | Size | Auth | Notes |
|--------|--------|------|------|-------|
| **CoRoLa** | `corola.racai.ro` | ~1B words | Free registration | Reference Corpus of Contemporary Romanian, Romanian Academy. Multiple registers (literary, journalistic, scientific, juridical, administrative). Not gated like OSCAR — just an account. Worth it as a curated reference comparison. |
| **MaCoCu-RO** | `macocu.eu` | sizeable | None | EU-funded multilingual web corpus, Romanian portion. Public. |

## Recommended starter set (pragmatic, all-public)

Replace the current `Wikipedia + OSCAR` setup with **four** axes:

| Axis | Corpus | Tokens (rough) | Auth | Purpose |
|------|--------|----------------|------|---------|
| Modern formal | Wikipedia RO | ~80M | None | (existing) |
| Modern web / mixed | **CulturaX RO** | ~10B+ | None | Statistical power; OSCAR replacement |
| Modern news | **CC-News RO** | ~hundreds of M | None | Register check vs. encyclopedic |
| Historical literary | **Wikisource RO** | ~hundreds of M | None | The diachronic baseline |

This gives:

- Two orders of magnitude more tokens than today
- At least three distinct modern registers (encyclopedic, news, web-mixed)
- A *then* corpus to compare *now* against
- No HuggingFace login walls or scraping of grey-zone sources

Optional additions later: OpenSubtitles for conversational, Reddit dumps for
colloquial-online, CoRoLa for a curated reference comparison.

## Integration notes

The good news: the existing schema almost works.

- `corpus_word_frequency` (`process_corpus.py:75-91`) already keys on
  `(word, corpus_name)`. Adding new corpora is a `corpus_name` enum
  extension, no migration.
- Add a `corpus_metadata` table with
  `(corpus_name, era, register, total_tokens, source_url, license,
  collected_at)` so downstream scoring can weight or stratify by axis
  instead of summing blindly. This is the SQL backbone for the diachronic
  comparison.
- For the diachronic comparison, the validator should not compute a single
  `freq_per_million` summed across all corpora (which is what
  `validate_forgotten_words.py:109-110` does today). It should compute
  *per-corpus* rates, then derived signals like
  `log(freq_modern / freq_historical)`.
- Streaming via `datasets.load_dataset(..., streaming=True)` works for
  everything HF-hosted. Wikisource and Gutenberg need a small fetch + parse
  step; both are XML-ish dumps with mature parsers (`mwparserfromhell` for
  Wikisource).

## What to do next

If you only do one thing: add **Wikisource RO** as a second corpus. It's
the same loading code as Wikipedia (`wikimedia/*` HF dataset family or a
direct dump from `dumps.wikimedia.org/rowikisource/`), no auth, and it's
the only addition that makes the "fell out of use" claim *defensible*
rather than aspirational.

If you do two: add **CulturaX RO** alongside, drop OSCAR, and now you have
both more tokens *and* a temporal axis. That's the minimum credible setup.
