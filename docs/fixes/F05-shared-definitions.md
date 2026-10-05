# F05 — Render the same definition on direct and interactive arrival

Status: open. Priority: P2.

## Evidence and target

`/?word=zapciu` initially shows flat text and pipe-separated quotations.
Clicking `zapciu` loads three structured senses.
`public/index.php` passes only `w` and `ssr` to the detail partial.
`public/api/word.php` additionally loads senses and citations.
The target is identical semantic content through both paths, including without JavaScript.

## Scope and decisions

Own the shared detail loader, `index.php`, `api/word.php`, and focused rendering tests.
Extract one data-loading path used by both entry points. Avoid an HTTP request from PHP to itself.
Pass senses and citations explicitly. Preserve the SSR `h1` and fragment heading behavior.
Preserve stable word IDs, share-relax behavior, pin ordering, metadata, and canonical URLs.
Do not overwrite `words.definition`; structured senses remain additive.
Missing sense tables on an older database retain the existing flat fallback.
Report unexpected database errors; do not expand the compatibility fallback to mask every failure.
Keep flat-only and synonym-only senses usable, including `zăticni` where the fixture permits.
Coordinate answer-body markup with F03.

## Acceptance

- Direct arrival and API detail show matching senses, citations, tags, etymon, and synonyms.
- A structured word and a flat-only word both render correctly with JavaScript disabled.
- An older schema without sense tables uses the flat fallback.
- Missing/invalid words retain existing status and metadata behavior.
- SSR has a real `h1`; fragment rendering introduces no duplicate page heading.
- Word share, playlist share, filter relaxation, and pinned ordering tests pass.
- Before/after screenshots show readable definitions on desktop and mobile.

## Boundary

Do not rebuild dictionary data, change scoring, redesign the panel, or add new scraping.
