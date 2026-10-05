# F06 — Repair About-page preference initialization

Status: open. Priority: P2.

## Evidence and target

`public/despre.html` contains a one-line inline script with a `//` comment.
The comment consumes the remainder. Chromium reports a syntax error.
The target is correct theme, skin, and text scale on direct arrival, before first paint.

## Scope and decisions

Repair the invalid script. Remove the historical comment or use a block comment.
Keep the current preference keys, valid-skin fallback, and default light theme.
Do not turn the static page into PHP solely for this fix.
Do not introduce script generation or a new frontend dependency.
Existing malformed/unavailable localStorage must still leave a readable page.
Add a focused browser or syntax check to the required web checks from F07.

## Acceptance

- No JavaScript parse error on About-page arrival.
- Saved dark/light theme, a non-default skin, and text scale apply on direct navigation.
- Missing/invalid stored values retain safe defaults.
- All inline executable scripts parse; exclude JSON-LD from JavaScript parsing.
- Check default, saved-preference, and unavailable-storage cases in a real browser.

## Boundary

No palette redesign, new preference model, or general rewrite of static document pages.
