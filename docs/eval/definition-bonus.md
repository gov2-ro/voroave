# The five-point definition bonus (`SCORE_HAS_DEF`)

Measured 2026-11-09 for [F11](../fixes/F11-local-followups.md) Step 3. No weight was changed. The owner decides.

## Rule

`validate_diachronic.py` sets `has_definition` from `data/processed/definitions.db`.
`make_shortlist.score()` adds 5 points when it is 1. A word joins the `relevant` seam at 92 points.

## Observed drift

The shortlist of 2026-08-11 predates the definition scrape merged on 2026-08-17.
Rebuilt on 2026-11-09 from the same corpus counts, 660 words gained a definition.
Each gained exactly 5 points and nothing else. 68 of them moved from `curiosity` to `relevant`.
So a definition scrape alone moves words between seams. This is the effect the backlog asked to measure.

## Measurement

Input: the rebuilt `forgotten_words_shortlist.csv` (18,277 words). Hide flags come from the 2026-08-18 `ui.db`.
The default view is the `relevant` seam without the six hide flags, sorted by score; votes are ignored.
The script removes 5 points where `has_definition = 1`; it does not re-run the lemma de-duplication.

| variant | relevant seam | default view | top-50 overlap |
|---|---|---|---|
| bonus 5, threshold 92 (current) | 3,567 | 2,500 | — |
| no bonus, threshold 92 | 1,765 | 1,205 | 50/50 |
| no bonus, threshold 87 | 3,573 | 2,503 | 50/50 |

94% of the shortlist (17,148 words) has a definition. So the bonus lifts nearly every word, and the threshold of 92
was tuned with it included. Dropping the bonus without lowering the threshold halves the seam; that compares two
different thresholds, not the bonus.

The fair comparison is the third row. The bonus is then equivalent to one rule: **a word without a definition
needs 5 more points of evidence.** Its effects:

- 6 words without a definition reach the `relevant` seam (3 visible in the default view: `alău`, `blăni`, `hiriș`).
- The 3 default-view words without a definition (`bălăi`, `boboni`, `bulucbașa`) rank at a median of 1,731
  with the bonus and 706 without it.
- Every other word moves by at most 3 places (median 2). The top 50 is identical.

## Reading

The bonus has little effect on what the default view shows. It acts as a soft requirement that a relevant word has
something to read when opened. Its real cost is drift: each definition scrape moves words between seams without
any change in corpus evidence (68 words this time).

Options for the owner:

1. Keep the bonus. Accept that a scrape moves words; record the counts after each merge.
2. Replace it with a display rule: no bonus, threshold 87, and sort words without a definition last in the default view.
3. Remove the bonus and keep 92: the seam halves. Not recommended without a new tuning of the threshold.

The pipeline figure says that a definition adds points. Update it if the rule changes.
