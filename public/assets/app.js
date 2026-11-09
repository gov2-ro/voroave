// ── Page state ────────────────────────────────────────────────────────────────
//
// The research store itself (getResearch / getWord / updateWord) lives in store.js,
// which is loaded before this file and shared with joc.php. QUICK_TAG_EMOJIS,
// hydrateDetail() and the bookmark/tag/note click handlers also live there now, for
// the same reason — joc.php's word-detail panel needs them too.

let openWord = null;
let arrivedViaShare = false;   // true while opening the panel from a shared ?word= link

// ── Annotation hydration ───────────────────────────────────────────────────────

function currentSuppressEmoji() {
  const marks = document.querySelector('[name=marks]');
  if (!marks) return '';
  const v = marks.value;
  if (v === 'bookmarked') return '⭐';
  if (v === 'noted')      return '📝';
  if (v.startsWith('tag:')) {
    const tag = v.slice(4).trim();
    return QUICK_TAG_EMOJIS[tag] || '🏷️';
  }
  return '';
}

function buildOverlay(state, suppress) {
  let s = '';
  (state.tags || []).forEach(function(t) {
    const e = QUICK_TAG_EMOJIS[t] || '🏷️';
    if (e !== suppress) s += e;
  });
  if (state.note && '📝' !== suppress) s += '📝';
  if (state.bookmarked && '⭐' !== suppress) s += '⭐';
  return s;
}

function hydrateRows(root) {
  const suppress = currentSuppressEmoji();
  (root || document).querySelectorAll('.word-row[data-word]').forEach(function(row) {
    const word  = row.dataset.word;
    const state = getWord(word);

    // bookmarked class
    row.classList.toggle('bookmarked', !!state.bookmarked);

    // annotation overlay
    let overlay = row.querySelector('.ann-overlay');
    const text  = buildOverlay(state, suppress);
    if (text) {
      if (!overlay) {
        overlay = document.createElement('span');
        overlay.className = 'ann-overlay';
        row.appendChild(overlay);
      }
      overlay.textContent = text;
    } else if (overlay) {
      overlay.remove();
    }
  });
}

// Pop a word chip out of the grid when it just got tagged ascunde/meh — called from
// store.js's quick-tag click handler, right after the tag itself is persisted.
function fadeOutRow(word, onGone) {
  const all = document.querySelectorAll('#word-list .word-row[data-word]');
  for (const row of all) {
    if (row.dataset.word !== word) continue;
    row.classList.add('row-hiding');
    row.addEventListener('animationend', function() {
      row.remove();
      if (typeof onGone === 'function') onGone();
    }, { once: true });
    return;
  }
  // No row to fade (tagged from the joc page, or the word is already gone) —
  // the caller still needs its continuation to run.
  if (typeof onGone === 'function') onGone();
}

// **Every mark advances to the next word** — fav, lol, meh and ascunde alike.
// One mark per word is the intended interaction, so the ability to stack a second
// one on the same word is not worth four controls that behave differently: marking
// is a triage loop, and a loop where three keys move you on and one does not is a
// loop you have to think about. Convenience and consistency over the rare double-tag.
//
// Only *applying* a mark advances. Un-favouriting is a correction, and moving on
// from a correction would take you off the word you just came back to fix.
//
// `removesRow` is the only difference between the two cases: `meh`/`ascunde` also
// pop the row out of the grid, so the current row does not survive the move.
//
// For that case the next row is resolved *before* the fade and re-found by element
// afterwards. Resolving it after removal would race the animation; selecting it by
// index before removal would leave `selectedIdx` off by one the moment the fade
// lands — and that is the number j/k read to decide where to go next.
function advanceAfterMark(word, removesRow) {
  const all = rows();
  const idx = all.findIndex(function(r) { return r.dataset.word === word; });
  if (idx < 0) { if (removesRow) fadeOutRow(word); return; }

  if (!removesRow) {
    // The row stays, so "next" only exists if there is one. On the last row, stay
    // put rather than wrapping to the top, which would silently restart the list.
    if (idx + 1 < all.length) selectRow(idx + 1);
    return;
  }

  // At the end of the grid there is no next word — step back to the previous one
  // rather than closing, so triaging the last row does not dump you out.
  const nextEl = all[idx + 1] || all[idx - 1] || null;
  fadeOutRow(word, function() {
    if (!nextEl || !nextEl.isConnected) { closePanel(); return; }
    const i = rows().indexOf(nextEl);
    if (i >= 0) selectRow(i);   // not noClick: the click is what loads the panel
    else closePanel();
  });
}

// ── Bookmark count ──────────────────────────────────────────────────────────────

function updateBookmarkCount() {
  const el = document.getElementById('bookmark-count');
  if (!el) return;
  const count = Object.values(getResearch().words).filter(function(w) { return w.bookmarked; }).length;
  el.textContent = String(count);
  const shareBtn = document.getElementById('share-bookmarks-btn');
  if (shareBtn) shareBtn.style.display = count > 0 ? '' : 'none';
}

function showToast(msg) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function() { t.remove(); }, 2200);
}

// ── Playlist URLs ───────────────────────────────────────────────────────────────
//
// The word list travels as `?w=`, a version prefix plus one base36 word id per word
// (pack_words() in api/_lib.php). The ids live in ui.db, not here, so the browser asks
// api/pack.php to encode rather than carrying a 25k-word dictionary of its own.

function packWords(words) {
  return fetch(OTIOS_BASE + '/api/pack.php', {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ words: words })
  }).then(function(r) { return r.ok ? r.json() : null; }).catch(function() { return null; });
}

function playlistUrl(packed) {
  return location.origin + location.pathname + '?w=' + packed;
}

function shareBookmarks() {
  const bookmarked = bookmarkedWords();
  if (!bookmarked.length) { showToast('Nu ai favorite încă'); return; }
  packWords(bookmarked).then(function(res) {
    if (!res || !res.w) { showToast('Nu am putut crea linkul'); return; }
    navigator.clipboard.writeText(playlistUrl(res.w))
      .then(function() { showToast('Link copiat — ' + res.count + ' cuvinte'); });
  });
}

function copyPlaylistUrl() {
  const packed = (document.getElementById('playlist-w') || {}).value;
  if (packed) {
    navigator.clipboard.writeText(playlistUrl(packed)).then(function() { showToast('Link copiat!'); });
    return;
  }
  // Legacy `?words=` playlist still open in this tab — pack it on the way out, so the
  // link that gets shared is the short one.
  const pwInput = document.getElementById('playlist-words');
  if (!pwInput || !pwInput.value) return;
  packWords(pwInput.value.split(',').filter(Boolean)).then(function(res) {
    if (!res || !res.w) { showToast('Nu am putut crea linkul'); return; }
    navigator.clipboard.writeText(playlistUrl(res.w)).then(function() { showToast('Link copiat!'); });
  });
}

// The server ignores the filter sheet entirely in two states — a playlist is open, or a
// query has been typed (word_scope() in api/_lib.php). This is the visible half of both:
// the sheet is dimmed and inert, a note says which state is in force, and the chip bar
// stops claiming filters are doing something. `sort` stays live in either, since ordering
// cannot make a row disappear.
//
// Two attributes rather than one, because they are set by different code at different
// times and either can be true alone. `applyScopeInert()` is what reads them together —
// neither setter may turn `inert` off on its own, or typing into the box while a shared
// list is open would hand the reader a live-looking sheet the server is not reading.
function applyScopeInert() {
  const form = document.getElementById('filter-form');
  if (!form) return;
  const on = form.hasAttribute('data-playlist') || form.hasAttribute('data-search');
  // `inert` rather than `disabled`: the controls keep their values and keep being
  // submitted, so leaving either mode restores the view you had before it. It also
  // takes them out of the tab order, which opacity alone would not.
  form.querySelectorAll('.fs-body > .fs-section:not(.fs-section-top), .fs-tier')
      .forEach(function(el) { el.inert = on; });
  renderActiveFilters();
}

function setPlaylistMode(on) {
  const form = document.getElementById('filter-form');
  if (!form) return;
  if (on) form.setAttribute('data-playlist', '1');
  else    form.removeAttribute('data-playlist');
  applyScopeInert();
}

