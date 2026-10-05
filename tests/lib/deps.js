// Shared dependency loading for the JS suites.
//
// Dependencies resolve from the repository (package.json, `npm ci`), never from the home
// directory or a global install. When one is missing:
//   - with OTIOS_STRICT=1 (set by tools/run_tests.py) the suite FAILS with exit code 1;
//   - otherwise the suite prints a SKIP line and exits 0, so a manual run stays easy.
'use strict';

const strict = process.env.OTIOS_STRICT === '1';

function missing(suite, what, fix) {
  const msg = `${suite} needs ${what}. Fix: ${fix}`;
  if (strict) {
    console.log(`  FAIL  ${msg}`);
    process.exit(1);
  }
  console.log(`SKIP  ${msg}`);
  process.exit(0);
}

function loadPlaywright(suite) {
  let pw;
  try { pw = require('playwright'); } catch (_) {
    missing(suite, 'the playwright package', 'run `npm ci` in the repository root');
  }
  return pw;
}

// Launch Chromium; a missing browser binary gets the same actionable treatment.
async function launchChromium(suite, chromium) {
  try {
    return await chromium.launch();
  } catch (e) {
    missing(suite, 'a Chromium browser build',
      'run `npx playwright install chromium` (' + String(e.message).split('\n')[0] + ')');
  }
}

function loadJsdom(suite) {
  let mod;
  try { mod = require('jsdom'); } catch (_) {
    missing(suite, 'the jsdom package', 'run `npm ci` in the repository root');
  }
  return mod;
}

module.exports = { strict, loadPlaywright, launchChromium, loadJsdom };
