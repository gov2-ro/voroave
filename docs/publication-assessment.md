# Is this worth a paper?

Assessment written 2026-08-11, in answer to exactly that question.
Reconciled 2026-10-05: measurements below are historical; [F09](fixes/F09-evaluation.md) defines the next evaluation task.
Normalized frequency is a valid unit. Unequal sampling resolution and corpus composition limit comparisons. Nothing here has been
acted on — it is a note to pick at later, not a plan. It sits beside
`docs/conceptual-roadmap.md` (the minimum credible methodology) and
`docs/methodology-v2.md` (the wider menu), and largely restates their §2 and §5 as *the
thing a reviewer will ask about first*.

**Short answer: yes, but not the paper that exists today.** There is a real contribution;
what is missing is an evaluation, and that is a bounded amount of work rather than a
redesign.

## State at the time of writing

| | |
|---|---|
| shortlist | 16,941 words, two seams |
| historical panel | `wikisource_ro` 45,218 forms / 5.42M counted occ; `lumro_ro` 25,930 / 1.83M |
| modern panel | `culturax_ro` 122,463 forms / 6.17B occ |
| loaded, not in any panel | `corola_ro` 1,813,746 forms / 637.8M occ; `subtitle_ro` 29,733 / 3.58M |
| human judgments collected | 366 annotations in the local `app.db` |
| evaluation against any ground truth | **none** |

## What is genuinely publishable

### 1. The paradigm rollup as a method

Counting surface forms and rolling them up through DEX's own 2.27M inflected forms — with
`n_lemmas` share-splitting for the 12% of forms claimed by more than one lemma — is a
better answer to the lemmatization problem than running a lemmatizer, and there is a
receipt: TTL's CoRoLa lemma lists put 12,176 on `strugur` and 724 on `strugure`;
`aggregate_by_family` puts it back at 749 / 12,034. The fix was the input file, not a
reconciliation algorithm.

That generalizes to any morphologically rich language with a machine-readable dictionary,
which is what makes it a *method* rather than a build note. It is also the part with the
cleanest demonstration already in hand.

### 2. The negative results — the strongest material here

Four measured traps, each of which a competent team would fall into, and none of which
anybody publishes:

- **The old shared ppm absence gate was misleading across corpora that differ 1,187×.** A shared `0.1 ppm` floor meant
  "< 1,697 occurrences" modern and "≥ 1.43" historical. It classified `zapciu` (1,322
  modern hits) as extinct and put `vapor`, `fluviu` and `cioban` in "declining".
- **A reference corpus is not a *modern* corpus if it spans 1945+.** CoRoLa wired into
  `modern_occ` for one build removed 35 words from the relevant seam — `birjă`,
  `dorobanț`, `vechil`, `dijmă`, `cocoană` among them, i.e. the project's best material.
  Against CulturaX per token: `condițiune` 112.8×, `comisiune` 49.6×, both pre-1953-reform
  spellings a 1945-onward corpus necessarily contains. Pinned by
  `test_corola_is_not_in_the_modern_panel`.
- **Register contamination inverts the signal.** `subtitle_ro` is ~1/6th folk-music
  television; clips carrying ≥3 genre markers are 15.6% of tokens but 27.5% of all
  shortlist-word occurrences, and **444 of the 2,446 shortlist words it attests appear only
  in those clips**. Scoring subtitle presence as "alive today" would rescue precisely the
  words the project exists to find.
- **Document counts are an independence claim, and the unit matters.** LUMRO's
  `document_count` is 111 distinct authors, not 175 novels: 638 of the 1,425 words it
  attests came from a single author, `jupâneșică` at 47 occurrences all by V.A. Urechia.
  Wikisource keeps counting pages because it has no author metadata — the asymmetry follows
  what is knowable.

"What counts as evidence that a word has fallen out of use" is a paper, and these four are
its body.

### 3. The resource

16,941 scored candidates with diachronic counts, dictionary attestation years (97%
coverage), definitions, synonyms, and four hide-flags with individually measured precision
— including the rules that were **measured and rejected** (`e → ă` fires 2,300 times to
find 69 twins and would equate `peți` with `păți`).

## What blocks it

**There is no evaluation.** `conceptual-roadmap.md` §2 identified this and it is still
open: `ARCHAIC_TAGS` in `make_shortlist.py:58` is used as a *feature*, never as held-out
labels. The paper currently cannot answer:

- does the corpus signal beat DEX `frequency` alone?
- does it beat `wordfreq` alone (which is already implemented, in `validate_with_wordfreq.py`)?
- are the hand-set `SCORE_*` weights better than uniform?

Every claim would rest on tuned constants with no error bars.

Three smaller blockers:

1. **Zero counts carry no uncertainty.** The historical panel holds ~7.25M counted
   occurrences. At that size "0 hits" and "true rate 1e-7" are indistinguishable, but
   `verdict()` reads `hist_occ >= 3 AND hist_docs >= 2` as fact. Roadmap §5, still open.
   The `HIST_MIN_OCC`/`HIST_MIN_DOCS` floors added 2026-08-08 make the signal honest but
   cannot create evidence — see the thin-corpus entry at the top of `BACKLOG.md`.
2. **The historical panel is register-skewed.** Wikisource plus 111 novelists is literary
   prose, so "absent historically" partly means "absent from literature".
3. **Licensing.** A resource paper needs a releasable artifact, and the DEX dump, CulturaX
   and the LUMRO novels have three different answers. The novels are the one that could
   stop a release outright; check before promising a dataset.

## Venues, best fit first

| Venue | Fit |
|---|---|
| **LChange** (Computational Approaches to Historical Language Change) | Exactly this topic; workshop scope tolerates a resource+method paper. Lead with the negative results — they land hardest with people who have made the same mistakes. |
| **ConsILR** (Iași, resources and tools for Romanian) | Direct audience, and the CoRoLa people will have opinions on the §3 finding |
| **LREC-COLING**, resource track | Right track, but needs the evaluation *and* a clean license |
| **CHR / NLP4DH** | If leading with the lexicographic-heritage framing |
| **ACL/EMNLP demo track** | The site itself, as a separate short paper |

(Venue names from memory — confirm each is still running and check the current CFP before
building a schedule around one.)

## Minimum path to submittable

1. Hold out `învechit` / `arhaizant` as labels, **with those tags removed from the
   features**, and report P/R/AUC.
2. Three baselines: DEX frequency alone, `wordfreq` alone, modern count alone. Show the
   diachronic ratio earns its place — the roadmap explicitly warns it might not.
3. A Beta-binomial (or Good–Turing) upper bound in place of the `hist_occ`/`hist_docs`
   thresholds.
4. Ablate `SCORE_*`.
5. A few hundred native-speaker "am auzit / n-am auzit" judgments. The site infrastructure
   exists and 366 annotations already prove the loop works — but note the existing four
   marks (`fav`/`lol`/`ascunde`/`meh`) are *aesthetic*, not recognition, so this needs its
   own question rather than a re-read of what is there.

Steps 1 and 2 are roughly a day each and would establish whether there is a paper before a
word of it gets written. Do those first.