// A typed query searches the whole table, not the slice the defaults left standing — the
// reasoning is in word_scope(). That has to be said on the sheet: the controls are still
// sitting there with their values, and a reader who does not know they were dropped reads
// „niciun rezultat" as "this word is not in the project" rather than as a filter they
// never set. Called on every keystroke (cheap — it only toggles attributes), on reset,
// and once on load for a `?q=` deep link.
function setSearchMode(on) {
  const form = document.getElementById('filter-form');
  if (!form) return;
  if (on) form.setAttribute('data-search', '1');
  else    form.removeAttribute('data-search');
  applyScopeInert();
}

function syncSearchMode() {
  const input = document.getElementById('search');
  setSearchMode(!!input && input.value.trim() !== '');
}

function exitPlaylist() {
  ['playlist-w', 'playlist-words'].forEach(function(id) {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const banner = document.getElementById('playlist-banner');
  if (banner) banner.style.display = 'none';
  setPlaylistMode(false);
  var params = new URLSearchParams(location.search);
  params.delete('w');
  params.delete('words');
  var qs = params.toString();
  history.replaceState(null, '', location.pathname + (qs ? '?' + qs : ''));
  var form = document.getElementById('filter-form');
  if (form) htmx.trigger(form, 'change');
}

function showPlaylistBanner(count) {
  const banner = document.getElementById('playlist-banner');
  const countEl = document.getElementById('playlist-count');
  if (banner) banner.style.display = '';
  if (countEl) countEl.textContent = count + (count === 1 ? ' cuvânt în listă' : ' cuvinte în listă');
  setPlaylistMode(true);
}

// ── Play / exploration ───────────────────────────────────────────────────────────

function openWordPanel(word, share) {
  if (!word) return;
  openWord = word;
  if (share) arrivedViaShare = true;
  var base = (typeof OTIOS_BASE !== 'undefined' ? OTIOS_BASE : '');
  htmx.ajax('GET', base + '/api/word.php?word=' + encodeURIComponent(word),
            { target: '#detail-panel', swap: 'innerHTML' });
}

function formQuery() {
  var form = document.getElementById('filter-form');
  if (!form) return '';
  return new URLSearchParams(new FormData(form)).toString();
}

function surpriseWord() {
  var base = (typeof OTIOS_BASE !== 'undefined' ? OTIOS_BASE : '');
  var qs = formQuery();
  fetch(base + '/api/random.php' + (qs ? '?' + qs : ''))
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.word) { showToast('Niciun cuvânt pentru aceste filtre'); return; }
      openWordPanel(d.word, false);
    })
    .catch(function() { showToast('Eroare la „surprise”'); });
}

// Word of the day
function wotdToday() { return new Date().toISOString().slice(0, 10); }

function openWotd() {
  var b = document.getElementById('wotd-banner');
  if (b) openWordPanel(b.dataset.word, false);
  dismissWotd();
}

function dismissWotd() {
  var b = document.getElementById('wotd-banner');
  if (b) b.style.display = 'none';
  try { localStorage.setItem('otios.wotd.seen', wotdToday()); } catch (_) {}
}

(function initWotd() {
  var b = document.getElementById('wotd-banner');
  if (!b) return;
  var seen = '';
  try { seen = localStorage.getItem('otios.wotd.seen') || ''; } catch (_) {}
  if (seen !== wotdToday()) b.style.display = '';
})();

// Restore last view mode (cloud/table)
(function initView() {
  try {
    var saved = localStorage.getItem('otios.view');
    if (saved === 'table') setView('table');
  } catch (_) {}
})();

// ── Feed / swipe mode ──────────────────────────────────────────────────────────

var FEED_DAILY_LIMIT = 50;          // soft, friendly nudge — not a hard block
var feedQueue = [];
var feedIdx   = 0;
var feedKept  = 0;
var feedLoading = false;

function feedOpen() {
  var o = document.getElementById('feed-overlay');
  return o && o.style.display !== 'none';
}

function feedDailyCount() {
  try {
    var raw = JSON.parse(localStorage.getItem('otios.feed') || '{}');
    return raw.date === wotdToday() ? (raw.count || 0) : 0;
  } catch (_) { return 0; }
}
function feedBumpDaily() {
  var c = feedDailyCount() + 1;
  try { localStorage.setItem('otios.feed', JSON.stringify({ date: wotdToday(), count: c })); } catch (_) {}
  return c;
}

function enterFeed() {
  var o = document.getElementById('feed-overlay');
  if (!o) return;
  feedQueue = []; feedIdx = 0; feedKept = 0;
  o.style.display = 'flex';
  closePanel();
  loadFeedBatch(function() { renderFeedCard(); });
}

function exitFeed() {
  var o = document.getElementById('feed-overlay');
  if (o) o.style.display = 'none';
}

function loadFeedBatch(cb) {
  if (feedLoading) return;
  feedLoading = true;
  var base = (typeof OTIOS_BASE !== 'undefined' ? OTIOS_BASE : '');
  var qs = formQuery();
  fetch(base + '/api/feed.php?n=24' + (qs ? '&' + qs : ''))
    .then(function(r) { return r.json(); })
    .then(function(d) {
      feedLoading = false;
      if (d.words && d.words.length) { feedQueue = feedQueue.concat(d.words); }
      if (cb) cb();
    })
    .catch(function() { feedLoading = false; });
}

function renderFeedCard() {
  var card = document.getElementById('feed-card');
  var prog = document.getElementById('feed-progress');
  if (!card) return;
  if (feedIdx >= feedQueue.length) {
    if (!feedLoading) {
      loadFeedBatch(function() {
        if (feedIdx >= feedQueue.length) {
          card.innerHTML = '<div class="feed-empty">Niciun cuvânt pentru aceste filtre.</div>';
        } else { renderFeedCard(); }
      });
    }
    card.innerHTML = '<div class="feed-empty">se încarcă…</div>';
    return;
  }
  var w = feedQueue[feedIdx];
  var verdict = w.verdict || 'unknown';
  var pos = (w.dex_pos || '').split('|')[0];
  var freq = (w.dex_frequency !== null && w.dex_frequency !== undefined) ? Math.round(w.dex_frequency * 100) : null;
  var dictN = w.sources ? w.sources.split('|').filter(Boolean).length : 0;
  var meta = [];
  if (pos)  meta.push(escHtml(pos));
  if (freq !== null) meta.push('dex ' + freq);
  if (dictN) meta.push('📚 ' + dictN);
  card.innerHTML =
    '<div class="feed-verdict verdict-badge vb-' + escHtml(verdict.replace(/ /g, '_')) + '">' + escHtml(verdict) + '</div>' +
    '<div class="feed-word">' + escHtml(w.word) + '</div>' +
    (meta.length ? '<div class="feed-cardmeta">' + meta.join(' · ') + '</div>' : '') +
    '<div class="feed-def">' + escHtml(w.definition || '') + '</div>';
  card.classList.remove('feed-anim-keep', 'feed-anim-skip');
  if (prog) {
    var today = feedDailyCount();
    prog.textContent = 'azi: ' + today + ' · păstrate: ' + feedKept;
  }
}

function feedAdvance(animClass) {
  var card = document.getElementById('feed-card');
  if (card && animClass) card.classList.add(animClass);
  var count = feedBumpDaily();
  feedIdx++;
  var go = function() { renderFeedCard(); };
  if (count === FEED_DAILY_LIMIT) {
    showToast('Ai explorat ' + FEED_DAILY_LIMIT + ' de cuvinte azi 🎉');
  }
  setTimeout(go, animClass ? 160 : 0);
}

function feedKeep() {
  if (feedIdx >= feedQueue.length) return;
  var w = feedQueue[feedIdx];
  if (w && !getWord(w.word).bookmarked) {
    updateWord(w.word, { bookmarked: true });
    feedKept++;
    updateBookmarkCount();
  }
  feedAdvance('feed-anim-keep');
}

function feedSkip() {
  if (feedIdx >= feedQueue.length) return;
  feedAdvance('feed-anim-skip');
}

// Touch swipe on the feed card
(function() {
  var startX = 0, startY = 0, tracking = false;
  var card = function() { return document.getElementById('feed-card'); };
  document.addEventListener('touchstart', function(e) {
    if (!feedOpen() || e.touches.length !== 1) return;
    var c = card();
    if (!c || !c.contains(e.target)) return;
    startX = e.touches[0].clientX; startY = e.touches[0].clientY; tracking = true;
  }, { passive: true });
  document.addEventListener('touchend', function(e) {
    if (!tracking) return;
    tracking = false;
    var t = e.changedTouches[0];
    var dx = t.clientX - startX, dy = t.clientY - startY;
    if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy)) {
      if (dx > 0) feedKeep(); else feedSkip();
    }
  }, { passive: true });
})();

