# Ranking evaluation protocol (F09)

Status: protocol ready for owner review; study not run.
Version: 1.0 (draft). Date: 2026-10-05. Brief: [F09](../fixes/F09-evaluation.md).

This file is the pre-registration. It fixes the questions, labels, sample, split, baselines,
metrics and decision rules before any judgment exists. The owner approves it, then it is frozen.
After approval, every change goes in the amendment log (section 15) with a date and a reason.
No annotator has been contacted. No judgment has been collected. No weight has changed.

## 1. Purpose and limits

Question: does the ranking identify rediscoverable vocabulary better than simple baselines?

The output of the project is a heuristic candidate ranking. It is not proof of speaker
recognition or extinction. This study adds the first independent human reference.

Limits that the study cannot remove:

1. The population is the shortlist in `public/data/ui.db` (18,270 words). The shortlist is already
   gated by the pipeline. The study measures ranking quality inside it. It does not measure
   recall: words the pipeline never admitted are not sampled.
2. Annotators are a small, non-random group. Recognition depends on age and region.
   The result describes those annotators, not "Romanian speakers".
3. Corpus-derived verdicts are not independent ground truth. The verdict and the score use the
   same corpus counts. The study never uses a verdict as a reference label for a corpus-based feature.
4. Fav/lol/meh marks are taste. They do not measure recognition. This study does not use them.
   It does not read `private/app.db`.
5. Historical coverage is about 19.4M tokens. Modern coverage is about 17.0B tokens (about 876 times larger).
   A zero historical count is insufficient evidence, not proof of non-use.

## 2. Target constructs: three separate questions

Each word receives three separate labels. The study never fuses them into one label
and never reports a composite as a headline result.

| Id | Construct | Question to the annotator (short) |
|---|---|---|
| Q1 | Recognition | Do you know this word? Do you know what it means? |
| Q2 | Current use | Do people use this word today? |
| Q3 | Rediscovery value | Would the word be worth bringing back to attention? |

Two further items support the analysis and are not targets:

- Q2b (register versus decline): did the word once belong to everyday speech, or only to books?
- Free-text note and one error category (section 10).

