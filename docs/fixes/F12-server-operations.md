# F12 — Deploy, server clean-up and backup verification

Status: brief ready 2026-11-09; not started. Priority: P1. Needs SSH access that the owner grants.

## Question

Nothing since 2026-10-05 is deployed. Deploy the local fixes, verify them live, remove the old
Sinonime files, and prove that backups work. Read `AGENTS.md` ("Deploying to a subfolder",
"Backing up `app.db`") and [the backup runbook](../recovery/backup-runbook.md) first.

## Decisions already made

- The owner authorizes this deploy and these server changes, once access is given.
- Sinonime moved to its own project. Remove its files from voroave.ro. No redirect is required.
- Never overwrite the server's `api/config.local.php`, `app.db`, `secret.key` or `backups/`.
- No user merge, no identity change, no restore over production data.

## Before you start

The owner gives: the SSH host, the app folder (`~/voroave.ro`), the private folder
(`~/voroave-private`), and an off-server destination for backup copies.
Without the destination, do Steps 1–3 and report Step 4 as blocked.
F11 Step 0 (commit) must be done; deploy a committed state only.

## Step 1 — Snapshot, then deploy

1. On the server: `php api/_backup.php`, then `php api/_backup.php --list`. Record the snapshot name.
2. Deploy the server half first: `rsync -av --exclude 'api/config.local.php' public/api/ host:~/voroave.ro/api/`.
3. Then the rest: `rsync -av --exclude 'api/config.local.php' --exclude 'data/*.db' public/ host:~/voroave.ro/`.
   Upload `public/data/ui.db` only if F11 rebuilt it and its tests passed.

## Step 2 — Live acceptance checks (F02–F06 and the 2026-11-09 fixes)

Use a fresh browser profile. Do not write marks with an existing account.

- F04: `/statistici` serves the app; `/stats` is still the host report; the nav links `/statistici`.
- F05: `/?word=zapciu` shows the structured senses on first arrival.
- F03: `/ghici` sense round withholds the definition until answered; `/ghici?mode=flash` until „arată definiția”.
- F06: `/despre` keeps a saved theme, skin and text scale; the console shows no errors.
- F02: mark a word, go offline, mark another, go online; both reach the server (check `api/me.php` or a second device).
- Layout: `/metodologie` and `/despre` at 390px have no horizontal scroll.
Record each result in the brief's `Status:` line (F02–F06), with the date.

## Step 3 — Remove the old Sinonime files

List first, then delete: `sinonime.php`, `api/syn.php`, `api/_syn.php`, `api/_syn_check.php`,
`api/_partials/syn_autocomplete.php`, `api/_partials/syn_landing.php`, `api/_partials/syn_result.php`,
`api/_partials/syn_unavailable.php`, `assets/syn.js`, `data/syn.db`.
Confirm `/sinonime` returns 404 and the home page still works.
Also run `git config pack.threads 1` and remove `.git/gc.log` if the server checkout has them.

## Step 4 — Backups

1. Confirm the nightly cron line from `AGENTS.md` exists and ran (check `backup.log` and snapshot dates).
2. Confirm retention keeps 14 snapshots.
3. Set up a daily copy of the newest snapshot, `secret.key` and `config.local.php` to the owner's destination.
4. Restore drill: copy one snapshot into a disposable directory (not the live private folder),
   run `PRAGMA integrity_check`, and count annotations and lists. Delete the directory afterwards.

## Stop and ask

- A check in Step 2 fails. Do not patch on the server; report it.
- Anything would overwrite `app.db`, `secret.key` or `config.local.php`.
- The backup destination or the cron setup needs credentials you do not have.

## Deliver

Update the F02–F06 status lines, `docs/BACKLOG.md` and `docs/activity-history.md`.
Separate what was verified live from what was only checked locally.
