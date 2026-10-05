<?php
declare(strict_types=1);

define('DB_PATH', __DIR__ . '/../data/ui.db');

// URL prefix for the public/ directory, e.g. '' (root) or '/otios' (subdirectory).
// Computed from DOCUMENT_ROOT vs the actual filesystem path of public/.
(function () {
    $doc_root = rtrim($_SERVER['DOCUMENT_ROOT'] ?? '', '/');
    $pub_dir  = rtrim(dirname(__DIR__), '/');   // parent of api/ = public/
    $base     = $doc_root !== '' ? substr($pub_dir, strlen($doc_root)) : '';
    define('BASE', $base === false ? '' : rtrim($base, '/'));
})();
define('PAGE_SIZE', 250);

// Skin discovery (assets/skins/*.css). Required here so every page that pulls
// in _lib.php — index, joc, stats, lista — gets the dropdown for free.
require_once __DIR__ . '/_skins.php';

// 'quality' is the default: the composite score from make_shortlist.py, which balances
// historical attestation against modern absence instead of ranking on modern rarity
// alone. Sorting by 'rare' put the most obscure regionalisms first — jbârc, barabor,
// hâșăi — which is the opposite of what the list is for.
$SORT_OPTIONS = [
    'quality'  => 'quality_score DESC NULLS LAST, dex_frequency DESC',
    'rare'     => 'COALESCE(modern_occ, -1) ASC',
    'declined' => 'rank_shift DESC NULLS LAST',
    'dex_freq' => 'dex_frequency ASC NULLS LAST',
    // Oldest last attestation first — the word no dictionary has reprinted since
    // 1929 ahead of the one still in DOOM 3. Nulls last: no year is "unknown",
    // not "ancient", and 453 of ~16k words have none.
    'attested' => 'newest_dict_year ASC NULLS LAST, word ASC',
    'alpha'    => 'word ASC',
    // 'populare' is filled in below — it needs VOTE_BOOST_SQL, and it is only usable
    // when app.db can be attached, which search.php checks.
];

/**
 * The damped vote weight added to quality_score by the `populare` sort.
 *
 * This is `4·ln(1 + |votes|)`, signed, rounded into bands. Bands rather than a call to
 * LN() because SQLite's math functions are a compile-time option
 * (SQLITE_ENABLE_MATH_FUNCTIONS) that a shared-host PHP build may not have — and
 * because a banded ladder is how make_shortlist.py already expresses a damped weight.
 *
 *     |votes|   1   2   3–4   5–8   9–16   17–32   33–64   65+
 *     boost     3   4    6     8     10      12      15     18
 *
 * **Each doubling of the vote count is worth about two more points.** That is the whole
 * anti-abuse argument: the 20th vote adds ~0.2 where the 1st added 2.8, so stuffing has
 * sharply diminishing returns. The scale matters — the `relevant` seam's quality_score
 * spans 92–121, with 76% of its 3,499 words inside a ten-point band, so a linear weight
 * of even 5/vote would let four votes carry a word from the median to the top forty.
 * Against that span, 20 forged votes buy ~12 points: real movement, not the top.
 *
 * Votes can only ever reorder. Nothing here removes a row — see vote_counts_subquery().
 */
const VOTE_BOOST_SQL = "
    CASE
      WHEN COALESCE(v.votes, 0) = 0 THEN 0
      ELSE (CASE WHEN v.votes < 0 THEN -1 ELSE 1 END) *
           (CASE
              WHEN ABS(v.votes) =  1 THEN  3
              WHEN ABS(v.votes) =  2 THEN  4
              WHEN ABS(v.votes) <= 4 THEN  6
              WHEN ABS(v.votes) <= 8 THEN  8
              WHEN ABS(v.votes) <= 16 THEN 10
              WHEN ABS(v.votes) <= 32 THEN 12
              WHEN ABS(v.votes) <= 64 THEN 15
              ELSE 18
            END)
    END";

// Derived score blended with what people actually marked. Not the default: identity is
// an anonymous device token, so this stays a control a reader opts into rather than the
// front page. Ties fall back to the plain quality order.
$SORT_OPTIONS['populare'] =
    'COALESCE(quality_score, 0) + (' . VOTE_BOOST_SQL . ') DESC, '
    . 'quality_score DESC NULLS LAST, dex_frequency DESC';

// The front page is the blend. Votes only ever reorder — nothing here can remove a word —
// so making this the default costs at most a nudge in position, and the damping keeps that
// nudge small (each doubling of the vote count is worth about two more points). Falls back
// to 'quality' when app.db cannot be attached; see search.php.
define('DEFAULT_SORT', 'populare');
define('FALLBACK_SORT', 'quality');

/**
 * Leading ORDER BY term that sinks curator-demoted words to the end.
 *
 * `editor_demote` used to be a WHERE clause — the word was gone from the default view
 * entirely. Demoting instead of hiding is the less destructive reading and removes an
 * asymmetry: the curator's judgement was the only human signal allowed to *subtract*,
 * while the community's could only reorder. Now both only reorder.
 *
 * The control stays a three-state (`în spate` / `normal` / `doar`) precisely because
 * sinking is not self-explaining: with 2,685 words at 250 a page, a demoted word lands
 * about eleven pages down, which is hidden in every practical sense. Without a control
 * saying so, that would be worse than an honest hide — there would be nothing to undo.
 */
function demote_order_sql(array $p): string {
    if (!db_has_column('editor_demote')) return '';
    return class_mode($p, 'editorial', 'back', []) === 'back'
        ? 'COALESCE(editor_demote, 0) ASC, ' : '';
}

/**
 * Resolve one class control's mode: `hide` / `show` / `only` (or `back` for `editorial`).
 *
 * `$aliases` maps a superseded param name to the mode it implies — `null` meaning the
 * alias carries its own three-state value, which is how a param that used to be its own
 * row keeps working after being folded into a bundle (`?spellings=only` → the whole
 * `variants` control on `only`). The explicit param always wins; aliases are tried in
 * declaration order, so the newest spelling beats the checkbox-era one.
 *
 * Kept out of build_word_filter() because demote_order_sql() has to reach the same
 * answer for `editorial` — reading `$p['editorial']` directly there is how the two got
 * out of step, and the ORDER BY silently disagreeing with the WHERE is invisible.
 */
