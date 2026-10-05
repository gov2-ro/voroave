// F01: /sinonime success states and operational-failure states.
//
//   python3 tools/run_tests.py --only "sinonime states"
//
// Needs OTIOS_TEST_URL (a staged server) and OTIOS_TEST_DATA_DIR (that server's data/ folder).
// It replaces the STAGED syn.db with broken fixtures and restores it in a finally block.
// It never touches public/data/syn.db in the repository. Needs the sqlite3 command-line tool.
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const BASE = process.env.OTIOS_TEST_URL;
const DATA = process.env.OTIOS_TEST_DATA_DIR;
if (!BASE || !DATA) { console.log('FAIL  OTIOS_TEST_URL and OTIOS_TEST_DATA_DIR are required (use tools/run_tests.py)'); process.exit(1); }
if (path.resolve(DATA) === path.resolve(__dirname, '..', 'public', 'data')) {
  console.log('FAIL  refusing to mutate the repository data dir'); process.exit(1);
}
const DB = path.join(DATA, 'syn.db');
const KEEP = DB + '.keep';
const SERVER_LOG = path.join(DATA, '..', '..', 'php-server.log');

let failures = 0;
const check = (ok, msg) => { if (!ok) failures++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`); };
const get = async (p) => { const r = await fetch(BASE + p); return { status: r.status, headers: r.headers, body: await r.text() }; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const logText = () => { try { return fs.readFileSync(SERVER_LOG, 'utf8'); } catch { return ''; } };

const LEAKS = [/\.db\b/, /\bSELECT\b[^<]{0,80}\bFROM\b/i, /PDOException/, /Stack trace/i, /\/private\//, /\/tmp\//, /no such table/i];
function noLeak(body, label) {
  const hit = LEAKS.find((re) => re.test(body));
  check(!hit, `${label}: body shows no path, SQL or trace${hit ? ' (matched ' + hit + ')' : ''}`);
}

function restore() {
  try { fs.chmodSync(DB, 0o644); } catch {}
  fs.rmSync(DB, { force: true });
  fs.copyFileSync(KEEP, DB);
}

// Every outage fixture must give the same visible behaviour.
async function expectUnavailable(label) {
  const before = logText().length;
  const page = await get('/sinonime?q=frumos');
  check(page.status === 503, `${label}: full page -> ${page.status} (want 503)`);
  check(page.body.includes('syn-unavailable'), `${label}: full page shows the unavailable state`);
  check(page.body.includes('id="syn-form"'), `${label}: full page keeps the search form`);
  check(!page.body.includes('syn-graph'), `${label}: full page shows no graph`);
  check(page.headers.get('retry-after') !== null, `${label}: Retry-After is set`);
  check((page.headers.get('cache-control') || '').includes('no-store'), `${label}: Cache-Control is no-store`);
  check(/noindex/.test(page.body), `${label}: full page is noindex`);
  check(!page.headers.get('set-cookie'), `${label}: no Set-Cookie`);
  noLeak(page.body, `${label}: full page`);

  const frag = await get('/api/syn.php?q=frumos');
  check(frag.status === 503, `${label}: fragment -> ${frag.status} (want 503)`);
  check(frag.body.includes('syn-unavailable'), `${label}: fragment shows the unavailable state`);
  noLeak(frag.body, `${label}: fragment`);

  const ac = await get('/api/syn.php?ac=1&q=fru');
  check(ac.status === 503, `${label}: autocomplete -> ${ac.status} (want 503)`);
  check(ac.body.trim() === '', `${label}: autocomplete body is empty`);

  const unknown = await get('/sinonime?q=zzznotarealword');
  check(unknown.status === 503, `${label}: unknown word is also 503 (the lookup cannot run)`);

  // The empty query needs no database and stays an intentional landing state.
  const empty = await get('/sinonime');
  check(empty.status === 200 && empty.body.includes('syn-landing'), `${label}: empty query -> 200 landing`);

  let logged = false;
  for (let i = 0; i < 20 && !logged; i++) { logged = logText().slice(before).includes('[sinonime] unavailable'); if (!logged) await sleep(100); }
  check(logged, `${label}: technical detail reached the server log`);
}

(async () => {
  console.log(`Testing against ${BASE}`);
  if (!fs.existsSync(DB)) { console.log('FAIL  staged syn.db is missing'); process.exit(1); }
  fs.copyFileSync(DB, KEEP);
  try {
    console.log('\n-- healthy database');
    {
      const page = await get('/sinonime?q=frumos');
      check(page.status === 200, `known word, full page -> ${page.status}`);
      check(/class="syn-node/.test(page.body) && /class="syn-row"/.test(page.body),
        'no-JS shared URL: graph nodes and list rows are in the server HTML');
      check(/<title>frumos — sinonime/.test(page.body), 'shared URL has the word in <title>');
      check(!page.body.includes('syn-unavailable'), 'healthy page does not show the unavailable state');

      const frag = await get('/api/syn.php?q=frumos');
      check(frag.status === 200 && /class="syn-row"/.test(frag.body), `known word, fragment -> ${frag.status} with rows`);
      check(page.body.includes(frag.body.trim()), 'page embeds the same markup the fragment returns');

      const unk = await get('/sinonime?q=zzznotarealword');
      check(unk.status === 200 && unk.body.includes('syn-empty') && !unk.body.includes('syn-unavailable'),
        `unknown word -> ${unk.status} with the not-found state`);
      const unkFrag = await get('/api/syn.php?q=zzznotarealword');
      check(unkFrag.status === 200 && unkFrag.body.includes('syn-empty'), 'unknown word, fragment -> 200 not-found state');

      const empty = await get('/sinonime');
      check(empty.status === 200 && empty.body.includes('syn-landing'), 'empty query, page -> 200 landing');
      const emptyFrag = await get('/api/syn.php?q=');
      check(emptyFrag.status === 200 && emptyFrag.body.includes('syn-landing'), 'empty query, fragment -> 200 landing');

      const ac = await get('/api/syn.php?ac=1&q=fru');
      check(ac.status === 200 && ac.body.includes('>frumos<'), 'autocomplete "fru" lists frumos');
      const acD = await get('/api/syn.php?ac=1&q=' + encodeURIComponent('tân'));
      check(acD.status === 200 && acD.body.includes('>tânăr<'), 'autocomplete with diacritics "tân" lists tânăr');
      const acF = await get('/api/syn.php?ac=1&q=tan');
      check(acF.status === 200 && acF.body.includes('>tânăr<'), 'autocomplete without diacritics "tan" lists tânăr');
      const acE = await get('/api/syn.php?ac=1&q=');
      check(acE.status === 200 && acE.body.trim() === '', 'autocomplete with an empty query is an empty 200');
    }

    console.log('\n-- fixture: syn.db missing');
    fs.rmSync(DB);
    await expectUnavailable('missing');
    check(!fs.existsSync(DB), 'missing: the request did not create an empty syn.db');

    console.log('\n-- fixture: syn.db is an empty file');
    fs.writeFileSync(DB, '');
    await expectUnavailable('empty file');

    console.log('\n-- fixture: syn.db is not a SQLite file');
    fs.writeFileSync(DB, 'this is not a database\n'.repeat(500));
    await expectUnavailable('not sqlite');

    console.log('\n-- fixture: syn.db is unreadable (chmod 000)');
    restore();
    fs.chmodSync(DB, 0o000);
    let readable = true;
    try { fs.accessSync(DB, fs.constants.R_OK); } catch { readable = false; }
    if (readable) console.log('SKIP  chmod 000 does not block this user (running as root?); unreadable fixture not run');
    else await expectUnavailable('unreadable');

    console.log('\n-- fixture: incompatible schema (edge.t renamed)');
    restore();
    execFileSync('sqlite3', [DB, 'ALTER TABLE edge RENAME COLUMN t TO tt;']);
    await expectUnavailable('column renamed');

    console.log('\n-- fixture: incompatible schema (table sense_word dropped)');
    restore();
    execFileSync('sqlite3', [DB, 'DROP TABLE sense_word;']);
    await expectUnavailable('table dropped');

    console.log('\n-- fixture: truncated file (query error after a valid header)');
    restore();
    const size = fs.statSync(DB).size;
    fs.truncateSync(DB, Math.floor(size * 0.5));
    await expectUnavailable('truncated');

    console.log('\n-- restored database works again');
    restore();
    const again = await get('/sinonime?q=frumos');
    check(again.status === 200 && /class="syn-row"/.test(again.body), 'after restore: known word -> 200 with rows');
  } finally {
    try { restore(); } catch {}
    fs.rmSync(KEEP, { force: true });
  }
  console.log(failures ? `\n${failures} FAILED` : '\nAll passed');
  process.exit(failures ? 1 : 0);
})();
