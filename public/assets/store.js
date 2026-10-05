// ── Shared research store + server sync ───────────────────────────────────────
//
// Loaded by both index.php and joc.php. Previously each page carried its own copy
// of this logic (app.js and an inline block in joc.php), writing to the same
// localStorage key from two implementations.
//
// Writes stay local-first: every change lands in localStorage immediately so the UI
// is instant and keeps working offline, then the touched words are queued and pushed
// to the server. A failed push stays queued and retries on the next change or page
// load, so a server outage costs nothing but freshness.

var STORE_KEY = 'otios.research';   // { version, words: { word: {bookmarked, note, tags, updated_at} } }
var QUEUE_KEY = 'otios.pending';    // { word: { rev, ts, rejected? } }  (legacy: { word: "<iso8601>" })
var SYNC_KEY  = 'otios.sync';       // { since: <server seq>, migrated }
var REV_KEY   = 'otios.rev';        // last local revision handed out (never reused)

// Largest batch one request carries. The server reads at most 5,000 changes per call
// (SYNC_PAGE in api/sync.php); staying lower keeps request bodies small.
var SYNC_BATCH = 1000;

var syncInFlight = false;
var syncTimer    = null;

function nowIso() { return new Date().toISOString(); }

function readJson(key, fallback) {
  try {
    var raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) || fallback) : fallback;
  } catch (_) { return fallback; }
}

function writeJson(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
}

// ── Local store ───────────────────────────────────────────────────────────────

function getResearch() {
  var obj = readJson(STORE_KEY, null);
  if (obj && obj.version === 1) return obj;
  return { version: 1, words: {} };
}

function saveResearch(obj) { writeJson(STORE_KEY, obj); }

function getWord(word) {
  return getResearch().words[word] || { bookmarked: false, note: '', tags: [] };
}

// A change must carry an updated_at later than anything already queued or stored for
// the word. The server keeps a row only when excluded.updated_at > stored.updated_at,
// so two edits in one millisecond would otherwise tie and the second would be dropped.
function nextTimestamp(word, prevUpdatedAt) {
  var ts = nowIso();
  var q = getQueue();
  var floor = prevUpdatedAt || '';
  if (q[word] && q[word].ts > floor) floor = q[word].ts;
  if (floor && ts <= floor) ts = new Date(Date.parse(floor) + 1).toISOString();
  return ts;
}

function updateWord(word, patch) {
  var r = getResearch();
  var prev = r.words[word] || { bookmarked: false, note: '', tags: [] };
  var ts = nextTimestamp(word, prev.updated_at);
  var next = Object.assign({}, prev, patch, { updated_at: ts });
  // prune empty entries
  if (!next.bookmarked && !next.note && (!next.tags || next.tags.length === 0)) {
    delete r.words[word];
  } else {
    r.words[word] = next;
  }
  saveResearch(r);
  markDirty(word, ts);   // for a pruned word, ts is the tombstone's time
}

// ── Word-detail panel ────────────────────────────────────────────────────────────
//
// The panel markup (public/api/_partials/detail.php) and the annotation-editing
// behaviour are identical on index.php (sliding #detail-panel) and joc.php (a modal)
// — only the container differs, so nothing here hardcodes an id. Both containers
// carry the '.word-detail-panel' class instead, and handlers look up the nearest one
// from the click/keydown target.

var QUICK_TAG_EMOJIS = { ascunde: '⚠️', lol: '🤣', meh: '⛔️' };
var QUICK_TAG_KEYS   = Object.keys(QUICK_TAG_EMOJIS);
var QT_EXPLAINER_KEY = 'otios.qtExplainerDismissed';

function qtKeyToTag(key) {
  var map = { a: 'ascunde', l: 'lol', m: 'meh' };
  return map[key] || null;
}

function qtExplainerDismissed() {
  try { return localStorage.getItem(QT_EXPLAINER_KEY) === '1'; } catch (_) { return false; }
}

