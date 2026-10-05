<?php
declare(strict_types=1);

/**
 * Sinonime — DB access, lookup and SVG layout for the synonym writing-aid.
 *
 * Own database (public/data/syn.db), own connection, no app.db and no auth: a public
 * read must not mint a device identity for every passing crawler, the guard colectii.php
 * already documents. Requires _lib.php only for BASE / e() / normalize_diacritics() /
 * skins — never _appdb.php or _auth.php. See docs/sinonime/spec.md Phase 3.
 */

define('SYN_DB_PATH', __DIR__ . '/../data/syn.db');

/**
 * Operational failure of the synonym database: missing, empty, unreadable, not a SQLite
 * file, wrong schema, or a query that fails. The message is for the server log only --
 * it can hold a path. Visitors see syn_unavailable.php and a 503 (brief F01).
 */
class SynUnavailable extends RuntimeException {}

/** Tables and columns the lookup code reads. A database missing any of them is incompatible. */
const SYN_REQUIRED_SCHEMA = [
    'word'       => ['id', 'form', 'pos', 'band'],
    'key'        => ['k', 'word_id'],
    'sense'      => ['id', 'label', 'reg'],
    'sense_word' => ['sid', 'word_id'],
    'edge'       => ['sid', 'word_id', 't'],
];

/**
 * Check the file before PDO sees it. PDO's sqlite driver silently CREATES a missing file
 * when the directory is writable, which turns "not deployed" into "empty database" and a
 * misleading "no such table" error. Throws SynUnavailable with a technical message.
 */
function syn_db_preflight(string $path): void {
    if (!extension_loaded('pdo_sqlite')) throw new SynUnavailable('PHP extension pdo_sqlite is not loaded');
    if (!is_file($path))     throw new SynUnavailable("syn.db is missing: $path");
    if (!is_readable($path)) throw new SynUnavailable("syn.db is not readable by this PHP user: $path");
    $size = filesize($path);
    if ($size === false || $size < 100) throw new SynUnavailable("syn.db is empty or truncated ($size bytes): $path");
}

/** Throws SynUnavailable naming the first missing table or column. */
function syn_db_check_schema(PDO $pdo): void {
    foreach (SYN_REQUIRED_SCHEMA as $table => $cols) {
        $have = array_column($pdo->query('PRAGMA table_info(' . $table . ')')->fetchAll(), 'name');
        if (!$have) throw new SynUnavailable("syn.db schema: table '$table' is missing");
        $gone = array_diff($cols, $have);
        if ($gone) throw new SynUnavailable("syn.db schema: table '$table' lacks column(s) " . implode(',', $gone));
    }
}

function syn_db(): PDO {
    static $pdo = null;
    if ($pdo === null) {
        syn_db_preflight(SYN_DB_PATH);
        try {
            $conn = new PDO('sqlite:' . SYN_DB_PATH, null, null, [
                PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            ]);
            $conn->exec('PRAGMA query_only = ON');
            syn_db_check_schema($conn);
        } catch (PDOException $ex) {
            throw new SynUnavailable('syn.db cannot be opened or read: ' . $ex->getMessage(), 0, $ex);
        }
        $pdo = $conn;
    }
    return $pdo;
}

/**
 * The page and the fragment endpoint both call this, so they share one failure path.
 * Returns ['ok' => true, 'resolved' => ..., 'neighborhood' => ...] or ['ok' => false].
 * An unknown word and an empty query are NOT failures: they come back ok with word null.
 * On failure it logs the detail, sends 503 and no-store, and leaves the body to the caller.
 */
function syn_search(string $q): array {
    try {
        $resolved     = $q !== '' ? syn_resolve($q) : ['word' => null, 'suggestions' => []];
        $neighborhood = $resolved['word'] ? syn_neighborhood($resolved['word']) : null;
        return ['ok' => true, 'resolved' => $resolved, 'neighborhood' => $neighborhood];
    } catch (Throwable $t) {
        syn_report_failure($t);
        return ['ok' => false, 'resolved' => ['word' => null, 'suggestions' => []], 'neighborhood' => null];
    }
}