Why three: a word can be recognised and unused (the project's best material, for example `zapciu`).
A word can be unrecognised and still be valuable. A word can be in use and be worthless to rediscover.
A single "forgotten" label would hide which of these a ranking gets right.

### Expected direction (hypotheses, set now)

- H2: a higher score goes with lower current use (Q2). Primary.
- H3: a higher score goes with higher rediscovery value (Q3). Primary.
- H1: a higher score goes with higher recognition (Q1). Secondary.
  Reason: the project reads high DEX prominence plus corpus absence as "once established, now faded".
  A rise in the unrecognised share with score would be a finding, not an error.

## 3. Label scales

Every scale has two non-numeric codes. `?` means "cannot decide" (abstain). `X` means "the entry is defective"
(not a word, wrong definition, inflected form). Both are kept and reported. They are never recoded to a number.

**Q1 Recognition** (shown the word alone, stage A; see section 4)

| Code | Meaning |
|---|---|
| 0 | I have never seen or heard this word. |
| 1 | The word looks familiar. I cannot say what it means. |
| 2 | I know the word and I know what it means. |

**Q2 Current use** (shown word and definition, stage B)

| Code | Meaning |
|---|---|
| 0 | Nobody uses it today. It appears only in old texts or reference works. |
| 1 | Rare. Used only in a region, a trade, a literary style, or as a joke. |
| 2 | Used normally today. |

**Q2b Register versus decline**

| Code | Meaning |
|---|---|
| B | It belongs to books or formal writing. It was never everyday speech. |
| S | It was everyday speech once. It faded. |
| N | It is not old: it is regional, specialist or new. |
| ? | Cannot decide. |

**Q3 Rediscovery value**

| Code | Meaning |
|---|---|
| 0 | No. The word adds nothing. |
| 1 | Maybe. Useful to a few people or in few contexts. |
| 2 | Yes. The word is useful, expressive or beautiful. A modern speaker would gain from it. |

Q3 asks for a judgment of value, not of fame. An annotator may rate a word `2` that he or she
has never seen before reading the definition.

## 4. What annotators see

The annotator sees only the word and its definition. Never the score, verdict, seam,
flag, tier, count, dictionary list, register tag from the database, or position in the ranking.

The export `annotator_export.csv` has exactly four columns:
`item_id, word, definition, senses`. `definition` is the `words.definition` text.
`senses` is the numbered sense text for structured entries, without sense tags (tags carry register labels).
The sampler test `tests/test_eval_sample.py` checks the column list.

Two stages protect Q1 from the definition:

- Stage A: the tool shows the `word` only. The annotator records Q1.
- Stage B: the tool then shows the definition. The annotator records Q2, Q2b, Q3, the optional note.

Stage A cannot be undone after Stage B opens. A spreadsheet cannot enforce this. A simple form tool can.
Open decision for the owner: tool choice (section 14). A fallback is two separate files, A first and B later.

Known residual cue: definitions can contain text such as "(înv.)" or a citation author from the 19th century.
That is dictionary content. The study keeps it and records it as a limitation. The secondary analysis (section 9)
removes the matching features. Annotators do not receive instructions to ignore it.

Item order is a hash shuffle, so row order carries no stratum or score information.

## 5. Annotator instructions

Romanian text is what the annotator reads. The English gloss is for reviewers only and is not shown.

### 5.1 Romanian text (annotator-facing)

> **Evaluarea cuvintelor românești. Instrucțiuni**
>
> Vă vom arăta cuvinte, unul câte unul. Nu există răspunsuri corecte sau greșite. Ne interesează
> părerea dumneavoastră sinceră. Nu căutați cuvântul pe internet și nu întrebați pe altcineva.
> Dacă nu sunteți sigur, alegeți `?`.
>
> **Pasul A. Vedeți doar cuvântul.** Răspundeți la o singură întrebare.
>
> 1. *Cunoașteți cuvântul?*
>    0 = Nu l-am văzut și nu l-am auzit niciodată.
>    1 = Îmi pare cunoscut, dar nu știu ce înseamnă.
>    2 = Îl cunosc și știu ce înseamnă.
>
> Apăsați „Mai departe". După aceea nu vă mai puteți schimba răspunsul.
>
> **Pasul B. Vedeți și explicația cuvântului.** Răspundeți la trei întrebări. Fiecare întrebare este
> separată. Răspunsul la una nu trebuie să-l determine pe celălalt.
>
> 2. *Se folosește cuvântul astăzi?* (în vorbire, în scris, la televizor, între oameni pe care îi cunoașteți)
>    0 = Nu îl folosește nimeni astăzi. Apare doar în texte vechi sau în dicționare.
>    1 = Rar. Îl folosesc doar unii oameni: într-o regiune, într-o meserie, într-un stil literar sau în glumă.
>    2 = Se folosește normal astăzi.
>
> 2b. *Cum ar trebui să-l descriem?*
>    B = E un cuvânt de cărți sau de scris îngrijit. Nu a fost niciodată vorbire de zi cu zi.
>    S = A fost odată vorbire de zi cu zi. S-a stins treptat.
>    N = Nu e vechi: e regional, de specialitate sau nou.
>    ? = Nu pot decide.
>
> 3. *Ar merita cuvântul să fie readus în atenție?* Gândiți-vă dacă un vorbitor de azi ar câștiga
>    ceva folosindu-l: precizie, expresivitate, frumusețe.
>    0 = Nu.
>    1 = Poate. Ar fi util pentru puțini oameni sau în puține situații.
>    2 = Da.
>
> **Coduri speciale.** `?` = nu pot decide. `X` = problemă cu intrarea (nu e un cuvânt, explicația
> nu se potrivește, e doar o formă gramaticală a altui cuvânt). Dacă alegeți `X`, scrieți o notă scurtă.
>
> **Notă opțională.** O propoziție despre motiv. Nu scrieți date personale.
>
> **Ce nu măsurăm.** Nu ne interesează dacă vă place cuvântul. Nu ne interesează dacă cuvântul
> este „corect". Întrebările 2 și 3 sunt diferite: un cuvânt poate fi rar și totuși merită readus.
> Un cuvânt poate fi folosit des și să nu merite nicio atenție.

### 5.2 English gloss (reviewers)

The annotator sees one word at a time. There are no right answers. The annotator must not search
the web or ask another person. When unsure, choose `?`.
Step A shows the word only. Q1: 0 never met it; 1 looks familiar, meaning unknown; 2 knows it and its meaning.
The answer is locked after "Next".
Step B shows the definition. Q2 current use: 0 nobody today, old texts only; 1 rare, regional, trade, literary or jokes;
2 normal today. Q2b: B books only; S once everyday, faded; N regional, specialist or new; `?`.
Q3 rediscovery value: 0 no; 1 maybe; 2 yes (precision, expressiveness, beauty for a modern speaker).
Special codes: `?` cannot decide; `X` the entry is defective (add a note).
Optional one-sentence note without personal data. The study does not measure taste:
Q2 and Q3 are separate questions, and a rare word can still deserve revival.

## 6. Sampling design

Script: `tools/eval_sample.py` (version 1.0.0). Input: `public/data/ui.db`, opened read-only.
Output: `data/eval/annotator_export.csv`, `data/eval/sample_key.csv` (gitignored).
Committed: `docs/eval/sample-words.tsv` (item id, word, split, stratum; 70 KB; no scores and no private data)
and `docs/eval/sample-provenance.json`.

- **Seed:** `f09-voroave-eval-v1`. The seed is a string hashed with SHA-256. No random-number generator state is used.
- **Size:** N = 1,200 words.
- **Strata (cells):** seam (2) x verdict (4) x score band (5) x attribute (4). 58 non-empty cells are sampled.
  - Seam: `relevant`, `curiosity`.
  - Verdict: `extinct`, `declining`, `historical_only`, `absent`.
  - Score band (`quality_score`): <60, 60-79, 80-91, 92-104, >=105. 92 is `RELEVANT_MIN_SCORE`.
  - Attribute, one per word, with this precedence: `variant` (`variant_like`, `archaic_spelling` or `dex_variant`),
    then `regional` (`regional_only`), then `derived` (`deverbal_like` or `diminutive_like`), else `plain`.
- **Definition kind:** `structured` (the word has rows in `senses`) or `flat`. Inside each cell the draw alternates
  structured and flat items, so both kinds appear wherever the cell holds both. Result: 577 structured, 623 flat.
- **Allocation:** each non-empty cell gets min(size, 3). The remaining quota goes in proportion to the square root of the
  cell size, capped at the cell size. Square-root allocation over-samples small cells (extinct, regional, high scores)
  that proportional sampling would leave empty.
- **Within a cell:** items are ordered by SHA-256 of seed and word. The first items by that order are taken.
- **Weights:** each item has a weight = cell size / cell quota (inverse inclusion probability).
  All population estimates use these weights. Unweighted results are secondary.
- **Build identity:** the provenance file records `ui.db` size, SHA-256, modification time and row count
  (`ui.db` stores no build date; the modification time is a proxy), the seed, strata counts, and the SHA-256 of both
  exports. Re-running with the same `ui.db` bytes gives byte-identical files. A different build gives a different sample.
  Do not re-draw after labelling starts. If `ui.db` is rebuilt, keep the named build for analysis.

Realised sample (build in the provenance file):

| Stratum | n |
|---|---|
| seam: relevant / curiosity | 283 / 917 |
| verdict: absent / declining / extinct / historical_only | 345 / 319 / 53 / 483 |
| score band: <60 / 60-79 / 80-91 / 92-104 / >=105 | 187 / 434 / 296 / 225 / 58 |
| attribute: plain / variant / regional / derived | 612 / 279 / 191 / 118 |
| definition: flat / structured | 623 / 577 |
| split: development / test | 481 / 719 |

## 7. Held-out split by related words

Random word-level splitting leaks: `coconaș` in training and `cocon`-related words in test share one story.
The split is by group.

Group links (all computed over the whole table of 18,270 words, not only the sample):

1. `variant_of`
2. `spelling_of`
3. `dex_variant_of`
4. `deverbal_of`
5. the target of "Diminutiv al lui X" when `diminutive_like` is set
6. words that are forms of one lexeme in `inflected_forms.db` (shared inflection families)

Targets need not be in the table. Two words that share a target form one group. Links are transitive (union-find).
The group id is the smallest member string. The split is `SHA-256(seed, "split", group id) mod 100 < 40` for
development, else test. Result: 481 development and 719 test items in 1,174 groups.

Rules:

- The development split (40%) serves for the pilot, for fixing instructions, and for fitting any candidate weights.
- The test split (60%) is held out. Nobody fits or tunes anything on it.
- Exactly one frozen candidate scoring variant per question is evaluated once on test (section 12).
- Group links are conservative: they cannot see relations that no table records
  (for example unrelated paradigms such as `vivliotică`/`bibliotecă`). This residual leakage is a stated limitation.
- The flag-based links come from the same build as the flags. The shared-lexeme link needs `data/processed/inflected_forms.db`.
  The provenance file records its size and SHA-256.

## 8. Sample size rationale

Planning figures. They assume the weighted design. Kish effective sample size
n_eff = (sum w)^2 / sum(w^2): about 779 for all 1,200 items and about 458 for the 719 test items.

| Quantity | Estimate | 95% half-width (planning) |
|---|---|---|
| Weighted proportion on test (worst case p = 0.5) | n_eff 458 | +/- 4.6 percentage points |
| Same, all 1,200 items | n_eff 779 | +/- 3.5 percentage points |
| Proportion inside one cell of about 50 items | n = 50 | +/- 14 percentage points (read as descriptive) |
| Spearman rho on test (rho near 0.4), Fisher z | n_eff 458 | about +/- 0.09 |
| Paired difference of two rank metrics on the same items | n_eff 458 | about +/- 0.04 to 0.06 (to confirm by bootstrap on the pilot) |
| Weighted kappa, two annotators on all 1,200 items | n = 1,200 | standard error about 0.02 to 0.03 |
| Weighted kappa on 719 test items | n = 719 | standard error about 0.03 to 0.04 |

Meaning: the study can separate a difference of about 0.05 in AUC or precision. It cannot rank two baselines
that differ by 0.02. It can say little about small cells (extinct words: 53 items). Section 12 sets
decision thresholds above these half-widths on purpose.

Design: two annotators label every item. A third annotator labels items on which the first two differ by
more than one scale step on Q1, Q2 or Q3, or differ on abstain. Workload: 1,200 items x 2 annotators x 4 answers.
Owner decides the final number of annotators (section 14). More annotators lower label noise
and do not lower sampling error.

Pilot: 60 development items, labelled first by all annotators. The pilot checks instructions and the tool.
Pilot labels are kept as development data. The instructions are fixed after the pilot. Pilot items are not re-labelled.

## 9. Baselines and reference labels

All baselines are scalar scores computed from `ui.db` columns. A higher value means "better candidate".
No baseline is fitted on test.

| Baseline | Definition |
|---|---|
| B1 modern count | `-log(1 + modern_occ)`. Fewer modern occurrences rank higher. |
| B2 DEX prominence | `dex_frequency` (literary-prominence score, not usage; 0 means missing data). |
| B3 uniform component weights | The mean of the eight components of `make_shortlist.score()`, each scaled to 0..1 by its own maximum (below). |
| B4 current score | `quality_score`. |
| B5 wordfreq (coverage-limited) | `zipf_frequency` in `ui.db`. Lower Zipf ranks higher. |
| B6 wRodfreq (coverage-limited, offline) | Zipf from `../gov2/wrodfreq`, computed outside `ui.db`, for analysis only. |

B3 components, from `make_shortlist.score()` (`make_shortlist.py` lines 189-211):

| Component | Points in `score()` | Scaled to 0..1 by |
|---|---|---|
| Verdict (`SCORE_VERDICT`) | 30 / 30 / 20 / 12 | 30 |
| Modern rarity (`SCORE_MODERN`, default 4) | 25 down to 4 | 25 |
| Historical attestation (`SCORE_HIST`, default 25) | 0 up to 25 | 25 |
| DEX prominence (`SCORE_DEX_FREQ`) | 0 up to 20 | 20 |
| Dictionary count (`SCORE_DICTS`) | 0 up to 12 | 12 |
| In a current dictionary (`SCORE_CURRENT_DICT`) | 13 | 13 |
| Has definition (`SCORE_HAS_DEF`) | 5 | 5 |
| Moderate family ratio penalty (`PENALTY_FAMILY`) | -8 | 8, subtracted |

B3 = (sum of the first seven scaled values - family penalty scaled) / 8. This equals "every component weighs the same".
The question B3 answers: do the hand-set weights beat equal weights?
The point values in `score()` are guesses, not fitted values. B4 versus B3 tests that.

Missing values:

- B5 and B6 cover few words. In `ui.db`, `zipf_frequency` is above 0 for 38 of 18,270 words
  (8 of the 1,200 sampled words). Report B5 and B6 on the covered subset with the count and share.
  Report the uncovered words separately. Never impute a value, and never treat "missing" as "rare".
  Compare B5 and B6 with B4 on the same covered subset only.
- B2 treats `dex_frequency = 0` as missing. Report the missing count. Exclude them from B2's metrics and compare
  B4 on the same subset.

### Leakage controls

The human labels (Q1 to Q3) are independent of the database. They are the primary reference.

A secondary, exploratory analysis may use dictionary labels as a reference (for example "tagged old in DEX" as a
positive for archaic). In that analysis the evaluated features must not contain the labels or their proxies.
Remove these from every baseline and from the current score in that analysis:

- `dex_register` and `regional_only`, and every flag built from them;
- `confidence_tier` and `tier` (the tier uses the `învechit` tag);
- `in_current_dict`, `newest_dict_year`, `dict_count`, `sources` (dictionary coverage and dates are proxies for the tags);
- `dex_etymology`, `dex_pos` (partly derived from the same entries);
- `dex_frequency` when the reference is a DEX property that tracks it.

A score without these terms is a different score. Report it as "score minus dictionary terms". Do not call it B4.

Do not use the corpus verdict, `hist_occ`, `modern_occ` or the corpus-derived flags as reference labels for a model
that reads the same counts. A verdict-versus-score agreement is a consistency check, not evidence.

Annotator labels may be compared with DEX-derived flags (regional, variant) to describe error categories (section 10).
That is a description, not a metric.

## 10. Qualitative error categories

For every item where annotators and the ranking disagree, a reviewer assigns one category. The reviewer
works on the key file, after labelling closes. Disagreement means: the item is in the top third of B4 within its seam
and annotators give Q2 = 2 or Q3 = 0, or the item is in the bottom third and annotators give Q2 = 0 and Q3 = 2.

| Code | Category |
|---|---|
| E1 | Spelling variant or twin of a living word |
| E2 | Regional word |
| E3 | Specialist or trade word |
| E4 | Literary-register word (alive in books, never everyday speech; see Q2b) |
| E5 | Neologism, proper noun or loan (false candidate) |
| E6 | Inflected form or derived duplicate of another listed word |
| E7 | Definition problem (wrong sense, text of a twin word) |
| E8 | Corpus artefact (OCR, tokenisation, homograph with a living word) |
| E9 | Annotator taste or annotator age and region effect |
| E10 | True positive: forgotten and worth reviving |
| E11 | Other (write a note) |

Report the count per category with the exact item ids in the private key. Two reviewers assign categories to a 20% subset.
Report their agreement.

### Literary-register rarity versus temporal decline

A word rare in modern text may never have been everyday speech (E4). The ranking can confuse the two.
Wikisource and LUMRO are literary corpora, so "present in the historical panel" can mean "present in books".
Two labels address this: Q2b (B versus S versus N) and Q2.

Analyses, all reported:

1. Distribution of Q2b by score band and by seam. Share of `S` (spoken once, faded) among high scores.
2. Rank metrics for Q2 against B4 on items with Q2b = `S` only, and again with `B` only.
   If the score ranks `B` words as high as `S` words, it measures literary rarity, not decline.
3. The decline claim stays unsupported until dated sources exist (section 13). Annotator memory of "once everyday"
   is a weak proxy for temporal decline. State this wherever Q2b is reported.

## 11. Metrics, agreement and uncertainty

Labels per item: aggregate the annotators' codes by the median for ordinal scales (tie: the third annotator, then the
lower code). Items whose aggregate for a question is `?` or `X` leave that question's metric.
Report the abstain and `X` rate by stratum. Sensitivity analysis: recode `?` as 0 and as the top code and
report both.

