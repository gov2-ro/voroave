// The server a JS suite talks to — and a refusal to talk to any other.
//
// Most suites mint anonymous devices and write annotations, answers or lists. A dev
// server reads `public/api/config.local.php`, so a suite pointed at one writes to
// whatever `app.db` that file names — on a dev checkout, `private/app.db`. Setting
// OTIOS_PRIVATE_DIR in the environment does NOT redirect it: `_appdb.php` reads only the
// `define` in config.local.php. That happened once (2026-10-05, see activity history).
//
// So a suite runs only when tools/run_tests.py started it (it stages public/ with its own
// config.local.php and sets OTIOS_TEST_ISOLATED=1). To aim a suite at a server you staged
// yourself, with its own private dir, set OTIOS_TEST_ISOLATED=1 and OTIOS_TEST_URL by hand.
'use strict';

function testBase(suite) {
  const url = process.env.OTIOS_TEST_URL;
  if (!url || process.env.OTIOS_TEST_ISOLATED !== '1') {
    console.error(
      `${suite}: refusing to run without an isolated server.\n` +
      '  Run it through the runner:  python3 tools/run_tests.py --only <name>\n' +
      '  A hand-staged server needs its own config.local.php (OTIOS_PRIVATE_DIR outside\n' +
      '  private/), then OTIOS_TEST_URL=<url> OTIOS_TEST_ISOLATED=1.');
    process.exit(2);
  }
  return url;
}

module.exports = { testBase };