// Dismissal is held by a class on <html>, with CSS doing the hiding — not by an inline
// style written after each render.
//
// The inline version looked correct and failed in one specific way: the detail panel is
// re-rendered when you open the next word, and the fresh #qt-explainer arrives with no
// inline style, so the banner came back on every word even though localStorage said
// dismissed. (Verified: hydrateDetail did set display:none, and the computed style was
// `flex` a moment later with the inline value gone — a different element.) A root class
// cannot be lost that way, because it is not on the element being replaced.
function applyQtExplainerState() {
  if (typeof document === 'undefined' || !document.documentElement) return;
  document.documentElement.classList.toggle('qt-dismissed', qtExplainerDismissed());
}

function dismissQtExplainer() {
  try { localStorage.setItem(QT_EXPLAINER_KEY, '1'); } catch (_) {}
  applyQtExplainerState();
}

applyQtExplainerState();

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function hydrateDetail(root) {
  var panel = root || document.querySelector('.word-detail-panel');
  if (!panel) return;

  var noteEl = panel.querySelector('#note-input');
  var bookEl = panel.querySelector('#bookmark-btn');
  var tagsEl = panel.querySelector('#tags-row');
  if (!noteEl && !bookEl) return;

  var word = (noteEl || bookEl).dataset.word;
  if (!word) return;
  var state = getWord(word);

  // `.active` is the visible half and `aria-pressed` the spoken one. Both are needed:
  // these are toggles — pressing an applied tag removes it — and a state said only in
  // colour is no state at all to a screen reader, or to anyone who cannot separate the
  // two hues a given skin picked.
  if (bookEl) {
    bookEl.classList.toggle('active', !!state.bookmarked);
    bookEl.setAttribute('aria-pressed', state.bookmarked ? 'true' : 'false');
  }

  if (noteEl) noteEl.value = state.note || '';

  if (tagsEl) {
    tagsEl.querySelectorAll('.qt-btn[data-qtkey]').forEach(function(btn) {
      var tag = qtKeyToTag(btn.dataset.qtkey);
      if (!tag) return;
      var on = (state.tags || []).includes(tag);
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });

    tagsEl.querySelectorAll('.custom-tag').forEach(function(el) { el.remove(); });
    (state.tags || []).filter(function(t) { return !QUICK_TAG_KEYS.includes(t); }).forEach(function(t) {
      var span = document.createElement('span');
      span.className = 'tag custom-tag';
      span.innerHTML = escHtml(t) + ' <button class="tag-delete" data-tag="' + escHtml(t) + '" data-word="' + escHtml(word) + '">×</button>';
      tagsEl.appendChild(span);
    });
  }

  // The explainer's visibility is CSS, keyed on `.qt-dismissed` on <html> — see
  // applyQtExplainerState(). Nothing to do per render.
}

function closeDictTooltips() {
  document.querySelectorAll('.dict-tooltip:not([hidden])').forEach(function(t) { t.setAttribute('hidden', ''); });
  document.querySelectorAll('.fp-dicts-toggle[aria-expanded="true"]').forEach(function(b) { b.setAttribute('aria-expanded', 'false'); });
}

