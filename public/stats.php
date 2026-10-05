<?php
declare(strict_types=1);
require_once __DIR__ . '/api/_lib.php';

$registers = vocab('register');
$domains   = vocab('domain');
$etyms     = vocab('etymology');

global $POS_OPTIONS;

?>
<!DOCTYPE html>
<html lang="ro" data-skin="<?= DEFAULT_SKIN ?>">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <?= otios_skin_boot() ?>
  <title>Statistici — Voroave</title>
  <link rel="canonical" href="<?= e(otios_abs_url(NAV_ITEMS['stats']['path'])) ?>">
  <meta property="og:url" content="<?= e(otios_abs_url(NAV_ITEMS['stats']['path'])) ?>">
  <meta property="og:title" content="Statistici — Voroave">
  <meta property="og:description" content="Statistical breakdown of forgotten Romanian words: etymology, parts of speech, registers, domains, and more.">
  <meta property="og:type" content="website">
  <link rel="stylesheet" href="<?= BASE ?>/assets/fonts/app-fonts.css">
  <script src="<?= BASE ?>/assets/lib/htmx-2.0.4.min.js"></script>
  <link rel="stylesheet" href="<?= BASE ?>/assets/app.css">
  <?= otios_skin_links() ?>
    <!-- favicon -->
  <link rel="icon" type="image/png" href="/assets/favicon/favicon-96x96.png" sizes="96x96" />
  <link rel="icon" type="image/svg+xml" href="/assets/favicon/favicon.svg" />
  <link rel="shortcut icon" href="/assets/favicon/favicon.ico" />
  <link rel="apple-touch-icon" sizes="180x180" href="/assets/favicon/apple-touch-icon.png" />
  <meta name="apple-mobile-web-app-title" content="Voroave neglijate" />
  <link rel="manifest" href="/assets/favicon/site.webmanifest" />

</head>
<body style="display:flex;flex-direction:column;height:100vh;overflow:hidden;">

  <?php $page = 'stats'; $brand_tag = 'statistici'; require __DIR__ . '/api/_partials/header.php'; ?>

  <form id="filter-form"
        hx-get="<?= BASE ?>/api/stats.php"
        hx-trigger="change"
        hx-target="#stats-container"
        hx-include="#filter-form">

    <!-- Row 1: word_tier + has_def + loading indicator -->
    <div class="filter-row">
      <div class="seg">
        <label class="seg-opt"><input type="radio" name="word_tier" value="forgotten" checked> uitate</label>
        <label class="seg-opt"><input type="radio" name="word_tier" value="rare_in_use"> rare</label>
      </div>
      <div class="fsep"></div>
      <div class="seg">
        <label class="seg-opt"><input type="radio" name="has_def" value="" checked> any</label>
        <label class="seg-opt"><input type="radio" name="has_def" value="1"> def ✓</label>
        <label class="seg-opt"><input type="radio" name="has_def" value="0"> def ✗</label>
      </div>
      <span class="htmx-indicator" style="margin-left:8px;">loading…</span>
    </div>

    <!-- Row 2: tier + POS checkboxes -->
    <div class="filter-row">
      <span class="flabel">tier</span>
      <?php foreach (TIERS as $v => $meta): ?>
      <label class="pill" title="<?= e($meta['tip']) ?>">
        <input type="checkbox" name="tier[]" value="<?= e($v) ?>" checked> <?= e($meta['label']) ?>
      </label>
      <?php endforeach; ?>
      <div class="fsep"></div>
      <span class="flabel">POS</span>
      <?php foreach ($POS_OPTIONS as [$val, $lbl]): ?>
      <label class="pill">
        <input type="checkbox" name="pos[]" value="<?= e($val) ?>" checked> <?= e($lbl) ?>
      </label>
      <?php endforeach; ?>
    </div>

    <!-- Row 3: taxonomy selects + reset -->
    <div class="filter-row">
      <span class="flabel">filter</span>
      <select name="register" class="tax-select" aria-label="Filter by register">
        <option value="">register: any</option>
        <?php foreach ($registers as $r): ?>
        <option value="<?= e($r) ?>"><?= e($r) ?></option>
        <?php endforeach; ?>
      </select>
      <select name="domain" class="tax-select" aria-label="Filter by domain">
        <option value="">domain: any</option>
        <?php foreach ($domains as $d): ?>
        <option value="<?= e($d) ?>"><?= e($d) ?></option>
        <?php endforeach; ?>
      </select>
      <select name="etymology" class="tax-select" aria-label="Filter by etymology">
        <option value="">etymology: any</option>
        <?php foreach ($etyms as $et): ?>
        <option value="<?= e($et) ?>"><?= e(str_replace('limba ', '', $et)) ?></option>
        <?php endforeach; ?>
      </select>
      <select name="dict_min" class="tax-select" data-default="" aria-label="Minimum dictionaries">
        <option value="">dicts: any</option>
        <option value="3">dicts ≥3</option>
        <option value="6">dicts ≥6</option>
        <option value="10">dicts ≥10</option>
        <option value="15">dicts ≥15</option>
      </select>
      <span id="dex-rare-control" style="display:none">
        <select name="dex_max" class="tax-select" data-default="0.60" aria-label="DEX frequency ceiling">
          <option value="all">DEX: all</option>
          <option value="0.60" selected>DEX-rare ≤0.60</option>
          <option value="0.50">DEX-rare ≤0.50</option>
          <option value="0.30">DEX-rare ≤0.30</option>
        </select>
      </span>
      <button type="reset" id="reset-filters" class="reset-btn" title="Reset all filters">reset</button>
    </div>

  </form>

  <div id="stats-page-content">
    <div id="stats-container"
         hx-get="<?= BASE ?>/api/stats.php"
         hx-trigger="load"
         hx-include="#filter-form"
         hx-swap="innerHTML">
      <span class="htmx-indicator" style="opacity:1;display:block;padding:32px;text-align:center;font-family:var(--serif);font-style:italic;color:var(--text-3);font-size:0.8125rem;">loading…</span>
    </div>
  </div>

  <?php require __DIR__ . '/api/_partials/footer.php'; ?>

  <script src="<?= BASE ?>/assets/prefs.js"></script>
  <script>
  // DEX-rare control visibility (same logic as app.js, no full app.js load needed)
  (function() {
    var ctrl = document.getElementById('dex-rare-control');
    if (!ctrl) return;
    function sync() {
      var sel = document.querySelector('#filter-form input[name=word_tier]:checked');
      ctrl.style.display = (sel && sel.value === 'rare_in_use') ? '' : 'none';
    }
    document.querySelectorAll('#filter-form input[name=word_tier]')
      .forEach(function(r) { r.addEventListener('change', sync); });
    sync();
  })();

  // Tax-select active highlight
  document.querySelectorAll('.tax-select').forEach(function(sel) {
    var dflt = sel.dataset.default !== undefined ? sel.dataset.default : '';
    function update() { sel.classList.toggle('active', sel.value !== dflt); }
    sel.addEventListener('change', update);
    if (sel.form) sel.form.addEventListener('reset', update);
    update();
  });

  // Form reset: re-dispatch change so HTMX re-fires the stats request
  var form = document.getElementById('filter-form');
  if (form) form.addEventListener('reset', function() {
    setTimeout(function() {
      form.dispatchEvent(new Event('change', { bubbles: true }));
    }, 0);
  });
  </script>

</body>
</html>
