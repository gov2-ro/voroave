# Oțios — UI Redesign Brief

> Historical redesign brief. Reviewed 2026-10-05; it is not the current feature inventory.
> Synonyms, public collections, server sync, structured senses, and the three-mark UI now exist.
> The rare-in-use tab and Zipf/loanword filters were removed. Current row numbers show historical evidence.
> Use [the README](../readme.md) for architecture and [audit briefs](fixes/README.md) for fixes.
> The audience and readability goals remain useful; old control lists do not authorize rebuilding removed features.


> Brief for a visual redesign of the Oțios web app, to be handed to a designer
> ("Claude Designer"). The current app is a **functional reference only** — the
> designer is free to propose a **fresh visual identity**. Priority: **mobile-first**.

## 1. What Oțios is

Oțios is an exploratory web tool that surfaces **forgotten Romanian words** — terms
that exist in the official dictionaries (DEX Online) but have fallen out of modern
usage. It is **not a dictionary lookup tool**; it is a tool for *browsing, discovering,
and playing* with rare and archaic vocabulary. Think "a museum of words you can wander
through," not "a search box."

The data is computed by an offline pipeline: each word carries a "verdict" about how its
usage has changed between a historical corpus and modern text, plus rich dictionary
metadata (part of speech, register, domain, etymology, which dictionaries list it, and
how rare it is).

## 2. Audience & moment

- **Now:** private beta with Romanian-speaking friends — word lovers, curious laypeople,
  some with a literary/academic bent. Not researchers.
- **Next:** public launch; shareable links matter (people will send words to each other).
- Language of the UI: **Romanian** (with a few English dev-isms currently that the
  redesign should replace with Romanian). All content has diacritics (ă â î ș ț) — the
  type system must render them beautifully.

## 3. Goals of the redesign

1. **Fresh, distinctive identity.** Current look is parchment + Mona Sans/Lora; the
   designer may keep, evolve, or replace it. Aim for something that feels *editorial and
   a little playful* — inviting to wander, not clinical.
2. **Mobile-first.** Most beta sharing will happen on phones. Every view must be designed
   for narrow screens first, then scaled up. The current app bolts mobile on at the end;
   invert that.
3. **Readable definitions.** The definition is the payoff — give it room, good measure,
   and typographic care.
4. **Calm information density.** There is a lot of metadata; the design should let it
   recede until wanted (progressive disclosure) rather than competing for attention.
5. **Encourage exploration/play.** Random discovery, daily word, a card/swipe feed, and a
   quiz/flashcard game already exist functionally — the redesign should make these feel
   first-class, not bolted on.

## 4. Functional inventory — everything the design must be able to show

Per word, the data available (all already in the database):

| Field | Meaning | Notes for design |
|---|---|---|
| `word` | the headword | hero element; can be long (≥11 chars) |
| `definition` | short definition | may be long, may contain literary citations (`... ALECSANDRI, T. 773.`); some words have none |
| `verdict` | `extinct` / `declining` / `historical_only` / `absent` | a categorical "how forgotten" label; **needs a calmer color encoding** — see §7 |
| `confidence_tier` | why it was flagged (5 values) | secondary metadata |
| `dex_pos` | part(s) of speech (pipe-delimited) | e.g. `substantiv feminin`, `verb` |
| `dex_register` | register tags | e.g. `învechit` (archaic), `regional`, `rar` |
| `dex_domain` | subject domains | e.g. `botanică`, `marină`; can be several |
| `dex_etymology` | language(s) of origin | e.g. `turcă`, `latină` |
| `dict_count` + `sources` | how many / which dictionaries list it | e.g. "în 11 dicționare: DEX '09 · DOOM 2 · MDA2 …" |
| `dex_frequency` | editorial frequency 0–100 | rarity signal |
| `zipf_frequency` | corpus frequency (0–8 Zipf) | rarity signal |
| web-validation signals | `in_wild`, `web_score`, `last_seen_approx`, `top_url` | "is it still used online" (sparse data) |
| **synonyms** | *not yet available* | design a slot for it; currently shows "în curând" placeholder |
| user annotations | bookmark, note, free tags, quick-tags (ignore/boring/funny/remove) | stored locally in the browser |

## 5. Required views / screens

