<?php
declare(strict_types=1);
require_once __DIR__ . '/api/_lib.php';

$total      = (int)db()->query("SELECT COUNT(*) FROM words WHERE word_tier='forgotten'")->fetchColumn();
$registers  = vocab_counts('register');
$domains    = vocab('domain');
$etyms      = vocab('etymology');

// Cuvântul zilei — disabled. Flip to true to bring the banner back; the markup
// and the JS (openWotd/dismissWotd/initWotd) are still in place.
const SHOW_WOTD = false;

$WOTD_FILTER = "word_tier='forgotten' AND has_definition=1 "
             . "AND (proper_noun_like IS NULL OR proper_noun_like=0) AND dict_count >= 3";
$wotd = null;
if (SHOW_WOTD) {
    $wotd_total = (int)db()->query("SELECT COUNT(*) FROM words WHERE $WOTD_FILTER")->fetchColumn();
    if ($wotd_total > 0) {
        $seed = (int)floor(time() / 86400) % $wotd_total;
        $ws   = db()->prepare("SELECT word, definition FROM words WHERE $WOTD_FILTER ORDER BY word LIMIT 1 OFFSET ?");
        $ws->execute([$seed]);
        $wotd = $ws->fetch() ?: null;
    }
}

global $QUICK_TAGS, $POS_OPTIONS;

?>
<!DOCTYPE html>
<html lang="ro" data-skin="<?= DEFAULT_SKIN ?>">
<head>
  <meta charset="utf-8">
  <!-- No maximum-scale: blocking pinch-zoom fails WCAG 1.4.4, and this site is
       nothing but unfamiliar words. The in-app A−/A+ stepper is an addition to
       browser zoom, not a replacement for it. -->
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <?= otios_skin_boot() ?>
  <?php
  // A `?word=` link is the site's main shareable unit and used to carry no metadata:
  // the param was read only by app.js, after load, so every link ever posted previewed
  // as the generic site card and a crawler saw none of the 18,270 words. share_meta()
  // returns null for anything not in the table, which is also what makes `?word=<junk>`
  // fall back to the site's own titles rather than advertising a word we cannot show.
  $sm    = share_meta($_GET);
  // The other half of a share, and the one below the fold: which filter-sheet controls
  // have to relax for the shared word to be in the list *behind* the panel. Keyed off
  // $sm['word'] rather than the raw param, so junk resolves to an empty map for the same
  // reason it falls back to the site's own titles above. Applied by applyUrlToForm()
  // before htmx fires the first search — see share_relax_params().
  $relax = $sm ? share_relax_params($sm['word']) : [];
  $title = $sm ? $sm['title'] : 'Voroave neglijate';
  $desc  = $sm ? $sm['desc']
                : 'Suveranism lexical. Cuvinte aproximativ căzute în uitare.';
  $canon = $sm ? $sm['canonical'] : site_origin() . '/';

  // Server-rendered word body, so a `?word=` hit ships real content instead of the
  // empty #detail-panel div app.js used to fill client-side only. Uses the same loader
  // as api/word.php (senses and citations included), so direct arrival and a click
  // show the same definition.
  $detail = $sm ? load_word_detail($sm['word']) : null;
  $w = $detail['w'] ?? null;
  ?>
  <title><?= e($title) ?></title>
  <meta name="description" content="<?= e($desc) ?>">
  <link rel="canonical" href="<?= e($canon) ?>">
  <meta property="og:title" content="<?= e($title) ?>">
  <meta property="og:description" content="<?= e($desc) ?>">
  <meta property="og:url" content="<?= e($canon) ?>">
  <meta property="og:image" content="<?= e(site_origin()) ?>/assets/despre/screenshot-voroave.png">
  <!-- `article` for a single word, `website` for the explorer — a word page is a
       document about one thing, and previews treat the two differently. -->
  <meta property="og:type" content="<?= $sm ? 'article' : 'website' ?>">
  <meta property="og:site_name" content="Voroave neglijate">
  <meta name="twitter:card" content="summary_large_image">
  <?php if ($w): ?>
  <script type="application/ld+json"><?= json_encode([
      '@context' => 'https://schema.org',
      '@type' => 'DefinedTerm',
      'name' => $w['word'],
      'description' => $sm['desc'],
      'url' => $sm['canonical'],
      'inLanguage' => 'ro',
      'inDefinedTermSet' => [
          '@type' => 'DefinedTermSet',
          'name' => 'Voroave neglijate',
          'url' => site_origin() . '/',
      ],
  ], JSON_UNESCAPED_UNICODE) ?></script>
  <?php endif; ?>
  <link rel="stylesheet" href="<?= BASE ?>/assets/fonts/app-fonts.css">
  <script src="<?= BASE ?>/assets/lib/htmx-2.0.4.min.js"></script>
  <link rel="stylesheet" href="<?= BASE ?>/assets/app.css">
  
  <!-- favicon -->
  <link rel="icon" type="image/png" href="/assets/favicon/favicon-96x96.png" sizes="96x96" />
  <link rel="icon" type="image/svg+xml" href="/assets/favicon/favicon.svg" />
  <link rel="shortcut icon" href="/assets/favicon/favicon.ico" />
  <link rel="apple-touch-icon" sizes="180x180" href="/assets/favicon/apple-touch-icon.png" />
  <meta name="apple-mobile-web-app-title" content="Voroave neglijate" />
  <link rel="manifest" href="/assets/favicon/site.webmanifest" />

  <?= otios_skin_links() ?>
