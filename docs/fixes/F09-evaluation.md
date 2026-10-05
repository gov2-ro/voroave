# F09 — Design a small ranking evaluation

Status: protocol ready for owner review; study not run. Stage 0 spot-check tooling ready; not run. Stage 0 can be marked in the web UI (`sc-*` tags, `tools/spotcheck_marker.js`, `eval_spotcheck.py --from-appdb`). Deliverables: [protocol](../eval/protocol.md), `tools/eval_sample.py`, `docs/eval/sample-provenance.json`, `docs/eval/sample-words.tsv`. No scoring change is authorized by this brief.

## Question and evidence

Does the ranking identify rediscoverable vocabulary better than simple baselines?
The project currently has no independent evaluation. Fav/lol/meh reflect taste, not recognition.
Historical coverage is roughly 19.4M tokens against 17B modern tokens.
Zero historical counts and register differences limit conclusions about disappearance.

## Deliverables

Produce a reviewable protocol and a deterministic, stratified candidate sample.
Cover both seams, verdicts, score bands, regional words, variants, and flat/structured definitions.
Specify separate questions for recognition, current use, and rediscovery value.
Include uncertainty/abstention and annotator instructions. Do not fuse these questions into one label.
Define how annotators will see definitions without seeing scores or verdicts.
Predefine a held-out evaluation split grouped by related lemmas/variants to reduce leakage.
Compare modern count, DEX prominence, uniform component weights, and the current score.
Treat wordfreq as a coverage-limited baseline; report missing estimates separately.
If dictionary labels are reference labels, remove those labels and their proxies from evaluated features.
Do not use corpus-derived verdicts as independent ground truth for the corpus model.
Specify ranking metrics, uncertainty intervals, agreement, and qualitative error categories.
Distinguish literary-register rarity from temporal decline.
Cost dated newspaper ingestion before collecting more undated modern text.

## Acceptance and boundary

The protocol states the target, sampling seed, strata, sample size rationale, labels,
split, baselines, leakage controls, metrics, and decision criteria before judgments are collected.
The sample is reproducible from a named build; include provenance, not private annotations.
Deliver planning artifacts only. Do not contact annotators, add tracking, collect personal data,
release datasets, change weights, or integrate wRodfreq into production scoring.
The owner decides whether to run the study and approve any later scoring change.