### 5.1 Word browser (primary)
Two layouts the user can switch between:
- **Cloud / chip grid** (today's masonry of word chips) — good for serendipitous scanning.
- **Table view (NEW)** — a sortable table with columns: **word, POS, domain, register,
  etymology, # dictionaries, verdict, frequency**. For users who want to scan metadata
  systematically. All columns' data already exists. Design column priority/collapse for
  mobile (e.g. word + verdict + one metadata column on phones, expandable rows).

### 5.2 Filter bar / controls (needs the most design love)
Today it is three dense rows of pills, checkboxes, dropdowns and number ranges. Redesign
for clarity and mobile:
- Filters: word-set toggle (forgotten / rare), text search, sort, verdict (4), confidence
  tier (5), POS (multi), register / domain / etymology (taxonomy), # dictionaries
  threshold, frequency ranges (Zipf + DEX), and toggles (hide loanwords, hide proper
  nouns), plus an annotations filter (bookmarked / noted / tagged).
- Provide a clear **"active filters" affordance** with per-filter removal (a chip bar
  exists today — make it central, not an afterthought) and a reset.
- Consider whether the **text search** should become an *attribute/filter search* (this is
  a browser, not a dictionary) — open question for the designer to weigh in on.
- On mobile: collapse into a filter sheet / drawer rather than always-visible rows.

### 5.3 Word detail / definition
The reveal when a word is chosen. Must present, in order of importance: the word, its
definition (large, readable), the verdict, key metadata as quiet tags, **which
dictionaries list it**, a **synonyms slot** (placeholder for now), rarity signals, a link
to dexonline.ro, and the user's annotation controls (bookmark, note, tags).
- **Shared-link arrival:** when someone opens a link to a specific word, the **definition
  should be the hero** and the surrounding list secondary (this behavior exists; the
  redesign should make it a deliberate, beautiful "landing" state).
- Today it's a short bottom drawer; the designer can choose drawer / panel / full page.

### 5.4 Play / exploration (make these feel first-class)
- **Surprise** — jump to a random word within current filters.
- **Word of the day** — one featured word per day (return hook, shareable).
- **Feed / swipe mode** — one card at a time, keep (→ save) or skip (←/swipe); a calm,
  TikTok-ish exploration mode with a gentle daily count.
- **Game page (`joc`)** — flashcards (word → reveal meaning) and a multiple-choice quiz
  (meaning → pick the word), with streak/score. Design the card, choice states
  (correct/incorrect), and progress.

### 5.5 Statistics page
Exists today: sliceable breakdowns (etymology / domain / register / POS / tier) that share
the same filters as the browser. Redesign to match the new system.

### 5.6 (Future, out of scope for first redesign but design with it in mind)
Sharing/virality: per-word social-preview cards (Open Graph image + meta) and named,
shareable curated lists. Don't build, but leave room in the system.

## 6. Technical constraints (please honor)

- **Stack:** PHP + HTMX + SQLite, served as plain pages. No SPA framework, no build step
  required. Interactions are HTMX partial swaps + a single vanilla `app.js`. Components
  should be expressible as server-rendered HTML + CSS.
- **Performance:** the word list paginates at 250/page with infinite scroll; the design
  must work with progressive loading.
- **Type:** must render Romanian diacritics cleanly at all sizes; definitions use a serif
  for readability today (keep a serif for body/definition unless you have a strong reason).
- **Assets:** keep it light (currently Google Fonts + htmx + a small CSS/JS). Avoid heavy
  frameworks or large image payloads.
- **Theming:** a single CSS variable system (`--surface`, `--text`, `--accent`, verdict
  colors, etc.) is in use — please deliver tokens in that spirit so it maps cleanly.

## 7. Specific notes & known issues to address

- **Verdict palette.** Today four full-saturation colors (red / brown / blue / purple)
  compete equally in the word grid. Propose a calmer encoding — e.g. one dominant accent +
  three muted, or a single-hue density scale — that still distinguishes the four verdicts.
- **Definition measure.** Long definitions with citations need graceful truncation/scroll;
  short ones shouldn't look empty.
- **"ignore" vs "remove" tags.** Two quick-tags with subtle meanings (ignore = not
  interesting to me; remove = not a genuinely forgotten word). Make the distinction legible.
- **Dictionary list** can be long (up to ~47 names). Design a compact, expandable
  presentation.

## 8. Deliverables requested from the designer

1. **Mobile + desktop mockups** for: word browser (both cloud and table layouts), filter
   experience, word detail (including the shared-link landing state), the four play modes,
   and the statistics page.
2. A **design token set** (color incl. the revised verdict palette, typography scale,
   spacing, radii, shadows) expressible as CSS variables.
3. **Component specs** for the recurring pieces: word chip, table row, filter control,
   active-filter chip, verdict badge, metadata tag, definition block, play card.
4. An explicit **table-view spec** (columns, sort affordances, responsive collapse).
5. **Interaction notes** (hover/tap, transitions, empty/loading/error states) appropriate
   to an HTMX app.

## 9. Pointers

- Live reference app: the current `public/` PHP app (word browser, `stats.php`, `joc.php`).
- Brand/name: **Oțios** (the word itself means "idle / otiose" — a wink at words that no
  longer do any work).
- Tone: scholarly but warm and a little playful; this should feel like a delight to share.