function class_mode(array $p, string $param, string $default, array $aliases): string {
    $valid = ['hide', 'show', 'only', 'back'];
    $mode  = trim($p[$param] ?? '');
    if (in_array($mode, $valid, true)) return $mode;
    foreach ($aliases as $alias => $implied) {
        $raw = trim($p[$alias] ?? '');
        if ($implied === null) {
            if (in_array($raw, $valid, true)) return $raw;
        } elseif ($raw === '1') {
            return $implied;
        }
    }
    return $default;
}

/**
 * The class controls, as `[param, [columns…], default, [alias => mode|null]]`.
 *
 * Lives here rather than inside build_word_filter() because share_relax_params() has to
 * read the same table — it answers "which of these defaults is hiding this word", and a
 * second copy of the mapping would go stale the day a class is added, silently: the
 * shared word would just not be in the list, which is the bug the relax exists to fix.
 * The prose for what each control means is at the point of use in build_word_filter().
 */
function class_modes(): array {
    return [
        ['regional',    ['regional_only'],   'hide', ['show_regional' => 'show']],
        ['variants',    ['variant_like', 'archaic_spelling', 'dex_variant'], 'hide',
                        ['spellings' => null, 'dexvar' => null,
                         'show_variants' => 'show', 'show_spellings' => 'show']],
        ['deverbal',    ['deverbal_like'],   'hide', []],
        ['diminutives', ['diminutive_like'], 'hide', ['hide_diminutives' => 'hide']],
        // `editorial` is the one class whose default does not subtract. Its states are
        // `back` (sink to the end) / `show` (normal order) / `only`, and `back` is
        // handled in the ORDER BY by demote_order_sql(), not in the WHERE.
        ['editorial',   ['editor_demote'],   'back', []],
    ];
}

$QUICK_TAGS = [
    ['ascunde', 'a'],
    ['lol',     'l'],
    ['meh',     'm'],
];

$QUICK_TAG_EMOJIS = [
    'ascunde' => '⚠️',
    'lol'     => '🤣',
    'meh'     => '⛔️',
];

$POS_OPTIONS = [
    ['substantiv feminin',  's.f.'],
    ['substantiv neutru',   's.n.'],
    ['substantiv masculin', 's.m.'],
    ['adjectiv',            'adj.'],
    ['verb',                'vb.'],
    ['adverb',              'adv.'],
    ['participiu',          'part.'],
    ['interjecție',         'interj.'],
];

// ── Classification labels ─────────────────────────────────────────────────────
//
// `verdict` and `confidence_tier` hold English identifiers because the pipeline
// writes them — they are keys, not copy, and the CSS classes derived from them
// (`vb-historical_only`, `verdict-extinct`, …) depend on the raw value. Every
// user-facing rendering goes through the maps below instead, so a label is
// translated in one place rather than in each of the five that draw one: the
// filter pills, the detail badge, the hover box, the word row, and the stats bars.

const VERDICTS = [
    'extinct' => [
        'label' => 'dispărut din uz', 'abbr' => 'EXT', 'dot' => 'v-ext',
        'tip'   => 'Prezent în corpus istoric, absent din cel modern',
    ],
    'declining' => [
        'label' => 'în declin', 'abbr' => 'DEC', 'dot' => 'v-dec',
        'tip'   => 'Semnificativ mai comun istoric față de româneasca modernă',
    ],
    'historical_only' => [
        'label' => 'doar istoric', 'abbr' => 'IST', 'dot' => 'v-hist',
        'tip'   => 'Găsit doar în Wikisource (istoric), nu în CulturaX (modern)',
    ],
    'absent' => [
        'label' => 'absent', 'abbr' => 'ABS', 'dot' => 'v-abs',
        'tip'   => 'Niciun semnal în corpus — posibil cel mai uitat',
    ],
];

const TIERS = [
    'corpus_extinct' => [
        'label' => 'corp. dispărut', 'fill' => 'bar-fill--ext',
        'tip'   => 'modern_ppm = 0, hist_ppm > 0',
    ],
    'corpus_declining' => [
        'label' => 'corp. în declin', 'fill' => 'bar-fill--dec',
        'tip'   => 'scădere log-ratio deasupra pragului',
    ],
    'corpus_historical_only' => [
        'label' => 'corp. doar istoric', 'fill' => 'bar-fill--hist',
        'tip'   => 'Wikisource da, CulturaX nu',
    ],
    'dex_invechit_absent' => [
        'label' => 'dex. învechit', 'fill' => 'bar-fill--abs',
        'tip'   => '"învechit" în DEX + absent din corpus modern',
    ],
    'dex_absent_highfreq' => [
        'label' => 'dex. absent', 'fill' => 'bar-fill--abs',
        'tip'   => 'Frecvență editorială DEX ridicată, dar zero prezențe în corpus',
    ],
];

/**
 * The five destinations of `_partials/footer.php`, in the order they appear.
 *
 * Here rather than in the partial for the same reason VERDICTS is: it is the one
 * list of user-facing strings for a thing drawn on every page, and a `const` in an
 * included file cannot be guarded against a second include.
 *
 * Every entry keeps an icon *and* a label — below 900px the labels are hidden and
 * the icons carry the bar alone, so an entry without one would vanish. The label
 * survives as the `title` in that state.
 */
