// Stage 0 spot-check marker (F09). Paste this whole file into the browser console
// (DevTools > Console) on the playlist page, once per page load. It changes nothing on disk.
//
// The detail panel has no free-text tag box since the quick-tags redesign, so this adds
// the marks as keys. Open a word, then press:
//   1 = sc-bun    2 = sc-meh    3 = sc-slab    0 = clear the mark
//   q = unsure: press q BEFORE the mark, for the next mark only (q then 1 = sc-bun-q)
// After 1, 2 or 3 the page moves to the next word, so q must come first. The tag is a normal custom tag, so it
// syncs to app.db like any other. It does not touch fav/lol/meh.
// Read the result with: python3 tools/eval_spotcheck.py --from-appdb
(function () {
  if (window.__scMarker) { console.log('spot-check marker already active'); return; }
  window.__scMarker = true;
  var KEYS = { '1': 'sc-bun', '2': 'sc-meh', '3': 'sc-slab' };
  var SC = /^sc-(bun|meh|slab)(-q)?$/;
  var badge = document.createElement('div');
  badge.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:99999;padding:6px 10px;' +
    'background:#222;color:#fff;font:14px/1.3 monospace;border-radius:4px;opacity:.92';
  badge.textContent = 'spot-check keys: 1 bun, 2 meh, 3 slab, 0 clear, q unsure';
  document.body.appendChild(badge);

  var unsureNext = false;
  function currentWord() {
    var row = document.querySelector('#detail-panel #tags-row, #tags-row');
    return row ? row.dataset.word : null;
  }
  function setMark(word, base, unsure) {
    var keep = (getWord(word).tags || []).filter(function (t) { return !SC.test(t); });
    var tags = base ? keep.concat([base + (unsure ? '-q' : '')]) : keep;
    updateWord(word, { tags: tags });
    badge.textContent = word + ': ' + (base ? base + (unsure ? '-q' : '') : '(cleared)');
  }
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (/^(INPUT|TEXTAREA|SELECT)$/.test((e.target.tagName || ''))) return;
    var k = e.key;
    if (!(k in KEYS) && k !== '0' && k !== 'q') return;
    var word = currentWord();
    if (!word) { badge.textContent = 'open a word first'; return; }
    e.preventDefault(); e.stopImmediatePropagation();
    if (k === 'q') {
      unsureNext = !unsureNext;
      badge.textContent = unsureNext ? 'unsure: the next mark gets -q' : 'unsure off';
      return;
    }
    if (k === '0') { setMark(word, null, false); return; }
    setMark(word, KEYS[k], unsureNext);
    unsureNext = false;
    if (typeof advanceAfterMark === 'function') advanceAfterMark(word, false);
  }, true);
  console.log('spot-check marker ready: 1 bun, 2 meh, 3 slab, 0 clear, q unsure');
})();
