# Methodology v2 — broader moves (aspirational)

> Status reconciled 2026-10-05. This is a historical menu, not the current implementation plan.
> The corpus pipeline already includes paradigm rollup and two panels. The wordfreq shortcut
> described below proved too coarse and was not retained in production. Evaluation remains open.
> Use [F09](fixes/F09-evaluation.md) for a bounded next task; no scoring changes are authorized here.

> **Scope note.** The user's actual goal for this project is pragmatic:
> produce a defensible list of Romanian dictionary words that are not in
> common modern use. The earlier proposed `wordfreq` recipe
> (`docs/archive-obsolete/wordfreq-recipe.md`) is retained as historical reasoning. This
> document captures the more ambitious methodological moves for future
> reference. **Nothing here is required to ship a useful list.** Treat it as
> a menu, not a spec.
>
> Companion to `docs/conceptual-roadmap.md` (which lays out the *minimum
> credible* methodology). This doc goes wider.

## Reframe 0: Pick a user

Methodology depends on what the output is *for*. Same word list serves
these audiences badly differently:

- **Lexicographers** want high-precision flags with provenance ("this entry
  should be marked `înv.` in DEX v2027").
- **Writers / poets** want expressive, recoverable words ranked by
  *aesthetic* potential, not rarity.
- **Educators** want curated short lists with example sentences and
  synonyms.
- **Diachronic linguists** want decay trajectories per word with confidence
  intervals.
- **Cultural-heritage workers** want to map *which kinds* of vocabulary
  disappeared and why.

Picking even one forces concrete methodological choices. A reasonable
default pairing for this project: **lexicographer + diachronic linguist**.
They share most of the substrate.

## Reframe 1: "Forgotten" → "lexical decay" (process, not state)

`forgotten=True/False` collapses a process into a label. A smarter
primitive: **per-word usage trajectory over time**, plus derived
statistics:

- **Decay rate** — fitted exponential slope of normalized frequency over
  decades. Steep negative = actively dying. Flat low = stably rare. Flat
  high = unaffected.
- **Half-life** — when did usage drop to half its peak?
- **Trajectory shape** — clusterable: smooth decline, cliff, U-shape
  (revival), oscillating, peak-then-die. Each shape is a different
  sociolinguistic phenomenon.

Even with two time bins (Wikisource ~1880 + Wikipedia ~2020) you can
compute log-ratios. With per-decade slices from a digitized newspaper
archive (DigiBuc) you can fit actual curves. Words then get a **trajectory
class**, not a binary label — more informative *and* more honest about
uncertainty.

## Reframe 2: Use the LLM oracle (this is 2026)

The biggest unused lever. Current LLMs are highly capable on multilingual
+ Romanian-specific tasks.

- **LLM-as-annotator.** Run a few thousand candidate words through Claude
  or a Romanian-tuned model with a structured prompt:
  `{active, declining, archaic, regional, technical, dialectal}`, plus an
  example sentence per register and a likely modern synonym. A few hundred
  dollars buys you a labeled training set that would take a year of
  native-speaker volunteering.
- **LLM-as-judge for ranking.** Pairwise comparisons → Elo. Smoother
  ranking than thresholded frequencies.
- **LLM-as-corpus-substitute.** Carefully — but multilingual LLMs have
  implicit frequency priors. Useful for triage.
- **LLM-generated synthetic test data.** Ask the model to use the word in
  a modern news sentence; if the result feels archaic to a human checker
  (or to another LLM-as-judge), that's signal.
- **Bootstrap loop.** LLM labels → small classifier on derived features →
  classifier-vs-LLM disagreements queued for human review.

The shift: **stop treating ground truth as something to wait for.**
Bootstrap it.

## Reframe 3: Mine all of DEX, not just `frequency`

DEX is rich. Each column is a feature:

- **Register markers** (`înv.`, `arh.`, `reg.`, `dial.`, `pop.`, `fam.`,
  `livr.`, `arg.`) — answer key for obvious cases. Use as labels and as
  features.
- **First attestation dates** — words first recorded in 1700 vs. 1900 have
  different baseline expectations. Critical for trajectory modeling.
- **Etymology layer** — Turkish loans peaked under Ottoman influence and
  largely vanished by 1900; Greek liturgical vocabulary is more stable;
  Slavic substrate is bedrock; French / Italian came in waves. Bucketing
  by etymology reveals patterns of decay.
- **Definition text** — gloss starting with "*Învechit pentru* X" gives
  you X as the modern synonym, free supervision.
- **Word family graph** — forgotten/living ratio within a family is
  informative.
- **Sense disambiguation** — most polysemous words have one obsolete sense
  among several active ones. Per-sense ≠ per-word.

A logistic regression on five DEX-derived features alone, evaluated against
`înv.` labels, will probably hit 80%+ AUC. Anything fancier should beat that
baseline or it's not earning its complexity.

## Reframe 4: Semantic shift, not just frequency shift

Frequency is one signal; **meaning drift** is another. Diachronic word
embeddings (Hamilton et al. 2016, Kim et al. 2014, modern transformer
extensions) train word vectors on time-binned corpora and measure how a
word's neighborhood changes.

For Romanian: train two embedding spaces — one on Wikisource (~1880), one
on a modern corpus. Align with Procrustes. For each word, compute cosine
distance between its 1880 vector and 2020 vector. High distance = meaning
shifted (often register change, not death). Low distance + low frequency =
stably-known-but-unused (passive vocabulary). Low distance + zero
frequency = genuine death.

This separates **forgotten** from **transformed** — two phenomena the
current pipeline conflates.

## Reframe 5: Topic-and-register-controlled rarity

A word is "rare" relative to *something*. "Chivot" (tabernacle) is rare in
general Romanian, normal in religious texts. "Ștaif" (collar stiffener) is
rare everywhere now because the *concept* receded.

- Run topic modeling (LDA or BERTopic) over the corpus.
- Compute per-word frequency *within each topic*.
- "In-topic rare" → genuine attrition. "Out-of-topic rare" → specialization,
  not forgottenness.

This single distinction would clean up a substantial chunk of false
positives.

## Reframe 6: Synonym competition

Languages don't lose words in a vacuum — usually a synonym wins.
"Doftor" → "doctor"; "feliu" → "fel." The *competition event* is
quantifiable:

- Identify candidate synonym pairs (DEX cross-references, Wiktionary,
  embedding nearest-neighbors).
- For each pair, plot relative frequency over time.
- Cross-over points and replacement velocity are richer than per-word
  frequency.

Output bonus: the modern synonym becomes part of the entry — useful for
writers, educators.

## Reframe 7: Make it a benchmark, not a CSV

Most durable move. Right now the project produces a list — a one-shot
artifact that ages, isn't easy to cite, can't be improved by anyone else.

Reframed as a **benchmark**:

- Labeled dataset (multi-annotator, multi-axis) of N thousand Romanian
  words.
- Formal task: given the entry + features, predict the labels.
- Public leaderboard.
- Versioned releases.

Now the project compounds. Other Romanian-NLP work has something to
evaluate against. Iterations have a measurable target. The dataset is more
valuable than any single model trained on it. HuggingFace is the natural
home.

## Reframe 8: Active-learning UI for native speakers

A small web app — Tinder-for-Romanian-words — where speakers swipe
`familiar / unfamiliar / never-heard-of-it`, optionally tagged with their
region and age.

- 5 native speakers × 30 minutes/day × a week ≈ 10,000 labels.
- Active learning queues most-uncertain words first.
- Dialect tagging (`speaker_region`) and generation tagging
  (`speaker_birthdecade`) immediately surfaces what frequency alone can't:
  regional vs. generational vs. universally forgotten.

HF Spaces free tier hosts something like this. Gradio gets 80% of the UI
for free.

## A "smart approach" recipe (if doing all of it)

1. Pick the user (lexicographer + diachronic linguist).
2. Define the deliverable as a **benchmark dataset** with multi-axis
   labels, not a CSV.
3. Bootstrap labels with LLM annotation + native-speaker validation through
   a Spaces UI.
4. Build features from all of DEX (frequency, register, etymology,
   attestation, sense structure, word family) plus per-corpus lemma rates
   plus diachronic-embedding distances.
5. Train a calibrated classifier with proper held-out evaluation; report
   decay trajectories with confidence intervals.
6. Ship as a versioned HF dataset + benchmark; model is secondary.
7. Iterate via the active-learning loop.

Months-long ambition, not a weekend hack. Every individual step has a
meaningful 1-day version.

## What this is *not* contradicting

- `docs/conceptual-roadmap.md` — the minimum credible methodology
  (lemmatization, ground truth from `înv.` markers, confidence intervals,
  diachronic baseline). Those are prerequisites for anything here.
- `docs/archive-obsolete/wordfreq-recipe.md` — historical shortcut rationale; measured coverage proved too coarse for the production ranking.
- `docs/BACKLOG.md` — implementation backlog. Code-level fixes still needed
  regardless of which methodology layer you adopt.

## Throughline

Stop trying to compute "forgotten" from frequency thresholds. Treat it as
a labeling problem with rich features and rigorous evaluation. That single
shift dwarfs every other improvement combined — but it's optional if all
you need is a list.
