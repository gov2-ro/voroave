// Sinonime — progressive enhancement only. The page (sinonime.php) is complete without
// this: every node is a real <a href>, the list is server-rendered, search and recentre
// both work as plain navigation/form submits. This file adds three things on top:
//   1. hover cross-highlighting between a graph node and its list row
//   2. a hover card off the #syn-data JSON island (no extra request)
//   3. mouseenter prefetch of the word a node/row link points to
//
// Layout itself is never recomputed here -- the geometry lives in PHP (_syn.php's
// syn_layout()) and staying there is what keeps the graph deterministic and testable.
// See docs/sinonime/ui.md § Markup, accessibility, and what works without JavaScript.
(function () {
  'use strict';

  var prefetched = Object.create(null);

  function prefetch(word) {
    if (!word || prefetched[word]) return;
    prefetched[word] = true;
    var url = (window.OTIOS_BASE || '') + '/api/syn.php?q=' + encodeURIComponent(word);
    fetch(url, { credentials: 'omit' }).catch(function () {});
  }

  function readSenses() {
    var el = document.getElementById('syn-data');
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function findMember(data, word) {
    if (!data) return null;
    for (var i = 0; i < data.senses.length; i++) {
      var members = data.senses[i].members;
      for (var j = 0; j < members.length; j++) {
        if (members[j].form === word) return members[j];
      }
    }
    return null;
  }

  function setActive(word, on) {
    document.querySelectorAll('[data-word="' + cssEscape(word) + '"]').forEach(function (el) {
      el.classList.toggle('is-active', on);
    });
  }

  function cssEscape(s) {
    return window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/["\\]/g, '\\$&');
  }

  var card = null;
  function showCard(word, x, y, data) {
    var member = findMember(data, word);
    if (!member || !member.ring2 || !member.ring2.length) return;
    if (!card) {
      card = document.createElement('div');
      card.className = 'syn-hover-card';
      document.body.appendChild(card);
    }
    var html = '<strong>' + escapeHtml(word) + '</strong><ul>';
    member.ring2.slice(0, 4).forEach(function (c) {
      html += '<li>' + escapeHtml(c.form) + '</li>';
    });
    card.innerHTML = html + '</ul>';
    card.style.left = (x + 12) + 'px';
    card.style.top = (y + 12) + 'px';
    card.style.display = 'block';
  }
  function hideCard() {
    if (card) card.style.display = 'none';
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function wireCopyButtons(root) {
    root.querySelectorAll('.syn-copy-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var word = btn.getAttribute('data-word');
        if (!word || !navigator.clipboard) return;
        navigator.clipboard.writeText(word).then(function () {
          btn.classList.add('is-copied');
          setTimeout(function () { btn.classList.remove('is-copied'); }, 1200);
        }).catch(function () {});
      });
    });
  }

  function wire(root) {
    var data = readSenses();
    wireCopyButtons(root);
    root.querySelectorAll('[data-word]').forEach(function (el) {
      var word = el.getAttribute('data-word');
      el.addEventListener('mouseenter', function (ev) {
        setActive(word, true);
        prefetch(word);
        if (el.classList.contains('syn-node')) showCard(word, ev.clientX, ev.clientY, data);
      });
      el.addEventListener('mouseleave', function () {
        setActive(word, false);
        hideCard();
      });
      el.addEventListener('focus', function () { setActive(word, true); prefetch(word); });
      el.addEventListener('blur', function () { setActive(word, false); });
    });
  }

  // Below 900px the graph starts collapsed (ui.md § layout: "list first"). The <details>
  // is `open` in the server-rendered markup so a no-JS visitor always sees the graph;
  // this only narrows that default on a phone, and only once per page load.
  function collapseGraphOnNarrow(root) {
    var d = root.querySelector('.syn-graph-details');
    if (d && window.innerWidth < 900) d.removeAttribute('open');
  }

  // htmx 2 does not swap 4xx/5xx responses. A 503 from api/syn.php carries the "not
  // available" message for #syn-result, so let that one target swap. The autocomplete 503
  // has an empty body and stays unswapped.
  document.addEventListener('htmx:beforeSwap', function (ev) {
    var d = ev.detail;
    if (d && d.xhr && d.xhr.status === 503 && d.target && d.target.id === 'syn-result') {
      d.shouldSwap = true;
      d.isError = false;
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    var result = document.getElementById('syn-result');
    if (result) { wire(result); collapseGraphOnNarrow(result); }
  });
  document.body && document.body.addEventListener('htmx:afterSwap', function (ev) {
    if (ev.detail && ev.detail.target && ev.detail.target.id === 'syn-result') {
      wire(ev.detail.target);
      collapseGraphOnNarrow(ev.detail.target);
    }
  });
})();
