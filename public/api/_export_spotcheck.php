<?php
declare(strict_types=1);

// Print the Stage 0 spot-check marks (F09) from app.db as TSV, and nothing else.
//
//   php api/_export_spotcheck.php > spotcheck_marks_export.tsv
//   php api/_export_spotcheck.php --db /path/to/app.db
//
// Output: header line, then `user_id<TAB>word<TAB>tag` for every live annotation tag that
// starts with `sc-`. No notes, no other tags, no bookmarks, no nicknames, no device data.
// Read-only: it opens app.db with SQLITE3_OPEN_READONLY and never runs a migration.
//
// CLI-only. The guard is the first thing that runs, before any include, like _backup.php.
// Run it on the server, then copy the TSV to the laptop:
//   python3 tools/eval_spotcheck.py --from-tsv-export spotcheck_marks_export.tsv

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit("Not Found\n");
}

// Do not include _appdb.php: its helpers can create the private folder and secret.key.
// Only the folder setting is needed, and config.local.php holds nothing but defines.
$args = $argv ?? [];
$i    = array_search('--db', $args, true);
$path = $i !== false && isset($args[$i + 1]) ? (string) $args[$i + 1] : null;

if ($path === null) {
    if (is_file(__DIR__ . '/config.local.php')) {
        require_once __DIR__ . '/config.local.php';
    }
    $dir  = defined('OTIOS_PRIVATE_DIR') ? OTIOS_PRIVATE_DIR : dirname(__DIR__, 2) . '/private';
    $path = $dir . '/app.db';
}

if (!is_file($path)) {
    fwrite(STDERR, "No database at $path\n");
    exit(1);
}

$db   = new SQLite3($path, SQLITE3_OPEN_READONLY);
$res  = $db->query("SELECT user_id, word, tags FROM annotations
                     WHERE deleted = 0 AND tags LIKE '%sc-%'
                     ORDER BY user_id, word");
echo "user_id\tword\ttag\n";
while ($row = $res->fetchArray(SQLITE3_ASSOC)) {
    $tags = json_decode((string) $row['tags'], true);
    if (!is_array($tags)) continue;
    foreach ($tags as $t) {
        if (!is_string($t) || strncmp($t, 'sc-', 3) !== 0) continue;
        // A tab or newline in a word or tag would break the row; none can be a real mark.
        $word = str_replace(["\t", "\r", "\n"], ' ', (string) $row['word']);
        $tag  = str_replace(["\t", "\r", "\n"], ' ', $t);
        echo $row['user_id'], "\t", $word, "\t", $tag, "\n";
    }
}
$db->close();