Metrics, per question separately. For Q2 the positive class is "Q2 <= 1" (not in normal use today).
For Q3 the positive class is "Q3 = 2". For Q1 the positive class is "Q1 >= 1".

| Metric | Use |
|---|---|
| Weighted AUC (probability that a positive outranks a negative) | Primary. |
| Weighted Spearman rho and Kendall tau-b against the ordinal label | Primary, with the expected sign from section 2. |
| Weighted precision at k (k = 100, 250, 500 in the whole population, estimated from weights) | Secondary. |
| Weighted NDCG at 100 and 500, gain = label | Secondary. |
| Calibration table: score band against weighted label rate | Descriptive. |

Everything is computed on the test split. The development split serves only for the pilot and any fitting.

Uncertainty: bootstrap over lemma groups (the groups of section 7), 2,000 replicates, resampling groups inside the
test split. Each replicate recomputes all weighted metrics. Report the 2.5th and 97.5th percentiles.
Differences between two scorings use the same replicates (paired). Report the paired difference with its interval.
No multiple-comparison correction is applied. The primary comparisons are fixed in section 12.
Everything else is exploratory and is labelled as such.

Agreement (computed on all double-labelled items, then on test only):

- Krippendorff's alpha (ordinal) per question, with bootstrap intervals;
- quadratic weighted Cohen's kappa per annotator pair;
- the abstain rate and the share of items needing a third annotator;
- percent exact and percent within one step.