/** Log the technical detail server-side; send 503 so crawlers and caches do not keep it. */
function syn_report_failure(Throwable $t): void {
    error_log('[sinonime] unavailable: ' . get_class($t) . ': ' . $t->getMessage());
    if (!headers_sent()) {
        http_response_code(503);
        header('Retry-After: 300');
        header('Cache-Control: no-store');
    }
}

// modelType -> short Romanian label. T and IL are inflected-form artifacts rather than
// real headword POS (see CLAUDE.md's dex_pos gotcha) and are deliberately left unmapped —
// syn_pos_label() returns '' for them, so the UI omits the line rather than printing 'T'.
const SYN_POS_LABELS = [
    'F'  => 'substantiv feminin',
    'M'  => 'substantiv masculin',
    'N'  => 'substantiv neutru',
    'A'  => 'adjectiv',
    'I'  => 'invariabil',
    'V'  => 'verb',
    'VT' => 'verb tranzitiv',
    'VI' => 'verb intranzitiv',
    'VR' => 'verb reflexiv',
    'PT' => 'participiu',
    'SP' => 'substantiv propriu',
    'AF' => 'adjectiv feminin',
    'AM' => 'adjectiv masculin',
    'AN' => 'adjectiv neutru',
    'NL' => 'nume de loc',
    'P'  => 'pronume',
];

function syn_pos_label(?string $model_type): string {
    return SYN_POS_LABELS[$model_type ?? ''] ?? '';
}

// sense.reg bitmask -> label, same bit order as tools/build_syn_db.py's REG_BITS.
const SYN_REG_LABELS = [
    0 => 'regional', 1 => 'învechit', 2 => 'rar', 3 => 'familiar', 4 => 'popular',
    5 => 'peiorativ', 6 => 'figurat', 7 => 'argou', 8 => 'livresc',
];

function syn_reg_labels(int $bitmask): array {
    $out = [];
    foreach (SYN_REG_LABELS as $bit => $label) {
        if ($bitmask & (1 << $bit)) $out[] = $label;
    }
    return $out;
}

const SYN_BAND_WORDS = [
    'absent azi', 'foarte slab', 'slab', 'moderat-slab',
    'moderat', 'moderat-viu', 'viu', 'foarte viu',
];

/** A CSS-filled meter plus a text equivalent, so the band survives without the meter's
 * visual fill (ui.md § accessibility: "the band stated in text as well as in the meter"). */
function syn_band_meter(int $band): string {
    $band = max(0, min(7, $band));
    $pct  = (int) round(($band / 7) * 100);
    $desc = SYN_BAND_WORDS[$band];
    return sprintf(
        '<span class="syn-meter" style="--syn-fill:%d%%" role="img" aria-label="folosire azi: %s"><i></i></span>'
        . '<span class="syn-meter-text">%s</span>',
        $pct, e($desc), e($desc)
    );
}

/**
 * Fold a query the same way tools/build_syn_db.py's fold() and _lib.php's
 * normalize_diacritics() do, so 'tanar' and 'sofragerie' resolve through `key`.
 */
function syn_fold(string $s): string {
    return normalize_diacritics($s);
}

/**
 * Resolve a query string to a word row, trying exact -> prefix -> substring against
 * key.k (folded), in that order, never falling through once a tier has a hit. Spec.md
 * "Search order": a writing aid nearly always knows the spelling, so prefix (index-backed)
 * covers the common near-miss and substring is the rare fallback.
 *
 * Returns ['word' => row, 'suggestions' => [rows...]] -- suggestions are populated only
 * when there is no exact hit, so the empty state (ui.md) can offer nearest matches.
 */