// Delegated on document.body so it works no matter how the panel HTML was inserted
// (htmx swap on index.php, plain fetch+innerHTML on joc.php). Guarded on
// `document.body` because this file also runs inside a Node `vm` stub in
// tests/test_store_sync.js, whose fake `document` has no `body`.
if (typeof document !== 'undefined' && document.body) {
  document.body.addEventListener('click', function(e) {
    var explainerClose = e.target.closest('#qt-explainer-close');
    if (explainerClose) {
      e.preventDefault();
      dismissQtExplainer();
      return;
    }

    var bookBtn = e.target.closest('#bookmark-btn');
    if (bookBtn) {
      e.preventDefault();
      var bWord = bookBtn.dataset.word;
      if (!bWord) return;
      var bState = getWord(bWord);
      var nowFav = !bState.bookmarked;
      updateWord(bWord, { bookmarked: nowFav });
      hydrateDetail(e.target.closest('.word-detail-panel'));
      if (typeof hydrateRows === 'function') hydrateRows(document.getElementById('word-list'));
      if (typeof updateBookmarkCount === 'function') updateBookmarkCount();
      // Marking moves you on (see advanceAfterMark in app.js). Un-favouriting does
      // not: that is a correction, and advancing would take you off the word you
      // just came back to fix. The row survives a fav, hence removesRow = false.
      if (nowFav && typeof advanceAfterMark === 'function') advanceAfterMark(bWord, false);
      return;
    }

    var qtBtn = e.target.closest('.qt-btn[data-qtkey]');
    if (qtBtn) {
      e.preventDefault();
      var tagsRow = qtBtn.closest('#tags-row');
      var qWord = tagsRow ? tagsRow.dataset.word : null;
      if (!qWord) return;
      var tag = qtKeyToTag(qtBtn.dataset.qtkey);
      if (!tag) return;
      var qState    = getWord(qWord);
      var qTags     = qState.tags || [];
      var wasTagged = qTags.includes(tag);
      var next      = wasTagged ? qTags.filter(function(t) { return t !== tag; }) : qTags.concat([tag]);
      updateWord(qWord, { tags: next });
      hydrateDetail(e.target.closest('.word-detail-panel'));
      if (typeof hydrateRows === 'function') hydrateRows(document.getElementById('word-list'));
      // Applying any quick tag moves you on to the next word; removing one does not
      // (see advanceAfterMark in app.js). `ascunde`/`meh` additionally pop the row
      // out of the grid instead of waiting for a re-search — that is what the second
      // argument says. `advanceAfterMark` is index-only; joc.php loads this file
      // without it and only ever needs the fade, hence the fallback.
      var hides = (tag === 'ascunde' || tag === 'meh');
      if (!wasTagged) {
        if (typeof advanceAfterMark === 'function')         advanceAfterMark(qWord, hides);
        else if (hides && typeof fadeOutRow === 'function') fadeOutRow(qWord);
      }
      return;
    }

    var delBtn = e.target.closest('.tag-delete');
    if (delBtn) {
      e.preventDefault();
      var dWord = delBtn.dataset.word;
      var dTag  = delBtn.dataset.tag;
      if (!dWord || !dTag) return;
      var dState = getWord(dWord);
      updateWord(dWord, { tags: (dState.tags || []).filter(function(t) { return t !== dTag; }) });
      hydrateDetail(e.target.closest('.word-detail-panel'));
      if (typeof hydrateRows === 'function') hydrateRows(document.getElementById('word-list'));
      if (typeof populateTagDatalist === 'function') populateTagDatalist();
      if (typeof populateTagFilterOptions === 'function') populateTagFilterOptions();
      return;
    }

    // Dictionary-name tooltip — the label doubles as its own toggle button so
    // the names stop printing straight into the panel body (see .fp-dicts in
    // detail.php). Closes any other open one first: only one at a time.
    var dictToggle = e.target.closest('.fp-dicts-toggle');
    if (dictToggle) {
      e.preventDefault();
      // document.querySelector, not dictToggle.parentElement.querySelector: the first
      // open reparents the tooltip to <body> (see below), so it stops being a sibling
      // of the toggle from then on. There is only ever one .dict-tooltip live in the
      // document at a time, so a global lookup is unambiguous either way.
      var dictTip = document.querySelector('.dict-tooltip');
      if (!dictTip) return;
      var willOpen = dictTip.hasAttribute('hidden');
      closeDictTooltips();
      if (willOpen) {
        // #detail-panel carries `transform: translateX(-50%)` on desktop to centre
        // itself (see app.css) — and a transformed ancestor becomes the *containing
        // block* for a `position: fixed` descendant, so .dict-tooltip's fixed
        // positioning was being resolved against the panel's own box instead of the
        // true viewport. The top/left computed below are correct viewport
        // coordinates either way; only the containing block was wrong. Moving the
        // tooltip out to <body> (untransformed) before positioning it is the fix —
        // recomputing the panel's own layout to avoid the transform would still leave
        // any *other* transformed ancestor able to reintroduce this later.
        if (dictTip.parentElement !== document.body) document.body.appendChild(dictTip);
        dictTip.removeAttribute('hidden');
        dictToggle.setAttribute('aria-expanded', 'true');
        // Fixed positioning has nothing to anchor to on its own — place it
        // under the toggle, clamped so it can't run past the viewport edge.
        var rect = dictToggle.getBoundingClientRect();
        var maxLeft = window.innerWidth - dictTip.offsetWidth - 8;
        dictTip.style.top = Math.round(rect.bottom + 4) + 'px';
        dictTip.style.left = Math.round(Math.max(8, Math.min(rect.left, maxLeft))) + 'px';
      }
      return;
    }
    if (!e.target.closest('.dict-tooltip')) closeDictTooltips();
  });

  // A stale-positioned tooltip left open through a scroll is worse than none —
  // 'scroll' doesn't bubble, so this has to be a capturing listener on document
  // to catch it from `.fp-body` (the panel's own scrolling region).
  document.addEventListener('scroll', closeDictTooltips, true);

  // Tag input — add custom tag on Enter
  document.body.addEventListener('keydown', function(e) {
    var input = e.target.closest('#tag-input');
    if (!input || e.key !== 'Enter') return;
    e.preventDefault();
    var val = input.value.trim();
    if (!val) return;
    var tagsRow = input.closest('#tags-row');
    var word = tagsRow ? tagsRow.dataset.word : null;
    if (!word) return;
    var state = getWord(word);
    var tags  = state.tags || [];
    if (!tags.includes(val)) {
      updateWord(word, { tags: tags.concat([val]) });
      hydrateDetail(e.target.closest('.word-detail-panel'));
      if (typeof hydrateRows === 'function') hydrateRows(document.getElementById('word-list'));
      if (typeof populateTagDatalist === 'function') populateTagDatalist();
      if (typeof populateTagFilterOptions === 'function') populateTagFilterOptions();
    }
    input.value = '';
  }, true);

  // Note — save on Enter
  document.body.addEventListener('keydown', function(e) {
    var textarea = e.target.closest('#note-input');
    if (!textarea || e.key !== 'Enter') return;
    e.preventDefault();
    var word = textarea.dataset.word;
    if (!word) return;
    updateWord(word, { note: textarea.value });
    var status = document.getElementById('note-status');
    if (status) {
      status.innerHTML = '<span class="saved-notice">saved</span>';
      status.style.display = '';
    }
    if (typeof hydrateRows === 'function') hydrateRows(document.getElementById('word-list'));
  }, true);
}

