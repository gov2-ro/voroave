# F03 — Hide all answer content before grading

Status: complete (local). Priority: P1.

## Evidence and target

The live sense quiz displayed the correct definition beside unanswered questions.
`public/ghici.php` masks `.definition-text`, `.fp-nodef`, `.fp-pos-line`, and `.joc-pos`.
The detail renderer now emits `.fp-senses`, `.fp-extras`, citations, and synonym hints.
The target is a playable sense quiz whose detail pane reveals answer content only after grading.

## Scope and decisions

Own spoiler logic in `ghici.php` and `tests/test_ghici.js`.
Coordinate renderer markup with F05; neither task changes the other's content contract silently.
Inventory answer-bearing content: senses, expressions, citations, synonyms, tags,
etymons, variant notes, action-noun notes, and dictionary information that reveals the answer.
Before grading, keep the headword and annotation controls available in sense mode.
Withhold the answer-bearing body as a unit rather than maintaining fragile selector fragments.
Ensure hidden answer content is also absent from the accessibility tree and keyboard order.
After grading, restore the complete detail widget, including on a wrong answer.
Keep quiz mode's withheld target word and signed-question protocol unchanged.
Preserve correct-only auto-advance and its cancellation on user interaction.
Prevent a late response from an earlier question replacing the current question's details.
This is ordinary UI spoiler prevention, not protection against inspecting browser traffic.

## Acceptance

- Test structured senses, flat fallback, expressions, citations, and synonyms.
- Before answering, none of the answer body is visible or keyboard reachable.
- After grading, the complete body is visible.
- Grade before the detail response arrives; the final state still reveals content correctly.
- Switch questions before a detail response arrives; stale details never replace the current pane.
- Marks remain usable and never count as an answer.
- Preserve wrong-answer comparison, auto-advance cancellation, and signed answer verification.
- Run `test_ghici.js` with jsdom installed; a skip is not acceptance.
- Verify desktop and mobile behavior in a real browser, using an isolated local database.

## Boundary

Do not change scoring, quiz pools, dictionaries, or game modes.
Stop if the proposed fix needs a different detail data contract; coordinate F05 first.
