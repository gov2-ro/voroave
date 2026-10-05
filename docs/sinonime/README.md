# Sinonime

A second tool, separate from the oțios explorer: a Romanian **writing aid**. Type a word,
get alternatives you could actually use, ranked by how alive each one is in modern
Romanian. No definitions.

**Status (2026-10-05): implemented and merged.** The page, relation extractor, database builder,
and local acceptance tests exist. Live searches returned HTTP 500 during the audit.
Track remediation in [F01](../fixes/F01-synonym-deployment.md); local passes do not close the live outage.
The documents below retain the original measured design. Read them as implementation contracts, not unbuilt feature plans.

| document | what it is |
|---|---|
| [`findings.md`](findings.md) | What was measured, with the snippets that produced each number. Start here. |
| [`spec.md`](spec.md) | Build order, exact schemas, acceptance tests. Written to be executed without re-deriving anything. |
| [`ui.md`](ui.md) | The page: layout geometry, node caps, tokens, accessibility, empty state. |
| [`escalate.md`](escalate.md) | The decisions the implementer must **not** make alone. |

## The one-paragraph version

The DEX dump has contained a complete synonym graph all along — dexonline's own
community-curated `Relation` table, 158,860 rows, unredacted, never read by anything in
this repo. It yields **164,399 word-level synonym pairs over 63,049 words in ~15 seconds**
with no HTTP, against ~4 hours of scraping for 2,075 words. Our own note saying synonyms
"can't come from the dump" was true only of the Litera dictionaries' *definition text*,
which is redacted for copyright, and got generalised to the whole subject in three places.

The reason to build on it rather than link to dexonline: **41.7% of the Romanian
thesaurus is dead**, and this project already owns the corpus rollup that says which 41.7%.
dexonline lists synonyms alphabetically, so `frumos` offers `bididel` and `boghet` beside
`arătos`. Ranking by modern currency is the product; coverage is table stakes.

The scraper stays. Measured, the two sources overlap by about a third and **59% of the
scrape's tokens are new information** — `Relation` is strong on modern vocabulary and weak
on the archaic layer, Seche is the reverse. It gets pointed at the remaining gap (21,489
words, ~18 h) instead of at everything.

## The page, in one paragraph

A search box, then the word's neighbourhood as a **graph beside a ranked list**. The graph
is a deterministic radial drawing — radius is hop count, angle is sense cluster, and a
word's size and opacity are how alive it still is — server-rendered as plain SVG with no
libraries and no physics, so it is stable, testable, and navigable with JavaScript off. It
is capped at **37 nodes** by construction, which is the only reason a graph works at all
here: uncapped, a quarter of lookups draw more than 60 nodes and the worst draws 2,400.
Going a second step out is done by clicking, not by a slider — measured, three hops reaches
a p90 of 1,809 words. The list beside it is what you actually take a word from, and it is
also the graph's screen-reader alternative, which is why both are always on screen.