// ── Outbound queue ────────────────────────────────────────────────────────────
//
// The queue holds one entry per touched word: { rev, ts, rejected? }. The payload is
// rebuilt from current local state at push time, so repeated edits to one word collapse
// into a single change and a replayed push is idempotent.
//
// `rev` is a local revision number from one counter that only grows (REV_KEY). Every
// edit gets a new rev. A push remembers the rev it sent for each word, and the reply may
// clear a word only when the server acknowledged that rev AND the queue still holds the
// same rev. An edit made during the request has a newer rev, so it stays queued.
// `ts` is the change's updated_at; for a deleted word it is the tombstone's time.
// `rejected` ('invalid' | 'quota') marks a word the server refused for good: its data
// stays local and the entry is not pushed again until the word is edited.
// Protocol and compatibility: docs/sync-protocol.md.

function nextRev(floor) {
  var n = Number(readJson(REV_KEY, 0)) || 0;
  if (floor && floor > n) n = floor;
  n += 1;
  writeJson(REV_KEY, n);
  return n;
}

function getQueue() {
  var raw = readJson(QUEUE_KEY, {}) || {};
  var q = {};
  Object.keys(raw).forEach(function (w) {
    var e = raw[w];
    if (typeof e === 'string') q[w] = { rev: 0, ts: e };        // legacy entry: rev 0 is older than any new edit
    else if (e && typeof e === 'object') q[w] = e;
  });
  return q;
}
function saveQueue(q) { writeJson(QUEUE_KEY, q); }

