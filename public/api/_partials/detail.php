<?php
// $w = array with word row data. $senses / $cites_by_sense come from load_word_detail()
// (_lib.php), used by api/word.php and by index.php's direct arrival. They are [] on a ui.db built before docs/senses-plan.md landed — default them so this
// partial still renders standalone if that ever changes.
$senses          = $senses ?? [];
$cites_by_sense  = $cites_by_sense ?? [];
// Set only by index.php's server-render of a `?word=` hit — api/word.php never passes
// this, so the only difference between the two paths is the heading tag. A real <h1> there is what gives a `?word=`
// page indexable body content instead of an empty div app.js fills in after load.
$ssr       = $ssr ?? false;
$title_tag = $ssr ? 'h1' : 'div';

$verdict      = $w['verdict'] ?? 'unknown';
$verdict_cls  = str_replace(' ', '_', $verdict);
$pos_parts    = array_filter(array_map('trim', explode('|', $w['dex_pos'] ?? '')));
$reg_parts    = array_filter(array_map('trim', explode('|', $w['dex_register'] ?? '')));
$dom_parts    = array_filter(array_map('trim', explode('|', $w['dex_domain'] ?? '')));
$etym_parts   = array_filter(array_map('trim', explode('|', $w['dex_etymology'] ?? '')));
$etym_parts   = array_map(fn($e) => str_replace('limba ', '', $e), $etym_parts);
// The etymon itself (`badana` for `bidinea`), from Meaning.type=1 via merge_senses() —
// gives the chip above something to say beyond the language name.
$etymon_parts = array_filter(array_map('trim', explode('|', $w['dex_etymon'] ?? '')));

/** Render one node's citations: a single quote inline, several collapsed behind a
 *  <details> so a long list of citations doesn't dominate the sense it belongs to. The
 *  trailing attribution ("PAS, L. I 97.") is kept — it's what makes a quote evidence
 *  rather than decoration, unlike share_excerpt()'s 160-char preview which strips it. */
function render_sense_cites(array $cites): string {
    if (!$cites) return '';
    if (count($cites) === 1) {
        return '<p class="sense-cite">' . e($cites[0]['text']) . '</p>';
    }
    $out = '<details class="sense-cites"><summary>' . count($cites) . ' citate</summary>';
    foreach ($cites as $c) {
        $out .= '<p class="sense-cite">' . e($c['text']) . '</p>';
    }
    return $out . '</details>';
}

/** Render one sense's synonyms (Relation.type=1, via extract_meanings.py's
 *  meaning_synonyms — see merge_senses() in tools/build_ui_db.py). Reuses the
 *  word-level `.fp-syn`/`.syn-chip` look further down this file, so a reader doesn't
 *  have to learn a second visual language for the same idea at a different scope.
 *  Called whether or not the sense has its own text — a sense can have both (dexonline
 *  shows synonyms under a sense that also has prose), and when text is empty this is
 *  the sense's ONLY content, not decoration on top of it. */
function render_sense_synonyms(array $synonyms): string {
    if (!$synonyms) return '';
    $out = '<div class="fp-syn sense-syn"><span class="fp-extra-label">≡ sinonime</span>';
    foreach ($synonyms as $syn) {
        $out .= '<a class="syn-chip" href="' . BASE . '/?q=' . urlenc($syn) . '">' . e($syn) . '</a>';
    }
    return $out . '</div>';
}

$sources = split_pipe($w['sources'] ?? '');
$dict_count = count($sources);

// Comma-separated, unlike the pipe-delimited taxonomy columns — they come from prose in
// the Sinonime dictionaries, where a comma is the separator the source itself uses.
$synonyms = array_values(array_filter(array_map('trim',
    explode(',', $w['synonyms'] ?? '')), fn($s) => $s !== ''));
$antonyms = array_values(array_filter(array_map('trim',
    explode(',', $w['antonyms'] ?? '')), fn($s) => $s !== ''));

$meta_parts = array_filter([
    $pos_parts   ? e($pos_parts[0])   : null,
    $reg_parts   ? e($reg_parts[0])   : null,
    $etym_parts  ? e($etym_parts[0])  : null,
]);
?>
<?php /* One button, two glyphs: a ✕ top-right on desktop, a back arrow top-left on a
     phone, where the sheet fills the screen and the header is hidden behind it —
     "back" is what a full-screen sheet dismisses to, and top-left is where a
     thumb looks for it. Both are in the markup and app.css shows one; a CSS
     `content` swap would have made the visible glyph invisible to assistive
     tech, which reads the accessible name below either way. */ ?>
<button class="fp-close" onclick="closePanel()" aria-label="Închide definiția"><span class="fp-close-x" aria-hidden="true">✕</span><span class="fp-close-back" aria-hidden="true">←</span></button>

