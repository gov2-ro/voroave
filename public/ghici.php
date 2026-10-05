<?php
declare(strict_types=1);
require_once __DIR__ . '/api/_lib.php';
?>
<!DOCTYPE html>
<html lang="ro" data-skin="<?= DEFAULT_SKIN ?>">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <?= otios_skin_boot() ?>
  <title>Quiz — Voroave</title>
  <meta property="og:title" content="Quiz — Voroave">
  <meta property="og:description" content="Învață cuvinte românești uitate: ghicește sensul sau cuvântul, în teste grilă.">
  <meta property="og:type" content="website">
  <link rel="stylesheet" href="<?= BASE ?>/assets/fonts/app-fonts.css">
  <link rel="stylesheet" href="<?= BASE ?>/assets/app.css">
  <?= otios_skin_links() ?>
  <style>
    body { display:flex; flex-direction:column; min-height:100vh; }
    /* .joc-head / .joc-title / .joc-nav are gone — the bar is the shared
       .brand-bar now, and the nav is in the shared footer. What is left is the
       two game-specific controls it hands to the header's $header_tools slot. */
    /* The three game controls go into the header's $header_center slot, not
       $header_tools, and that is what centres them: $header_tools lands inside
       `.brand-right`, which is pinned right by `margin-left: auto`, whereas the
       centre slot is a flex child that can take the leftover width and centre in
       it. `.landing-tagline` is hidden on this page — it is the other `flex: 1`
       child, and two of them would each centre inside their own half. Empty
       space at the top right on a wide desktop is the deliberate trade. */
    .joc-tools { flex:1 1 auto; min-width:0; display:flex; align-items:center; justify-content:center; gap:10px; flex-wrap:wrap; }
    body.page-ghici .landing-tagline { display:none; }
    .joc-modes { display:flex; gap:6px; }
    .joc-mode {
      font-family:var(--mono); font-size:0.75rem; padding:4px 12px; border-radius:14px;
      border:1px solid var(--border-2); background:var(--surface); color:var(--text-2); cursor:pointer;
    }
    .joc-mode.active { background:var(--accent); border-color:var(--accent); color:var(--on-accent); }
    .joc-score { font-family:var(--mono); font-size:0.75rem; color:var(--text-3); }
    .joc-score-short { display:none; }
    /* Game card + word-detail pane: stacked on mobile, side-by-side on desktop. */
    .joc-layout { flex:1; display:flex; flex-direction:column; min-height:0; }
    .joc-main { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:flex-start; padding:24px 16px; }
    .joc-card {
      width:100%; max-width:640px; margin:auto; background:var(--surface); border:1px solid var(--border-2);
      border-radius:16px; box-shadow:0 8px 30px rgba(0,0,0,.08); padding:30px 28px;
    }
    .joc-prompt-label { font-family:var(--mono); font-size:0.625rem; letter-spacing:.12em; text-transform:uppercase; color:var(--text-3); margin-bottom:10px; }
    .joc-word { font-family:var(--serif); font-weight:600; font-size:2.6em; letter-spacing:-.02em; line-height:1.05; color:var(--text); overflow-wrap:break-word; }
    .joc-def { font-family:var(--serif); font-style:italic; font-size:1.125rem; line-height:1.6; color:var(--text); margin-top:6px; }
    .joc-pos { font-family:var(--mono); font-size:0.75rem; color:var(--text-3); margin-top:8px; }
    /* Withheld while the round is live — the part of speech and the pane's
       definition both narrow four options to one or two. `visibility` rather than
       `display` on the card's POS line would be tidier, but it reserves a row of
       empty space under every headword; the reveal is a class removal either way. */
    .joc-spoiler, #panel-pane [hidden] { display:none !important; }

    .joc-choices { display:flex; flex-direction:column; gap:10px; margin-top:22px; }

    /* grilă only: the option and its three marks on one line. The option keeps
       `flex:1` so the words still left-align in a column you can scan. */
    .joc-choice-row { display:flex; align-items:stretch; gap:8px; }
    .joc-choice-row .joc-choice { flex:1; min-width:0; }
    .joc-marks { display:flex; align-items:center; gap:4px; flex-shrink:0; }
    .joc-mark {
      width:36px; height:36px; align-self:center;
      display:inline-flex; align-items:center; justify-content:center;
      font-size:1rem; line-height:1; cursor:pointer;
      border:1px solid var(--border); border-radius:8px;
      background:var(--surface); color:var(--text-2);
      /* Unmarked reads as available rather than applied; the marked state is the
         affordance, since pressing an applied mark removes it. */
      opacity:.45; transition:opacity .12s, border-color .12s, background .12s;
    }
    .joc-mark:hover { opacity:.9; border-color:var(--border-2); background:var(--surface-2); }
    .joc-mark:active { transform:scale(.94); }
    /* Two classes deep so a skin's own `[data-skin="x"] .joc-mark` cannot flatten
       the applied state by restyling the resting one — the same specificity trap
       app.css documents at `.fp-btns .qt-btn.active`. */
    .joc-marks .joc-mark.active {
      opacity:1; border-color:var(--accent); background:var(--accent-bg); color:var(--accent);
    }

    /* The marks, hoisted out of `.fp-foot` to just under the head by liftMarks().
       A border rather than a background: this is the explorer's own widget and the
       pane is narrow, so a filled block here would be the loudest thing in it. */
    .fp-btns--lifted {
      padding:10px 16px; margin:0;
      border-bottom:1px solid var(--border);
      background:var(--surface-2);
    }

    /* The 1s auto-advance after a correct answer, said in the button rather than
       with a separate countdown widget: any interaction cancels the timer, so the
       bar draining is also the affordance telling you it can be stopped. */
    .joc-btn--counting { position:relative; overflow:hidden; }
    .joc-btn--counting::after {
      content:''; position:absolute; left:0; bottom:0; height:3px; width:100%;
      background:var(--on-accent); opacity:.55;
      transform-origin:left; animation:joc-countdown 1s linear forwards;
    }
    @keyframes joc-countdown { from { transform:scaleX(1); } to { transform:scaleX(0); } }
    @media (prefers-reduced-motion: reduce) {
      .joc-btn--counting::after { animation:none; opacity:.25; }
    }
    .joc-choice {
      display:flex; align-items:flex-start; gap:10px;
      text-align:left; font-family:var(--serif); font-size:1.125rem; padding:12px 16px;
      border:1.5px solid var(--border-2); border-radius:10px; background:var(--surface); color:var(--text); cursor:pointer;
      transition:opacity .15s ease;
    }
    .joc-choice:hover:not(:disabled) { border-color:var(--accent); }
    .joc-choice--def { font-size:1rem; line-height:1.5; padding:12px 14px; }
    /* Verdict styling leans on shape + emoji, not colour alone */
    .joc-choice.correct, .joc-choice.wrong { font-weight:600; }
    .joc-choice.correct::before, .joc-choice.wrong::before {
      flex:none; font-family:var(--mono); font-size:1.125em; line-height:1.35;
    }
    /* inset ring thickens the border without nudging the text */
    .joc-choice.correct {
      border-color:var(--success-border); background:var(--success-bg); color:var(--success);
      box-shadow:inset 0 0 0 2px var(--success-border);
    }
    .joc-choice.correct::before { content:'✅'; }
    .joc-choice.wrong {
      border-color:var(--error-border); background:var(--error-bg); color:var(--error);
      box-shadow:inset 0 0 0 2px var(--error-border);
      text-decoration:line-through; text-decoration-thickness:1px;
      text-decoration-color:color-mix(in srgb, var(--error) 55%, transparent);
    }
    .joc-choice.wrong::before { content:'❌'; text-decoration:none; }
    /* Once answered, fade the choices nobody marked so the two verdicts pop */
    .joc-choice:disabled { cursor:default; }
    .joc-choice:disabled:not(.correct):not(.wrong) { opacity:.4; }
    .joc-actions { display:flex; gap:12px; margin-top:22px; flex-wrap:wrap; }
    .joc-btn {
      height:42px; padding:0 18px; border-radius:21px; font-family:var(--mono); font-size:0.8125rem; font-weight:700; cursor:pointer;
      border:1.5px solid var(--accent); background:var(--accent); color:var(--on-accent);
    }
    .joc-btn.secondary { background:var(--surface); color:var(--accent); }
    .joc-btn:active { transform:scale(.98); }
    .joc-feedback { font-family:var(--mono); font-size:0.875rem; font-weight:600; margin-top:16px; min-height:18px; }
    .joc-feedback.ok { color:var(--success); }
    .joc-feedback.no { color:var(--error); }
    .joc-reveal { font-family:var(--mono); font-size:0.75rem; color:var(--text-3); margin-top:8px; }
    .joc-dexlink { color:var(--accent); font-size:0.75rem; text-decoration:none; }

    /* Always-visible word-detail pane (reuses .fp-* content styling from app.css). */
    #panel-pane {
      border-top:1px solid var(--border);
      background:var(--surface);
    }
    .panel-placeholder { padding:20px 16px; color:var(--text-3); font-family:var(--mono); font-size:0.8125rem; text-align:center; }
    #panel-pane .fp-close { display:none; }   /* nothing to close — the pane is always shown */

    /* Read-only comparison card for a wrong 'grilă' guess — the word itself gets no
       bookmark/tags/notes (that would mean a second widget sharing element ids). */
    .panel-compare { padding:14px 16px; border-top:1px dashed var(--border); }
    .panel-compare-label { font-family:var(--mono); font-size:0.6875rem; color:var(--text-3); margin-bottom:4px; }
    .panel-compare-def { font-family:var(--serif); font-size:0.9375rem; line-height:1.5; color:var(--text-2); }

    /* Mobile: the card's desktop padding was eating the line length. `.joc-main`
       (16px) plus `.joc-card` (28px) plus the border left 285px of text on a
       375px phone — for a card whose whole job is four multi-line definitions
       you have to read and compare. Halving both takes it to ~325px, and the
       choices lose their own extra inset for the same reason. Vertical padding
       comes down too: the page already scrolls under a fixed footer, so the
       cheapest way to get a fourth option above the fold is to stop spending
       50px on air above the first one. */
    @media (max-width:768px) {
      .joc-word { font-size:2.1em; }
      .joc-def { font-size:1.0625rem; }
      .joc-choice--def { font-size:0.9375rem; }
      /* `corecte: 0 · ratate: 0` is 158px of a 362px bar; with the mode buttons
         at 208px the trophy had nowhere to go but a third row. */
      .joc-score-long { display:none; }
      .joc-score-short { display:inline; }
      .joc-main { padding:8px 8px 10px; }
      .joc-card { padding:14px 12px; border-radius:12px; }
      .joc-prompt-label { margin-bottom:6px; }
      .joc-choices { gap:6px; margin-top:12px; }
      .joc-choice { padding:10px 12px; }
      .joc-choice--def { padding:10px 12px; }
      .joc-actions { margin-top:12px; gap:8px; }
      .joc-mark { width:32px; height:32px; font-size:0.9375rem; }
      .joc-marks { gap:3px; }
      .panel-compare { padding:12px 12px; }
      .panel-placeholder { padding:14px 12px; }
      .fp-btns--lifted { padding:8px 12px; }

      /* ── The footer goes, and the bar folds to one row ─────────────────────
         This page is a card you read top to bottom and answer; every pixel above
         or below it is a pixel the fourth option is pushed past the fold for.
         The footer is ~76–96px of `--statusbar-h` carrying nav and the display
         toggles, none of which you act on mid-round — and the top nav is still
         there, so nothing becomes unreachable, it is one tap further away.

         `--statusbar-h` must go to 0 with it: `body { padding-bottom }` and the
         detail sheet's `bottom` both read that token, so hiding the bar alone
         would leave its height behind as dead space at the foot of the page. */
      body.page-ghici { --statusbar-h: 0px; padding-bottom:0; }
      body.page-ghici #status-bar { display:none; }

      /* ── One row for the bar ──────────────────────────────────────────────
         Measured at 390px, the bar wanted ~460px: wordmark 85 + nav 134 +
         tools 225. Everything below is that 70px deficit, taken from the parts
         that repeat information already on screen.

         The nav labels go here and *only* here — the whole point of the pass
         that put them back was that a bare glyph row is unreadable, but this is
         the one page whose bar also has to carry a mode switch, a score and a
         leaderboard button. Two icons is what fits; the labels are still there
         on every other page, and `title` keeps their names. Same for the
         trophy's „clasament". */
      body.page-ghici { --bar-h: 46px; }
      body.page-ghici .brand-bar { gap:8px; padding:0 10px; }
      /* Three deep to match app.css's own phone wordmark rule, which is
         `.brand-bar .brand-id .brand-name` and would otherwise size this bar up
         to 1.125rem. This block is inline in the head, after the app.css link,
         so an equal-specificity rule wins on source order. */
      body.page-ghici .brand-bar .brand-name { font-size:1.0625rem; }
      body.page-ghici .brand-tag,
      body.page-ghici .brand-sep { display:none; }
      body.page-ghici .top-nav { gap:12px; }
      body.page-ghici .top-nav .nav-label { display:none; }
      /* `display` as well as the size: app.css hides the top nav's icons at this
         width (labels alone are cheaper there), and this page does the opposite —
         so without the re-declare the two rules meet and the nav renders empty. */
      body.page-ghici .top-nav .nav-icon { display:inline; font-size:1rem; }
      body.page-ghici .play-label { display:none; }
      body.page-ghici .play-btn { padding:0 8px; }
      /* header.php's `?` → /despre chip goes too, for the same 70px. It is worth
         ~26px with its gap, which is a third of the deficit above, and this is
         the one bar that cannot pay it. Nothing becomes unreachable that was
         reachable before: the footer is hidden at this width too, so `despre`
         has never had a route from a phone-sized round — and between 769 and
         900px, where this block does not apply, the chip is there. */
      body.page-ghici .shortcuts-link--narrow { display:none; }
      .joc-tools { gap:8px; justify-content:flex-end; flex-wrap:nowrap; }
      .joc-modes { gap:4px; }
      .joc-mode { padding:4px 8px; font-size:0.6875rem; white-space:nowrap; }
    }

    @media (min-width:900px) {
      .joc-layout { flex-direction:row; align-items:stretch; }
      .joc-main { flex:1; min-width:0; }
      #panel-pane {
        width:380px; flex-shrink:0; border-top:none; border-left:1px solid var(--border);
        overflow-y:auto;
      }
    }
  </style>
  
    <!-- favicon -->
  <link rel="icon" type="image/png" href="/assets/favicon/favicon-96x96.png" sizes="96x96" />
  <link rel="icon" type="image/svg+xml" href="/assets/favicon/favicon.svg" />
  <link rel="shortcut icon" href="/assets/favicon/favicon.ico" />
  <link rel="apple-touch-icon" sizes="180x180" href="/assets/favicon/apple-touch-icon.png" />
  <meta name="apple-mobile-web-app-title" content="Voroave neglijate" />
  <link rel="manifest" href="/assets/favicon/site.webmanifest" />