</head>
<body>

  <!-- ═══════════════════════════════════════
       BRAND BAR — shared shell, three slots of explorer-specific controls.
       Nav lives in the footer; see api/_partials/header.php for why.
  ══════════════════════════════════════════ -->
  <?php
  $page = 'index';

  ob_start(); ?>
    <!-- Opens the shortcuts/legend modal — explorer-only, so it rides along in
         $header_nav_extra rather than living in header.php itself.

         **Wide-only, and header.php puts a link to /despre in this slot below
         901px.** Two thirds of that modal is keyboard shortcuts, which a phone
         has no way to press; the remaining third is the colour legend, and
         `despre` carries the same table verbatim plus the one thing the modal
         never explained — what the marks are for. So on a phone the `?` is
         better spent on the page that answers both. -->
    <a href="#" class="shortcuts-link shortcuts-link--wide" onclick="showShortcuts();return false;"
       title="Legendă și scurtături"><kbd>?</kbd><span class="shortcuts-alt">legendă</span></a>
  <?php $header_nav_extra = ob_get_clean();

  ob_start(); ?>
    <!-- Collapsed behind a magnifier by default — see openSearch()/closeSearchIfEmpty()
         in app.js. Opens on click, on the `/` shortcut, or already-open if the page
         loaded with a `q` in the URL (applyUrlToForm sets the value; the open check
         runs right after it). -->
    <div class="search-wrap" id="search-wrap">
      <button type="button" class="search-toggle-btn" id="search-toggle-btn"
              onclick="openSearch(true)" aria-label="Caută" aria-expanded="false"
              aria-controls="search" title="Caută (/)">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.6"/>
          <line x1="11" y1="11" x2="15" y2="15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
        </svg>
      </button>
      <input id="search" form="filter-form"
             type="text" name="q" placeholder="caută un cuvânt…"
             hx-get="<?= BASE ?>/api/search.php" hx-trigger="input changed delay:200ms"
             hx-target="#word-list" hx-include="#filter-form, #search" autocomplete="off"
             onblur="closeSearchIfEmpty()"
             title="Caută (diacriticele opționale: 'otios' găsește 'oțios')">
    </div>
  <?php $header_center = ob_get_clean();

  ob_start(); ?>
    <span class="htmx-indicator brand-spinner" aria-hidden="true">…</span>
    <span id="result-count" class="result-count"><?= number_format((int)$total) ?></span>
  <?php $header_tools = ob_get_clean();

  ob_start(); ?>
    <!-- Filter button — stays last in the bar, so it is the `$header_after` slot -->
    <button type="button" class="filter-toggle-btn" id="filter-toggle-btn"
            onclick="toggleFilterDrawer()" aria-label="Filtre" aria-expanded="false">
      <svg width="16" height="11" viewBox="0 0 16 11" fill="none" aria-hidden="true">
        <rect width="16" height="2" rx="1" fill="currentColor"/>
        <rect y="4.5" width="11" height="2" rx="1" fill="currentColor"/>
        <rect y="9" width="7" height="2" rx="1" fill="currentColor"/>
      </svg>
      <span class="filter-btn-label">filtre</span> <span class="filter-count-badge" id="filter-count-badge" style="display:none"></span>
    </button>
  <?php $header_after = ob_get_clean();

  require __DIR__ . '/api/_partials/header.php';
  ?>

  <!-- ═══════════════════════════════════════
       LAYOUT ROW — filter rail (desktop) + word area.
       Below 1024px the rail leaves the flow and becomes a bottom drawer.
  ══════════════════════════════════════════ -->
  <div class="layout-row">

  <!-- ═══════════════════════════════════════
       FILTER SHEET / RAIL
  ══════════════════════════════════════════ -->
  <form id="filter-form"
        class="filter-sheet"
        hx-get="<?= BASE ?>/api/search.php"
        hx-trigger="change"
        hx-target="#word-list"
        hx-include="#filter-form, #search">

    <!-- Drag handle (drawer only) -->
    <div class="fs-handle-wrap"><div class="fs-handle"></div></div>

    <!-- Header -->
    <div class="fs-header">
      <span class="fs-title">Filtre</span>
      <button type="reset" id="reset-filters" class="fs-reset">resetează</button>
      <button type="button" class="fs-close" onclick="toggleFilterDrawer()">✕</button>
    </div>

    <!-- Shown only while a playlist is open (form gets data-playlist) — the server
         ignores the filters for a curated list, so the sheet has to say so rather
         than sit there looking live. -->
    <p class="fs-playlist-note">
      Listă deschisă — filtrele nu se aplică, ca să vezi toate cuvintele primite.
      Ieși din listă ca să filtrezi.
    </p>

    <!-- Same, for a text search (form gets data-search). A query searches all 18.270 de
         cuvinte, not the ~2.700 the defaults leave standing — see word_scope() in
         api/_lib.php. Only one of the two notes ever shows; search wins, matching the
         server's precedence. -->
    <p class="fs-search-note">
      Cauți — filtrele nu se aplică, ca să găsești orice cuvânt din bază.
      Golește căutarea ca să filtrezi.
    </p>

    <!-- Scrollable body -->
    <div class="fs-body">

      <!-- Sort. The „uitate / rare" tier switch that used to sit here is gone: the rare
           tab was decided by wordfreq's Romanian list, which scores 99.6% of our
           candidates at exactly 0.00 and so could only ever fill with ordinary words.
           What it was reaching for is the „urme azi" control further down, measured on
           17B tokens of CulturaX instead. See mark_modern_band() in build_ui_db.py. -->
      <div class="fs-section fs-section-top">
        <div class="fs-sort-row">
        <select name="sort" class="fs-sort">
          <?php if (db_has_column('quality_score')): ?>
          <!-- Implicit: scorul amestecat cu marcajele tuturor. Voturile doar reordonează,
               niciodată nu scot un cuvânt din listă, iar amortizarea ține mișcarea mică —
               fiecare dublare a numărului de voturi valorează încă vreo două puncte. Vezi
               VOTE_BOOST_SQL în api/_lib.php. -->
          <option value="populare" selected>↓ populare</option>
          <option value="quality">↓ cele mai potrivite</option>
          <?php endif; ?>
          <option value="rare">↓ rarest modern</option>
          <option value="declined">↓ most declined</option>
          <option value="dex_freq">↓ DEX frequency</option>
          <?php if (db_has_column('newest_dict_year')): ?>
          <option value="attested">↑ ultima atestare</option>
          <?php endif; ?>
          <option value="alpha">↕ alphabetical</option>
        </select>
        <button type="button" class="fs-help" aria-expanded="false" aria-controls="fshelp-sortare"
                aria-label="Ce înseamnă ordinea?">?</button>
        </div>
        <p class="fs-help-text" id="fshelp-sortare" hidden>„populare” amestecă scorul din pipeline cu marcajele tuturor — voturile doar reordonează, niciodată nu scot un cuvânt din listă. „cele mai potrivite” e scorul singur. „ultima atestare” pune primul cuvântul pe care niciun dicționar nu l-a mai tipărit de multă vreme.</p>
      </div>

      <?php if (db_has_column('seam')): ?>
      <!-- Seam: which of the two lists you are browsing. A checkbox group rather than a
           radio with a third „toate": the seams are a partition, so both ticked already
           *is* „toate", and the extra option was a third name for a state the other two
           could express. Same shape as verdict/nivel/categorie below. -->
      <div class="fs-section" id="seam-control">
        <?= fs_label('listă', 'Care dintre cele două liste vezi. „relevante” sunt cuvintele cu dovezi puternice că au fost folosite și s-au stins; „curiozități” e restul candidaților, unde dovada e mai slabă. Bifează-le pe amândouă ca să le vezi pe toate.') ?>
        <div class="fs-pills">
          <label class="fs-pill" title="Cuvinte cu dovezi puternice că au fost folosite și s-au stins: atestate istoric, aproape absente azi, în dicționare multe, încă într-unul tipărit din 2005 încoace.">
            <span class="fs-check"></span>
            <input type="checkbox" name="seam[]" value="relevant" checked>
            relevante
          </label>
          <label class="fs-pill" title="Restul candidaților: încă îndeplinesc condițiile, dar dovada e mai slabă — adesea cuvinte care n-au circulat niciodată cu adevărat.">
            <span class="fs-check"></span>
            <input type="checkbox" name="seam[]" value="curiosity">
            curiozități
          </label>
        </div>
      </div>
      <?php endif; ?>

      <!-- Verdict -->
      <div class="fs-section">
        <?= fs_label('verdict', 'Ce spune comparația dintre corpusul istoric (Wikisource + romane vechi) și cel modern (CulturaX, 17 miliarde de cuvinte) despre fiecare cuvânt.') ?>
        <div class="fs-pills">
          <?php foreach (VERDICTS as $v => $meta): ?>
          <label class="fs-pill fs-pill-verdict fs-pill-<?= $meta['dot'] ?>" title="<?= e($meta['tip']) ?>">
            <span class="fs-dot" style="background:var(--<?= $meta['dot'] ?>)"></span>
            <input type="checkbox" name="verdict[]" value="<?= e($v) ?>" checked>
            <?= e($meta['label']) ?>
          </label>
          <?php endforeach; ?>
        </div>
      </div>

      <!-- Nivel / Tier -->
      <div class="fs-section">
        <?= fs_label('nivel', 'De unde vine dovada: din corpus (numărătoare de apariții) sau din DEX (eticheta „învechit”, ori frecvență editorială mare fără nicio apariție modernă).') ?>
        <?php foreach (TIERS as $v => $meta): ?>
        <label class="fs-pill" title="<?= e($meta['tip']) ?>">
          <span class="fs-check"></span>
          <input type="checkbox" name="tier[]" value="<?= e($v) ?>" checked>
          <?= e($meta['label']) ?>
        </label>
        <?php endforeach; ?>
      </div>

      <!-- Categorie / POS -->
      <div class="fs-section">
        <?= fs_label('categorie', 'Partea de vorbire, luată din modelul de flexiune al DEX-ului, nu din etichetele de sens — acoperire 99,5%.') ?>
        <div class="fs-pills fs-pills-pos">
          <?php foreach ($POS_OPTIONS as [$val, $lbl]): ?>
          <label class="fs-pill fs-pill-pos" title="<?= e($val) ?>">
            <span class="fs-check"></span>
            <input type="checkbox" name="pos[]" value="<?= e($val) ?>" checked>
            <?= e($lbl) ?>
          </label>
          <?php endforeach; ?>
        </div>
      </div>

      <!-- Taxonomy selects -->
      <div class="fs-section">
        <?= fs_label('filtru', 'Filtre după ce spune DEX-ul despre cuvânt: registrul, domeniul, etimologia, în câte dicționare apare, când a fost tipărit ultima oară, și cât se mai folosește azi.') ?>
        <select name="register" class="fs-select tax-select" data-default="" title="Filtru după registru DEX">
          <option value="">registru: orice</option>
          <?php foreach ($registers as $r => $cnt): ?>
          <option value="<?= e($r) ?>"><?= e($r) ?> (<?= number_format($cnt) ?>)</option>
          <?php endforeach; ?>
        </select>
        <select name="domain" class="fs-select tax-select" data-default="" title="Filtru după domeniu tehnic">
          <option value="">domeniu: orice</option>
          <?php foreach ($domains as $d): ?>
          <option value="<?= e($d) ?>"><?= e($d) ?></option>
          <?php endforeach; ?>
        </select>
        <select name="etymology" class="fs-select tax-select" data-default="" title="Filtru după limbă de origine">
          <option value="">etimologie: orice</option>
          <?php foreach ($etyms as $et): ?>
          <option value="<?= e($et) ?>"><?= e(str_replace('limba ', '', $et)) ?></option>
          <?php endforeach; ?>
        </select>
        <select name="dict_min" class="fs-select tax-select" data-default="" title="Arată doar cuvintele prezente în cel puțin N dicționare DEX">
          <option value="">dicționare: orice</option>
          <option value="3">≥ 3 dicționare</option>
          <option value="6">≥ 6 dicționare</option>
          <option value="10">≥ 10 dicționare</option>
          <option value="15">≥ 15 dicționare</option>
        </select>
        <?php if (db_has_column('newest_dict_year')): ?>
        <!-- Cel mai recent dicționar care încă tipărește cuvântul, ca interval — după
             Y1, înainte de Y2. Aproape tot ce răspunde la asta stă în seamul
             „curiozități”: „relevante” cere deja prezența într-un dicționar de după
             2005, deci „după” e aproape mereu adevărat acolo și „înainte” aproape
             mereu fals. -->
        <select name="attested_after" class="fs-select tax-select" data-default=""
                title="Cel mai recent dicționar în care apare cuvântul e din anul ales sau mai nou">
          <option value="">ultima atestare (după): oricând</option>
          <option value="1970">după 1970</option>
          <option value="1990">după 1990</option>
          <option value="2005">după 2005</option>
          <option value="2010">după 2010</option>
        </select>
        <select name="attested_before" class="fs-select tax-select" data-default=""
                title="Cel mai recent dicționar în care apare cuvântul e mai vechi de anul ales">
          <option value="">ultima atestare (înainte): oricând</option>
          <option value="1970">înainte de 1970</option>
          <option value="1990">înainte de 1990</option>
          <option value="2005">înainte de 2005</option>
          <option value="2010">înainte de 2010</option>
        </select>
        <?php endif; ?>
        <?php if (db_has_column('modern_band')): ?>
        <!-- Cât se mai folosește azi, măsurat pe CulturaX (17 miliarde de cuvinte).
             Atenție la sens: *mai multă* folosire înseamnă material mai bun, nu mai slab.
             Cuvintele cu câteva mii de apariții sunt exact cele pe care lumea le
             recunoaște ca uitate — birjă, zapciu, vechil, cocoană — iar cele cu zero sunt
             fantome de dicționar, care n-au circulat niciodată (celșag, racaleț, barabor).
             Benzile, nu cifrele, sunt stocate: un prag are sens doar raportat la cât text
             modern s-a citit, deci se rescalează la build. Vezi mark_modern_band(). -->
        <select name="modern" class="fs-select tax-select" data-default=""
                title="Cât de mult mai apare cuvântul în româna de azi (corpus CulturaX)">
          <option value="">urme azi: oricâte</option>
          <option value="2">încă în circulație</option>
          <option value="1">urme slabe</option>
          <option value="0">fără nicio urmă</option>
        </select>
        <?php endif; ?>
        <!-- „marcate" rather than „adnotate": the values cover every kind of meta
             a reader can leave on a word — fav, a quick tag, a custom tag, a note —
             and only the last of those is an annotation in the ordinary sense. The
             option *values* stay `marked`/`unmarked` because they are URL state and
             `markedWordsForFilter()` in app.js reads them. -->
        <select name="marks" class="fs-select tax-select" data-default="all">
          <option value="all">toate cuvintele</option>
          <option value="unmarked">nemarcate</option>
          <option value="marked">marcate</option>
          <option value="bookmarked">☆ favorite</option>
          <?php foreach ($QUICK_TAGS as [$tag, $key]): ?>
          <option value="tag:<?= e($tag) ?>">tag: <?= e($tag) ?></option>
          <?php endforeach; ?>
        </select>
        <div class="fs-row">
          <span class="fs-row-label">definiție</span>
          <div class="seg seg-sm">
            <label class="seg-opt"><input type="radio" name="has_def" value="" checked> orice</label>
            <label class="seg-opt"><input type="radio" name="has_def" value="1"> da</label>
            <label class="seg-opt"><input type="radio" name="has_def" value="0"> nu</label>
          </div>
        </div>
      </div>

      <!-- Clase speciale — one three-state control each. Four read „fără / cu / doar";
           `respinse` reads „în spate / normal / doar" because it is the one class that
           does not subtract — a demoted word sinks to the end of the order instead of
           leaving the list. See demote_order_sql() in api/_lib.php.

           These were six checkboxes, and the polarity had to differ per class because an
           unchecked box submits nothing: three read „arată X" and two „ascunde X", which
           looked like one set of controls and behaved like two. A radio always submits,
           so they all read the same way now and only the default differs. „doar" on
           several means their union; see build_word_filter().

           **„variante" is one row over three columns** (`variant_like`,
           `archaic_spelling`, `dex_variant`). As three rows it read „variante vechi /
           grafii vechi / variante DEX" — three near-synonyms in Romanian, in a 280px
           column that also holds four other rows. Which of the three found a given word
           is a fact about our method, not about the word, and the detail panel already
           names the living twin in each case. Do not split them back apart without
           re-reading the note at $class_modes in api/_lib.php. -->
      <div class="fs-section" id="class-control">
        <?= fs_label('clase', 'Grupuri de cuvinte pe care majoritatea cititorilor nu le vor amestecate în listă. Fiecare e un comutator vizibil, niciodată o excludere tăcută — „doar” ți le arată exact pe ele, ca să vezi unde am tras linia greșit.') ?>
        <?php
        // [param, [columns…], label, default, tip, [off-label, on-label]]
        // A row is drawn when *any* of its columns exists, and the ones that do not are
        // simply not filtered on — same rule build_word_filter() applies.
        $CLASS_ROWS = array_values(array_filter([
          ['regional', ['regional_only'], 'regionalisme', 'hide',
           'Cuvinte marcate doar regional/dialectal, fără să fie și învechite. Un cuvânt folosit într-o vale nu e un cuvânt pe care româna l-a uitat.', ['fără', 'cu']],
          ['variants', ['variant_like', 'archaic_spelling', 'dex_variant'], 'variante', 'hide',
           'Alte scrieri ale unor cuvinte încă foarte vii: sofragerie → sufragerie, octomvre → octombrie, situațiune → situație, politeță → politețe. Le găsim în trei feluri — paradigmă comună, regulă de grafie, sau chiar structura DEX — dar pentru cititor sunt același lucru, așa că sunt un singur comutator. Când deschizi cuvântul, panoul îți spune al cui e varianta.', ['fără', 'cu']],
          ['deverbal', ['deverbal_like'], 'nume de acțiune', 'hide',
           'Substantive definite ca „Faptul de a…”, al căror verb e deja în listă și vizibil: zăhăială lângă zăhăi, opintire lângă opinti. Când verbul lipsește din listă, substantivul rămâne — e singurul loc unde apare rădăcina.', ['fără', 'cu']],
          ['diminutives', ['diminutive_like'], 'diminutive', 'hide',
           'Diminutive (noruleț, cuconiță, fecioraș) — cuvinte pe care DEX le definește ca „diminutiv al lui…”.', ['fără', 'cu']],
          ['editorial', ['editor_demote'], 'respinse', 'back',
           'Cuvinte citite și lăsate deoparte ⚠️. Nu dispar — trec la coada listei. „normal” le pune la locul lor, „doar” ți le arată exact pe ele, ca să vezi unde am greșit.', ['în spate', 'normal']],
        ], function ($row) {
            return array_filter($row[1], 'db_has_column') !== [];
        }));
        ?>
        <?php foreach ($CLASS_ROWS as [$name, $cols, $label, $default, $tip, $words]): ?>
        <?php [$off_val, $off_label] = $name === 'editorial' ? ['back', $words[0]] : ['hide', $words[0]]; ?>
        <div class="fs-row" title="<?= e($tip) ?>">
          <span class="fs-row-label"><?= e($label) ?></span>
          <div class="seg seg-sm">
            <label class="seg-opt"><input type="radio" name="<?= e($name) ?>" value="<?= e($off_val) ?>"<?= $default === $off_val ? ' checked' : '' ?>> <?= e($off_label) ?></label>
            <label class="seg-opt"><input type="radio" name="<?= e($name) ?>" value="show"<?= $default === 'show' ? ' checked' : '' ?>> <?= e($words[1]) ?></label>
            <label class="seg-opt"><input type="radio" name="<?= e($name) ?>" value="only"> doar</label>
          </div>
        </div>
        <?php endforeach; ?>
      </div>

      <!-- Explore: numeric ranges.
           The zipf range that used to sit here is gone. wordfreq has no Romanian data for
           17,533 of the 17,577 words it was offered against — they all score exactly 0.00
           — so `zipf ≥` anything above zero left 44 rows out of 18,270. A slider that
           looks continuous and has two states is worse than no slider, which is the same
           call already made for `hide_loanwords` and for `proper_noun_like` as a browsing
           filter. The `zipf_frequency` column stays; it is just not a control. -->
      <div class="fs-section">
        <?= fs_label('explore', 'Intervale numerice brute, pentru cine vrea să sape: frecvența editorială DEX e un scor de prezență în canonul literar (zapciu 0,96 > internet 0,88), nu o frecvență de folosire.') ?>
        <div class="fs-range-row" title="Frecvență editorială DEX 0–100">
          <span class="fs-range-label">dex</span>
          <input type="number" name="dexfreq_min" step="1" min="0" max="100" placeholder="min" class="fs-input">
          <span class="fs-range-sep">–</span>
          <input type="number" name="dexfreq_max" step="1" min="0" max="100" placeholder="max" class="fs-input">
        </div>
      </div>

    </div><!-- .fs-body -->

    <!-- Apply button (drawer only) -->
    <div class="fs-footer">
      <button type="button" class="fs-apply" onclick="toggleFilterDrawer()">
        Arată <span id="result-count-sheet"><?= number_format((int)$total) ?></span> cuvinte
      </button>
    </div>

    <!-- Playlist transport. `w` is the compact form (base36 word ids, pack_words() in
         api/_lib.php) and is what new links use; `words` is the plaintext form, kept
         so links shared before the codec still load. -->
    <input type="hidden" id="playlist-w" name="w" value="">
    <input type="hidden" id="playlist-words" name="words" value="">

    <!-- The shared word, when this page was opened from a `?word=` link. It rides inside
         the form so htmx sends it with the first search *and* with every load-more (the
         `next_url` is built from $_GET), which is what keeps the pin part of one global
         order instead of putting the word at the top of every page. It is not a filter:
         word_scope() never reads it, and pin_order_sql() only touches the ORDER BY.

         **The param is `pin`, and it must never be `word`.** `hx-include` is one of
         htmx's inherited attributes, so `#word-list`'s `hx-include="#filter-form, #search"`
         applies to every `.word-row` inside it — and a row's own request is
         `api/word.php?word=<the row's word>`. Named `word`, this input appended a second,
         empty `word=` to that URL; PHP keeps the last one, so `api/word.php` saw `''`,
         answered 400, and clicking a word opened nothing at all. The collision is silent
         in both directions — nothing here knows the rows borrow this form. -->
    <input type="hidden" id="share-word" name="pin" value="">
  </form>

  <div class="word-area">

    <div id="playlist-banner" style="display:none">
      <span id="playlist-count"></span>
      <button class="playlist-btn" onclick="copyPlaylistUrl()">copy URL</button>
      <button class="playlist-btn playlist-btn-exit" onclick="exitPlaylist()">✕ exit playlist</button>
    </div>

    <div id="active-filters" aria-label="Active filters"></div>

    <?php if ($wotd): ?>
    <div id="wotd-banner" data-word="<?= e($wotd['word']) ?>" style="display:none">
      <span class="wotd-label">cuvântul zilei</span>
      <button type="button" class="wotd-word" onclick="openWotd()"><?= e($wotd['word']) ?></button>
      <?php if (!empty($wotd['definition'])): ?>
      <span class="wotd-def"><?= e(mb_strimwidth($wotd['definition'], 0, 110, '…')) ?></span>
      <?php endif; ?>
      <button type="button" class="wotd-dismiss" onclick="dismissWotd()" aria-label="închide">✕</button>
    </div>
    <?php endif; ?>

    <div id="app">
      <div id="hover-box">
        <div id="hb-word"></div>
        <div id="hb-verdict-row">
          <span id="hb-verdict" class="verdict-badge"></span>
          <span id="hb-meta"></span>
        </div>
        <div id="hb-def"></div>
      </div>
      <div id="word-list-container">
        <!-- A listbox with a roving tabindex, not 25k tab stops. Tab reaches the list
             once and lands on the selected word (or the first one); j/k/arrows move
             within it and carry the tabindex along. See selectRow() in app.js. -->
        <div id="word-list"
             role="listbox"
             aria-label="Cuvinte"
             tabindex="0"
             hx-get="<?= BASE ?>/api/search.php"
             hx-trigger="load"
             hx-include="#filter-form, #search"
             hx-swap="innerHTML">
          <span class="htmx-indicator">loading…</span>
        </div>
      </div>
      <div id="detail-panel" class="word-detail-panel<?= $w ? ' panel-open' : '' ?>"><?php if ($detail) render('detail.php', $detail + ['ssr' => true]); ?></div>
    </div>

  </div><!-- .word-area -->
  </div><!-- .layout-row -->

  <!-- Status bar — shared nav, plus the one thing only the explorer has -->
  <?php
  ob_start(); ?>
    <span id="status-word-count"><?= (int)$total ?></span> cuvinte · <span id="bookmark-count">0</span> favorite
    <button id="share-bookmarks-btn" onclick="shareBookmarks()" title="Copiază URL playlist" style="display:none">share ↗</button>
  <?php $footer_left = ob_get_clean();

  ob_start(); ?>
    <!-- Legend. The cloud encodes four things with no label anywhere on the
         page: the word's colour (beton) or its dot (paper), two different
         underlines, and the superscript. Hidden below 1280px, where the bar has
         no room — the same legend is in the ? modal for narrow screens. -->
    <span class="status-legend" aria-label="Legendă">
      <span class="lg"><i class="lg-sw lg-sw-ext"></i>dispărut</span>
      <span class="lg"><i class="lg-sw lg-sw-dec"></i>declin</span>
      <span class="lg"><i class="lg-sw lg-sw-hist"></i>istoric</span>
      <span class="lg"><i class="lg-sw lg-sw-abs"></i>absent</span>
      <span class="lg-sep"></span>
      <span class="lg"><i class="lg-mark lg-inv">învechit</i></span>
      <span class="lg"><i class="lg-mark lg-fav">favorit</i></span>
      <span class="lg"><i class="lg-hist">12</i>atestări istorice</span>
    </span>
  <?php $footer_extra = ob_get_clean();

  ob_start(); ?>
    <!-- Play modes (moved out of the filter panel — always reachable). Both
         hidden pending a home for them outside the footer: 🎲/surpriseWord()
         stays bound to the `r` shortcut, 📇/enterFeed() has no shortcut of its
         own yet. Either can come back by unhiding it. -->
    <div class="play-group" role="group" aria-label="Moduri de joc">
      <button type="button" class="play-btn" onclick="surpriseWord()" hidden
              title="Cuvânt aleator din selecția curentă (r)">🎲 <span class="play-label">la întâmplare</span></button>
      <button type="button" class="play-btn" onclick="enterFeed()" hidden
              title="Mod card: cuvânt cu cuvânt (f)">📇 <span class="play-label">feed</span></button>
    </div>

    <!-- View toggle: cloud ⊞ / table ≡ -->
    <div class="view-toggle" id="view-toggle" role="group" aria-label="Mod de afișare">
      <button type="button" class="vt-btn vt-active" id="btn-cloud" aria-pressed="true"
              onclick="setView('cloud')" title="Nor de cuvinte" aria-label="Nor de cuvinte">⊞</button>
      <button type="button" class="vt-btn" id="btn-table" aria-pressed="false"
              onclick="setView('table')" title="Tabel" aria-label="Tabel">≡</button>
    </div>
  <?php $footer_tools = ob_get_clean();

  require __DIR__ . '/api/_partials/footer.php';
  ?>

  <!-- Filter backdrop -->
  <div class="filter-backdrop" id="filter-backdrop" onclick="toggleFilterDrawer()"></div>

  <!-- Feed overlay -->
  <div id="feed-overlay" style="display:none">
    <div class="feed-top">
      <span class="feed-progress" id="feed-progress"></span>
      <button type="button" class="feed-exit" onclick="exitFeed()">✕ ieși</button>
    </div>
    <div class="feed-card" id="feed-card"></div>
    <div class="feed-actions">
      <button type="button" class="feed-skip" onclick="feedSkip()" title="sari (← / h)">✗ sari</button>
      <button type="button" class="feed-keep" onclick="feedKeep()" title="păstrează la favorite (→ / l)">★ păstrează</button>
    </div>
    <div class="feed-hint">← sari · păstrează → &nbsp;·&nbsp; sau glisează stânga/dreapta</div>
  </div>

  <div id="shortcuts-overlay" style="display:none">
    <div id="shortcuts-modal">
      <div class="shortcuts-header">
        <span>Legendă / shortcuts</span>
        <span class="shortcuts-esc">Esc pentru închidere</span>
      </div>
      <table class="shortcuts-table">
        <!-- Legend first: the cloud encodes two things with no label on them —
             the superscript number and (in the beton skin, which drops the
             verdict dot) the colour of the word itself. -->
        <tr><td colspan="2" class="shortcuts-group">Legendă</td></tr>
        <!-- hist_occ, not dex_frequency — see the comment in word_row.php for why. -->
        <tr><td><span class="legend-hist">12</span></td>
            <td>Atestări istorice, <strong>de câte ori apare cuvântul în corpusul istoric</strong> —
                lipsește dacă e zero
                (<a href="<?= BASE ?>/metodologie#frecvente">explicație</a>)</td></tr>
        <tr><td><span class="legend-sw" style="background:var(--v-ext-word,var(--v-ext))"></span></td>
            <td><em>dispărut din uz</em> — niciun semnal modern</td></tr>
        <tr><td><span class="legend-sw" style="background:var(--v-dec-word,var(--v-dec))"></span></td>
            <td><em>în declin</em> — încă folosit, dar tot mai rar</td></tr>
        <tr><td><span class="legend-sw" style="background:var(--v-hist-word,var(--v-hist))"></span></td>
            <td><em>doar istoric</em> — apare doar în surse istorice</td></tr>
        <tr><td><span class="legend-sw" style="background:var(--v-abs-word,var(--v-abs))"></span></td>
            <td><em>absent</em> — niciun semnal în corpus, posibil cel mai uitat</td></tr>
        <tr><td colspan="2" class="shortcuts-group">Acțiuni</td></tr>
        <tr><td><kbd>f</kbd></td><td><em>fav</em> — păstrează</td></tr>
        <!-- <tr><td><kbd>a</kbd></td><td><em>ascunde</em> — neinteresant, prea cunoscut</td></tr> -->
        <tr><td><kbd>l</kbd></td><td><em>lol</em> — amuzant</td></tr>
        <tr><td><kbd>m</kbd></td><td><em>meh</em> — ca <em>ascunde</em>, zis altfel</td></tr>
        <tr><td><kbd>o</kbd></td><td>Deschide dexonline.ro</td></tr>
        <tr><td><kbd>?</kbd></td><td>Arată / ascunde shortcut-uri</td></tr>
            <tr><td colspan="2" class="shortcuts-group">Navigare</td></tr>
        <tr><td><kbd>j</kbd><kbd>k</kbd><kbd>h</kbd><kbd>→</kbd></td><td>Navigare grilă (↓ ↑ ← →) — <kbd>l</kbd> e liber pentru <em>lol</em></td></tr>
        <tr><td><kbd>g</kbd><kbd>g</kbd></td><td>Salt la început</td></tr>
        <tr><td><kbd>G</kbd></td><td>Salt la final</td></tr>
        <tr><td colspan="2" class="shortcuts-group">Căutare</td></tr>
        <tr><td><kbd>/</kbd></td><td>Focus căutare</td></tr>
        <tr><td><kbd>r</kbd></td><td>Cuvânt aleator</td></tr>
        <tr><td><kbd>Esc</kbd></td><td>Închide</td></tr>
        
      </table>
    </div>
  </div>

  <script>
    var OTIOS_BASE = '<?= BASE ?>';
    // Empty unless this request is a `?word=` share whose word the defaults would hide.
    var OTIOS_SHARE_RELAX = <?= json_encode((object) $relax, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT) ?>;
  </script>
  <script src="<?= BASE ?>/assets/prefs.js"></script>
  <script src="<?= BASE ?>/assets/store.js"></script>
  <script src="<?= BASE ?>/assets/app.js"></script>
  <script async src="https://scripts.simpleanalyticscdn.com/latest.js"></script>
  <noscript><img src="https://queue.simpleanalyticscdn.com/noscript.gif" alt="" referrerpolicy="no-referrer-when-downgrade"/></noscript>
</body>
</html>