const NAV_ITEMS = [
    'index'  => ['path' => '/',                 'icon' => '◈',  'label' => 'cuvinte'],
    // Key, path and label all differ on purpose. The label is the user-facing name
    // („quiz"), the path is the Romanian slug the site is hosted under („/ghici"), and
    // the key is what `$page` and `aria-current` match on. `/joc` still resolves —
    // .htaccess 301s it here, since it was a shared link for months.
    'ghici'  => ['path' => '/ghici',        'icon' => '🎮', 'label' => 'quiz'],
    // „colecții" is the nav's third destination, and since 2026-08-13 it is the
    // *site-wide* one: what every visitor marked, ranked. `/liste` — your own buckets and
    // the directory of published ones — kept everything it had and lost the nav slot,
    // because the aggregate is what a first-time visitor with no marks of their own can
    // actually read. It is linked from the top of `/colectii`, one click further in.
    'colectii' => ['path' => '/colectii',   'icon' => '📋', 'label' => 'colecții'],
    'despre' => ['path' => '/despre',       'icon' => 'ℹ️', 'label' => 'despre'],
    // Still real pages and still marked `aria-current` when you are on them — they are
    // simply not in either nav any more. `despre` links to the first two and `colectii`
    // to the third, which is the shape the bar could actually afford: three labelled
    // entries competing for a phone bar is the measurement that split this nav between
    // header and footer in the first place, and a reader who wants the method has nearly
    // always read the overview first.
    'stats'  => ['path' => '/stats',        'icon' => '📊', 'label' => 'statistici'],
    'metod'  => ['path' => '/metodologie', 'icon' => '🧐', 'label' => 'metodologie'],
    'liste'  => ['path' => '/liste',        'icon' => '📋', 'label' => 'liste'],
];

/**
 * Absolute URL for a BASE-relative path — og:url and canonical need a real one.
 *
 * Reads the forwarded headers first so it stays correct behind a reverse proxy, where
 * HTTPS terminates upstream and $_SERVER['HTTPS'] is unset on the PHP side.
 */