function markDirty(word, ts) {
  var q = getQueue();
  q[word] = { rev: nextRev(q[word] && q[word].rev), ts: ts || nowIso() };
  saveQueue(q);
  scheduleSync();
}

// Words that still need a push, oldest revision first.
function pendingWords(q) {
  return Object.keys(q).filter(function (w) { return !q[w].rejected; }).sort(function (a, b) {
    return (q[a].rev - q[b].rev) || (a < b ? -1 : a > b ? 1 : 0);
  });
}

function getRejected() {
  var q = getQueue(), out = {};
  Object.keys(q).forEach(function (w) { if (q[w].rejected) out[w] = q[w].rejected; });
  return out;
}

// The visible signal: a count on <html> that a skin or the page can show, plus an event.
function updateRejectedSignal(announce) {
  var rejected = Object.keys(getRejected());
  if (typeof document !== 'undefined' && document.documentElement) {
    if (rejected.length) document.documentElement.setAttribute('data-sync-rejected', String(rejected.length));
    else document.documentElement.removeAttribute('data-sync-rejected');
  }
  if (announce && rejected.length && typeof document !== 'undefined') {
    document.dispatchEvent(new CustomEvent('otios:sync-rejected', { detail: { words: rejected } }));
  }
}

function getSyncState() { return readJson(SYNC_KEY, {}) || {}; }
function saveSyncState(s) { writeJson(SYNC_KEY, s); }

// One-time push of whatever a returning user already had in localStorage before
// server storage existed. Marks every stored word dirty; the normal sync path does
// the rest, and last-write-wins keeps it safe to run against existing server data.
function migrateLocalStore() {
  var state = getSyncState();
  if (state.migrated) return;

  var words = getResearch().words;
  var q = getQueue();
  Object.keys(words).forEach(function (w) {
    if (!q[w]) q[w] = { rev: nextRev(), ts: words[w].updated_at || nowIso() };
  });
  saveQueue(q);

  state.migrated = true;
  saveSyncState(state);
}

// ── Sync ──────────────────────────────────────────────────────────────────────

function buildChanges(queue, words) {
  var local = getResearch().words;
  return (words || Object.keys(queue)).map(function (w) {
    var e = local[w];
    if (!e) {
      // Pruned locally (unbookmarked, note cleared, tags removed) — send a tombstone
      // so the deletion reaches the user's other devices instead of being resurrected.
      return { word: w, rev: queue[w].rev, bookmarked: false, note: '', tags: [], updated_at: queue[w].ts, deleted: true };
    }
    return {
      word:       w,
      rev:        queue[w].rev,
      bookmarked: !!e.bookmarked,
      note:       e.note || '',
      tags:       e.tags || [],
      updated_at: e.updated_at || queue[w].ts,
      deleted:    false
    };
  });
}

function applyRemote(changes, queueBefore) {
  if (!changes || !changes.length) return false;
  var r = getResearch();
  var q = queueBefore || getQueue();
  var touched = false;

  changes.forEach(function (c) {
    var local = r.words[c.word];
    // Local edit is newer — keep it; our own copy will win on the next push.
    if (local && local.updated_at && local.updated_at >= c.updated_at) return;
    // A queued local delete has no row to compare against, so compare with the queued
    // tombstone's time. Without this an older remote copy would bring the word back.
    if (!local && q[c.word] && q[c.word].ts >= c.updated_at) return;

    if (c.deleted) {
      if (local) { delete r.words[c.word]; touched = true; }
      return;
    }
    r.words[c.word] = {
      bookmarked: !!c.bookmarked,
      note:       c.note || '',
      tags:       c.tags || [],
      updated_at: c.updated_at
    };
    touched = true;
  });

  if (touched) saveResearch(r);   // deliberately not markDirty — this came from the server
  return touched;
}

function scheduleSync(delay) {
  if (syncTimer) clearTimeout(syncTimer);
  syncTimer = setTimeout(function () { syncNow(); }, delay == null ? 1500 : delay);
}