<?php /* Head: word + verdict + meta */ ?>
<div class="fp-head">
  <<?= $title_tag ?> class="fp-title"><?= e($w['word']) ?></<?= $title_tag ?>>
  <div class="fp-subtitle">
    <span class="verdict-badge vb-<?= e($verdict_cls) ?>" title="<?= e(VERDICTS[$verdict]['tip'] ?? '') ?>"><?= e(verdict_label($verdict)) ?></span>
    <?php if ($meta_parts): ?>
    <span class="fp-pos-line"><?= implode(' · ', $meta_parts) ?></span>
    <?php endif; ?>
  </div>
</div>

<?php /* Scrollable body */ ?>
<div class="fp-body">

  <?php /* Obsolete spelling: name the living twin rather than leaving the reader to guess
       why a word that looks ordinary is on a list of forgotten ones. Only ever set when
       the modern form is >=20x more frequent in the modern corpus — see
       mark_archaic_spellings() in tools/build_ui_db.py.

       These three notes render ABOVE the definition/senses block below, not after it —
       docs/senses-plan.md §7 invariant 3: the sense tree is DEX's *entry* tree, which
       merges every dictionary that defines a word, so a variant's senses routinely
       carry its headword's own text (`sofragerie` arrives holding `sufragerie`'s DLRLC
       entry). More senses makes that bleed more visible, not less, so the line naming
       the living twin has to be read first. */ ?>
  <?php if (!empty($w['archaic_spelling']) && !empty($w['spelling_of'])): ?>
  <p class="fp-spelling">Grafie veche pentru <strong><?= e($w['spelling_of']) ?></strong>.</p>
  <?php endif; ?>

  <?php /* Same job, DEX's own relation instead of a spelling rule (mark_dex_variants()).
       Worth saying out loud here even more than for `archaic_spelling`, because the
       definition will not give it away: scrape_definitions.py reads dexonline's sinteză,
       which merges a variant into its headword, so `sofragerie` arrives carrying
       `sufragerie`'s full entry — Sadoveanu quote, twin's spelling and all. Without this
       line the panel reads as an ordinary find whose examples inexplicably spell the
       headword differently. The two flags are disjoint by construction, so this never
       doubles up with the line above. */ ?>
  <?php if (!empty($w['dex_variant']) && !empty($w['dex_variant_of'])): ?>
  <p class="fp-spelling">Variantă a lui <strong><?= e($w['dex_variant_of']) ?></strong>, după DEX.</p>
  <?php endif; ?>

  <?php /* Deverbal noun whose verb is on the list too (mark_deverbal_nouns()). Named for
       the same reason as the two above, and with one addition: the verb is *here*, so
       the line is a link rather than a dead end. */ ?>
  <?php if (!empty($w['deverbal_like']) && !empty($w['deverbal_of'])): ?>
  <p class="fp-spelling">Numele acțiunii de a
    <a href="?word=<?= urlencode($w['deverbal_of']) ?>"><strong><?= e($w['deverbal_of']) ?></strong></a>,
    care e și el în listă.</p>
  <?php endif; ?>

  <?php /* Full sense tree (docs/senses-plan.md) when the dump's Meaning table has one for
       this word; the flat one-sentence definition otherwise. **Not a degraded path when
       it fires — 7,470 of 18,270 shortlist words have no Tree/Meaning structure at all,
       so the fallback is half the site, not an edge case.** */ ?>
  <?php $tree_senses = array_values(array_filter($senses, fn($s) => $s['kind'] === 'sense')); ?>
  <?php $extras       = array_values(array_filter($senses, fn($s) => $s['kind'] !== 'sense')); ?>
  <?php if ($tree_senses): ?>
  <ol class="fp-senses">
    <?php foreach ($tree_senses as $s): ?>
    <li class="fp-sense" style="--sense-depth:<?= (int) $s['depth'] ?>">
      <span class="sense-num"><?= e($s['breadcrumb']) ?></span>
      <?php foreach (split_pipe($s['tags']) as $st): ?><span class="detail-tag sense-tag"><?= e($st) ?></span><?php endforeach; ?>
      <?php if ($s['text'] !== ''): ?><span class="sense-text"><?= e($s['text']) ?></span><?php endif; ?>
      <?= render_sense_synonyms(split_pipe($s['synonyms'] ?? '')) ?>
      <?= render_sense_cites($cites_by_sense[(int) $s['ord']] ?? []) ?>
    </li>
    <?php endforeach; ?>
  </ol>
  <?php if ($extras): ?>
  <?php /* Compounds / expressions: phrases built on the headword rather than meanings of it
       alone, so they get a visually distinct block after the senses rather than being
       numbered alongside them — their breadcrumb is always empty in the dump, dexonline
       never numbers them either. */ ?>
  <div class="fp-extras">
    <?php foreach ($extras as $s): ?>
    <div class="fp-extra">
      <span class="fp-extra-label"><?= $s['kind'] === 'compound' ? 'cuvânt compus' : 'expresie' ?></span>
      <?php if ($s['text'] !== ''): ?><span class="sense-text"><?= e($s['text']) ?></span><?php endif; ?>
      <?= render_sense_synonyms(split_pipe($s['synonyms'] ?? '')) ?>
      <?= render_sense_cites($cites_by_sense[(int) $s['ord']] ?? []) ?>
    </div>
    <?php endforeach; ?>
  </div>
  <?php endif; ?>
  <?php elseif ($w['definition']): ?>
  <div class="definition-text"><?= e($w['definition']) ?></div>
  <?php else: ?>
  <span class="fp-nodef">fără definiție locală</span>
  <?php endif; ?>

  <?php /* Tag chips */ ?>
  <?php $all_tags = array_merge(
      array_slice($pos_parts, 1),
      $reg_parts,
      $dom_parts,
      $etym_parts
  ); ?>
  <?php $tier_lbl = tier_label($w['confidence_tier'] ?? null); ?>
  <?php if ($all_tags || $tier_lbl): ?>
  <div class="fp-chips">
    <?php if (count($pos_parts) > 1): ?>
      <?php foreach (array_slice($pos_parts, 1) as $p): ?><span class="detail-tag"><?= e($p) ?></span><?php endforeach; ?>
    <?php endif; ?>
    <?php foreach ($reg_parts as $r): ?><span class="detail-tag"><?= e($r) ?></span><?php endforeach; ?>
    <?php foreach ($dom_parts as $d): ?><span class="detail-tag" style="opacity:.85"><?= e($d) ?></span><?php endforeach; ?>
    <?php foreach ($etym_parts as $et): ?><span class="detail-tag" style="opacity:.7"><?= e($etymon_parts ? $et . ' (' . implode(', ', $etymon_parts) . ')' : $et) ?></span><?php endforeach; ?>
    <?php if ($tier_lbl): ?><span class="detail-tag" style="opacity:.5;font-size:0.5625rem;" title="<?= e(TIERS[$w['confidence_tier']]['tip'] ?? '') ?>"><?= e($tier_lbl) ?></span><?php endif; ?>
  </div>
  <?php endif; ?>

  <?php /* Synonyms / antonyms (scrape_synonyms.py; absent until a word has been scraped) */ ?>
  <?php
    $syns = array_slice($synonyms, 0, 12);
    $ants = array_slice($antonyms, 0, 8);
  ?>
  <?php if ($syns): ?>
  <div class="fp-syn">
    <span class="fp-extra-label">≡ sinonime</span>
    <?php foreach ($syns as $s): ?><a class="syn-chip" href="<?= BASE ?>/?q=<?= urlenc($s) ?>"><?= e($s) ?></a><?php endforeach; ?>
    <?php if (count($synonyms) > count($syns)): ?><span class="syn-more">+<?= count($synonyms) - count($syns) ?></span><?php endif; ?>
  </div>
  <?php endif; ?>
  <?php if ($ants): ?>
  <div class="fp-syn">
    <span class="fp-extra-label">≠ antonime</span>
    <?php foreach ($ants as $a): ?><a class="syn-chip syn-chip--ant" href="<?= BASE ?>/?q=<?= urlenc($a) ?>"><?= e($a) ?></a><?php endforeach; ?>
  </div>
  <?php endif; ?>

  <?php /* Dictionaries. Names are listed in a click-open tooltip rather than inline —
       a word in ~20 dictionaries used to print ~20 chips into the body every time,
       which is more chrome than the definition above it.

       **This row always renders**, even for a word with no `sources`, because the
       dexonline link now ends it: as a chip among the other dictionary references
       rather than the full-width filled button it used to be in `.fp-foot`. That
       button was the loudest thing in the panel — louder than the definition —
       and four skins each amplified it independently (beton a red slab, govuk a
       green GDS button). Wrapping the row in `if ($sources)` would have made the
       link vanish for exactly the words whose dictionary coverage is thinnest. */ ?>
  <div class="fp-dicts">
    <?php if ($sources): ?>
    <button type="button" class="fp-extra-label fp-dicts-toggle"
            aria-haspopup="true" aria-expanded="false">📚 în <?= $dict_count ?> <?= $dict_count === 1 ? 'dicționar' : 'dicționare' ?></button>
    <?php endif; ?>
    <?php
    // Last attestation: the newest dictionary that still prints this word. A
    // lexicographic claim, independent of the corpus figures in the footer below —
    // and a far more legible one than `raport 3.12`. `newest_dict_year` has been in
    // ui.db since the dict-sources extractor learned to read `Source.year`; this is
    // the first thing to read it. Absent for ~3% of words, where the dictionary is
    // unnamed or unmatched, and then simply not shown.
    $attested = isset($w['newest_dict_year']) ? (int) $w['newest_dict_year'] : 0;
    if ($attested > 0): ?>
      <span class="dict-chip dict-chip--year"
            title="Cel mai recent dicționar din DEX care încă include acest cuvânt">ultima atestare <?= $attested ?></span>
    <?php endif; ?>
    <a class="dex-link"
       href="https://dexonline.ro/definitie/<?= urlenc($w['word']) ?>"
       target="_blank" rel="noopener"
       title="Deschide intrarea completă pe dexonline.ro (o)">dexonline ↗</a>
    <?php if ($sources): ?>
    <div class="dict-tooltip" hidden>
      <?php foreach ($sources as $src): ?><span class="dict-chip"><?= e($src) ?></span><?php endforeach; ?>
    </div>
    <?php endif; ?>
  </div>