// ── Datalist for tag autocomplete ───────────────────────────────────────────────

function populateTagDatalist() {
  const dl = document.getElementById('tag-suggestions');
  if (!dl) return;
  const seen = new Set();
  Object.values(getResearch().words).forEach(function(w) {
    (w.tags || []).forEach(function(t) {
      if (!QUICK_TAG_KEYS.includes(t)) seen.add(t);
    });
  });
  dl.innerHTML = '';
  seen.forEach(function(t) {
    const opt = document.createElement('option');
    opt.value = t;
    dl.appendChild(opt);
  });
}

// Populate marks <select> with custom tags from localStorage so they're filterable
function populateTagFilterOptions() {
  const sel = document.querySelector('select[name=marks]');
  if (!sel) return;
  sel.querySelectorAll('option.custom-tag-opt').forEach(function(o) { o.remove(); });
  const seen = new Set();
  Object.values(getResearch().words).forEach(function(w) {
    (w.tags || []).forEach(function(t) {
      if (!QUICK_TAG_KEYS.includes(t)) seen.add(t);
    });
  });
  seen.forEach(function(t) {
    const opt = document.createElement('option');
    opt.value = 'tag:' + t;
    opt.textContent = 'tag: ' + t;
    opt.className = 'custom-tag-opt';
    sel.appendChild(opt);
  });
}

// ── Marks filter: inject marked_words before HTMX search request ───────────────

function markedWordsForFilter(marks) {
  const research = getResearch();
  const words    = research.words;

  if (marks === 'bookmarked') {
    return Object.entries(words).filter(function([,w]) { return w.bookmarked; }).map(function([k]) { return k; });
  }
  if (marks === 'noted') {
    return Object.entries(words).filter(function([,w]) { return w.note && w.note.trim(); }).map(function([k]) { return k; });
  }
  if (marks === 'marked') {
    return Object.entries(words).filter(function([,w]) {
      return w.bookmarked || (w.note && w.note.trim()) || (w.tags && w.tags.length);
    }).map(function([k]) { return k; });
  }
  if (marks === 'unmarked') {
    // return all marked words so server can do NOT IN
    return Object.entries(words).filter(function([,w]) {
      return w.bookmarked || (w.note && w.note.trim()) || (w.tags && w.tags.length);
    }).map(function([k]) { return k; });
  }
  if (marks.startsWith('tag:')) {
    const tag = marks.slice(4).trim();
    return Object.entries(words).filter(function([,w]) {
      return (w.tags || []).includes(tag);
    }).map(function([k]) { return k; });
  }
  return null;
}

document.addEventListener('htmx:configRequest', function(e) {
  const url = e.detail.path || '';
  const base = (typeof OTIOS_BASE !== 'undefined' ? OTIOS_BASE : '');
  if (!url.startsWith(base + '/api/search.php')) return;
  const marks = e.detail.parameters['marks'] || 'all';

  // Once the store has synced, the server filters from its own copy of the
  // annotations and this parameter is dead weight — it is the thing that used to
  // blow the URL length limit. Still sent before the first successful sync so the
  // filter works offline and during migration.
  if (getSyncState().since) return;

  const wordList = markedWordsForFilter(marks);
  if (wordList !== null) {
    e.detail.parameters['marked_words'] = wordList.join(',');
  }
});

// ── HTMX lifecycle ─────────────────────────────────────────────────────────────


// ── Filter explainers ───────────────────────────────────────────────────────────
//
// A „?" beside each section heading reveals a one-line explanation. Delegated so it
// survives any re-render of the sheet, and `type=button` so it neither submits the form
// nor fires the `change` that htmx searches on.
document.addEventListener('click', function(e) {
  var btn = e.target.closest && e.target.closest('.fs-help');
  if (!btn) return;
  e.preventDefault();
  var panel = document.getElementById(btn.getAttribute('aria-controls'));
  if (!panel) return;
  var open = btn.getAttribute('aria-expanded') === 'true';
  btn.setAttribute('aria-expanded', open ? 'false' : 'true');
  panel.hidden = open;
});


document.body.addEventListener('htmx:afterSwap', function(e) {
  const target = e.detail.target;
  if (target.id === 'word-list') {
    selectedIdx = -1;
    hydrateRows(target);
    // Highlight the word from a shared URL after the list renders
    if (openWord) {
      var all = rows();
      var idx = all.findIndex(function(r) { return r.dataset.word === openWord; });
      if (idx >= 0) selectRow(idx, true);
    }
    // Update result count in filter sheet footer
    var countEl = document.getElementById('result-count-sheet');
    var mainCount = document.getElementById('result-count');
    if (countEl && mainCount) countEl.textContent = mainCount.textContent;
  }
  if (target.id === 'detail-panel') activateDetailPanel(target);
});

