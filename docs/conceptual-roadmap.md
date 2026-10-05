# Conceptual roadmap

> Historical critique; status reconciled 2026-10-05. The current implementation already uses
> diachronic panels, paradigm rollup, and sense-level metadata. References below to Wikipedia,
> future taxonomy, and guessed earlier weights describe older versions. Independent evaluation
> and calibrated uncertainty remain open. Use [F09](fixes/F09-evaluation.md) for the next scoped task.
> A normalized rate has consistent units across corpus sizes; sparse sampling and register differences limit inference.

This document sits above the implementation backlog in `docs/BACKLOG.md`. The
backlog there is about *code*: bugs, duplications, missing CLI flags. This
document is about *what the project is measuring* and whether the design can
honestly answer the question it claims to.

If a single line summarizes the conceptual move: the project is currently an
unsupervised heuristic on a single modern corpus, and it should be a
supervised, diachronic, lemma-level rarity-modeling problem with calibrated
uncertainty. Same data sources, mostly the same code surface — but the claims
become defensible.

## 1. "Forgotten" is undefined, so the pipeline can't be wrong

Today "forgotten" silently fuses at least five distinct phenomena:

- **Archaic** — common historically, no longer used (e.g. 19th-century terms)
- **Regional / dialectal** — alive in Banat or Oltenia, absent from standard
  Romanian
- **Specialist** — alive within botany, theology, law, traditional crafts
- **Register-restricted** — alive in literary or formal prose, absent from
  Wikipedia's encyclopedic register
- **Long-tail-but-active** — precise synonyms used rarely but recognized

Each warrants different evidence and a different downstream use. The DEX
`frequency` field collapses these; Wikipedia frequency collapses them again.
The pipeline measures the intersection of two collapses and applies a single
label. That's a category error, not a tuning issue.

**Move.** Drop the single label. Score along independent axes — *temporal
decay*, *register breadth*, *domain specificity*, *speaker recognition* — and
let the user (or downstream UI) combine them. If you want one number, derive
it explicitly from the axes.

## 2. There is no ground truth, so there is no way to know if it works

DEX itself marks entries with `înv.` (învechit / archaic), `arh.`, `reg.`,
`dial.`, `pop.`, etc. Those markers are essentially the answer the project is
trying to compute. They are currently scheduled as Phase 3 *enrichment*;
conceptually they should be the **labels**.

Reframed:

- Take the `înv.` / `arh.`-tagged subset as positive labels for "archaic"
- Take the high-DEX-frequency subset as negative labels
- Hold out a test split
- Compute precision / recall / AUC for the current pipeline
- Use the labels to *fit* the confidence weights (currently `0.3 / 0.5 / 0.2`,
  which are guesses). A trivial logistic regression with three features will
  likely beat them, and — more importantly — establish whether adding corpus
  signal beats DEX-frequency-alone. It might not.

This single change converts the project from a heuristic exercise into
something measurable. Without it, every "improvement" is unverifiable.

## 3. Wikipedia is the wrong oracle for "fell out of use"

Wikipedia RO is overwhelmingly:

- Written-formal register, no colloquial or literary prose
- Topic-skewed toward translatable encyclopedic content (biographies,
  geography, science)
- Edited by a small group of enthusiasts using a deliberately neutral style

So "absent from Wikipedia" can mean genuinely forgotten, *or* alive but
informal, *or* alive but literary, *or* alive in domains Wikipedia doesn't
cover well — exactly where archaic-feeling words concentrate.

To answer "fell *out* of use" you need a **diachronic** comparison: same word
tracked across eras. Concretely, a 19th–early-20th-century literary corpus
(Eminescu, Caragiale, Creangă, Slavici) as the *past* baseline, plus a
modern web-scale corpus as the *present*. The signal of interest is the
*ratio* of frequencies, with smoothing. See `corpus-options.md` for sources.