Reading agreement: alpha at or above 0.67 is usable. Between 0.40 and 0.67 the question is tentative and results carry
that label. Below 0.40 the question is not usable for ranking claims. Q1 and Q3 are judgments that vary by person.
Low agreement on them is a finding about the construct, not only about the annotators.

## 12. Decision criteria (set before judgments)

The owner decides. This section states what result would justify proposing a scoring change.
A proposal is not a change. No weight changes under this brief.

Primary comparisons on the test split, per question, B4 versus each of B1, B2, B3:
the paired AUC difference and the paired Spearman difference.

1. **The score is not better than a simple baseline.** If B4 does not beat B1, B2 and B3 with the lower end of its paired 95%
   interval above 0 on AUC for Q2 or Q3, report that the added complexity is unproven. Propose to simplify
   or to keep with a warning on the About page. Do not propose new weights.
2. **A reweighting is worth proposing** only if all hold:
   - One variant is frozen on the development split before test is opened, with its fitting recipe written down.
   - On test, its paired AUC gain over B4 is at least +0.03 on Q2 or Q3, and the lower end of the 95% interval is above 0.
   - The gain holds in the `relevant` seam and in the `curiosity` seam separately (point estimate positive in both).
   - It does not lose more than 0.02 AUC on the other primary question.
   - Alpha for that question is at least 0.40.
   - The gain survives excluding `regional`, `variant` and `derived` items, and excluding items abstained by any annotator.