function syn_resolve(string $q): array {
    $q = trim($q);
    if ($q === '') return ['word' => null, 'suggestions' => []];
    $folded = syn_fold($q);
    $db = syn_db();

    $exact = $db->prepare(
        'SELECT w.* FROM key k JOIN word w ON w.id = k.word_id WHERE k.k = ? '
        . 'ORDER BY (w.form = ?) DESC, w.band DESC, w.form ASC LIMIT 1');
    $exact->execute([$folded, $q]);
    $hit = $exact->fetch();
    if ($hit) return ['word' => $hit, 'suggestions' => []];

    $prefix = $db->prepare(
        'SELECT DISTINCT w.* FROM key k JOIN word w ON w.id = k.word_id WHERE k.k LIKE ? '
        . 'ORDER BY w.band DESC, w.form ASC LIMIT 8');
    $prefix->execute([$folded . '%']);
    $rows = $prefix->fetchAll();
    if ($rows) {
        if (count($rows) === 1) return ['word' => $rows[0], 'suggestions' => []];
        return ['word' => null, 'suggestions' => $rows];
    }

    $sub = $db->prepare(
        'SELECT DISTINCT w.* FROM key k JOIN word w ON w.id = k.word_id WHERE k.k LIKE ? '
        . 'ORDER BY w.band DESC, w.form ASC LIMIT 8');
    $sub->execute(['%' . $folded . '%']);
    $rows = $sub->fetchAll();
    return ['word' => null, 'suggestions' => $rows];
}

/** Autocomplete: prefix-only, index-backed, capped at 8. api/syn.php's ?ac= path. */
function syn_autocomplete(string $q): array {
    $folded = syn_fold(trim($q));
    if ($folded === '') return [];
    $stmt = syn_db()->prepare(
        'SELECT DISTINCT w.form, w.band FROM key k JOIN word w ON w.id = k.word_id '
        . 'WHERE k.k LIKE ? ORDER BY w.band DESC, w.form ASC LIMIT 8');
    $stmt->execute([$folded . '%']);
    return $stmt->fetchAll();
}

/**
 * The two-way symmetric lookup tools/build_syn_db.py's docstring promises: `sense_word`
 * holds a sense's own word(s), `edge` holds the related ones, one direction per DB row
 * (rule 1-2) -- so finding everything related to $word_id means looking both ways:
 * forward (word is a sense_word member -> read that sense's edges) and backward (word is
 * an edge target -> read that sense's sense_word). Without the backward half, any word
 * that only ever appears as a Relation *target* (64% of stored pairs, findings.md §2)
 * would show no synonyms of its own.
 *
 * Returns senses ordered (max band in sense DESC, sense.id ASC) per ui.md's angle rule,
 * each with its ring-1 members already ordered band DESC/form ASC and capped.
 */
