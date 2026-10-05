<?php
declare(strict_types=1);
require_once __DIR__ . '/_lib.php';
require_once __DIR__ . '/_syn.php';

// Public read-only fragment endpoint. Never requires _appdb.php or _auth.php -- a device
// token must not be minted for a crawler passing through /sinonime. See _syn.php's header.
header('Content-Type: text/html; charset=utf-8');

if (isset($_GET['ac'])) {
    try {
        $rows = syn_autocomplete((string) ($_GET['q'] ?? ''));
    } catch (Throwable $t) {
        // The suggestion list is optional. Answer 503 with an empty body; the page keeps working.
        syn_report_failure($t);
        exit;
    }
    render('syn_autocomplete.php', ['rows' => $rows]);
    exit;
}

$q = trim((string) ($_GET['q'] ?? ''));
$r = syn_search($q);
if (!$r['ok']) {
    render('syn_unavailable.php');
    exit;
}

render('syn_result.php', ['q' => $q, 'resolved' => $r['resolved'], 'neighborhood' => $r['neighborhood']]);