3. **A new signal (for example wRodfreq) is worth proposing** under the same rules, on the covered subset, with the
   covered share stated. A coverage-limited signal can only support a coverage-limited claim.
4. **The seam boundary is worth revisiting** if the weighted precision at the `RELEVANT_MIN_SCORE` boundary
   (score 92) shows no difference in Q2 and Q3 rates between score bands 80-91 and 92-104, with intervals that exclude
   a difference of 0.10.
5. **The register problem is material** if, among top-quartile B4 items with Q2b answered, more than 50% carry `B`
   (weighted). The protocol then recommends a register-aware reading of the ranking before any weight change.
6. **Inconclusive results are reportable.** If intervals are wider than the differences, the study says "unresolved"
   and does not recommend a change. The next step then is more labels, not a guess.

## 13. Cost note: dated newspapers versus more undated modern text

The decline claim needs time. Today the historical panel (19.4M tokens) is literary and has no dates inside it.
CulturaX (17.0B tokens) is modern and undated. CoRoLa (637.8M tokens, 1945 onward) is loaded and deliberately not in any panel,
because it cannot give a post-2000 slice.

| Option | What it adds | Main costs and risks |
|---|---|---|
| More undated modern text | Smaller sampling error for modern counts. No time axis. Does not separate "never used" from "faded". | Low engineering cost (the corpus path exists). It cannot answer the register-versus-decline question. Gains shrink: modern counts are already large. |
| Dated newspaper archives | A time axis in everyday-register text. Allows per-decade rates and a trend test. Can test E4 directly. | Rights and licence checks. OCR error on older print. Pre-1953 spelling (`sînt`, `ă`/`â`/`î` rules) needs normalisation before counting. Diacritics lost in OCR. Archive access and storage. A new corpus panel and tests. Calibration of thresholds against the new panel's size. |