</head>
<body class="page-ghici">
  <?php
  ob_start(); ?>
    <div class="joc-tools">
      <div class="joc-modes">
        <button type="button" class="joc-mode active" data-mode="sense" onclick="setMode('sense')" aria-pressed="true">🔤 sensuri</button>
        <button type="button" class="joc-mode" data-mode="quiz" onclick="setMode('quiz')" aria-pressed="false">❓ grilă</button>
      </div>
      <span class="joc-score" id="joc-score"></span>
      <button type="button" class="play-btn" onclick="openBoard();return false;"
              title="Clasament">🏆 <span class="play-label">clasament</span></button>
    </div>
  <?php $header_center = ob_get_clean();

  $page      = 'ghici';
  $brand_tag = 'quiz';
  require __DIR__ . '/api/_partials/header.php';
  ?>

  <div class="joc-layout">
    <div class="joc-main">
      <div class="joc-card" id="joc-card">se încarcă…</div>
    </div>
    <div id="panel-pane" class="word-detail-panel">
      <p class="panel-placeholder">se încarcă…</p>
    </div>
  </div>

  <div id="board-overlay" style="display:none" onclick="if(event.target===this)closeBoard()">
    <div id="board-modal">
      <div class="board-head">
        <span id="board-title">Clasament · cele mai lungi serii</span>
        <button class="board-x" onclick="closeBoard()">✕</button>
      </div>
      <div id="board-body"><p class="board-empty">se încarcă…</p></div>
    </div>
  </div>

  <?php require __DIR__ . '/api/_partials/footer.php'; ?>

  <script>var OTIOS_BASE = '<?= BASE ?>';</script>
  <script src="<?= BASE ?>/assets/prefs.js"></script>
  <script src="<?= BASE ?>/assets/store.js"></script>
  <script>
  (function() {
    var base = (typeof OTIOS_BASE !== 'undefined' ? OTIOS_BASE : '');
    // 'sense' (word → pick the meaning) is the default; 'flash' is retained but has
    // no button — reach it with ?game=carduri.
    var MODES = { sense: 1, quiz: 1, flash: 1 };

    // ── ?game= is the public spelling; `mode` stays the internal one ──────────
    // The URL says what the buttons say — /ghici?game=sensuri, ?game=grila — while
    // the code, `api/quiz.php`, `api/game.php` and the leaderboard all keep talking
    // in `sense`/`quiz`/`flash`. Renaming those would have meant re-keying
    // `localStorage['otios.quiz']` and the server's per-mode stats, which is the
    // same class of change as renaming the device cookie: a visible name is cheap,
    // a stored key is not.
    //
    // `?mode=` still works. It was the only spelling for months and `?mode=flash`
    // is how the unlisted card mode was reached; a link that used to work should
    // not answer with a different game.
    var GAME_TO_MODE = { sensuri: 'sense', grila: 'quiz', 'grilă': 'quiz', carduri: 'flash' };
    var MODE_TO_GAME = { sense: 'sensuri', quiz: 'grila', flash: 'carduri' };

    var params = new URLSearchParams(location.search);
    var mode   = GAME_TO_MODE[(params.get('game') || '').toLowerCase()]
              || (params.get('mode') || '');
    if (!MODES[mode]) mode = 'sense';

    // replaceState, not pushState: the modes are two views of one activity, and a
    // back button that walks you through every switch you made — while the question
    // itself is never in the URL, so none of those entries restores anything — is a
    // trap rather than history. The URL is here to be copied and shared.
    function syncUrl() {
      var u = new URL(location.href);
      u.searchParams.delete('mode');          // drop the legacy spelling once we own the URL
      u.searchParams.set('game', MODE_TO_GAME[mode] || 'sensuri');
      history.replaceState(null, '', u);
    }
    // Current question. Options are opaque {id, text}: the server does not say which
    // one is correct, so grading goes through /api/game.php.
    var cur = null;
    var answered = false;
    var askedAt = 0;       // for the per-answer response time recorded server-side
    // Distinct from `answered`, which goes true the moment a choice is clicked — this
    // one goes true when the verdict is on screen. `showWordDetail` is a fetch, so a
    // fast answer can land while the pane is still in flight; without this the pane
    // would resolve *after* revealSpoilers() and re-hide the definition the verdict
    // had just uncovered, leaving „✅ corect!" above an empty panel.
    var roundDecided = false;

    // ── Bookmarks (shared store in store.js, synced to the server) + per-mode score ──
    function isBookmarked(w) { return !!getWord(w).bookmarked; }
    function toggleBookmark(w) { updateWord(w, { bookmarked: !isBookmarked(w) }); }
    // Local mirror of the server's per-mode correct/total, keyed by mode, so the score
    // is on screen immediately on load instead of waiting for a round trip. Sense and
    // quiz are tracked separately — they test different skills, so a streak or tally
    // built up in one shouldn't bleed into the other's readout. The server remains
    // authoritative.
    function getQuizStats(m) {
      try {
        var all = JSON.parse(localStorage.getItem('otios.quiz') || '{}') || {};
        return all[m] || { correct: 0, total: 0 };
      } catch (_) { return { correct: 0, total: 0 }; }
    }
    function setQuizStats(m, s) {
      try {
        var all = JSON.parse(localStorage.getItem('otios.quiz') || '{}') || {};
        all[m] = s;
        localStorage.setItem('otios.quiz', JSON.stringify(all));
      } catch (_) {}
    }

    function esc(s) { return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

    // Two spellings of the same tally, one shown per width (see .joc-score-long /
    // .joc-score-short). The long one is 158px of a 362px bar, which pushed the
    // trophy onto a third row and took the header to 121px — 14% of a phone
    // screen spent on a bar above the card you are meant to be reading.
    function renderScore() {
      var el = document.getElementById('joc-score');
      if (mode === 'quiz' || mode === 'sense') {
        var s = getQuizStats(mode);
        var total = s.total || 0, correct = s.correct || 0, missed = total - correct;
        el.innerHTML =
          '<span class="joc-score-long">corecte: ' + correct + ' · ratate: ' + missed + '</span>' +
          '<span class="joc-score-short" title="corecte · ratate">✓ ' + correct + ' · ✗ ' + missed + '</span>';
      } else {
        el.textContent = '';
      }
    }

    function syncModeButtons() {
      document.querySelectorAll('.joc-mode').forEach(function(b) {
        var on = b.dataset.mode === mode;
        b.classList.toggle('active', on);
        // The markup ships aria-pressed and nothing was keeping it in step, so a
        // screen reader heard „sensuri" as the live mode however many times you
        // switched to „grilă".
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    }
    function setMode(m) {
      mode = m;
      syncModeButtons();
      syncUrl();
      load();
    }
    window.setMode = setMode;

    function dexLink(w) {
      return '<a class="joc-dexlink" href="https://dexonline.ro/definitie/' + encodeURIComponent(w) + '" target="_blank" rel="noopener">↗ dexonline.ro</a>';
    }

    // ── Word-detail pane (full widget from the main page — tags, dictionaries,
    // fav/ascunde/lol/meh quick-tags — reused as-is via store.js's hydrateDetail/handlers) ──
    // Always visible rather than opened on demand. In `quiz` mode the word is
    // deliberately withheld from the client until grading, so the pane shows a
    // placeholder until showVerdict() reveals it; every other mode knows the word
    // immediately and can populate the pane right away.
    function showDetailPlaceholder(text) {
      document.getElementById('panel-pane').innerHTML = '<p class="panel-placeholder">' + esc(text) + '</p>';
    }
    // ── Spoilers in the pane, and what counts as one ──────────────────────────
    // In 'sense' mode the word is on screen from the start, so the pane can be
    // filled immediately — but the pane is the *same widget as the explorer's*, and
    // everything in it describes the answer: senses, expressions, citations,
    // synonyms, tags, etymon, variant notes, the dictionary row. Listing those by
    // selector broke every time the renderer grew a block (`.fp-senses` was missed
    // that way), so the pane's answer body is withheld AS ONE UNIT: the `.fp-body`
    // wrapper from detail.php. The part of speech sits in the head, outside it, and
    // is withheld separately: „s.f." beside the headword eliminates every option
    // phrased as a verb. The headword and the marks stay.
    // Contract with the renderer: docs/fixes/F05-shared-definitions.md.
    //
    // `hidden` + `inert` + `aria-hidden`, not only a CSS mask: the content has to be
    // absent from the accessibility tree and the tab order, not just invisible.
    // The reveal removes the attributes; the markup stays the server's.
    var SPOILER_SEL = '.fp-body, .fp-pos-line';

    function setWithheld(el, on) {
      if (on) {
        el.classList.add('joc-spoiler');
        el.hidden = true;
        el.setAttribute('inert', '');
        el.setAttribute('aria-hidden', 'true');
      } else {
        el.classList.remove('joc-spoiler');
        el.hidden = false;
        el.removeAttribute('inert');
        el.removeAttribute('aria-hidden');
      }
    }
    function hideSpoilers(root) {
      root.querySelectorAll(SPOILER_SEL).forEach(function(el) { setWithheld(el, true); });
    }
    function revealSpoilers() {
      document.querySelectorAll('.joc-spoiler').forEach(function(el) { setWithheld(el, false); });
    }

    // Each detail request takes a ticket. A response only lands if its ticket is still
    // the newest: otherwise a slow answer for question N would overwrite question N+1's
    // pane, and — worse — arrive after N+1's own response and replace the right word.
    var paneSeq = 0;

    // The marks are the reason to keep the pane open while playing, and in the
    // server's order they sit below the definition, the chips, the synonyms and the
    // dictionary row — i.e. below a fold, on the one screen where you are most
    // likely to want them. Moved to just under the head. Done by relocating the
    // server's own node rather than re-rendering it, so store.js's delegated
    // handlers and `hydrateDetail()` go on working unchanged.
    function liftMarks(pane) {
      var head  = pane.querySelector('.fp-head');
      var btns  = pane.querySelector('.fp-btns');
      if (!head || !btns) return;
      btns.classList.add('fp-btns--lifted');
      head.insertAdjacentElement('afterend', btns);
    }

    function showWordDetail(word, spoilers) {
      if (!word) return;
      var pane = document.getElementById('panel-pane');
      var seq = ++paneSeq;
      pane.innerHTML = '<p class="panel-placeholder">se încarcă…</p>';
      fetch(base + '/api/word.php?word=' + encodeURIComponent(word), { credentials: 'same-origin' })
        .then(function(r) { return r.text(); })
        .then(function(html) {
          if (seq !== paneSeq) return;
          pane.innerHTML = html;
          if (spoilers && !roundDecided) hideSpoilers(pane);
          liftMarks(pane);
          hydrateDetail(pane);
        })
        .catch(function() { if (seq === paneSeq) pane.innerHTML = '<p class="panel-placeholder">Nu am putut încărca detaliile.</p>'; });
    }
    // Pull just the title + definition out of a word.php fragment, for the read-only
    // "you picked X" comparison card — the wrong choice gets no bookmark/tags/notes of
    // its own (that would mean two widgets sharing the same element ids), just enough
    // to see why it wasn't the answer.
    function extractWordSummary(html) {
      var tmp = document.createElement('div');
      tmp.innerHTML = html;
      var title = tmp.querySelector('.fp-title');
      var def   = tmp.querySelector('.definition-text');
      // A structured entry has no `.definition-text`: its meaning is the sense list.
      // Numbered senses with no text of their own (synonym-only) are skipped.
      var texts = [].map.call(tmp.querySelectorAll('.fp-senses > .fp-sense > .sense-text'),
        function(n) { return n.textContent.trim(); }).filter(Boolean).slice(0, 3);
      var text = def ? def.textContent : (texts.length ? texts.join(' · ') : '(fără definiție locală)');
      return { word: title ? title.textContent : '', definition: text };
    }
    // Wrong 'quiz' answer: show the correct word's full widget plus a lightweight
    // comparison card for the word the player actually picked, so both definitions are
    // visible side by side.
    function showWordDetailCompare(correctWord, wrongWord) {
      var pane = document.getElementById('panel-pane');
      var seq = ++paneSeq;
      pane.innerHTML = '<p class="panel-placeholder">se încarcă…</p>';
      Promise.all([
        fetch(base + '/api/word.php?word=' + encodeURIComponent(correctWord), { credentials: 'same-origin' }).then(function(r) { return r.text(); }),
        fetch(base + '/api/word.php?word=' + encodeURIComponent(wrongWord), { credentials: 'same-origin' }).then(function(r) { return r.text(); })
      ]).then(function(results) {
        if (seq !== paneSeq) return;
        var wrongSummary = extractWordSummary(results[1]);
        pane.innerHTML = results[0] +
          '<div class="panel-compare">' +
            '<div class="panel-compare-label">ai ales „' + esc(wrongSummary.word) + '”</div>' +
            '<div class="panel-compare-def">' + esc(wrongSummary.definition) + '</div>' +
          '</div>';
        liftMarks(pane);
        hydrateDetail(pane);
      }).catch(function() { if (seq === paneSeq) pane.innerHTML = '<p class="panel-placeholder">Nu am putut încărca detaliile.</p>'; });
    }
    // detail.php's markup still carries a "✕" close button (hidden here via CSS,
    // since there's nothing to close) that calls this by name — keep it a harmless
    // no-op rather than leaving the name undefined.
    window.closePanel = function() {};

    // ── The auto-advance timer, and its off switch ────────────────────────────
    // One timer id at module scope, because there is only ever one round in flight.
    // `cancelAutoNext` is called from three places: any pointer or key event on the
    // page (below), a mark press, and `load()` itself — the last one so a manual
    // „următoarea" cannot leave a timer running into the next question and skip it.
    var AUTO_NEXT_MS = 1000;
    var autoNextTimer = null;

    function cancelAutoNext() {
      if (autoNextTimer === null) return;
      clearTimeout(autoNextTimer);
      autoNextTimer = null;
      var b = document.getElementById('quiz-next');
      if (b) b.classList.remove('joc-btn--counting');
    }

    function scheduleAutoNext() {
      cancelAutoNext();
      var b = document.getElementById('quiz-next');
      if (b) b.classList.add('joc-btn--counting');
      autoNextTimer = setTimeout(function() { autoNextTimer = null; load(); }, AUTO_NEXT_MS);
    }

    // Capture phase: the cancel has to land before the handler for whatever was
    // clicked, or a click on a mark would toggle it and then be advanced away from.
    ['pointerdown', 'keydown', 'wheel', 'touchstart'].forEach(function(ev) {
      document.addEventListener(ev, cancelAutoNext, true);
    });

    function load() {
      cancelAutoNext();
      paneSeq++;          // any detail request still in flight belongs to the old question
      answered = false;
      roundDecided = false;
      askedAt = 0;
      var card = document.getElementById('joc-card');
      card.textContent = 'se încarcă…';
      fetch(base + '/api/quiz.php?mode=' + encodeURIComponent(mode), { credentials: 'same-origin' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
          if (d.error) { card.textContent = 'Niciun cuvânt disponibil.'; return; }
          cur = d;
          askedAt = Date.now();
          if (mode === 'sense') renderSense();
          else if (mode === 'quiz') renderQuiz();
          else renderFlash();
          renderScore();
        })
        .catch(function() { card.textContent = 'Eroare la încărcare.'; });
    }

    function renderFlash() {
      var card = document.getElementById('joc-card');
      var star = isBookmarked(cur.word) ? '★' : '☆';
      card.innerHTML =
        '<div class="joc-prompt-label">card · ghicește sensul</div>' +
        '<div class="joc-word">' + esc(cur.word) + '</div>' +
        (cur.pos ? '<div class="joc-pos">' + esc(cur.pos) + '</div>' : '') +
        '<div id="flash-def" style="display:none">' +
          '<div class="joc-def">' + esc(cur.definition) + '</div>' +
          '<div class="joc-reveal">' + dexLink(cur.word) + '</div>' +
        '</div>' +
        '<div class="joc-actions" id="flash-actions">' +
          '<button class="joc-btn" id="flash-reveal">arată definiția</button>' +
        '</div>';
      document.getElementById('flash-reveal').onclick = function() {
        document.getElementById('flash-def').style.display = '';
        document.getElementById('flash-actions').innerHTML =
          '<button class="joc-btn secondary" id="flash-keep">' + star + ' păstrează</button>' +
          '<button class="joc-btn" id="flash-next">următorul →</button>';
        document.getElementById('flash-keep').onclick = function() {
          toggleBookmark(cur.word);
          this.textContent = (isBookmarked(cur.word) ? '★' : '☆') + ' păstrează';
        };
        document.getElementById('flash-next').onclick = load;
      };
      showWordDetail(cur.word);
    }

    // ── Marks beside a grilă option ───────────────────────────────────────────
    // In `grilă` every option *is* a word, so all four are markable without waiting
    // for the round to end — and marking one is the fastest triage the site has, four
    // words a question. Icons only: the row is already a full-width option button and
    // three labelled chips beside it would be wider than the word.
    //
    // These do NOT reuse detail.php's `#bookmark-btn` / `#tags-row` markup, and that
    // is the point — those are addressed by *id* in store.js's delegated handler, so
    // four copies on one screen would be four elements sharing one id and one of them
    // answering for the rest. They carry `data-joc-word` instead and are handled
    // below, calling the same `getWord`/`updateWord` store.
    var JOC_MARKS = [
      { tag: 'fav', icon: '⭐️', label: 'fav' },
      { tag: 'lol', icon: '🤣', label: 'lol' },
      { tag: 'meh', icon: '⛔️', label: 'meh' }
    ];

    function markIsOn(word, tag) {
      var st = getWord(word);
      return tag === 'fav' ? !!st.bookmarked : (st.tags || []).includes(tag);
    }

    function marksHtml(word) {
      var w = esc(word);
      return '<span class="joc-marks">' + JOC_MARKS.map(function(m) {
        return '<button type="button" class="joc-mark' + (markIsOn(word, m.tag) ? ' active' : '') +
               '" data-joc-word="' + w + '" data-joc-tag="' + m.tag + '"' +
               ' aria-pressed="' + (markIsOn(word, m.tag) ? 'true' : 'false') + '"' +
               ' title="' + m.label + ' — „' + w + '”" aria-label="' + m.label + ' — ' + w + '">' +
               m.icon + '</button>';
      }).join('') + '</span>';
    }

    function syncMarks(root) {
      (root || document).querySelectorAll('.joc-mark').forEach(function(b) {
        var on = markIsOn(b.dataset.jocWord, b.dataset.jocTag);
        b.classList.toggle('active', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    }

    // Both graded modes render the same shape: a prompt plus four opaque choices,
    // keyed by the server's option id. `withMarks` is grilă-only — in `sensuri` the
    // options are definitions, not words, so there is nothing to mark.
    function renderChoices(label, promptHtml, defClass, withMarks) {
      var card = document.getElementById('joc-card');
      var html =
        '<div class="joc-prompt-label">' + label + '</div>' + promptHtml +
        '<div class="joc-choices" id="quiz-choices">';
      (cur.options || []).forEach(function(o) {
        var btn = '<button class="joc-choice' + (defClass ? ' joc-choice--def' : '') +
                  '" data-id="' + o.id + '">' + esc(o.text) + '</button>';
        // The marks are siblings of the option, never children: `.joc-choice` is a
        // <button>, and a button inside a button is invalid markup that browsers
        // recover from by dropping the inner one.
        html += withMarks
          ? '<div class="joc-choice-row">' + btn + marksHtml(o.text) + '</div>'
          : btn;
      });
      html += '</div><div class="joc-feedback" id="quiz-feedback"></div>' +
              '<div class="joc-actions" id="quiz-actions"></div>';
      card.innerHTML = html;
      card.querySelectorAll('.joc-choice').forEach(function(btn) {
        btn.onclick = function() { answer(parseInt(btn.dataset.id, 10)); };
      });
    }

    // Delegated once, on the card, so it survives every re-render.
    document.getElementById('joc-card').addEventListener('click', function(e) {
      var mk = e.target.closest('.joc-mark');
      if (!mk) return;
      e.preventDefault();
      e.stopPropagation();          // never let a mark count as answering the question
      cancelAutoNext();             // and never let it be swept away by the timer
      var w = mk.dataset.jocWord, tag = mk.dataset.jocTag;
      if (tag === 'fav') {
        updateWord(w, { bookmarked: !getWord(w).bookmarked });
      } else {
        var tags = getWord(w).tags || [];
        updateWord(w, {
          tags: tags.includes(tag) ? tags.filter(function(t) { return t !== tag; })
                                   : tags.concat([tag])
        });
      }
      syncMarks(document.getElementById('joc-card'));
    });

    // One word, four candidate definitions. The word is known up front, so the
    // detail pane can populate immediately — but the definition itself is the puzzle,
    // so it stays hidden in the pane until the round is decided some other way.
    // The part of speech is withheld with the definition, on the card as well as in
    // the pane: „s.f." under the headword rules out every option phrased as a verb,
    // which on a four-option round is most of the work done for you. It comes back
    // with the verdict, where it is information rather than a hint.
    function renderSense() {
      renderChoices('sensuri · ce înseamnă acest cuvânt?',
        '<div class="joc-word">' + esc(cur.word) + '</div>' +
        (cur.pos ? '<div class="joc-pos joc-spoiler">' + esc(cur.pos) + '</div>' : ''),
        true);
      showWordDetail(cur.word, true);
    }

    // One definition, four candidate words. The definition arrives already masked, so
    // the target word — and its detail pane — stay unknown until showVerdict() grades
    // the answer.
    function renderQuiz() {
      renderChoices('grilă · ce cuvânt are acest sens?',
        '<div class="joc-def">' + esc(cur.definition) + '</div>', false, true);
      showDetailPlaceholder('răspunde ca să vezi detaliile cuvântului');
    }

    function answer(choiceId) {
      if (answered || !cur || !cur.qid) return;
      answered = true;

      var buttons = document.querySelectorAll('.joc-choice');
      buttons.forEach(function(b) { b.disabled = true; });
      var fb = document.getElementById('quiz-feedback');
      fb.className = 'joc-feedback';
      fb.textContent = 'se verifică…';

      fetch(base + '/api/game.php', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qid: cur.qid, choice_id: choiceId, ms: askedAt ? Date.now() - askedAt : null })
      })
        .then(function(r) { return r.json(); })
        .then(function(d) {
          if (d.error) throw new Error(d.error);
          showVerdict(d, choiceId);
        })
        .catch(function() {
          // Every question already needs the network, so a failure here is the same
          // outage that would have blocked the next question anyway. Let them retry.
          answered = false;
          buttons.forEach(function(b) { b.disabled = false; });
          fb.className = 'joc-feedback no';
          fb.textContent = '⚠ nu am putut verifica răspunsul — încearcă din nou.';
        });
    }

    function showVerdict(d, choiceId) {
      document.querySelectorAll('.joc-choice').forEach(function(btn) {
        var id = parseInt(btn.dataset.id, 10);
        if (id === d.correct_id) btn.classList.add('correct');
        else if (id === choiceId) btn.classList.add('wrong');
      });

      // The round is decided, so the part of speech and the pane's definition stop
      // being hints and become the thing you came to learn. The flag has to be set
      // before the reveal, not after: it is what stops an in-flight pane fetch from
      // re-hiding them when it lands.
      roundDecided = true;
      revealSpoilers();

      var fb = document.getElementById('quiz-feedback');
      fb.className = 'joc-feedback ' + (d.correct ? 'ok' : 'no');
      // In 'sense' mode the word is already on screen — point at the highlighted
      // definition instead of naming the word again.
      var miss = mode === 'sense' ? '❌ greșit — sensul corect e cel bifat. '
                                  : '❌ greșit — era „' + esc(d.answer) + '”. ';
      fb.innerHTML = (d.correct ? '✅ corect! ' : miss) + dexLink(d.answer);

      document.getElementById('quiz-actions').innerHTML = '<button class="joc-btn" id="quiz-next">următoarea →</button>';
      document.getElementById('quiz-next').onclick = load;

      // ── Auto-advance, on a right answer only ────────────────────────────────
      // A correct round has nothing left to read on the card: you already knew the
      // answer, and stopping to press „următoarea" is the only thing between you and
      // the next one. A wrong round is the opposite — the whole value is in the two
      // definitions now side by side — so it never auto-advances.
      //
      // **Any interaction cancels it**, and that is what makes 1s safe rather than
      // rushed: the pane is live even on a correct answer (marks, dictionaries, the
      // dexonline link), so the moment you reach for it the timer is off and the
      // button behaves normally. Without that the feature would be a race against
      // your own reading.
      if (d.correct) scheduleAutoNext();

      // 'sense' already populated the detail pane before answering (the word was
      // never secret there); 'quiz' only learns the word now, from the grading
      // response, so the pane can only be filled in at this point. On a wrong guess,
      // compare both: the correct word's full widget plus what the player picked.
      if (mode === 'quiz') {
        if (d.correct) {
          showWordDetail(d.answer);
        } else {
          var chosen = (cur.options || []).find(function(o) { return o.id === choiceId; });
          if (chosen) showWordDetailCompare(d.answer, chosen.text);
          else showWordDetail(d.answer);
        }
      }

      setQuizStats(mode, { correct: d.total_correct, total: d.total });
      renderScore();
    }

    // Keyboard: space/enter reveals or advances; 1-4 pick a quiz choice
    document.addEventListener('keydown', function(e) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;   // leave browser shortcuts alone
      if (mode === 'quiz' || mode === 'sense') {
        if (!answered && e.key >= '1' && e.key <= '4') {
          var btns = document.querySelectorAll('.joc-choice');
          var i = parseInt(e.key, 10) - 1;
          if (btns[i]) { e.preventDefault(); btns[i].click(); }
        } else if (answered && (e.key === 'Enter' || e.key === ' ')) {
          var n = document.getElementById('quiz-next'); if (n) { e.preventDefault(); n.click(); }
        }
      } else {
        if (e.key === 'Enter' || e.key === ' ') {
          var rv = document.getElementById('flash-reveal'); var nx = document.getElementById('flash-next');
          if (rv) { e.preventDefault(); rv.click(); } else if (nx) { e.preventDefault(); nx.click(); }
        }
      }
    });

    // ── Leaderboard ──
    // Nothing here is client-asserted: game.php recomputes streaks server-side, so a
    // rank reflects answers the server actually graded.
    var BOARD_MODE_LABEL = { sense: 'sensuri', quiz: 'grilă' };
    function openBoard() {
      // flash isn't graded and has no leaderboard of its own — fall back to sense,
      // matching the clamp leaderboard.php already applies server-side.
      var boardMode = BOARD_MODE_LABEL[mode] ? mode : 'sense';
      document.getElementById('board-overlay').style.display = 'flex';
      document.getElementById('board-title').textContent = 'Clasament · ' + BOARD_MODE_LABEL[boardMode] + ' · cele mai lungi serii';
      var body = document.getElementById('board-body');
      body.innerHTML = '<p class="board-empty">se încarcă…</p>';

      fetch(base + '/api/leaderboard.php?mode=' + encodeURIComponent(boardMode), { credentials: 'same-origin' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
          var rows = d.entries || [];
          var html = '';

          if (!rows.length) {
            html += '<p class="board-empty">Niciun scor încă. Fii primul!</p>';
          } else {
            html += '<table class="board-table"><tbody>';
            rows.forEach(function(e) {
              html += '<tr' + (e.you ? ' class="board-you"' : '') + '>' +
                      '<td class="board-rank">' + e.rank + '</td>' +
                      '<td class="board-name"></td>' +
                      '<td class="board-best">' + e.best + '</td>' +
                      '<td class="board-tot">' + e.correct + '/' + e.total + '</td></tr>';
            });
            html += '</tbody></table>';
          }

          // Not on the board yet: show where they stand and offer the one opt-in.
          if (d.you && d.you.listed === false) {
            html += '<div class="board-self">Seria ta cea mai lungă: <strong>' + d.you.best + '</strong>' +
                    ' · locul ' + d.you.rank + ' dacă te înscrii.' +
                    '<button class="joc-btn secondary" id="board-join">apari în clasament</button></div>';
          }
          body.innerHTML = html;

          // Nicknames are user input — assigned as text, never built into the HTML.
          var names = body.querySelectorAll('.board-name');
          rows.forEach(function(e, i) { if (names[i]) names[i].textContent = e.nickname; });

          var join = document.getElementById('board-join');
          if (join) join.onclick = joinBoard;
        })
        .catch(function() {
          document.getElementById('board-body').innerHTML =
            '<p class="board-empty">Nu am putut încărca clasamentul.</p>';
        });
    }

    function closeBoard() { document.getElementById('board-overlay').style.display = 'none'; }

    function joinBoard() {
      var name = prompt('Sub ce nume vrei să apari?');
      if (!name || name.trim().length < 2) return;
      fetch(base + '/api/profile.php', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname: name.trim() })
      })
        .then(function(r) { return r.json(); })
        .then(function(d) { if (d.nickname) openBoard(); });
    }

    window.openBoard = openBoard;
    window.closeBoard = closeBoard;

    syncModeButtons();
    load();

    // Reconcile the local score mirror with the server's, so the tally survives a
    // cleared browser the same way bookmarks now do.
    if (typeof otiosMe === 'function') {
      otiosMe().then(function(me) {
        if (!me || !me.stats) return;
        ['sense', 'quiz'].forEach(function(m) {
          if (me.stats[m]) setQuizStats(m, me.stats[m]);
        });
        renderScore();
      });
    }
  })();
  </script>
</body>
</html>