function syn_lookup_senses(int $word_id, int $type = 1): array {
    $db = syn_db();
    $stmt = $db->prepare("
        SELECT e.sid AS sid, s.label AS label, s.reg AS reg,
               e.word_id AS word_id, w.form AS form, w.pos AS pos, w.band AS band
          FROM sense_word sw
          JOIN edge e   ON e.sid = sw.sid AND e.t = ?
          JOIN sense s  ON s.id  = e.sid
          JOIN word w   ON w.id  = e.word_id
         WHERE sw.word_id = ? AND e.word_id != ?
        UNION
        SELECT e.sid AS sid, s.label AS label, s.reg AS reg,
               sw2.word_id AS word_id, w.form AS form, w.pos AS pos, w.band AS band
          FROM edge e
          JOIN sense_word sw2 ON sw2.sid = e.sid
          JOIN sense s        ON s.id    = e.sid
          JOIN word w         ON w.id    = sw2.word_id
         WHERE e.word_id = ? AND e.t = ? AND sw2.word_id != ?
    ");
    $stmt->execute([$type, $word_id, $word_id, $word_id, $type, $word_id]);
    $rows = $stmt->fetchAll();

    $senses = [];
    foreach ($rows as $r) {
        $sid = (int) $r['sid'];
        if (!isset($senses[$sid])) {
            $senses[$sid] = ['sid' => $sid, 'label' => $r['label'], 'reg' => (int) $r['reg'], 'members' => []];
        }
        $senses[$sid]['members'][(int) $r['word_id']] = [
            'word_id' => (int) $r['word_id'], 'form' => $r['form'],
            'pos' => $r['pos'], 'band' => (int) $r['band'],
        ];
    }

    // Dedup pass, richest sense first. Without this, a word with its own rich forward
    // cluster (sense_word = {word}, edge = {many synonyms}) also picks up one fragmented
    // extra "sense" per synonym that independently lists it back (backward: sense_word =
    // {that one synonym}, edge = {..., word}) -- văz's own cluster already contains
    // privire/vedere/văzut, but privire/vedere/văzut each also have their own separate
    // DEX entry that lists văz as a synonym, so the backward half of the union surfaces
    // three more sids labelled "privire", "vedere", "văzut" whose only member is that
    // same word again. Richness (member count) rather than band decides the claim order
    // here specifically to prefer the multi-member forward cluster over a same-band
    // singleton; ui.md's (max band DESC, sid ASC) ordering is applied afterward, to the
    // already-deduplicated groups, for the actual display order.
    $richness = $senses;
    usort($richness, fn($a, $b) => count($b['members']) <=> count($a['members'])
        ?: max(array_column($b['members'], 'band') ?: [0]) <=> max(array_column($a['members'], 'band') ?: [0])
        ?: $a['sid'] <=> $b['sid']);

    $claimed = [];
    foreach ($richness as $i => $s) {
        foreach ($s['members'] as $wid => $m) {
            if (isset($claimed[$wid])) {
                unset($richness[$i]['members'][$wid]);
            } else {
                $claimed[$wid] = true;
            }
        }
    }
    $senses = array_values(array_filter($richness, fn($s) => count($s['members']) > 0));

    foreach ($senses as &$s) {
        uasort($s['members'], fn($a, $b) => $b['band'] <=> $a['band'] ?: strcmp($a['form'], $b['form']));
        $s['members']  = array_values($s['members']);
        $s['max_band'] = $s['members'] ? $s['members'][0]['band'] : 0;
    }
    unset($s);

    usort($senses, fn($a, $b) => $b['max_band'] <=> $a['max_band'] ?: $a['sid'] <=> $b['sid']);
    return array_values($senses);
}

/**
 * Build the capped neighbourhood a word's page renders: up to 4 senses, ring-1 capped at
 * 6/sense and 12 total, ring-2 capped at 4/parent and 24 total -- ui.md § Caps, the whole
 * reason the graph is bounded (uncapped depth-2 draws up to 2,400 nodes).
 *
 * Returns:
 *   ['center' => word row,
 *    'senses' => [ ['sid','label','reg','members' => [ member + 'ring2' => [...] ]] ... ] ]
 */
function syn_neighborhood(array $center): array {
    $wid = (int) $center['id'];
    $all_senses = syn_lookup_senses($wid, 1);

    $senses = array_slice($all_senses, 0, 4);
    $ring1_total = 0;
    foreach ($senses as &$s) {
        $budget = max(0, 12 - $ring1_total);
        $s['members'] = array_slice($s['members'], 0, min(6, $budget));
        $ring1_total += count($s['members']);
    }
    unset($s);

    // Ring 2: walk ring-1 nodes in the same order the graph will render them (sense
    // priority, then within-sense band/form order -- already how $senses is shaped), one
    // parent at a time, each contributing up to 4 children, capped at 24 total and never
    // reusing a word already placed as the centre, ring-1, or an earlier ring-2 slot.
    $placed = [$wid => true];
    foreach ($senses as $s) {
        foreach ($s['members'] as $m) { $placed[$m['word_id']] = true; }
    }

    $ring2_total = 0;
    foreach ($senses as &$s) {
        foreach ($s['members'] as &$m) {
            $m['ring2'] = [];
            if ($ring2_total >= 24) continue;
            $candidates = syn_lookup_senses($m['word_id'], 1);
            $taken = 0;
            foreach ($candidates as $cs) {
                foreach ($cs['members'] as $cm) {
                    if ($taken >= 4 || $ring2_total >= 24) break 2;
                    if (isset($placed[$cm['word_id']])) continue;
                    $m['ring2'][] = $cm;
                    $placed[$cm['word_id']] = true;
                    $taken++;
                    $ring2_total++;
                }
            }
        }
        unset($m);
    }
    unset($s);

    return ['center' => $center, 'senses' => $senses, 'sense_count_total' => count($all_senses)];
}

// ── Layout: deterministic radial arithmetic, no simulation ── ui.md § Layout
const SYN_CX = 410.0;
const SYN_CY = 350.0;
const SYN_EDGE_START = 18.0;
const SYN_GAP = 0.06;
const SYN_LABEL_PAD = 6;

function syn_r1(int $n1): float {
    return max(140.0, min(180.0, 130.0 + 6.0 * $n1));
}

/**
 * Pure arithmetic: capped node lists in, coordinates out. No DB access, no HTML -- what
 * keeps the geometry in ui.md testable and syn_svg() a formatter. See ui.md § Layout.
 */
function syn_layout(array $neighborhood): array {
    $senses = $neighborhood['senses'];
    $n1 = array_sum(array_map(fn($s) => count($s['members']), $senses));
    $r1 = syn_r1($n1);
    $r2 = $r1 + 100.0;

    $weights = array_map(fn($s) => count($s['members']) + 1, $senses);
    $total_w = array_sum($weights) ?: 1;

    $nodes = [];   // word_id => ['x','y','r','opacity','label','ring']
    $theta = -M_PI / 2;
    $multi = count($senses) > 1;

    foreach ($senses as $i => $s) {
        $share = $weights[$i] / $total_w;
        $span  = 2 * M_PI * $share;
        $start = $theta + ($multi ? SYN_GAP : 0);
        $width = $multi ? max(0.0, $span - 2 * SYN_GAP) : $span;
        $n = count($s['members']);

        foreach ($s['members'] as $j => $m) {
            $a = $n > 0 ? $start + ($j + 0.5) * $width / $n : $start + $width / 2;
            $x = SYN_CX + $r1 * cos($a);
            $y = SYN_CY + $r1 * sin($a);
            $nodes[$m['word_id']] = [
                'x' => $x, 'y' => $y, 'angle' => $a, 'ring' => 1,
                'r' => 3.5 + 0.8 * $m['band'], 'opacity' => max(0.45, 0.38 + 0.088 * $m['band']),
                'form' => $m['form'], 'band' => $m['band'],
            ];

            $m2 = count($m['ring2']);
            if ($m2 > 0) {
                $s_slot = $width / max(1, $n);
                foreach ($m['ring2'] as $k => $cm) {
                    $a2 = $a - 0.45 * $s_slot + ($k + 0.5) * 0.9 * $s_slot / $m2;
                    $x2 = SYN_CX + $r2 * cos($a2);
                    $y2 = SYN_CY + $r2 * sin($a2);
                    if (!isset($nodes[$cm['word_id']])) {
                        $nodes[$cm['word_id']] = [
                            'x' => $x2, 'y' => $y2, 'angle' => $a2, 'ring' => 2, 'parent' => $m['word_id'],
                            'r' => 3.5 + 0.8 * $cm['band'], 'opacity' => max(0.45, 0.38 + 0.088 * $cm['band']),
                            'form' => $cm['form'], 'band' => $cm['band'],
                        ];
                    }
                }
            }
        }
        $theta += $span;
    }

    return ['nodes' => $nodes, 'r1' => $r1, 'r2' => $r2];
}

function syn_label_text(string $form): string {
    if (mb_strlen($form) > 16) return mb_substr($form, 0, 15) . '…';
    return $form;
}

/** Formatter only -- reads $neighborhood + $layout, emits SVG. No DB, no layout math. */
function syn_svg(array $neighborhood, array $layout): string {
    $center = $neighborhood['center'];
    $nodes  = $layout['nodes'];

    $edges_svg = ''; $nodes_svg = ''; $labels_svg = '';

    foreach ($nodes as $wid => $n) {
        $ex1 = SYN_CX; $ey1 = SYN_CY;
        if (($n['ring'] ?? 1) === 2 && isset($nodes[$n['parent']])) {
            $ex1 = $nodes[$n['parent']]['x']; $ey1 = $nodes[$n['parent']]['y'];
        }
        // Edges leave the centre outside the headword's halo, never from (cx,cy) itself,
        // for ring-1 nodes; ring-2 edges run parent -> child directly.
        if (($n['ring'] ?? 1) === 1) {
            $dx = $n['x'] - SYN_CX; $dy = $n['y'] - SYN_CY;
            $len = max(0.001, sqrt($dx * $dx + $dy * $dy));
            $sx = SYN_CX + $dx / $len * SYN_EDGE_START;
            $sy = SYN_CY + $dy / $len * SYN_EDGE_START;
        } else {
            $sx = $ex1; $sy = $ey1;
        }
        $stroke = ($n['ring'] ?? 1) === 1 ? 'var(--syn-edge)' : 'var(--syn-edge)';
        $opacity = ($n['ring'] ?? 1) === 1 ? 0.55 : 0.32;
        $edges_svg .= sprintf(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%s" opacity="%.2f"/>' . "\n",
            $sx, $sy, $n['x'], $n['y'], $stroke, ($n['ring'] ?? 1) === 1 ? '1.4' : '1', $opacity
        );
    }

    foreach ($nodes as $wid => $n) {
        $href = BASE . '/sinonime?q=' . urlenc($n['form']);
        $cls = 'syn-node' . (($n['ring'] ?? 1) === 2 ? ' syn-node--ring2' : '');
        $nodes_svg .= sprintf(
            '<a href="%s" class="%s" data-word="%s"><circle cx="%.1f" cy="%.1f" r="%.2f" fill="var(--syn-node)" opacity="%.2f"><title>%s</title></circle></a>' . "\n",
            e($href), $cls, e($n['form']), $n['x'], $n['y'], $n['r'], $n['opacity'], e($n['form'])
        );

        $label = syn_label_text($n['form']);
        $anchor = cos($n['angle']) >= 0 ? 'start' : 'end';
        $lx = $anchor === 'start' ? $n['x'] + $n['r'] + SYN_LABEL_PAD : $n['x'] - $n['r'] - SYN_LABEL_PAD;
        $size = ($n['ring'] ?? 1) === 1 ? 11 : 9.5;
        $labels_svg .= sprintf(
            '<a href="%s"><text x="%.1f" y="%.1f" text-anchor="%s" dominant-baseline="middle" '
            . 'font-size="%s" paint-order="stroke" stroke="var(--surface)" stroke-width="4" '
            . 'fill="var(--syn-node)" opacity="%.2f">%s</text></a>' . "\n",
            e($href), $lx, $n['y'], $anchor, $size, max(0.45, $n['opacity']), e($label)
        );
    }

    $center_label = e($center['form']);
    $sense_count = count($neighborhood['senses']);
    // ui.md's own example ("frumos: 6 sinonime în 2 sensuri") counts ring-1 only -- ring-2
    // words are synonyms-of-synonyms (semantic drift), not synonyms of the centre itself.
    $ring1_count = array_sum(array_map(fn($s) => count($s['members']), $neighborhood['senses']));
    $aria = sprintf('%s: %d %s în %d %s', $center['form'], $ring1_count,
        $ring1_count === 1 ? 'sinonim' : 'sinonime', $sense_count, $sense_count === 1 ? 'sens' : 'sensuri');

    return '<svg role="img" aria-label="' . e($aria) . '" viewBox="0 0 820 700" class="syn-graph" xmlns="http://www.w3.org/2000/svg">' . "\n"
        . '<g class="syn-edges">' . $edges_svg . '</g>' . "\n"
        . '<g class="syn-nodes">' . $nodes_svg . '</g>' . "\n"
        . '<g class="syn-labels">' . $labels_svg . "\n"
        . sprintf('<text x="%.1f" y="%.1f" text-anchor="middle" dominant-baseline="middle" '
            . 'font-size="17" font-weight="600" fill="var(--accent)">%s</text>' . "\n",
            SYN_CX, SYN_CY, $center_label)
        . '</g>' . "\n"
        . '</svg>';
}