Rule: cost the dated option before any collection. The cost estimate answers five items:
(1) which archives and their licence terms; (2) token count per decade; (3) OCR word-error rate on a sample of 50 pages;
(4) the orthography normalisation effort and its failure rate on shortlist words; (5) engineering days for a new panel
and its threshold scaling (see `scaled_modern_thresholds`).
Do the estimate after the pilot, and only if the study shows that Q2b is `B` for many high-scoring words.
If most high-scoring words are `S` and the score already predicts Q2, more text has low value.
Do not collect any text under this brief.

## 14. Open decisions for the owner

1. Approve this protocol, or return it with changes.
2. Annotator count and recruitment (suggested: two primary, one adjudicator, mixed age bands and regions).
   Recruitment and consent are outside this brief. Use pseudonymous codes (A1, A2). Collect no names or contact data
   in the label file. Any demographic field needs a separate privacy decision. Without one, record nothing.
3. Tool: a two-stage form (preferred, enforces Stage A before B) or two spreadsheets.
4. Compensation, the legal basis for processing labels, and where the files live.
5. Whether to add a small set of control words outside the shortlist to estimate recall. This needs the full candidate
   file and is not planned here.
6. Whether to run the optional wRodfreq offline comparison (B6). It requires the sibling checkout and does not touch scoring.
7. Whether labels may ever be released. This brief releases nothing.

## 15. Amendment log

| Date | Change | Reason |
|---|---|---|
| 2026-10-05 | Version 1.0 draft written. Sample drawn from the build in `sample-provenance.json`. | Initial. |

## 16. Reproduction

```bash
.venv/bin/python tools/eval_sample.py \
  --inflected-db data/processed/inflected_forms.db \
  --provenance-out docs/eval/sample-provenance.json \
  --words-out docs/eval/sample-words.tsv
.venv/bin/python -m pytest tests/test_eval_sample.py -q
```

Compare the SHA-256 values in the output with `docs/eval/sample-provenance.json`.
The study is not run. No label file exists. `private/app.db` was not opened.
