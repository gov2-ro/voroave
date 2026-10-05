// Unit tests for the client sync queue (public/assets/store.js), brief F02.
//
// The REAL store.js runs in a VM with a fake localStorage, a fake clock, a manual timer
// queue and a deferred fetch, so every race is reproduced deterministically. No server
// and no database are involved. The integration suite (test_store_sync.js) covers the
// real PHP endpoint. Protocol: docs/sync-protocol.md.
'use strict';
const vm = require('vm');
const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'public', 'assets', 'store.js'), 'utf8');

let failures = 0;
function check(ok, msg) {
  if (!ok) failures++;
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`);
}
const tick = () => new Promise((r) => setImmediate(r));
async function settle() { for (let i = 0; i < 8; i++) await tick(); }

// A browser with a controllable clock, timers and fetch.
function boot(initialStorage) {
  const ls = Object.assign({}, initialStorage || {});
  const clock = { now: Date.parse('2026-10-05T10:00:00.000Z') };
  const timers = [];
  const calls = [];            // every fetch: { body, resolve(resp), reject(err) }
  const events = [];
  const listeners = {};
  class FakeDate extends Date {
    constructor(...a) { if (a.length) super(...a); else super(clock.now); }
    static now() { return clock.now; }
  }
  const root = { dataset: {}, setAttribute(k, v) { this.attrs = this.attrs || {}; this.attrs[k] = v; },
                 removeAttribute(k) { if (this.attrs) delete this.attrs[k]; },
                 classList: { toggle() {} } };
  const ctx = {
    localStorage: {
      getItem: (k) => (k in ls ? ls[k] : null),
      setItem: (k, v) => { ls[k] = String(v); },
      removeItem: (k) => { delete ls[k]; },
    },
    document: {
      visibilityState: 'visible',
      documentElement: root,
      addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
      dispatchEvent: (e) => { events.push(e); (listeners[e.type] || []).forEach((f) => f(e)); return true; },
    },
    CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } },
    Date: FakeDate,
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1] = null; },
    fetch: (url, opts) => new Promise((resolve, reject) => {
      calls.push({ url, body: JSON.parse(opts.body),
        resolve: (resp) => resolve(resp), reject });
    }),
    console, OTIOS_BASE: '',
  };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  const b = {
    ctx, ls, calls, events, root,
    clock,
    q: () => JSON.parse(ls['otios.pending'] || '{}'),
    words: () => JSON.parse(ls['otios.research'] || '{"words":{}}').words,
    since: () => (JSON.parse(ls['otios.sync'] || '{}').since),
    pendingTimers: () => timers.filter(Boolean).length,
    // Run queued timer callbacks (the timer fires once).
    async runTimers() {
      const due = timers.splice(0).filter(Boolean);
      due.forEach((t) => t.fn());
      await settle();
    },
  };
  return b;
}

// Responses ------------------------------------------------------------------------------
const okResp = (json) => ({ ok: true, status: 200, json: async () => json });
const statusResp = (status) => ({ ok: false, status, json: async () => ({}) });
// A well-behaved new-protocol server: everything is stored unless `override[word]` says otherwise.
function serverReply(call, opts) {
  opts = opts || {};
  const ov = opts.override || {};
  const outcomes = call.body.changes.map((c) => ({ word: c.word, rev: c.rev, status: ov[c.word] || 'stored' }));
  return okResp({
    server_seq: opts.server_seq == null ? 1 : opts.server_seq,
    server_time: 'x', changes: opts.changes || [], applied: outcomes.length,
    rejected: outcomes.filter((o) => o.status === 'invalid' || o.status === 'quota').length,
    outcomes, has_more: !!opts.has_more,
  });
}
const respond = async (call, resp) => { call.resolve(resp); await settle(); };

const watchdog = setTimeout(() => { console.log('  FAIL  test hung (pending promise)'); process.exit(1); }, 60000);
(async () => {
  console.log('\n1. Edit during an in-flight push stays queued');
  {
    const b = boot();
    b.ctx.updateWord('alfa', { note: 'unu' });
    const p1 = b.ctx.syncNow();
    check(b.calls.length === 1 && b.calls[0].body.changes[0].note === 'unu', 'first push carries the first value');
    b.clock.now += 5;
    b.ctx.updateWord('alfa', { note: 'doi' });
    await respond(b.calls[0], serverReply(b.calls[0]));
    await p1;
    check(Object.keys(b.q()).includes('alfa'), 'second revision is still queued after the first ack');
    check(b.pendingTimers() > 0, 'another push is scheduled');
    await b.runTimers();
    check(b.calls.length === 2 && b.calls[1].body.changes[0].note === 'doi', 'next push sends the newest value');
    await respond(b.calls[1], serverReply(b.calls[1]));
    check(Object.keys(b.q()).length === 0, 'queue drains once the newest revision is acknowledged');
  }

  console.log('\n2. Two edits in the same millisecond');
  {
    const b = boot();
    b.ctx.updateWord('alfa', { note: 'unu' });
    const t1 = b.words().alfa.updated_at;
    b.ctx.updateWord('alfa', { note: 'doi' });   // clock has not moved
    const t2 = b.words().alfa.updated_at;
    check(t2 > t1, 'second edit gets a strictly later updated_at');
    const r1 = b.q().alfa.rev;
    b.ctx.updateWord('alfa', { note: 'trei' });
    check(b.q().alfa.rev > r1, 'revision counter increases on every edit');
    // The same-ms race through the queue.
    const c = boot();
    c.ctx.updateWord('alfa', { note: 'unu' });
    const p = c.ctx.syncNow();
    c.ctx.updateWord('alfa', { note: 'doi' });   // same ms, in flight
    await respond(c.calls[0], serverReply(c.calls[0]));
    await p;
    check(c.q().alfa && c.words().alfa.note === 'doi', 'same-ms in-flight edit stays queued');
    check(c.words().alfa.updated_at > c.calls[0].body.changes[0].updated_at,
          'queued edit carries a later updated_at than the one already sent');
  }

  console.log('\n3. Delete and re-create during a push');
  {
    const b = boot();
    b.ctx.updateWord('alfa', { bookmarked: true });
    const p = b.ctx.syncNow();
    b.clock.now += 1;
    b.ctx.updateWord('alfa', { bookmarked: false });          // delete while in flight
    await respond(b.calls[0], serverReply(b.calls[0]));
    await p;
    check(!!b.q().alfa, 'tombstone made during the push stays queued');
    await b.runTimers();
    check(b.calls[1] && b.calls[1].body.changes[0].deleted === true, 'next push sends the tombstone');
    const tomb = b.calls[1].body.changes[0];
    const p2 = b.ctx.syncNow();   // in flight already (timer) -> returns false; harmless
    b.ctx.updateWord('alfa', { note: 'din nou' });            // re-create while tombstone in flight
    await respond(b.calls[1], serverReply(b.calls[1]));
    await p2;
    check(!!b.q().alfa, 're-creation during the tombstone push stays queued');
    await b.runTimers();
    const last = b.calls[b.calls.length - 1].body.changes[0];
    check(last.deleted === false && last.note === 'din nou' && last.updated_at > tomb.updated_at,
          're-creation is sent later than the tombstone, with the new value');
  }

  console.log('\n4. Other words survive an in-flight push');
  {
    const b = boot();
    b.ctx.updateWord('alfa', { note: 'a' });
    const p = b.ctx.syncNow();
    b.ctx.updateWord('beta', { note: 'b' });
    await respond(b.calls[0], serverReply(b.calls[0]));
    await p;
    check(!b.q().alfa && !!b.q().beta, 'alfa cleared, beta kept');
  }

  console.log('\n5. More than 5,000 queued changes are sent in bounded batches');
  {
    const words = {}, queue = {};
    for (let i = 0; i < 5001; i++) {
      const w = 'w' + String(i).padStart(5, '0');
      words[w] = { bookmarked: true, note: '', tags: [], updated_at: '2026-07-01T00:00:00.000Z' };
      queue[w] = '2026-07-01T00:00:00.000Z';        // legacy queue format: also tested here
    }
    const b = boot({
      'otios.research': JSON.stringify({ version: 1, words }),
      'otios.pending': JSON.stringify(queue),
      'otios.sync': JSON.stringify({ migrated: true }),
    });
    const sent = new Set();
    let guard = 0;
    b.ctx.syncNow();
    while (guard++ < 20) {
      await settle();
      const open = b.calls.filter((c) => !c.done);
      if (!open.length) { if (b.pendingTimers()) { await b.runTimers(); continue; } break; }
      const c = open[0]; c.done = true;
      c.body.changes.forEach((x) => sent.add(x.word));
      await respond(c, serverReply(c));
    }
    const sizes = b.calls.map((c) => c.body.changes.length);
    check(sizes.every((n) => n <= 5000) && sizes.length >= 2, `batches are bounded (${sizes.join(', ')})`);
    check(sent.size === 5001, 'every change was sent');
    check(Object.keys(b.q()).length === 0, 'queue is empty at the end');
  }

  console.log('\n6. Rejected words keep their data, look rejected and stop retrying');
  {
    const b = boot();
    b.ctx.updateWord('alfa', { note: 'invalid' });
    b.ctx.updateWord('beta', { note: 'quota' });
    b.ctx.updateWord('gama', { note: 'ok' });
    const p = b.ctx.syncNow();
    await respond(b.calls[0], serverReply(b.calls[0], { override: { alfa: 'invalid', beta: 'quota' } }));
    await p;
    check(!!b.words().alfa && b.words().alfa.note === 'invalid', 'local data of a rejected word is kept');
    check(!b.q().gama, 'accepted word is cleared');
    check(b.q().alfa && b.q().alfa.rejected === 'invalid' && b.q().beta.rejected === 'quota',
          'rejected entries are marked with the reason');
    check(typeof b.ctx.getRejected === 'function' && Object.keys(b.ctx.getRejected()).sort().join() === 'alfa,beta',
          'getRejected() lists them');
    check(b.events.some((e) => e.type === 'otios:sync-rejected'), 'a sync-rejected event fires');
    check(b.root.attrs && b.root.attrs['data-sync-rejected'] === '2', 'html data-sync-rejected shows the count');
    b.clock.now += 10;
    const p2 = b.ctx.syncNow();   // a pull-only request: nothing to push
    check(b.calls.length === 2 && b.calls[1].body.changes.length === 0, 'rejected entries are not sent again');
    await respond(b.calls[1], serverReply(b.calls[1]));
    await p2;
    check(!!b.q().alfa.rejected, 'and they stay marked rejected');
    b.ctx.updateWord('alfa', { note: 'corrected' });
    check(!b.q().alfa.rejected, 'a new edit clears the rejected mark and queues it again');
  }

  console.log('\n7. Transient failures keep everything queued and do not move the cursor');
  const failures7 = {
    'network error': (c) => c.reject(new Error('offline')),
    'HTTP 429': (c) => c.resolve(statusResp(429)),
    'HTTP 500': (c) => c.resolve(statusResp(500)),
    'malformed JSON': (c) => c.resolve({ ok: true, status: 200, json: async () => { throw new SyntaxError('bad'); } }),
    'JSON null': (c) => c.resolve(okResp(null)),
    'no server_seq': (c) => c.resolve(okResp({ changes: [], outcomes: [] })),
    'changes not an array': (c) => c.resolve(okResp({ server_seq: 9, changes: 'x' })),
  };
  for (const [name, fail] of Object.entries(failures7)) {
    const b = boot({ 'otios.sync': JSON.stringify({ since: 4, migrated: true }) });
    b.ctx.updateWord('alfa', { note: 'x' });
    const before = JSON.stringify(b.q());
    const p = b.ctx.syncNow();
    fail(b.calls[0]);
    const res = await p;
    check(res === false && JSON.stringify(b.q()) === before && b.since() === 4 && !!b.words().alfa,
          `${name}: queue, data and cursor unchanged`);
  }

  console.log('\n8. A queued tombstone is not resurrected by an older remote echo');
  {
    const b = boot();
    b.ctx.updateWord('alfa', { note: 'x' });
    b.clock.now += 100;
    b.ctx.updateWord('alfa', { note: '' });                  // prune -> tombstone
    check(!b.words().alfa, 'word deleted locally');
    const old = { word: 'alfa', bookmarked: true, note: 'vechi', tags: [], deleted: false,
                  updated_at: '2026-10-05T09:00:00.000Z' };
    b.ctx.applyRemote([old]);
    check(!b.words().alfa, 'older remote update did not recreate the word');
    b.ctx.applyRemote([old]);
    check(!b.words().alfa, 'replaying the echo is idempotent');
    // The same echo arriving in the reply that also acknowledges the tombstone.
    const p = b.ctx.syncNow();
    await respond(b.calls[0], serverReply(b.calls[0], { changes: [old], server_seq: 3 }));
    await p;
    check(!b.words().alfa && Object.keys(b.q()).length === 0, 'echo in the acknowledging reply does not recreate it either');
    // A genuinely newer remote still wins.
    const newer = Object.assign({}, old, { updated_at: '2026-10-05T11:00:00.000Z', note: 'nou' });
    b.ctx.applyRemote([newer]);
    check(b.words().alfa && b.words().alfa.note === 'nou', 'a newer remote update still applies');
  }

  console.log('\n9. Pull cursor advances only to what the server delivered');
  {
    const b = boot();
    b.ctx.updateWord('alfa', { note: 'x' });
    const rows = [1, 2, 3].map((i) => ({ word: 'r' + i, bookmarked: true, note: '', tags: [], deleted: false,
      updated_at: '2026-10-05T0' + i + ':00:00.000Z' }));
    const p = b.ctx.syncNow();
    await respond(b.calls[0], serverReply(b.calls[0], { changes: rows, server_seq: 7, has_more: true }));
    await p;
    check(b.since() === 7 && Object.keys(b.words()).length === 4, 'cursor = last delivered seq, rows applied');
    check(b.pendingTimers() > 0, 'next page is scheduled when has_more');
  }

  console.log('\n10. Old server without per-word outcomes');
  {
    const b = boot();
    b.ctx.updateWord('alfa', { note: 'x' });
    const p = b.ctx.syncNow();
    await respond(b.calls[0], okResp({ server_seq: 1, changes: [], applied: 1, rejected: 0, has_more: false }));
    await p;
    check(Object.keys(b.q()).length === 0, 'rejected = 0: legacy ack clears the sent revision');

    const c = boot();
    c.ctx.updateWord('alfa', { note: 'x' });
    c.ctx.updateWord('beta', { note: 'y' });
    const p2 = c.ctx.syncNow();
    await respond(c.calls[0], okResp({ server_seq: 1, changes: [], applied: 1, rejected: 1, has_more: false }));
    await p2;
    check(Object.keys(c.q()).length === 2, 'rejected > 0 without outcomes: nothing is cleared');
    check(c.calls.length === 1, 'and no tight retry loop starts');
  }

  console.log('\n11. Mixed outcomes: unknown or missing status is not an acknowledgement');
  {
    const b = boot();
    b.ctx.updateWord('alfa', { note: 'x' });
    b.ctx.updateWord('beta', { note: 'y' });
    const timersBefore = b.pendingTimers();
    const p = b.ctx.syncNow();
    await respond(b.calls[0], serverReply(b.calls[0], { override: { alfa: 'deferred', beta: 'weird' } }));
    await p;
    check(!!b.q().alfa && !!b.q().beta && !b.q().alfa.rejected, 'deferred / unknown stay queued, not rejected');
    check(b.calls.length === 1 && b.pendingTimers() === timersBefore, 'no progress, so no reschedule');
  }

  console.log(failures ? `\n${failures} FAILED\n` : '\nAll checks passed\n');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.log('  FAIL  unexpected error: ' + (e && e.stack || e)); process.exit(1); });
