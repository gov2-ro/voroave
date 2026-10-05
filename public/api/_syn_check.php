<?php
declare(strict_types=1);

/**
 * Read-only deployment check for /sinonime (brief F01). Run it on the host, from the app folder:
 *
 *     php api/_syn_check.php
 *
 * It checks the PHP runtime, the SQLite library, the file public/data/syn.db, its schema and one
 * real lookup. It prints paths and versions only: no user data, no secrets. Exit code 0 = all
 * checks pass, 1 = at least one failed. CLI only: any web request gets a 404 before any include.
 * Run it as the same user that runs PHP for the site (php-fpm / suPHP), or the permission check
 * answers for the wrong user.
 */
if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}

require_once __DIR__ . '/_lib.php';
require_once __DIR__ . '/_syn.php';

$fail = 0;
function line(string $label, string $value, ?bool $ok = null): void {
    global $fail;
    if ($ok === false) $fail++;
    printf("%-6s %-28s %s\n", $ok === null ? 'info' : ($ok ? 'ok' : 'FAIL'), $label, $value);
}

line('php version', PHP_VERSION . ' (' . PHP_SAPI . ')', version_compare(PHP_VERSION, '8.1', '>='));
foreach (['pdo_sqlite', 'sqlite3', 'mbstring', 'json'] as $ext) {
    line("extension $ext", extension_loaded($ext) ? 'loaded' : 'MISSING', extension_loaded($ext));
}
line('memory_limit', (string) ini_get('memory_limit'));
line('process user', function_exists('posix_getpwuid') ? (posix_getpwuid(posix_geteuid())['name'] ?? '?') : '?');

$path = SYN_DB_PATH;
$real = realpath($path);
line('syn.db path', $real ?: $path);
line('file exists', is_file($path) ? 'yes' : 'NO', is_file($path));
if (is_file($path)) {
    $size = filesize($path);
    line('file size', number_format((int) $size) . ' bytes (a full build is about 16,379,904)', $size > 1000000);
    line('file mode', substr(sprintf('%o', fileperms($path)), -4));
    line('readable by this user', is_readable($path) ? 'yes' : 'NO', is_readable($path));
    $fh = @fopen($path, 'rb');
    $magic = $fh ? fread($fh, 16) : '';
    if ($fh) fclose($fh);
    line('SQLite file header', str_starts_with((string) $magic, "SQLite format 3\0") ? 'valid' : 'NOT A SQLITE FILE',
        str_starts_with((string) $magic, "SQLite format 3\0"));
}
line('data dir writable', is_writable(dirname($path)) ? 'yes (PDO could create an empty syn.db here)' : 'no');

try {
    $db = syn_db();
    line('open and schema', 'ok', true);
    line('SQLite library', (string) $db->query('SELECT sqlite_version()')->fetchColumn());
    foreach (array_keys(SYN_REQUIRED_SCHEMA) as $t) {
        line("rows in $t", (string) $db->query("SELECT COUNT(*) FROM $t")->fetchColumn());
    }
    $meta = $db->query("SELECT v FROM meta WHERE k='build_date'")->fetchColumn();
    line('build_date', (string) ($meta ?: 'none'));
    $t0 = microtime(true);
    $r = syn_resolve('frumos');
    $n = $r['word'] ? syn_neighborhood($r['word']) : null;
    $senses = $n ? count($n['senses']) : 0;
    line('lookup "frumos"', sprintf('%d senses, %.0f ms, peak memory %.1f MB', $senses,
        (microtime(true) - $t0) * 1000, memory_get_peak_usage(true) / 1048576), $senses > 0);
} catch (Throwable $t) {
    line('open and lookup', get_class($t) . ': ' . $t->getMessage(), false);
}

echo $fail ? "\n$fail check(s) failed.\n" : "\nAll checks passed.\n";
exit($fail ? 1 : 0);