</div>

<?php /* Footer: corpus stats + marking actions. The dexonline link used to end this
     block as a full-width button; it is a chip in the dictionary row above now. */ ?>
<div class="fp-foot">

  <div class="fp-stats">
    <?php if ($w['zipf_frequency'] !== null): ?><span title="Frecvență Zipf în română (wordfreq, log10 la un miliard de cuvinte) — sub 3,0 e sub pragul de fiabilitate, nu o estimare reală"><em>zipf ro</em><?= number_format((float)$w['zipf_frequency'], 1) ?></span><?php endif; ?>
    <?php if ($w['en_zipf'] !== null): ?><span title="Frecvență Zipf în engleză — o valoare mare sugerează un împrumut recent"><em>zipf en</em><?= number_format((float)$w['en_zipf'], 1) ?></span><?php endif; ?>
    <span title="Apariții la un milion de cuvinte în corpusul istoric (Wikisource)"><em>istoric</em><?= $w['hist_ppm'] !== null ? number_format((float)$w['hist_ppm'], 2) : '—' ?></span>
    <span title="Apariții la un milion de cuvinte în corpusul modern (CulturaX)"><em>modern</em><?= $w['modern_ppm'] !== null ? number_format((float)$w['modern_ppm'], 2) : '—' ?></span>
    <span title="log2(istoric / modern) — cât de mult a scăzut folosirea"><em>raport</em><?= $w['log_ratio'] !== null ? number_format((float)$w['log_ratio'], 2) : '—' ?></span>
  </div>

  <div class="fp-btns">
    <?php /* `aria-pressed="false"` is in the markup rather than only set by JS: the panel
             is server-rendered and hydrateDetail() runs a tick later, so without it the
             buttons announce as plain buttons for that tick — and as nothing at all if
             the script fails. hydrateDetail() flips it to the word's real state. */ ?>
    <button id="bookmark-btn" aria-pressed="false" data-word="<?= e($w['word']) ?>" title="fav (f) — păstrează, cuvânt de care ești mândru"><span class="qt-key">f</span><span class="fav-star">★</span> fav</button>
    <div id="tags-row" data-word="<?= e($w['word']) ?>">
      <div class="quick-tags">
        <?php /* <button type="button" class="qt-btn" aria-pressed="false" data-qtkey="a" title="ascunde (a) — neinteresant, prea cunoscut. Dispare din listă, îl regăsești în settings"><span class="qt-key">a</span>ascunde</button> */ ?>
        <button type="button" class="qt-btn" aria-pressed="false" data-qtkey="l" title="lol (l) — amuzant, de păstrat"><span class="qt-key">l</span>lol</button>
        <button type="button" class="qt-btn" aria-pressed="false" data-qtkey="m" title="meh (m) — la fel ca ascunde, doar zis altfel. Dispare din listă, îl regăsești în settings"><span class="qt-key">m</span>meh</button>
      </div>
    </div>
  </div>

  <div id="qt-explainer" class="qt-explainer">
    <?php /* „dispare din listă" was true until meh became a demote rather than a hide —
             the word now sinks to the end of the order and „normal" in Filtre → clase
             brings it straight back. Copy that describes a filter as removing something
             it no longer removes is worse than no copy. */ ?>
    <span>★ <strong>fav</strong> &amp; <strong>lol</strong> = cuvinte de păstrat. / <strong>meh</strong> = prea cunoscut sau banal — trece la coada listei (îl aduci înapoi din <em>Filtre → clase → respinse</em>). &nbsp; &middot; &nbsp; Am aprecia dacă <a href="liste">publica și tu</a> colecția-ți.</span> 
    <button type="button" id="qt-explainer-close" title="ascunde acest mesaj">✕</button>
  </div>

</div>