function otios_abs_url(string $path = '/'): string {
    $proto = $_SERVER['HTTP_X_FORWARDED_PROTO']
        ?? ((($_SERVER['HTTPS'] ?? '') !== '' && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http');
    $host  = $_SERVER['HTTP_X_FORWARDED_HOST'] ?? $_SERVER['HTTP_HOST'] ?? 'localhost';
    return $proto . '://' . $host . BASE . $path;
}

/**
 * A filter-section heading with a „?" that reveals a one-line explainer.
 *
 * A real button and a real paragraph, not a `title=` tooltip: a title attribute needs a
 * hover, and a phone has none — which on this site means the explanation is missing on
 * exactly the device where an unfamiliar filter name is hardest to guess at. `aria-expanded`
 * and `aria-controls` carry the state for assistive tech; app.js does the toggling.
 */
function fs_label(string $label, string $help = ''): string {
    $out = '<div class="fs-label">' . e($label);
    if ($help !== '') {
        $id = 'fshelp-' . preg_replace('/[^a-z0-9]+/', '-', strtolower($label));
        $out .= ' <button type="button" class="fs-help" aria-expanded="false"'
              . ' aria-controls="' . e($id) . '" aria-label="Ce înseamnă ' . e($label) . '?">?</button>';
        $out .= '</div><p class="fs-help-text" id="' . e($id) . '" hidden>' . e($help) . '</p>';
        return $out;
    }
    return $out . '</div>';
}

function verdict_label(?string $v): string { return VERDICTS[$v ?? '']['label'] ?? 'neclasificat'; }
function verdict_abbr(?string $v): string  { return VERDICTS[$v ?? '']['abbr']  ?? '?'; }

/**
 * '' for an unmapped tier, not the raw key: an unknown value means the pipeline grew
 * one this build hasn't been taught, and a bare enum on the page is worse than no chip.
 */
function tier_label(?string $t): string { return TIERS[$t ?? '']['label'] ?? ''; }

// ── Share metadata for a `?word=` link ────────────────────────────────────────
//
// A word link is the site's main shareable unit, and until 2026-08-12 it carried no
// metadata at all: `?word=` was read only by app.js, after load, so every link ever
// posted showed the generic „Voroave neglijate / Suveranism lexical" card and a crawler
// saw none of the 18,270 words. The panel is still opened client-side — this only fills
// the head, which is the half a crawler and a chat preview actually read.
//
// `null` for anything not in the table, so the page falls back to its own titles rather
// than advertising a word the site cannot show. That also makes `?word=<garbage>` inert.

const SHARE_DESC_MAX = 160;   // what Google and most chat previews render before cutting

/**
 * Trim a DEX definition down to one shareable sentence.
 *
 * Definitions arrive as pipe-separated senses, most with a literary citation attached
 * („…SADOVEANU, O. I 452."). The first sense minus its citations is the part that reads
 * as a definition; the citations are an author's name in caps followed by a volume
 * reference, and in a 160-character preview they crowd the meaning out entirely.
 */
function share_excerpt(?string $definition, int $max = SHARE_DESC_MAX): string {
    $seg = trim(explode('|', (string) $definition)[0]);
    // Drop a trailing citation: a run of 2+ capitals, then anything to the end.
    $seg = (string) preg_replace('/\s*\p{Lu}{2,}[^.]*$/u', '', $seg);
    $seg = trim(preg_replace('/\s+/u', ' ', $seg));
    if ($seg === '' || mb_strlen($seg) <= $max) return $seg;
    $cut = mb_substr($seg, 0, $max - 1);
    $sp  = mb_strrpos($cut, ' ');
    return rtrim($sp !== false ? mb_substr($cut, 0, $sp) : $cut, " ,;:.") . '…';
}

/**
 * Absolute origin + BASE, for `og:url` and `rel=canonical`, which must not be relative.
 *
 * Derived rather than hardcoded so a subfolder deploy and a local `php -S` both produce
 * URLs that resolve — the same reason BASE itself is computed. `HTTP_HOST` is attacker-
 * controlled, so it is whitelisted against a character class before being echoed: it
 * lands in an absolute URL that crawlers and chat apps follow.
 */
function site_origin(): string {
    $host = (string) ($_SERVER['HTTP_HOST'] ?? '');
    if ($host === '' || !preg_match('/^[A-Za-z0-9.\-]+(:\d+)?$/', $host)) {
        $host = 'voroave.ro';
    }
    $https = ($_SERVER['HTTPS'] ?? '') !== '' && ($_SERVER['HTTPS'] ?? '') !== 'off';
    return ($https ? 'https://' : 'http://') . $host . BASE;
}

/**
 * Head metadata for `?word=X`, or null when there is no such word.
 *
 * Returns title / description / canonical, already plain text — the caller escapes.
 */
function share_meta(array $p): ?array {
    $word = trim((string) ($p['word'] ?? ''));
    if ($word === '' || mb_strlen($word) > 64) return null;

    $st = db()->prepare(
        'SELECT word, definition, dex_pos FROM words WHERE word = ? LIMIT 1');
    $st->execute([$word]);
    $row = $st->fetch();
    if (!$row) return null;

    // The part-of-speech prefix comes out of the excerpt's budget, not on top of it —
    // added afterwards it pushed `văz` to 187 characters and the preview cut mid-word
    // in whatever place the reader's client chose rather than at ours.
    $pos    = trim(explode('|', (string) ($row['dex_pos'] ?? ''))[0]);
    $prefix = $pos !== '' ? $pos . ' — ' : '';
    $desc   = share_excerpt($row['definition'] ?? null,
                            SHARE_DESC_MAX - mb_strlen($prefix));
    if ($desc === '') {
        // No definition is not a reason to serve a bare word: say what the site knows,
        // which is that the word is in DEX and out of use.
        $desc = 'Cuvânt din DEX ieșit din uzul de astăzi. Vezi ce spun dicționarele.';
    } else {
        $desc = $prefix . $desc;
    }
    return [
        'title'     => $row['word'] . ' — definiție · Voroave',
        'desc'      => $desc,
        'canonical' => site_origin() . '/?word=' . urlenc($row['word']),
        'word'      => $row['word'],
    ];
}

/**
 * The filter-sheet controls a `?word=` link has to relax for its own word to be in the
 * list underneath it — `['seam' => 'relevant,curiosity', 'variants' => 'show', …]`, empty
 * when the defaults already show the word (and when there is no such word).
 *
 * **A share must land on the word.** The panel itself was never at risk: `api/word.php`
 * is a bare `WHERE word = ?` and no filter has ever reached it. What was at risk is
 * everything around the panel — 15,803 of the 18,270 words are outside the default view,
 * 11,193 of them on the seam alone, so closing the panel on a shared `curiosity` word
 * left the reader on a list that did not contain the word they had come for, with the
 * rail showing filters they never set as the reason.
 *
 * Relaxing the control rather than injecting the row is what keeps the site's own rule
 * — every exclusion is a visible control, never silent. The reader arrives with
 * „curiozități" ticked in the rail and `?seam=relevant,curiosity` written into the URL by
 * syncUrlFromForm(), so the wider list is both explained and undoable in one click. A row
 * quietly added to a list whose controls say it should not be there is the mirror image
 * of the bug.
 *
 * Two things this deliberately does not do:
 *
 * - **It never narrows.** `seam` gains the word's seam alongside `relevant`; it does not
 *   swap to it. A share is one word arriving on top of the site, not a different site.
 * - **It leaves `editorial` alone**, because `back` does not subtract — a demoted word is
 *   in the list already, at the end. Being *reachable* on the page is the pin's job
 *   (pin_order_sql), not this one's; the two halves are separate because only this half
 *   can be undone from the rail.
 *
 * An explicit param in the URL always wins over this — see applyUrlToForm() in app.js,
 * which is where the map is applied. Someone who shared a link *with* filters on it
 * shared the filters too.
 */
function share_relax_params(string $word): array {
    $word = trim($word);
    if ($word === '' || mb_strlen($word) > 64) return [];

    $st = db()->prepare('SELECT * FROM words WHERE word = ? LIMIT 1');
    $st->execute([$word]);
    $row = $st->fetch();
    if (!$row) return [];

    $relax = [];
    if (db_has_column('seam')
        && ($row['seam'] ?? 'relevant') !== 'relevant') {
        $relax['seam'] = 'relevant,' . $row['seam'];
    }
    foreach (class_modes() as [$param, $cols, $default, $_aliases]) {
        if ($default !== 'hide') continue;          // `editorial` — demotes, never hides
        foreach ($cols as $col) {
            if (db_has_column($col) && (int) ($row[$col] ?? 0) === 1) {
                $relax[$param] = 'show';
                break;
            }
        }
    }
    return $relax;
}

/**
 * Leading ORDER BY term that pins one word to the top of the first page.
 *
 * The companion to share_relax_params(): that one makes the shared word *eligible*, this
 * one makes it *visible*. They are both needed and neither is enough. Measured on the
 * current build, with the seam relaxed a `curiosity` word ranks between 2,468 and 13,660
 * under the default `populare` sort — at 250 rows a page, never on the page the reader is
 * looking at. Ticking the seam alone would have been a filter change nobody could see the
 * point of.
 *
 * Pinning in the ORDER BY rather than the WHERE is what keeps this honest: the row is in
 * the set on its own merits, this only decides where it sits. It also cannot duplicate
 * across pages — the term is part of one global order that every page request repeats
 * (the hidden `pin` input is inside #filter-form, so htmx sends it with the initial
 * search and `next_url` carries it into every load-more), so the pinned row is rank 1 and
 * appears on page 1 only. A word that is not in the result set makes the term a no-op.
 *
 * **The param is `pin`, not `word`, and that is not cosmetic.** `hx-include` is inherited
 * in htmx, so every `.word-row` inside `#word-list` sends this whole form along with its
 * own `api/word.php?word=<row>` — a hidden input named `word` appended an empty second
 * copy, PHP kept the last, and clicking any word 400'd instead of opening its definition.
 * Pinned by tests/test_share_view.js §8.
 *
 * Binds one param, which the caller must merge *after* the WHERE params and *before*
 * LIMIT/OFFSET — placeholders are positional.
 */
function pin_order_sql(array $p, array &$params): string {
    $word = trim((string) ($p['pin'] ?? ''));
    if ($word === '' || mb_strlen($word) > 64) return '';
    $params[] = $word;
    return '(words.word = ?) DESC, ';
}

function db(): PDO {
    static $pdo = null;
    if ($pdo === null) {
        $pdo = new PDO('sqlite:' . DB_PATH, null, null, [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
        $pdo->exec('PRAGMA query_only = ON');
    }
    return $pdo;
}

/** True when ui.db has the named table. Probed once per table per request, so an older
 *  ui.db (built before docs/senses-plan.md) is recognised by what it lacks, not by
 *  swallowing whatever error a query raises. */
function db_has_table(string $table): bool {
    static $known = [];
    if (!array_key_exists($table, $known)) {
        $st = db()->prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?");
        $st->execute([$table]);
        $known[$table] = $st->fetchColumn() !== false;
    }
    return $known[$table];
}

/**
 * The one loader behind a word's detail panel (brief F05). Both `api/word.php` (click)
 * and `index.php` (direct `?word=` arrival, no JavaScript) call it, so the two paths
 * cannot drift apart. Returns null when the word is not in the table.
 *
 * Result: ['w' => word row, 'senses' => rows, 'cites_by_sense' => [sense_ord => rows]].
 * The sense tree is additive to `$w['definition']`, never a replacement for it. A ui.db
 * built before the feature has neither table: senses are then [] and the panel shows the
 * flat definition. Only that case is tolerated. Any other database error propagates.
 */
function load_word_detail(string $word): ?array {
    $st = db()->prepare('SELECT * FROM words WHERE word = ? LIMIT 1');
    $st->execute([$word]);
    $w = $st->fetch();
    if ($w === false) return null;

    $senses = [];
    $cites_by_sense = [];
    if (db_has_table('senses')) {
        $sstmt = db()->prepare('SELECT * FROM senses WHERE word = ? ORDER BY ord');
        $sstmt->execute([$word]);
        $senses = $sstmt->fetchAll();
    }
    if (db_has_table('sense_citations')) {
        $cstmt = db()->prepare(
            'SELECT * FROM sense_citations WHERE word = ? ORDER BY sense_ord, ord');
        $cstmt->execute([$word]);
        foreach ($cstmt->fetchAll() as $c) {
            $cites_by_sense[(int) $c['sense_ord']][] = $c;
        }
    }
    return ['w' => $w, 'senses' => $senses, 'cites_by_sense' => $cites_by_sense];
}

function normalize_diacritics(string $s): string {
    $s = mb_strtolower($s, 'UTF-8');
    return str_replace(
        ['ț', 'ș', 'ţ', 'ş', 'ă', 'â', 'î'],
        ['t', 's', 't', 's', 'a', 'a', 'i'],
        $s
    );
}

function e(?string $s): string {
    return htmlspecialchars($s ?? '', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function urlenc(string $s): string {
    return rawurlencode($s);
}

function vocab(string $kind): array {
    $stmt = db()->prepare('SELECT value FROM vocab WHERE kind = ? ORDER BY count DESC');
    $stmt->execute([$kind]);
    return $stmt->fetchAll(PDO::FETCH_COLUMN);
}

/** Same as vocab(), keyed by value => word count. For options that display their count. */
function vocab_counts(string $kind): array {
    $stmt = db()->prepare('SELECT value, count FROM vocab WHERE kind = ? ORDER BY count DESC');
    $stmt->execute([$kind]);
    return $stmt->fetchAll(PDO::FETCH_KEY_PAIR);
}

function render(string $partial, array $vars = []): void {
    extract($vars, EXTR_SKIP);
    include __DIR__ . '/_partials/' . $partial;
}

function parse_multi(mixed $raw): array {
    if ($raw === null) return [];
    if (is_array($raw)) return array_values(array_filter(array_map('trim', $raw)));
    return array_values(array_filter(array_map('trim', explode(',', (string)$raw))));
}

function split_pipe(?string $s): array {
    if ($s === null || $s === '') return [];
    return array_values(
        array_filter(array_map('trim', explode('|', $s)), fn(string $v) => $v !== '')
    );
}

function db_has_column(string $col): bool {
    static $cols = null;
    if ($cols === null) {
        $cols = array_column(db()->query('PRAGMA table_info(words)')->fetchAll(), 'name');
    }
    return in_array($col, $cols, true);
}

// ── Packed word lists ─────────────────────────────────────────────────────────
//
// A share URL carries base36 word ids rather than the words: Romanian diacritics
// percent-encode to six characters each (ă → %C4%83), so twenty words run past 300
// characters as `?words=`, versus about 70 as `?w=`.
//
// The ids come from data/word_ids.tsv via the word_id column (tools/word_ids.py) and
// are append-only, so a link shared today still resolves after any number of data
// rebuilds. The leading version segment is the escape hatch if that ever has to
// change — an old client meeting a version it does not know decodes nothing rather
// than decoding the wrong words.

const WORD_PACK_VERSION = 1;
const WORD_PACK_MAX     = 500;   // ceiling on one URL, so `?w=` can't force a huge query

/** ['abacă','oțios'] → "1.1.396f". Unknown words are dropped; '' if none survive. */
function pack_words(array $words): string {
    $words = array_slice(array_values(array_unique(array_filter(
        $words, fn($w) => is_string($w) && $w !== ''
    ))), 0, WORD_PACK_MAX);
    if ($words === [] || !db_has_column('word_id')) return '';

    $ids = [];
    foreach (array_chunk($words, 400) as $chunk) {
        $ph   = implode(',', array_fill(0, count($chunk), '?'));
        $stmt = db()->prepare("SELECT word, word_id FROM words WHERE word IN ($ph) AND word_id IS NOT NULL");
        $stmt->execute($chunk);
        foreach ($stmt->fetchAll() as $r) { $ids[$r['word']] = (int) $r['word_id']; }
    }

    $out = [];
    foreach ($words as $w) {                       // caller's order is the payload
        if (isset($ids[$w])) $out[] = base_convert((string) $ids[$w], 10, 36);
    }
    return $out === [] ? '' : WORD_PACK_VERSION . '.' . implode('.', $out);
}

/** "1.1.396f" → ['abacă','oțios'], in URL order. [] on any version or format problem. */
function unpack_words(string $packed): array {
    $parts = explode('.', trim($packed));
    if (count($parts) < 2) return [];
    if (array_shift($parts) !== (string) WORD_PACK_VERSION) return [];
    if (!db_has_column('word_id')) return [];

    $ids = [];
    foreach (array_slice($parts, 0, WORD_PACK_MAX) as $seg) {
        // base_convert() silently treats out-of-alphabet characters as zero, so a
        // malformed segment would decode to id 0 rather than being rejected.
        if (!preg_match('/^[0-9a-z]{1,6}$/', $seg)) continue;
        $id = (int) base_convert($seg, 36, 10);
        if ($id > 0) $ids[] = $id;
    }
    if ($ids === []) return [];

    $by_id = [];
    foreach (array_chunk(array_unique($ids), 400) as $chunk) {
        $ph   = implode(',', array_fill(0, count($chunk), '?'));
        $stmt = db()->prepare("SELECT word_id, word FROM words WHERE word_id IN ($ph)");
        $stmt->execute($chunk);
        foreach ($stmt->fetchAll() as $r) { $by_id[(int) $r['word_id']] = $r['word']; }
    }

    $out = [];
    foreach ($ids as $id) {
        if (isset($by_id[$id])) $out[] = $by_id[$id];
    }
    return $out;
}

/**
 * The words a playlist parameter names, or null when the request carries no playlist.
 *
 * `w=` is the packed form (base36 ids, see above), `words=` the legacy plaintext one.
 * An empty array is a real answer for `w=`: one that decodes to nothing — mangled, or a
 * version this build predates — must match no words rather than falling through to the
 * whole list, which would silently serve 16k words under a "3 words in list" banner.
 * A blank `words=` is treated as no playlist at all, which is how it has always behaved.
 *
 * Callers pair this with skipping build_word_filter(): a playlist is a list someone
 * curated by hand, and the default filters would subtract from what they chose.
 */
function playlist_words(array $p): ?array {
    $packed = trim((string) ($p['w'] ?? ''));
    if ($packed !== '') return unpack_words($packed);

    $raw = trim((string) ($p['words'] ?? ''));
    if ($raw === '') return null;
    $words = array_values(array_filter(array_map('trim', explode(',', $raw))));
    return $words === [] ? null : $words;
}

/** `word IN (…)` for a playlist, or the never-matching condition for an empty one. */
function playlist_condition(array $words, array &$conditions, array &$params): void {
    if ($words === []) {
        $conditions[] = '1=0';
        return;
    }
    $conditions[] = 'word IN (' . implode(',', array_fill(0, count($words), '?')) . ')';
    $params       = array_merge($params, array_values($words));
}

/**
 * Scope one word query, appending its conditions to $conditions/$params and returning
 * which of the three scopes it chose: `search`, `playlist` or `filter`.
 *
 * The precedence is **q, then playlist, then the filter sheet**, and the first of those
 * is the one worth explaining.
 *
 * **A text query searches the whole table.** Someone typing a word is asking whether this
 * project knows it — not asking to search inside whatever slice they happen to have open.
 * The defaults alone leave 2,685 of 18,270 words visible: `relevant` seam, no
 * regionalisms, no variants, no old spellings, no diminutives. So a first-time visitor
 * searching `celșag` got „niciun rezultat" while the word sat in the database with a
 * definition, and nothing on the page said which of five untouched controls was
 * responsible. A search that answers "not here" about a word that *is* here is worse than
 * no search. Every filter dropped in this branch is one the reader never set; the one
 * thing they did set is the query.
 *
 * That covers the marks filter too, which is why the mode is returned rather than kept
 * private: `search.php` reads it and skips its own `marks` clause. Sort is untouched —
 * ordering cannot make a match disappear.
 *
 * `word_tier` goes with the rest. It is a no-op today (every row is `forgotten`) but it
 * is a filter, and re-adding it here would quietly re-narrow the search the day a second
 * tier lands.
 *
 * A playlist keeps its own branch below q for the same reason it has one at all: it is a
 * list someone curated, and the defaults would subtract from what they chose. Searching
 * *within* an open playlist is the one thing this ordering gives up — see the note in
 * setSearchMode() (app.js) for why the sheet says so rather than the URL quietly meaning
 * two things.
 */
function word_scope(array $p, array &$conditions, array &$params): string {
    $q = trim((string) ($p['q'] ?? ''));
    if ($q !== '') {
        $q_norm       = normalize_diacritics($q);
        $conditions[] = '(word LIKE ? OR word_normalized LIKE ?)';
        $params[]     = '%' . $q . '%';
        $params[]     = '%' . $q_norm . '%';
        return 'search';
    }

    $playlist = playlist_words($p);
    if ($playlist !== null) {
        playlist_condition($playlist, $conditions, $params);
        return 'playlist';
    }

    ['conditions' => $filter_conditions, 'params' => $filter_params] = build_word_filter($p);
    $conditions = array_merge($conditions, $filter_conditions);
    $params     = array_merge($params, $filter_params);
    return 'filter';
}

function build_word_filter(array $p): array {
    global $POS_OPTIONS;
    static $TIER_TOTAL    = 5;
    static $VERDICT_TOTAL = 4;
    $POS_TOTAL = count($POS_OPTIONS);

    // There is one list. `word_tier` used to switch between it and a second
    // `rare_in_use` tab; that tab is gone (see mark_modern_band() in build_ui_db.py for
    // why — it was decided by a frequency list with no resolution below "moderately
    // common"). The column stays and is still filtered on, so a `?word_tier=rare_in_use`
    // link from before simply lands on the list rather than returning nothing.
    $word_tier  = 'forgotten';
    $conditions = ['word_tier = ?'];
    $params     = [$word_tier];

    // ── Defaults that shape what a first-time visitor sees ─────────────────────
    // Each is a one-click toggle in the filter sheet, never a silent exclusion: the
    // whole point of opening this to markers is to learn where these lines are wrong.

    // Seam: 'relevant' is the 3,499-word band with the strongest evidence of having been
    // used and faded; 'curiosity' is the other 14,771.
    //
    // A checkbox group, not a radio with a third „toate" option. The two seams are a
    // partition, so "both ticked" already *is* „toate" — the extra radio was a third name
    // for a state the other two could express, and it had to be kept in step with them.
    // This also lines it up with `verdict`/`tier`/`pos`, which have always been checkbox
    // groups read through parse_multi().
    //
    // Nothing ticked means no condition rather than no results, matching those three: an
    // empty group reads as "don't filter on this", which is what an untouched group means
    // and what a reader clearing the last box almost certainly wants.
    if (db_has_column('seam')) {
        $seam_values = array_values(array_intersect(
            parse_multi($p['seam'] ?? 'relevant'), ['relevant', 'curiosity']));
        if ($seam_values !== [] && count($seam_values) < 2) {
            $conditions[] = 'seam = ?';
            $params[]     = $seam_values[0];
        }
    }

    // ── Special classes: hidden, included, or the only thing shown ──────────────
    //
    // Four controls over six flags. Each control is one three-state row in the sheet:
    //
    //   regional     regional/dialectal without also being tagged old — a word used in
    //                one valley is not a word Romanian forgot
    //   variants     `variant_like` + `archaic_spelling` + `dex_variant` — see below,
    //                this one governs three columns
    //   deverbal     a noun defined as "Faptul de a X" whose verb X is already on the
    //                list and visible — `zăhăială` beside `zăhăi`. The flag is about the
    //                duplication, not the derivation: with the verb absent or itself
    //                hidden, the noun is the only place that root appears at all
    //   diminutives  noruleț, cuconiță
    //   editorial    the curator read the word and marked it ⚠️ meh. Unlike the others
    //                this is a person's judgement rather than a measured property, which
    //                is exactly why it is a control and not a term in quality_score: a
    //                scored-in opinion cannot be appealed. It is also the *only* human
    //                signal permitted to subtract — community marks are aggregated live
    //                and may only reorder (see the `populare` sort), because identity
    //                here is an anonymous device token and hiding a word must not be
    //                cheaper than publishing a list.
    //
    // **`variants` is one control over three columns on purpose.** They are three
    // different measurements of one thing a reader cares about — "this is another
    // spelling of a word that is still alive":
    //
    //     variant_like      the paradigm-sharing ratio (politeță/politețe)
    //     archaic_spelling  a spelling rule plus a much-commoner live twin
    //                       (situațiune → situație, sgomot → zgomot)
    //     dex_variant       DEX's own entry structure — EntryLexeme.main (sofragerie →
    //                       sufragerie, octomvre → octombrie), no spelling rule involved
    //
    // As three rows the sheet read „variante vechi / grafii vechi / variante DEX", three
    // near-synonyms in Romanian that no reader can be expected to tell apart, in a 280px
    // column that also has to hold four other rows. The distinction is real but it is a
    // fact about *how we found the word*, which belongs in the detail panel — and is
    // there, naming the twin in each case. The columns stay separate in `ui.db`; only the
    // control is bundled. `deverbal` is deliberately *not* in the bundle: it says the
    // word is a duplicate of a *different* word on the list, not a spelling of the same
    // one, and it is the one of the four a reader might plausibly want on its own.
    //
    // Each control is a three-state radio rather than a checkbox. The checkbox form
    // forced the polarity to differ per class: an unchecked box is not submitted, so a
    // class hidden by default needed `show_x=1` while one shown by default needed
    // `hide_x=1`, and the sheet ended up with „ascunde…" and „arată…" rows that looked
    // like one set of controls and were not. A radio always submits, so they all read the
    // same way and only the default moves.
    //
    // `only` on several classes means their union — a class left on `hide` is still
    // subtracted from that union, so „doar regionalisme" + „fără variante" drops the rows
    // that are both.
    //
    // Every superseded spelling still resolves, mapped onto the control that now covers
    // it: `spellings=` and `dexvar=` (their own rows until the bundle), and the
    // checkbox-era `show_regional=1` / `show_variants=1` / `show_spellings=1` /
    // `hide_diminutives=1`. **`applyUrlToForm()` in app.js must map the same set**, or an
    // old link renders as unfiltered while behaving as filtered — htmx searches from form
    // state on load, so a server-only mapping is half a mapping.
    //
    $class_modes = class_modes();
    $only_cols   = [];
    foreach ($class_modes as [$param, $cols, $default, $aliases]) {
        $cols = array_values(array_filter($cols, 'db_has_column'));
        if ($cols === []) { continue; }
        $mode = class_mode($p, $param, $default, $aliases);
        if ($mode === 'hide') {
            foreach ($cols as $col) { $conditions[] = "(COALESCE($col, 0) = 0)"; }
        } elseif ($mode === 'only') {
            $only_cols = array_merge($only_cols, $cols);
        }
        // 'back' and 'show' add no condition — 'back' only changes the order.
    }
    if ($only_cols !== []) {
        $parts = array_map(function ($c) { return "COALESCE($c, 0) = 1"; }, $only_cols);
        $conditions[] = '(' . implode(' OR ', $parts) . ')';
    }

    // Minimum historical attestation. Off by default so the no-corpus-signal words
    // (the `oțios` class) stay visible, but available as a filter.
    $hist_min = (int)trim($p['hist_min'] ?? '');
    if ($hist_min > 0 && db_has_column('hist_occ')) {
        $conditions[] = 'hist_occ >= ?';
        $params[]     = $hist_min;
    }

    // Verdict multi-select checkboxes
    $verdict_values = parse_multi($p['verdict'] ?? null);
    if ($verdict_values !== [] && count($verdict_values) < $VERDICT_TOTAL) {
        $ph           = implode(',', array_fill(0, count($verdict_values), '?'));
        $conditions[] = "verdict IN ($ph)";
        $params       = array_merge($params, $verdict_values);
    }

    // Confidence tier checkboxes
    $tier_values = parse_multi($p['tier'] ?? null);
    if ($tier_values !== [] && count($tier_values) < $TIER_TOTAL) {
        $ph           = implode(',', array_fill(0, count($tier_values), '?'));
        $conditions[] = "confidence_tier IN ($ph)";
        $params       = array_merge($params, $tier_values);
    }

    // Taxonomy pipe-delimited single-value filters
    foreach ([
        ['dex_register',  trim($p['register']  ?? '')],
        ['dex_domain',    trim($p['domain']    ?? '')],
        ['dex_etymology', trim($p['etymology'] ?? '')],
    ] as [$col, $val]) {
        if ($val !== '') {
            $conditions[] = "('|'||{$col}||'|' LIKE ?)";
            $params[]     = '%|' . $val . '|%';
        }
    }

    // POS multi-select (OR across selected values)
    $pos_values = parse_multi($p['pos'] ?? null);
    if ($pos_values !== [] && count($pos_values) < $POS_TOTAL) {
        $or_parts     = array_fill(0, count($pos_values), "('|'||dex_pos||'|' LIKE ?)");
        $conditions[] = '(' . implode(' OR ', $or_parts) . ')';
        foreach ($pos_values as $pv) { $params[] = '%|' . $pv . '|%'; }
    }

    // Definition filter
    $has_def = trim($p['has_def'] ?? '');
    if ($has_def === '1') {
        $conditions[] = 'definition IS NOT NULL';
    } elseif ($has_def === '0') {
        $conditions[] = 'definition IS NULL';
    }

    // Minimum dictionaries
    $dict_min_int = (int)trim($p['dict_min'] ?? '');
    if ($dict_min_int > 0) {
        $conditions[] = 'dict_count >= ?';
        $params[]     = $dict_min_int;
    }

    // Last attestation: newest dictionary that still prints the word.
    //
    // A lexicographic signal, entirely independent of the corpus work — a word whose
    // most recent dictionary is Șăineanu (1929) is forgotten in a way one still in
    // DOOM 3 (2021) is not. Mostly useful on the `curiosity` seam: `relevant` requires
    // `in_current_dict` (2005+) to begin with, so `attested_after` is close to always
    // true there and `attested_before` close to always false — both filters are built
    // for drilling into `curiosity`, not `relevant`.
    //
    // Rows with no year are excluded when either bound is set. 453 words have none —
    // the dictionary is unnamed or unmatched — and "unknown" is not evidence of age
    // in either direction.
    $attested_before = (int)trim($p['attested_before'] ?? '');
    if ($attested_before > 0 && db_has_column('newest_dict_year')) {
        $conditions[] = 'newest_dict_year IS NOT NULL AND newest_dict_year < ?';
        $params[]     = $attested_before;
    }
    $attested_after = (int)trim($p['attested_after'] ?? '');
    if ($attested_after > 0 && db_has_column('newest_dict_year')) {
        $conditions[] = 'newest_dict_year IS NOT NULL AND newest_dict_year >= ?';
        $params[]     = $attested_after;
    }

    // How much life the word still has in modern Romanian — the replacement for the
    // deleted „rare" tab, and the thing that tab was reaching for.
    //
    // **More modern usage is better material here, not worse.** The words with a few
    // hundred to a couple of thousand modern occurrences are the ones people recognise
    // as forgotten — `birjă` 1,964, `zapciu` 1,747, `vechil` 1,843, `cocoană` 1,906 —
    // while the words at zero are dictionary ghosts that were never really in
    // circulation (`celșag`, `racaleț`, `barabor`). Sorting by rarity alone puts the
    // ghosts first, which is the mistake $SORT_OPTIONS already records for `sort=rare`.
    //
    // Filters on the stored band, never on a raw count: an occurrence count only means
    // something relative to how much modern text was read, so the edges are rescaled at
    // build time by mark_modern_band(). A number here would silently change meaning the
    // first time a corpus is added.
    if (db_has_column('modern_band')) {
        $modern = trim($p['modern'] ?? '');
        if ($modern !== '' && in_array($modern, ['0', '1', '2'], true)) {
            $conditions[] = 'modern_band = ?';
            $params[]     = (int)$modern;
        }
    }

    // ── Explore filters ────────────────────────────────────────────────────────

    // The zipf range filter is gone. wordfreq scores 17,533 of 17,577 of these words at
    // exactly 0.00 — it has no Romanian data for them — so any floor above zero left 44
    // rows out of 18,270. Same reason `hide_loanwords` went and `proper_noun_like` stopped
    // being a browsing filter: a control that reveals nothing is worse than no control.
    // The column stays for the detail panel and for `sort=rare`'s neighbours.

    // DEX frequency range (0–100 UI scale → 0–1 storage)
    $dexfreq_min = isset($p['dexfreq_min']) && $p['dexfreq_min'] !== '' ? (float)$p['dexfreq_min'] : null;
    $dexfreq_max = isset($p['dexfreq_max']) && $p['dexfreq_max'] !== '' ? (float)$p['dexfreq_max'] : null;
    if ($dexfreq_min !== null) { $conditions[] = 'dex_frequency >= ?'; $params[] = $dexfreq_min / 100.0; }
    if ($dexfreq_max !== null) { $conditions[] = 'dex_frequency <= ?'; $params[] = $dexfreq_max / 100.0; }

    // `hide_loanwords` (en_zipf ≥ 4.0) went with the rare tab. It matched 8 of those 219
    // words and **zero** of the 17,577 here — measured twice, before and after that tab's
    // last rebuild. On this list it is a switch with nothing behind it, which is the same
    // reason `proper_noun_like` stopped being a browsing filter below. The `en_zipf`
    // column stays; only the control is gone.

    // `proper_noun_like` is deliberately *not* a default exclusion any more. It was one
    // when the flag caught 447 words; narrowing it to "DEX knows this spelling only as a
    // capitalised headword" (so that `gheb` stopped being hidden by the surname `Gheb`)
    // left 2 in the whole database — `sirius` and `weltanschauung`, both in `curiosity`.
    // A default hide is only worth its toggle if the toggle reveals something, and this
    // one revealed nothing while quietly subtracting two words. The column still earns
    // its keep as a quality gate on the word of the day (index.php) and on quiz
    // distractors (api/quiz.php), which is a different question from what a browsing
    // reader may see.

    return ['conditions' => $conditions, 'params' => $params, 'word_tier' => $word_tier];
}