// Work out what the server said about each change we sent. Returns { word: status }
// where status is stored | current | invalid | quota | unacked.
function ackStatuses(data, sent) {
  var res = {};
  if (Array.isArray(data.outcomes)) {
    Object.keys(sent).forEach(function (w) { res[w] = 'unacked'; });
    data.outcomes.forEach(function (o) {
      if (!o || typeof o.word !== 'string' || !(o.word in sent) || o.rev !== sent[o.word]) return;
      res[o.word] = (o.status === 'stored' || o.status === 'current' || o.status === 'invalid' || o.status === 'quota')
        ? o.status : 'unacked';
    });
  } else {
    // Old server: no per-change outcomes. `rejected: 0` means it took every change in
    // the request (it also read at most 5,000, and we send fewer). Anything else cannot
    // be attributed to a word, so nothing is acknowledged.
    Object.keys(sent).forEach(function (w) { res[w] = data.rejected === 0 ? 'stored' : 'unacked'; });
  }
  return res;
}

function syncNow() {
  if (syncInFlight) return Promise.resolve(false);
  var base = (typeof OTIOS_BASE !== 'undefined' ? OTIOS_BASE : '');

  var queue = getQueue();
  var batch = pendingWords(queue).slice(0, SYNC_BATCH);
  var sent  = {};                       // word -> rev that this request carries
  batch.forEach(function (w) { sent[w] = queue[w].rev; });
  var state = getSyncState();

  syncInFlight = true;
  return fetch(base + '/api/sync.php', {
    method:      'POST',
    credentials: 'same-origin',
    headers:     { 'Content-Type': 'application/json' },
    body:        JSON.stringify({ since: state.since || 0, changes: buildChanges(queue, batch) })
  })
    .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('sync ' + r.status)); })
    .then(function (data) {
      // Check the reply before touching any state: a bad reply must change nothing.
      if (!data || typeof data !== 'object' || !Array.isArray(data.changes) ||
          typeof data.server_seq !== 'number' || !isFinite(data.server_seq)) {
        throw new Error('sync: malformed reply');
      }

      // Clear a word only when its sent revision was acknowledged and is still the
      // current one. A newer revision (an edit during the request) stays queued.
      var status = ackStatuses(data, sent);
      var q = getQueue();
      var queueBefore = JSON.parse(JSON.stringify(q));
      var progress = false, newlyRejected = false;
      Object.keys(sent).forEach(function (w) {
        var st = status[w];
        if (!q[w] || q[w].rev !== sent[w]) return;
        if (st === 'stored' || st === 'current') { delete q[w]; progress = true; }
        else if (st === 'invalid' || st === 'quota') { q[w].rejected = st; progress = true; newlyRejected = true; }
      });
      saveQueue(q);
      if (newlyRejected) updateRejectedSignal(true);

      var changed = applyRemote(data.changes, queueBefore);
      var s = getSyncState();
      var moved = data.server_seq !== (s.since || 0);
      s.since = data.server_seq;
      saveSyncState(s);

      if (changed) {
        document.dispatchEvent(new CustomEvent('otios:synced', { detail: { changed: true } }));
      }
      // Next batch: more of our own changes, or more server rows. Only when this round
      // made progress, so a server that acknowledges nothing cannot start a loop.
      var morePush = pendingWords(getQueue()).length > 0 && progress;
      var morePull = !!data.has_more && (data.changes.length > 0 || moved);
      if (morePush || morePull) scheduleSync(200);
      return changed;
    })
    .catch(function () { return false; })   // stay queued, retry on next change or load
    .then(function (result) { syncInFlight = false; return result; });
}

function otiosMe() {
  var base = (typeof OTIOS_BASE !== 'undefined' ? OTIOS_BASE : '');
  return fetch(base + '/api/me.php', { credentials: 'same-origin' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () { return null; });
}

// Push anything still queued when the page goes away (tab close, navigation).
document.addEventListener('visibilitychange', function () {
  if (document.visibilityState === 'hidden' && pendingWords(getQueue()).length) syncNow();
});

migrateLocalStore();
updateRejectedSignal(false);
scheduleSync(300);
