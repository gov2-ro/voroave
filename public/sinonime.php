<?php
declare(strict_types=1);
require_once __DIR__ . '/api/_lib.php';
require_once __DIR__ . '/api/_syn.php';

// Served at /sinonime by the existing `.htaccess` $uri.php rewrite -- no new rule needed.
// Reads ?q= and server-renders the whole result region, so a shared link is complete,
// indexable, and works with JavaScript off (docs/sinonime/spec.md Phase 3).
$q = trim((string) ($_GET['q'] ?? ''));
$r            = syn_search($q);   // on an operational failure: logs, sends 503, ok = false
$unavailable  = !$r['ok'];
$resolved     = $r['resolved'];
$neighborhood = $r['neighborhood'];

$title = 'Sinonime';
$desc  = 'O unealtă de scris: alternative pentru cuvinte românești, ordonate după cât de vii sunt azi.';
if ($q !== '' && !$unavailable) {
    if ($resolved['word']) {
        $title = $resolved['word']['form'] . ' — sinonime';
        $desc  = 'Sinonime pentru „' . $resolved['word']['form'] . '", ordonate după folosirea de azi.';
    } else {
        $title = 'Sinonime — ' . $q;
    }
}
$canonical = otios_abs_url('/sinonime' . ($q !== '' ? '?q=' . urlenc($q) : ''));
?>
<!DOCTYPE html>
<html lang="ro" data-skin="<?= DEFAULT_SKIN ?>">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <?= otios_skin_boot() ?>
  <title><?= e($title) ?> — Voroave</title>
  <?php if ($unavailable): ?><meta name="robots" content="noindex">
  <?php endif; ?><meta name="description" content="<?= e($desc) ?>">
  <link rel="canonical" href="<?= e($canonical) ?>">
  <meta property="og:title" content="<?= e($title) ?> — Voroave">
  <meta property="og:description" content="<?= e($desc) ?>">
  <meta property="og:type" content="website">
  <meta property="og:url" content="<?= e($canonical) ?>">
  <link rel="stylesheet" href="<?= BASE ?>/assets/fonts/app-fonts.css">
  <script src="<?= BASE ?>/assets/lib/htmx-2.0.4.min.js"></script>
  <link rel="stylesheet" href="<?= BASE ?>/assets/app.css">
  <?= otios_skin_links() ?>
  <link rel="icon" type="image/png" href="/assets/favicon/favicon-96x96.png" sizes="96x96" />
  <link rel="icon" type="image/svg+xml" href="/assets/favicon/favicon.svg" />
  <link rel="shortcut icon" href="/assets/favicon/favicon.ico" />
  <link rel="apple-touch-icon" sizes="180x180" href="/assets/favicon/apple-touch-icon.png" />
  <link rel="manifest" href="/assets/favicon/site.webmanifest" />
</head>
<body class="page-doc">

  <?php $brand_tag = 'sinonime'; require __DIR__ . '/api/_partials/header.php'; ?>

  <main id="syn-page" class="syn-page">
    <form id="syn-form" hx-get="<?= BASE ?>/api/syn.php" hx-target="#syn-result" hx-push-url="true">
      <label for="syn-q" class="syn-q-label">Caută un cuvânt</label>
      <div class="syn-search-row">
        <input type="text" id="syn-q" name="q" value="<?= e($q) ?>" placeholder="ex: frumos"
               autocomplete="off" autocapitalize="off" spellcheck="false"
               hx-get="<?= BASE ?>/api/syn.php?ac=1" hx-trigger="keyup changed delay:150ms"
               hx-target="#syn-ac" hx-swap="innerHTML">
        <button type="submit" class="syn-search-btn">caută</button>
      </div>
      <div id="syn-ac" class="syn-ac" role="presentation"></div>
    </form>

    <div id="syn-result">
      <?php if ($unavailable) render('syn_unavailable.php');
            else render('syn_result.php', ['q' => $q, 'resolved' => $resolved, 'neighborhood' => $neighborhood]); ?>
    </div>

    <p class="syn-attribution">
      Graful de sinonime vine din <a href="https://dexonline.ro" target="_blank" rel="noopener">dexonline.ro</a>,
      lucrarea comunității care întreține DEX online — mulțumim.
    </p>
  </main>

  <?php require __DIR__ . '/api/_partials/footer.php'; ?>

  <script src="<?= BASE ?>/assets/prefs.js"></script>
  <script>var OTIOS_BASE = '<?= BASE ?>';</script>
  <script src="<?= BASE ?>/assets/syn.js"></script>
</body>
</html>