Words that were common then and rare now are the genuine archaisms. Words
that are rare in both are simply rare; words that are rare then and common
now are neologisms (a built-in negative control). Right now the project has
no temporal axis at all, so it cannot distinguish "fell out of use" from
"was always uncommon."

## 4. Surface-form matching makes the corpus numbers fictional

Romanian nouns have ~16 inflected forms; verbs have dozens. The pipeline
matches lemmas as bare strings. So "0 occurrences" of `bucle` may coexist
with hundreds of occurrences of `buclele`, `buclelor`, `buclat`, etc. Every
per-million figure in `validate_forgotten_words.py` is therefore a
*lemma-form* frequency, not a word frequency. The two diverge by an order
of magnitude.

This is in `readme.md` as a "known limitation," but it's not a limitation —
it invalidates the corpus side of the validator. `simplemma` is a pip
install and ~10 lines at the tokenizer (`process_corpus.py:39-54`). Until
that's done, the confidence scores are ranking lemma-string rarity, not word
rarity, and the project's headline numbers are mostly noise.

A second-order point: lemmatization also exposes **derivation** as a signal.
Often the lemma is "forgotten" but a derivative survives (`a otioza` rare,
`otios` recognizable). Tracking these together gives a more honest picture.

## 5. Zero-counts need confidence intervals, not bins

The validator's thresholds — `< 0.1 per million = confirmed_forgotten`,
`< 1.0 = likely_forgotten`, etc. (`validate_forgotten_words.py:151-172`) —
treat the corpus count as a point estimate. With ~1M tokens, the expected
count for a word with true rate 1e-6 is one. So "saw 0" is statistically
indistinguishable from "rate 1e-7" or "rate 0," yet the pipeline treats them
identically and assigns 0.99 confidence.

The right statistic is a one-sided upper bound:

- Beta-Binomial credible interval (or Good–Turing smoothing) on the
  per-million rate
- Report `rate ≤ X with 95% confidence` instead of a category
- Words with wide intervals (small corpus, zero hits) are *not yet
  evaluated*, not *confirmed forgotten*

This changes both the math and the UX: the project goes from "here's a
label" to "here's how confident we are, given how much we looked." The
latter is honest; the former isn't.

## 6. The pipeline is one-shot; it should be a feedback loop

The whole flow is run-scripts-emit-CSV. There's no place to:

- Mark a word as a verified false positive and have it stick across reruns
- Annotate a word as confirmed-archaic, regional, or specialist (which is
  exactly the labeled data §2 needs)
- Track score changes as new corpora are added

A small SQLite annotation table —
`(word, verdict, category, reviewer, reviewed_at, notes)` — turns the
project from a script into an iterating asset. The first 200 hand-labeled
rows feed §2's evaluation; subsequent rows compound. The current
architecture throws away every judgment ever made on the data.

## Tying it together

Of the six reframings, three are foundational and three are leverage:

**Foundational (unblock everything else):**

- §2 — Ground truth from DEX's own `înv.` / `arh.` markers
- §3 — Diachronic baseline corpus (Wikisource RO, 19th-century literary
  Romanian)
- §6 — Annotation table to capture labels as they're made

**Leverage (best ROI per unit of work):**

- §4 — Lemmatization (single dependency, single function, fixes the
  corpus-side measurement)
- §5 — Confidence intervals on zero-counts (replaces a guess with a
  statistic)
- §1 — Multi-axis scoring (cosmetic without §2; transformative with it)

Suggested ordering: §6 → §2 → §4 → §3 → §5 → §1.

## What this does *not* contradict

The implementation backlog in `docs/BACKLOG.md` ("Enhancement backlog") still
applies. Items there — fix the candidate-set mismatch, add `requirements.txt`,
consolidate MySQL→SQLite paths, add tests/CI — are prerequisites or
co-requisites, not alternatives. This document is what those items are
*for*.

The roadmap in `readme.md` ("Phases 3–5") describes a UI / API layer over
the same data. None of that is wrong, but it's premature: the data isn't
yet defensible. Build §2 first.
