// F04: /statistici serves the application statistics page; other routes are unchanged.
//
//   python3 tools/run_tests.py --only statistici
//
// Runs against the runner's staged, isolated server (dev router). The Apache rule is
// pinned by tests/test_statistics_route.py (static check, and a real httpd when present).
const BASE = require('./lib/target').testBase('tests/test_statistics_route.js');

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };
const get = (p, opt = {}) => fetch(BASE + p, { redirect: 'manual', ...opt });

(async () => {
  console.log('\n1. /statistici serves the application, with a matching canonical');
  const r = await get('/statistici');
  const html = await r.text();
  check(r.status === 200, `GET /statistici -> ${r.status}`);
  check(html.includes('<title>Statistici'), 'it is the statistics page');
  check(html.includes(`<link rel="canonical" href="${BASE}/statistici">`), 'canonical names /statistici');
  check(html.includes(`<meta property="og:url" content="${BASE}/statistici">`), 'og:url names /statistici');
  check(html.includes('hx-get="/api/stats.php"'), 'the page still loads its panels from api/stats.php');

  console.log('\n2. /statistici/ and query strings resolve; /stats.php still works');
  check((await get('/statistici/')).status === 200, 'trailing slash -> 200');
  const q = await get('/statistici?word_tier=forgotten&pos=s.f.');
  check(q.status === 200, 'filters in the query string -> 200 (no redirect)');
  const legacy = await get('/stats.php');
  check(legacy.status === 200 && (await legacy.text()).includes('<title>Statistici'), '/stats.php -> 200, same page');

  console.log('\n3. Navigation points at /statistici');
  const despre = await (await get('/despre')).text();
  check(/href="statistici"/.test(despre), 'despre links to statistici');
  check(!/href="stats"/.test(despre), 'despre no longer links to /stats');
  const nav = await (await get('/colectii')).text();
  check(!/href="[^"]*\/stats["?]/.test(nav + despre + html), 'no page links to the reserved /stats');

  console.log('\n4. Other clean URLs are unchanged');
  for (const p of ['/despre', '/metodologie', '/ghici', '/colectii', '/liste']) {
    const x = await get(p);
    check(x.status === 200, `GET ${p} -> ${x.status}`);
  }
  const joc = await get('/joc');
  check(joc.status === 301 && /\/ghici$/.test(joc.headers.get('location') || ''), '/joc still 301 -> /ghici');

  console.log('\n5. A POST to an API endpoint is not redirected');
  const p = await get('/api/game.php', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Origin: 'https://evil.example' }, body: '{}' });
  check(p.status === 403 && !p.headers.get('location'), `cross-origin POST -> ${p.status}, no Location header`);

  console.log(failures ? `\n${failures} FAILED` : '\nall passed');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.log('FAIL  ' + e.stack); process.exit(1); });