// Everything a freshly-filled #detail-panel needs before it reads as "open" — pulled out
// of the htmx:afterSwap handler above so the SSR arrival path (bottom of this file) can
// call it directly on the panel index.php already rendered, instead of re-fetching
// api/word.php and replacing that content wholesale. Without this split, arriving at a
// share link fired an ajax call that swapped the server-rendered <h1> for api/word.php's
// plain <div> within milliseconds of load — invisible to a quick glance at the page, but
// it is what a headless renderer (Google's included) sees once it runs this same JS, so
// the whole point of server-rendering the <h1> would have been lost the moment JS ran.
function activateDetailPanel(target) {
  // The dict-name tooltip (store.js) gets reparented to <body> when opened, to
  // escape #detail-panel's `transform` (its containing block for position:fixed
  // otherwise — see the comment at store.js's dictToggle handler). htmx's
  // `innerHTML` swap only replaces what's still inside #detail-panel, so a
  // tooltip left open on the *previous* word survives the swap as an orphan
  // sitting directly under <body>; every word switch would otherwise leave one
  // more behind. It's already superseded by the fresh `.dict-tooltip` the new
  // HTML just brought in, so this is a plain removal, not a hide.
  var staleTip = document.body.querySelector(':scope > .dict-tooltip');
  if (staleTip) staleTip.remove();

  target.classList.add('panel-open');
  // Mobile reclaims the brand bar and the status bar while a definition is up —
  // on a 375×812 phone those two are ~186px, 23% of the screen, and neither is
  // doing anything you can act on while reading. The class is set at every width
  // and the hiding is scoped to the mobile media query, so a desktop window
  // narrowed with the panel open lands in the right state without a resize
  // listener. `.fp-close` becomes the back arrow there — see app.css.
  document.body.classList.add('detail-open');
  // On desktop, switch #app to side-by-side row layout
  if (window.innerWidth >= 769) {
    var app = document.getElementById('app');
    if (app) app.classList.add('has-panel');
  }
  // Definition-as-hero when arriving from a shared link; normal height otherwise.
  if (arrivedViaShare) {
    target.classList.add('share-focus');
    arrivedViaShare = false;
    setTimeout(function() { target.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, 60);
  } else {
    target.classList.remove('share-focus');
  }
  const hb = document.getElementById('hover-box');
  if (hb) hb.classList.remove('visible');
  hydrateDetail(target);
  var wordEl = target.querySelector('[data-word]');
  if (wordEl) { openWord = wordEl.dataset.word; syncUrlFromForm(); }
}

// Also hydrate OOB-swapped load-more results
document.body.addEventListener('htmx:oobAfterSwap', function() {
  hydrateRows(document.getElementById('word-list'));
});

// ── Grid navigation (preserved from base.html) ─────────────────────────────────

let selectedIdx = -1;
let gPressed    = false;

function rows() { return Array.from(document.querySelectorAll('.word-row')); }

function selectRow(idx, noClick) {
  const all = rows();
  if (!all.length) return;
  selectedIdx = Math.max(0, Math.min(idx, all.length - 1));
  all.forEach(function(r) {
    r.removeAttribute('data-selected');
    // Roving tabindex: exactly one row is tabbable at a time, so Tab enters and
    // leaves the list in one step instead of walking every word on the page.
    r.setAttribute('tabindex', '-1');
    r.setAttribute('aria-selected', 'false');
  });
  const r = all[selectedIdx];
  if (r) {
    // Move DOM focus along with the selection, but only when focus was already on a
    // row. j/k from a focused row should carry the caret; the same call made on page
    // load from a ?word= link must not yank focus out of wherever the user is.
    const focusWasInList = document.activeElement &&
                           document.activeElement.classList.contains('word-row');
    r.setAttribute('data-selected', '');
    r.setAttribute('tabindex', '0');
    r.setAttribute('aria-selected', 'true');
    r.scrollIntoView({ block: 'nearest' });
    if (focusWasInList) r.focus({ preventScroll: true });
    if (!noClick) r.click();
  }
  // The container is only a tab stop while no row owns the tabindex — otherwise the
  // list would be two stops. It goes back to being one when the list empties out,
  // so a filter that matches nothing is still reachable.
  const list = document.getElementById('word-list');
  if (list) list.setAttribute('tabindex', r ? '-1' : '0');
}

function navigateSpatial(direction) {
  const all = rows();
  if (!all.length) return;
  if (selectedIdx < 0) { selectRow(0); return; }
  const cur   = all[selectedIdx].getBoundingClientRect();
  const curMX = (cur.left + cur.right) / 2;
  let best    = { idx: -1, score: Infinity };
  all.forEach(function(el, idx) {
    if (idx === selectedIdx) return;
    const r  = el.getBoundingClientRect();
    const mx = (r.left + r.right) / 2;
    const sameRow = Math.abs(r.top - cur.top) < cur.height * 0.6;
    let score;
    if (direction === 'left') {
      if (!sameRow || r.right > cur.left + 1) return;
      score = cur.left - r.right;
    } else if (direction === 'right') {
      if (!sameRow || r.left < cur.right - 1) return;
      score = r.left - cur.right;
    } else if (direction === 'up') {
      if (r.bottom > cur.top + 1) return;
      score = (cur.top - r.bottom) * 10 + Math.abs(mx - curMX);
    } else {
      if (r.top < cur.bottom - 1) return;
      score = (r.top - cur.bottom) * 10 + Math.abs(mx - curMX);
    }
    if (score < best.score) best = { idx: idx, score: score };
  });
  if (best.idx >= 0) selectRow(best.idx);
}

// Above this width the filter form is docked as a persistent left rail;
// below it, it is a bottom drawer. Keep in sync with the media query in app.css.
const RAIL_BP = '(min-width: 1024px)';
function filterRailDocked() { return window.matchMedia(RAIL_BP).matches; }

function toggleFilterDrawer() {
  const sheet = document.getElementById('filter-form');
  const backdrop = document.getElementById('filter-backdrop');
  if (!sheet) return;

  if (filterRailDocked()) {
    // Docked: the button collapses/expands the rail. No backdrop, no scroll lock.
    const collapsed = sheet.classList.toggle('rail-collapsed');
    try { localStorage.setItem('otios.rail', collapsed ? 'collapsed' : 'open'); } catch (_) {}
    syncFilterToggleBtn();
    return;
  }

  const open = sheet.classList.toggle('open');
  if (backdrop) backdrop.classList.toggle('visible', open);
  document.body.style.overflow = open ? 'hidden' : '';
  syncFilterToggleBtn();
}

function syncFilterToggleBtn() {
  const sheet = document.getElementById('filter-form');
  const btn = document.getElementById('filter-toggle-btn');
  if (!sheet || !btn) return;
  const shown = filterRailDocked() ? !sheet.classList.contains('rail-collapsed')
                                   : sheet.classList.contains('open');
  btn.setAttribute('aria-expanded', shown ? 'true' : 'false');
  btn.classList.toggle('filter-toggle-active', shown);
}

// Restore the rail's collapsed state; re-sync when crossing the breakpoint so a
// drawer left open on a narrow window doesn't reappear as a collapsed rail.
(function initFilterRail() {
  const sheet = document.getElementById('filter-form');
  if (!sheet) return;
  try {
    if (localStorage.getItem('otios.rail') === 'collapsed') sheet.classList.add('rail-collapsed');
  } catch (_) {}
  const mq = window.matchMedia(RAIL_BP);
  const onChange = function() {
    sheet.classList.remove('open');
    const backdrop = document.getElementById('filter-backdrop');
    if (backdrop) backdrop.classList.remove('visible');
    document.body.style.overflow = '';
    syncFilterToggleBtn();
  };
  if (mq.addEventListener) mq.addEventListener('change', onChange);
  else if (mq.addListener) mq.addListener(onChange);
  syncFilterToggleBtn();
})();

function setView(mode) {
  const list = document.getElementById('word-list');
  const btnCloud = document.getElementById('btn-cloud');
  const btnTable = document.getElementById('btn-table');
  if (!list) return;
  // aria-pressed alongside the class: the class is what CSS reads, the attribute is
  // what a screen reader reads, and only one of them existed before.
  function setPressed(btn, on) {
    if (!btn) return;
    btn.classList.toggle('vt-active', on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
  if (mode === 'table') {
    list.classList.add('word-list-table');
    list.classList.remove('word-list-cloud');
    setPressed(btnCloud, false);
    setPressed(btnTable, true);
  } else {
    list.classList.remove('word-list-table');
    list.classList.add('word-list-cloud');
    setPressed(btnCloud, true);
    setPressed(btnTable, false);
  }
  try { localStorage.setItem('otios.view', mode); } catch (_) {}
}

// Theme, skin and text-scale controls live in prefs.js — every page carries
// those toggles, this file is index-only.

// Search is collapsed behind the magnifier button (.search-wrap) until opened —
// on click, on the `/` shortcut, or already-open on load if the URL carried a
// query (see the applyUrlToForm() call site below).
function openSearch(focus) {
  var wrap = document.getElementById('search-wrap');
  if (!wrap) return;
  wrap.classList.add('is-open');
  var btn = document.getElementById('search-toggle-btn');
  if (btn) btn.setAttribute('aria-expanded', 'true');
  if (focus) document.getElementById('search').focus();
}
function closeSearchIfEmpty() {
  var input = document.getElementById('search');
  if (!input || input.value.trim() !== '') return;
  var wrap = document.getElementById('search-wrap');
  if (wrap) wrap.classList.remove('is-open');
  var btn = document.getElementById('search-toggle-btn');
  if (btn) btn.setAttribute('aria-expanded', 'false');
}

function showShortcuts() { document.getElementById('shortcuts-overlay').style.display = 'flex'; }
function hideShortcuts() { document.getElementById('shortcuts-overlay').style.display = 'none'; }
function closePanel() {
  var panel = document.getElementById('detail-panel');
  // An open dict-name tooltip is reparented to <body> (store.js) and no longer sits
  // inside #detail-panel's own collapsing box — it would otherwise keep floating over
  // the page after the panel itself is gone.
  if (typeof closeDictTooltips === 'function') closeDictTooltips();
  panel.classList.remove('panel-open');
  panel.classList.remove('share-focus');
  document.body.classList.remove('detail-open');
  var app = document.getElementById('app');
  if (app) app.classList.remove('has-panel');
  openWord = null;
  // Retire the pin with the panel. Nothing re-fires here, so the word stays where it is
  // in the list you are looking at; it stops being pinned from the next search onwards —
  // which is the moment the URL stops naming it too. Left set, it would silently hold a
  // word at the top of results the reader has since filtered for something else.
  var pin = document.getElementById('share-word');
  if (pin) pin.value = '';
  syncUrlFromForm();
}

document.addEventListener('keydown', function(e) {
  // Never shadow a browser shortcut: Cmd/Ctrl+R was reaching the `r` handler and
  // firing surpriseWord() instead of reloading the page.
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const tag     = document.activeElement.tagName;
  const inInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
  // Feed mode captures navigation keys
  if (feedOpen()) {
    if (e.key === 'Escape') { e.preventDefault(); exitFeed(); return; }
    if (e.key === 'ArrowRight' || e.key === 'l') { e.preventDefault(); feedKeep(); return; }
    if (e.key === 'ArrowLeft'  || e.key === 'h') { e.preventDefault(); feedSkip(); return; }
    return;
  }
  if (e.key === '?') { e.preventDefault(); showShortcuts(); return; }
  if (inInput) {
    if (e.key === 'Escape') {
      hideShortcuts();
      const wasSearch = document.activeElement.id === 'search';
      document.activeElement.blur();
      if (wasSearch && rows().length) selectRow(selectedIdx >= 0 ? selectedIdx : 0, true);
    }
    return;
  }
  if (e.key === 'Escape') { hideShortcuts(); closePanel(); return; }
  if (e.key === '/') { e.preventDefault(); openSearch(true); return; }
  if (e.key === 'j' || e.key === 'ArrowDown')  { e.preventDefault(); navigateSpatial('down');  gPressed = false; return; }
  if (e.key === 'k' || e.key === 'ArrowUp')    { e.preventDefault(); navigateSpatial('up');    gPressed = false; return; }
  if (e.key === 'h' || e.key === 'ArrowLeft')  { e.preventDefault(); navigateSpatial('left');  gPressed = false; return; }
  // Bare 'l' is the lol quick-tag shortcut below, not grid nav — ArrowRight still
  // covers the vim-style hjkl direction.
  if (e.key === 'ArrowRight') { e.preventDefault(); navigateSpatial('right'); gPressed = false; return; }
  if (e.key === 'G') { e.preventDefault(); selectRow(rows().length - 1); gPressed = false; return; }
  if (e.key === 'g') {
    if (gPressed) { selectRow(0); gPressed = false; }
    else { gPressed = true; setTimeout(function() { gPressed = false; }, 400); }
    return;
  }
  if (e.key === 'r') { e.preventDefault(); surpriseWord(); return; }
  // Actions — call localStorage handlers instead of HTMX
  if (e.key === 'f') {
    const btn = document.getElementById('bookmark-btn');
    if (btn) { e.preventDefault(); btn.click(); }
    return;
  }
  if (e.key === 'n') {
    const note = document.getElementById('note-input');
    if (note) { e.preventDefault(); note.focus(); }
    return;
  }
  if (e.key === 'o') {
    const link = document.querySelector('#detail-panel .dex-link');
    if (link) { e.preventDefault(); window.open(link.href, '_blank', 'noopener'); }
    return;
  }
  if (e.key === 't') {
    const ti = document.getElementById('tag-input');
    if (ti) { e.preventDefault(); ti.focus(); }
    return;
  }
  if (e.key === 'a' || e.key === 'l' || e.key === 'm') {
    const btn = document.querySelector('#detail-panel .qt-btn[data-qtkey="' + e.key + '"]');
    if (btn) { e.preventDefault(); btn.click(); }
    return;
  }
});

// Sync selectedIdx on mouse click (and handle dismissing on mobile)
document.addEventListener('click', function(e) {
  const container = document.getElementById('word-list-container');
  if (!container || !container.contains(e.target)) return;
  const row = e.target.closest('.word-row');
  
  if (!row) {
    // Tapped an empty spot in the list -> Hide panel and deselect
    closePanel();
    const selected = document.querySelector('.word-row[data-selected]');
    if (selected) selected.removeAttribute('data-selected');
    return;
  }

  const all = rows();
  const idx = all.indexOf(row);
  // Route through selectRow so the mouse path keeps aria-selected and the roving
  // tabindex in step — it used to set data-selected by hand, and after this pass
  // that would have left the keyboard's tab stop on whatever was selected before.
  if (idx !== -1) { selectRow(idx, true); return; }
  if (idx < 0) return;
  all.forEach(function(r) { r.removeAttribute('data-selected'); });
  row.setAttribute('data-selected', '');
  selectedIdx = idx;
});

// ── Keyboard access to the word list ────────────────────────────────────────────
//
// The rows are `role="option"` inside a `role="listbox"`, which buys the right
// announcement but no behaviour: a div does not activate on Enter the way a button
// does, and a listbox is expected to be one tab stop that you then arrow around in.
// Both halves are supplied here. j/k/h/l and the arrows are already handled by the
// global keydown listener above and move selection (and, from a focused row, focus).

document.addEventListener('keydown', function(e) {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const row = document.activeElement && document.activeElement.closest('.word-row');
  if (!row) return;
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();          // Space would otherwise scroll the list
    row.click();
  }
});

// Tabbing into an untouched list lands on the container; hand it straight to the
// selected word (or the first) so the very next arrow key does something visible.
// selectRow can't move focus itself here — it only does so when focus is already on
// a row, and at this instant it is on the container — so focus is passed explicitly.
document.addEventListener('focusin', function(e) {
  if (e.target.id !== 'word-list') return;
  const all = rows();
  if (!all.length) return;
  selectRow(selectedIdx < 0 ? 0 : selectedIdx, true);
  const sel = all[selectedIdx];
  if (sel) sel.focus({ preventScroll: true });
});

// After a search, the results are the next thing a reader wants, but in DOM order the
// header's shortcuts link, the filter button and the sheet's controls come first.
// So, while the box holds a query: Tab from it lands on the selected word (or the
// first), and Shift+Tab from a word goes back to the box. With an empty box, or before
// any result has arrived, Tab keeps its normal order.
document.addEventListener('keydown', function(e) {
  if (e.key !== 'Tab' || e.metaKey || e.ctrlKey || e.altKey) return;
  const input = document.getElementById('search');
  if (!input || input.value.trim() === '') return;
  if (!e.shiftKey && e.target === input) {
    const all = rows();
    if (!all.length) return;
    e.preventDefault();
    selectRow(selectedIdx < 0 ? 0 : selectedIdx, true);
    const sel = all[selectedIdx];
    if (sel) sel.focus({ preventScroll: true });
  } else if (e.shiftKey && e.target.closest && e.target.closest('.word-row')) {
    e.preventDefault();
    input.focus();
  }
});

// Shortcuts overlay dismiss
document.addEventListener('click', function(e) {
  const overlay = document.getElementById('shortcuts-overlay');
  if (overlay && e.target === overlay) hideShortcuts();
});

// Deselectable radio pills
document.querySelectorAll('#filter-form label.pill').forEach(function(label) {
  label.addEventListener('mousedown', function() {
    const input = this.querySelector('input[type=radio]');
    if (input) input.dataset.wasChecked = input.checked ? '1' : '';
  });
});
document.querySelectorAll('#filter-form label.pill input[type=radio]').forEach(function(r) {
  r.addEventListener('click', function() {
    if (this.dataset.wasChecked === '1') {
      this.checked = false;
      this.dataset.wasChecked = '';
      this.form.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });
});

// There used to be a tab-gating block here — three sections shown or hidden depending on
// `word_tier`, because the „rare" tab could not use the seam or the class controls and the
// main tab could not use the DEX ceiling. It is gone with that tab, and it is worth
// recording what it cost: the gate had to be kept in step in three places, it silently
// mis-set every one of them on a deep link (applyUrlToForm() changes the radios without
// dispatching `change`, and the gate ran at script-eval time), and every filter added
// afterwards had to decide whether it was tab-specific. One list needs none of that.

// Tax-select active highlight
document.querySelectorAll('.tax-select').forEach(function(sel) {
  const dflt = sel.dataset.default !== undefined ? sel.dataset.default : '';
  function update() { sel.classList.toggle('active', sel.value !== dflt); }
  sel.addEventListener('change', update);
  if (sel.form) sel.form.addEventListener('reset', update);
  update();
});

// ── Hover info box ─────────────────────────────────────────────────────────────

(function() {
  const box    = document.getElementById('hover-box');
  const hbWord = document.getElementById('hb-word');
  const hbVerd = document.getElementById('hb-verdict');
  const hbMeta = document.getElementById('hb-meta');
  const hbDef  = document.getElementById('hb-def');
  const panel  = document.getElementById('detail-panel');

  document.addEventListener('mouseover', function(e) {
    const row = e.target.closest('.word-row');
    if (!row || panel.classList.contains('panel-open')) return;
    const verdict = row.dataset.verdict || 'unknown';
    hbWord.textContent = row.querySelector('.word-text').textContent;
    // The label is rendered into the row by word_row.php rather than mapped here, so
    // verdict copy has exactly one home (VERDICTS in api/_lib.php).
    hbVerd.textContent = row.dataset.vlabel || '';
    hbVerd.className   = 'verdict-badge vb-' + verdict.replace(/ /g, '_');
    const parts = [];
    if (row.dataset.pos)  parts.push(row.dataset.pos);
    if (row.dataset.hist) parts.push('ist ' + row.dataset.hist);
    hbMeta.textContent = parts.join(' · ');
    if (row.dataset.def) {
      hbDef.textContent  = row.dataset.def;
      hbDef.style.display = '';
    } else {
      hbDef.style.display = 'none';
    }
    box.classList.add('visible');
  });

  document.addEventListener('mouseout', function(e) {
    const row = e.target.closest('.word-row');
    if (!row) return;
    const to = e.relatedTarget;
    if (to && row.contains(to)) return;
    box.classList.remove('visible');
  });
})();

// ── Active-filter chips (at-a-glance, individually removable) ────────────────────

// The special classes, in one place — they are `forgotten`-tab-only controls and
// three separate lists here would have to be kept in step by hand. Adding one here
// registers it in both URL directions and both tab guards at once, which is the whole
// reason this array exists rather than five literals.
// `variants` is one control over three columns (variant_like / archaic_spelling /
// dex_variant) — see $class_modes in api/_lib.php for why they are bundled. It is one
// entry here because it is one radio in the form; the bundling happens server-side.
var CLASS_PARAMS = ['regional', 'variants', 'deverbal', 'diminutives', 'editorial'];

// Checkbox groups whose "no filter" state is not "everything ticked".
// `verdict`/`tier`/`pos` all start fully checked, so all-checked reads as untouched. The
// seams are a partition and start with only `relevant` on, so 1-of-2 IS the default —
// without this the URL would carry ?seam=relevant on every page and the chip bar would
// claim a filter the reader never set.
var URL_GROUP_DEFAULTS = { seam: ['relevant'] };

function groupIsDefault(form, name) {
  var all  = Array.from(form.querySelectorAll('input[name="' + name + '[]"]'));
  if (!all.length) return true;
  var chkd = all.filter(function(cb) { return cb.checked; }).map(function(cb) { return cb.value; });
  var def  = URL_GROUP_DEFAULTS[name] || all.map(function(cb) { return cb.value; });
  return chkd.length === def.length && chkd.every(function(v) { return def.indexOf(v) !== -1; });
}

var AF_SPECS = [
  { name: 'q',              type: 'text',     label: function(v){ return '„' + v + '”'; } },
  { name: 'has_def',        type: 'radio',  def: '', label: function(v){ return v === '1' ? 'cu definiție' : 'fără definiție'; } },
  { name: 'register',       type: 'select', def: '', label: function(v){ return 'registru: ' + v; } },
  { name: 'domain',         type: 'select', def: '', label: function(v){ return 'domeniu: ' + v; } },
  { name: 'etymology',      type: 'select', def: '', label: function(v){ return 'etim: ' + v.replace('limba ', ''); } },
  { name: 'dict_min',       type: 'select', def: '', label: function(v){ return 'dicts ≥' + v; } },
  // Bands, not counts — the chip says what the control says, and neither carries a
  // threshold that a new corpus would silently move. See mark_modern_band().
  { name: 'modern',         type: 'select', def: '', label: function(v){
      return v === '2' ? 'încă în circulație' : v === '1' ? 'urme slabe' : 'fără urme azi'; } },
  { name: 'attested_after',  type: 'select', def: '', label: function(v){ return 'atestat ≥' + v; } },
  { name: 'attested_before', type: 'select', def: '', label: function(v){ return 'atestat <' + v; } },
  // `marks` was in both URL arrays but not here, so it filtered the grid without
  // ever showing a chip — the same "registered in one direction only" gap the
  // CLAUDE.md filter rule is about, on the chip side rather than the URL side.
  { name: 'marks',          type: 'select', def: 'all', label: function(v){
      if (v === 'unmarked')   return 'nemarcate';
      if (v === 'marked')     return 'marcate';
      if (v === 'bookmarked') return '★ favorite';
      return v.indexOf('tag:') === 0 ? 'tag: ' + v.slice(4) : v; } },
  { name: 'dexfreq_min',    type: 'number',   label: function(v){ return 'dex ≥' + v; } },
  { name: 'dexfreq_max',    type: 'number',   label: function(v){ return 'dex ≤' + v; } },
  // The special classes. Three states each, so the chip has to name which one is
  // live — „cu regionalisme" and „doar regionalisme" are different filters, and the
  // second is the one that needs saying loudest. The chip label must match the rail's
  // row label exactly: they are the same control seen twice, and „cu grafii vechi" on a
  // chip beside a row reading „variante" reads as two filters.
  { name: 'regional',    type: 'radio', def: 'hide', label: function(v){ return (v === 'only' ? 'doar ' : 'cu ') + 'regionalisme'; } },
  { name: 'variants',    type: 'radio', def: 'hide', label: function(v){ return (v === 'only' ? 'doar ' : 'cu ') + 'variante'; } },
  { name: 'deverbal',    type: 'radio', def: 'hide', label: function(v){ return (v === 'only' ? 'doar ' : 'cu ') + 'nume de acțiune'; } },
  { name: 'diminutives', type: 'radio', def: 'hide', label: function(v){ return (v === 'only' ? 'doar ' : 'cu ')  + 'diminutive'; } },
  { name: 'editorial',   type: 'radio', def: 'back', label: function(v){ return v === 'only' ? 'doar respinse' : 'respinse la rând'; } },
  // A checkbox group now, like verdict/tier/pos — both ticked is what „toate" used to be.
  // Chips only when the selection is partial, which the 'group' type already handles.
  // Two options, so the chip names them rather than counting them — „listă 1/2" does not
  // say *which* one, and this is the filter a reader is most likely to have forgotten.
  { name: 'seam',           type: 'group',  label: function(n, t, vals){
      if (n === 0) return 'nicio listă';
      if (n === t) return 'ambele liste';
      return 'listă: ' + (vals[0] === 'curiosity' ? 'curiozități' : 'relevante'); } },
  { name: 'verdict',        type: 'group',    label: function(n, t){ return 'verdict ' + n + '/' + t; } },
  { name: 'tier',           type: 'group',    label: function(n, t){ return 'tier ' + n + '/' + t; } },
  { name: 'pos',            type: 'group',    label: function(n, t){ return 'POS ' + n + '/' + t; } },
];

function activeFilterChips() {
  var form = document.getElementById('filter-form');
  if (!form) return [];
  var chips = [];
  AF_SPECS.forEach(function(spec) {
    if (spec.type === 'text' || spec.type === 'number') {
      var el = form.querySelector('input[name=' + spec.name + ']');
      if (el && el.value.trim()) chips.push({ spec: spec, text: spec.label(el.value.trim()) });
    } else if (spec.type === 'radio') {
      var r = form.querySelector('input[name=' + spec.name + ']:checked');
      if (r && r.value !== spec.def) chips.push({ spec: spec, text: spec.label(r.value) });
    } else if (spec.type === 'select') {
      var s = form.querySelector('select[name=' + spec.name + ']');
      if (s && s.value !== spec.def && s.value !== '') chips.push({ spec: spec, text: spec.label(s.value) });
    } else if (spec.type === 'checkbox') {
      var c = form.querySelector('input[name=' + spec.name + ']');
      if (c && c.checked) chips.push({ spec: spec, text: spec.label() });
    } else if (spec.type === 'group') {
      var all = Array.from(form.querySelectorAll('input[name="' + spec.name + '[]"]'));
      var chk = all.filter(function(cb){ return cb.checked; });
      if (all.length && !groupIsDefault(form, spec.name)) {
        var vals = chk.map(function(cb){ return cb.value; });
        chips.push({ spec: spec, text: spec.label(chk.length, all.length, vals) });
      }
    }
  });
  return chips;
}

function clearFilter(spec) {
  var form = document.getElementById('filter-form');
  if (!form) return;
  if (spec.type === 'text' || spec.type === 'number') {
    var el = form.querySelector('input[name=' + spec.name + ']');
    if (el) el.value = '';
  } else if (spec.type === 'radio') {
    form.querySelectorAll('input[name=' + spec.name + ']').forEach(function(r){ r.checked = (r.value === spec.def); });
  } else if (spec.type === 'select') {
    var s = form.querySelector('select[name=' + spec.name + ']');
    if (s) { s.value = spec.def; s.dispatchEvent(new Event('change', { bubbles: true })); return; }
  } else if (spec.type === 'checkbox') {
    var c = form.querySelector('input[name=' + spec.name + ']');
    if (c) c.checked = false;
  } else if (spec.type === 'group') {
    var gdef = URL_GROUP_DEFAULTS[spec.name];
    form.querySelectorAll('input[name="' + spec.name + '[]"]').forEach(function(cb){
      cb.checked = gdef ? gdef.indexOf(cb.value) !== -1 : true;
    });
  }
  form.dispatchEvent(new Event('change', { bubbles: true }));
}

function renderActiveFilters() {
  var bar = document.getElementById('active-filters');
  if (!bar) return;
  // Playlist open, or a query typed → the server applied no filters, so neither does the
  // chip bar. The playlist banner (or the sheet's search note) is the state that holds.
  var form = document.getElementById('filter-form');
  if (form && (form.hasAttribute('data-playlist') || form.hasAttribute('data-search'))) {
    bar.innerHTML = '';
    return;
  }
  var chips = activeFilterChips();
  bar.innerHTML = '';
  chips.forEach(function(c) {
    var chip = document.createElement('span');
    chip.className = 'af-chip';
    chip.appendChild(document.createTextNode(c.text + ' '));
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('aria-label', 'elimină filtrul');
    btn.textContent = '×';
    btn.addEventListener('click', function() { clearFilter(c.spec); });
    chip.appendChild(btn);
    bar.appendChild(chip);
  });
  if (chips.length > 1) {
    var clearAll = document.createElement('button');
    clearAll.type = 'button';
    clearAll.className = 'af-clear-all';
    clearAll.textContent = 'resetează tot';
    clearAll.addEventListener('click', function() {
      var form = document.getElementById('filter-form');
      if (form) form.reset();
    });
    bar.appendChild(clearAll);
  }
}

document.getElementById('filter-form') &&
  document.getElementById('filter-form').addEventListener('change', renderActiveFilters);

// ── URL ↔ filter sync ──────────────────────────────────────────────────────────

// Param names whose default value means "no filter" (omit from URL when at default)
var URL_PARAM_DEFAULTS = {
  has_def:   '',
  sort:      'populare',
  marks:     'all',
  // Special classes — three states each, so unlike the old checkboxes these always
  // submit a value and need a default here to stay out of the URL when untouched.
  regional:    'hide',
  variants:    'hide',
  deverbal:    'hide',
  diminutives: 'hide',
  editorial:   'back',
};

function applyUrlToForm() {
  var params = new URLSearchParams(location.search);
  if (!params.toString()) return;
  var form = document.getElementById('filter-form');
  if (!form) return;

  // Text input
  var q = params.get('q');
  if (q) { var qi = form.querySelector('input[name=q]'); if (qi) qi.value = q; }

  // Radio groups
  ['has_def'].concat(CLASS_PARAMS).forEach(function(name) {
    var val = params.get(name);
    if (val === null) return;
    form.querySelectorAll('input[name=' + name + ']').forEach(function(r) {
      r.checked = (r.value === val);
    });
  });

  // Superseded param spellings. The server maps these too (class_mode() in _lib.php),
  // but htmx searches from *form* state on load, so a server-only mapping leaves an old
  // link rendering as unfiltered while behaving as filtered. **This list must stay in
  // step with the `$aliases` in $class_modes** — the two halves of one mapping.
  //
  // Two shapes. `null` means the alias carries its own three-state value: `spellings`
  // and `dexvar` were their own rows until they were folded into `variants`, so
  // `?spellings=only` has to land on that radio. A string is a checkbox-era `=1` flag
  // and names the mode it implies.
  [['show_regional', 'regional', 'show'],
   ['spellings', 'variants', null],
   ['dexvar', 'variants', null],
   ['show_variants', 'variants', 'show'],
   ['show_spellings', 'variants', 'show'],
   ['hide_diminutives', 'diminutives', 'hide']].forEach(function(m) {
    // An explicit value for the target always wins, and an earlier alias that already
    // set it wins over a later one — same precedence as class_mode().
    if (params.get(m[1]) !== null || form.dataset['alias_' + m[1]]) return;
    var val = m[2] === null ? params.get(m[0]) : (params.get(m[0]) === '1' ? m[2] : null);
    if (val === null || ['hide', 'show', 'only', 'back'].indexOf(val) === -1) return;
    form.dataset['alias_' + m[1]] = '1';
    form.querySelectorAll('input[name=' + m[1] + ']').forEach(function(r) {
      r.checked = (r.value === val);
    });
  });

  // Checkbox groups (verdict, tier, pos): comma-separated in URL; absent = all checked
  ['verdict', 'tier', 'pos', 'seam'].forEach(function(name) {
    var val = params.get(name);
    if (val === null) return; // not in URL → leave all checked
    var selected = val.split(',').filter(Boolean);
    form.querySelectorAll('input[name="' + name + '[]"]').forEach(function(cb) {
      cb.checked = selected.includes(cb.value);
    });
  });

  // Selects: sort, register, domain, etymology, modern, dict_min, attested_after, attested_before, marks
  ['sort', 'register', 'domain', 'etymology', 'modern', 'dict_min', 'attested_after', 'attested_before', 'marks'].forEach(function(name) {
    var val = params.get(name);
    if (val === null) return;
    var el = form.querySelector('select[name=' + name + ']');
    if (el) el.value = val;
  });

  // Explore: number inputs (the zipf pair went with the dead wordfreq filter)
  ['dexfreq_min', 'dexfreq_max'].forEach(function(name) {
    var val = params.get(name);
    if (val === null) return;
    var el = form.querySelector('input[name=' + name + ']');
    if (el) el.value = val;
  });

  // Explore: checkboxes. Only ever subtract, so "unchecked submits nothing" is exactly
  // the state they mean — the classes that need a default-on state are radios above.
  [].forEach(function(name) {
    var val = params.get(name);
    if (val === null) return;
    var el = form.querySelector('input[name=' + name + ']');
    if (el) el.checked = (val === '1');
  });

  // Word profile param, and the filters it has to relax to bring its own row with it.
  //
  // A share is one word arriving on top of the site, and until now it arrived *without*
  // its row: 15,803 of the 18,270 words are outside the default view, so closing the
  // panel on a shared `curiosity` word left the reader on a list that did not contain it,
  // with the rail naming filters they never set as the reason. OTIOS_SHARE_RELAX is the
  // server's answer to "which of these defaults is hiding this particular word" —
  // share_relax_params() in _lib.php, computed from the same table build_word_filter()
  // filters on, so the two cannot drift.
  //
  // **An explicit param in the URL always wins**, including a superseded spelling that
  // already landed on the control above (the `alias_*` flags) — a link shared *with*
  // filters on it shared the filters too, and quietly widening those would be the same
  // class of bug in the other direction. This block therefore runs last of the three.
  //
  // Being in the list is only half of it: with the seam relaxed a `curiosity` word still
  // ranks thousands of rows down, so it is also pinned to the top for this one request.
  // That half is the hidden #share-word input — which posts as `pin`, never as `word`:
  // the rows inherit this form through hx-include and carry their own `word` in the URL,
  // and a second empty one appended to it is what PHP would keep. See pin_order_sql().
  var wordParam = params.get('word');
  if (wordParam) {
    openWord = wordParam;
    var pin = document.getElementById('share-word');
    if (pin) pin.value = wordParam;

    var relax = (typeof OTIOS_SHARE_RELAX !== 'undefined' && OTIOS_SHARE_RELAX) || {};
    Object.keys(relax).forEach(function(name) {
      if (params.get(name) !== null || form.dataset['alias_' + name]) return;
      if (name === 'seam') {
        // A checkbox group: the word's seam is added beside `relevant`, never swapped
        // for it. Arriving at one curiosity word is not a reason to take the default
        // list away from the reader.
        var want = relax[name].split(',');
        form.querySelectorAll('input[name="seam[]"]').forEach(function(cb) {
          if (want.indexOf(cb.value) !== -1) cb.checked = true;
        });
      } else {
        form.querySelectorAll('input[name=' + name + ']').forEach(function(r) {
          r.checked = (r.value === relax[name]);
        });
      }
    });
  }

  // Playlist param. Set synchronously — htmx fires the first search on load, and the
  // hidden input has to be populated before it does.
  var packedParam = params.get('w');
  if (packedParam) {
    var pkInput = document.getElementById('playlist-w');
    if (pkInput) pkInput.value = packedParam;
    // One segment is the version prefix; the rest are words.
    showPlaylistBanner(Math.max(0, packedParam.split('.').filter(Boolean).length - 1));
  } else {
    var wordsParam = params.get('words');
    if (wordsParam) {
      var pwInput = document.getElementById('playlist-words');
      if (pwInput) pwInput.value = wordsParam;
      showPlaylistBanner(wordsParam.split(',').filter(Boolean).length);
    }
  }
}

function syncUrlFromForm() {
  var form = document.getElementById('filter-form');
  if (!form) return;
  var params = new URLSearchParams();

  // 'word' always comes first, when present — keeps shared word links clean
  if (openWord) params.set('word', openWord);

  // Text input
  var q = form.querySelector('input[name=q]');
  if (q && q.value.trim()) params.set('q', q.value.trim());

  // Radio groups
  ['has_def'].concat(CLASS_PARAMS).forEach(function(name) {
    var el = form.querySelector('input[name=' + name + ']:checked');
    var val = el ? el.value : '';
    if (val && val !== (URL_PARAM_DEFAULTS[name] || '')) params.set(name, val);
  });

  // Checkbox groups: written only when the selection differs from the group's default.
  ['verdict', 'tier', 'pos', 'seam'].forEach(function(name) {
    var all  = Array.from(form.querySelectorAll('input[name="' + name + '[]"]'));
    var chkd = all.filter(function(cb) { return cb.checked; });
    if (chkd.length > 0 && !groupIsDefault(form, name)) {
      params.set(name, chkd.map(function(cb) { return cb.value; }).join(','));
    }
  });

  // Selects — this array is the write half; its twin is in applyUrlToForm(). A name
  // missing from one direction filters the grid without ever reaching the URL, or the
  // reverse, and neither shows up as an error.
  ['sort', 'register', 'domain', 'etymology', 'modern', 'dict_min', 'attested_after', 'attested_before', 'marks'].forEach(function(name) {
    var el = form.querySelector('select[name=' + name + ']');
    if (!el) return;
    var val = el.value;
    if (val && val !== (URL_PARAM_DEFAULTS[name] || '')) params.set(name, val);
  });

  // Explore: number inputs
  ['dexfreq_min', 'dexfreq_max'].forEach(function(name) {
    var el = form.querySelector('input[name=' + name + ']');
    if (el && el.value.trim()) params.set(name, el.value.trim());
  });

  // Preserve playlist — the compact form when there is one, else a legacy plaintext
  // playlist still open in this tab.
  var pkInput = document.getElementById('playlist-w');
  var pwInput = document.getElementById('playlist-words');
  if (pkInput && pkInput.value.trim())      params.set('w', pkInput.value.trim());
  else if (pwInput && pwInput.value.trim()) params.set('words', pwInput.value.trim());

  var qs = params.toString();
  history.replaceState(null, '', location.pathname + (qs ? '?' + qs : ''));
}

// Reset: re-fire HTMX search and clear URL after the browser resets form values
document.getElementById('filter-form') && document.getElementById('filter-form').addEventListener('reset', function() {
  setTimeout(function() {
    var form = document.getElementById('filter-form');
    if (form) form.dispatchEvent(new Event('change', { bubbles: true }));
    syncUrlFromForm();
    syncSearchMode();          // reset clears the query box, so it also ends search mode
    renderActiveFilters();
    closeSearchIfEmpty();
  }, 0);
});

// The sheet has to follow the box on every keystroke, not on `change` — the input fires
// htmx on `input changed delay:200ms` and `change` only lands on blur, which would leave
// the filters looking live for the whole time someone is typing and reading results.
document.getElementById('search') &&
  document.getElementById('search').addEventListener('input', syncSearchMode);

// Apply URL params to form before HTMX fires its initial load request
applyUrlToForm();

// A query already in the URL means search is already in use — leave the box
// open rather than collapsing an active search behind the magnifier.
if (document.getElementById('search') && document.getElementById('search').value.trim() !== '') {
  openSearch(false);
}
syncSearchMode();

// Rehydrate open word from URL on page load — definition takes the spotlight.
// A reload is not a share: refreshing drops the word instead of re-opening the
// panel, so you land back on the plain list. Following a ?word=… link still opens it.
(function() {
  var w = new URLSearchParams(location.search).get('word');
  if (!w) return;

  var nav = (performance.getEntriesByType && performance.getEntriesByType('navigation')[0]) || null;
  var isReload = nav ? nav.type === 'reload'
                     : (performance.navigation && performance.navigation.type === 1);
  if (isReload) {
    openWord = null;              // stop syncUrlFromForm() from writing it back
    var pin = document.getElementById('share-word');
    if (pin) pin.value = '';      // and with it the pin, for the same reason as closePanel()
    syncUrlFromForm();            // drop ?word=… from the address bar
    return;
  }

  arrivedViaShare = true;

  // index.php already server-rendered this word into #detail-panel (panel-open plus a
  // real <h1>) when the request itself was a `?word=` hit — the ordinary case for
  // following a share link. Activate that in place rather than re-fetching
  // api/word.php and replacing it: that endpoint always renders the <div> fragment
  // (api/word.php never sets detail.php's $ssr flag), so re-swapping here would erase
  // the SSR'd <h1> the instant this script runs, including in Google's own renderer,
  // which executes page JS before indexing the DOM. `wordEl` is the same
  // `[data-word]` lookup activateDetailPanel() itself uses to confirm the rendered
  // panel is actually this word, not a stale one from a different `?word=` request.
  var panel = document.getElementById('detail-panel');
  var wordEl = panel && panel.classList.contains('panel-open') && panel.querySelector('[data-word]');
  if (wordEl && wordEl.dataset.word === w) {
    activateDetailPanel(panel);
    return;
  }

  var base = (typeof OTIOS_BASE !== 'undefined' ? OTIOS_BASE : '');
  htmx.ajax('GET', base + '/api/word.php?word=' + encodeURIComponent(w), { target: '#detail-panel', swap: 'innerHTML' });
})();

// Keep URL in sync with every HTMX search request
document.addEventListener('htmx:configRequest', function(e) {
  var url = e.detail.path || '';
  var base = (typeof OTIOS_BASE !== 'undefined' ? OTIOS_BASE : '');
  if (!url.startsWith(base + '/api/search.php')) return;
  syncUrlFromForm();
});

// ── Word lists ──────────────────────────────────────────────────────────────────
//
// The collections themselves live on liste.php — the three buckets (fav / lol / meh),
// each card carrying whatever has been published from it. All this page needs is the
// fav bucket, for the status-bar share button.

function bookmarkedWords() {
  const r = getResearch();
  return Object.keys(r.words).filter(function(w) { return r.words[w].bookmarked; });
}

// ── Init ────────────────────────────────────────────────────────────────────────

updateBookmarkCount();
populateTagDatalist();
populateTagFilterOptions();
renderActiveFilters();

// store.js fires this after a sync pulled changes made on another device.
document.addEventListener('otios:synced', function() {
  hydrateRows();
  if (openWord) hydrateDetail();
  updateBookmarkCount();
  populateTagDatalist();
  populateTagFilterOptions();
});

// ── Mobile Auto-Close on Scroll ─────────────────────────────────────────────────

(function() {
  let mobileTouchStartY = 0;
  
  // Track where a swipe begins
  document.addEventListener('touchstart', function(e) {
    if (e.touches.length > 0) {
      mobileTouchStartY = e.touches[0].clientY;
    }
  }, { passive: true });

  // Check if they swipe significantly
  document.addEventListener('touchmove', function(e) {
    if (window.innerWidth > 768 || e.touches.length === 0) return;
    
    const panel = document.getElementById('detail-panel');
    if (!panel || !panel.classList.contains('panel-open')) return;

    // Do NOT close if they are scrolling INSIDE the definition drawer itself
    if (panel.contains(e.target)) return;

    const touchY = e.touches[0].clientY;
    // If they drag up or down by 15px in the word list, close it
    if (Math.abs(touchY - mobileTouchStartY) > 15) {
      closePanel();
      
      // Visually remove the dark highlight from the word
      const selected = document.querySelector('.word-row[data-selected]');
      if (selected) selected.removeAttribute('data-selected');
    }
  }, { passive: true });
})();