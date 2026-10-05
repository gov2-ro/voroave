# Backup and restore runbook

Status: runbook ready for owner review. Operational checks need access.
No ops access existed when this was written. Cron scheduling and off-machine coverage are UNVERIFIED.
Nothing here changes a scheduled job, a credential or production data.

## 1. What must be backed up

| Item | Why | Where it lives | Covered by `_backup.php` | Covered by git |
|---|---|---|---|---|
| `app.db` | Only copy of annotations, lists, nicknames, devices, game log, reports. | `<OTIOS_PRIVATE_DIR>/app.db` | Yes (`VACUUM INTO`) | No (gitignored) |
| `secret.key` | Seals quiz tokens and admin sessions. Loss logs the admin out and breaks quiz rounds in progress. No data is lost. | `<OTIOS_PRIVATE_DIR>/secret.key` | No | No |
| `config.local.php` | Private directory path, admin token (`OTIOS_ADMIN_TOKEN`), optional `OTIOS_QUIZ_SECRET`. | `public/api/config.local.php` on the server | No | No (gitignored) |
| `data/word_ids.tsv` | Permanent share-link ids. Append-only. | Repository | No | Yes |
| `data/editorial.tsv` | Curator marks. | Repository | No | Yes |
| `ui.db`, `syn.db` | Rebuilt by the pipeline. Not irreplaceable. | `public/data/` | No | No |

Notes:

- If `OTIOS_QUIZ_SECRET` is defined, `secret.key` is not read (`public/api/_appdb.php:64-68`). Then the constant in `config.local.php` is the secret to keep.
- `secret.key` and `config.local.php` hold secrets. Store them in the encrypted copy only. Never commit them.
- A restore of `app.db` without `secret.key` still works. The app writes a fresh key. Sessions and quiz tokens reset.
- The tracked files are safe if the git remote is safe. The owner confirms that the remote is a separate machine (UNVERIFIED).

## 2. Consistent snapshots

`php api/_backup.php` (`public/api/_backup.php`) does this:

1. Open `app.db` read-only, without running migrations (`_backup.php:67-72`).
2. Run `VACUUM INTO '<dest>'`. This gives one consistent file while the site keeps writing. A plain `cp` can tear a WAL database.
3. Name the file `app-YYYYMMDD-HHMMSS.db` in UTC.
4. Set mode `0600` on the file and `0700` on the directory.
5. Open the new file and run `PRAGMA integrity_check`. Exit 1 if the result is not `ok`.
6. Prune to the newest `--keep N` files (default 14). Pruning runs only after a good snapshot.

Limits to know:

- It needs SQLite 3.27 or newer. It exits with an error and a `sqlite3 .backup` hint if not.
- The snapshot is in `delete` journal mode (measured in section 8). The app switches it to WAL when it opens the file.
- A snapshot in the same private directory survives a bad migration or a mistaken delete. It does not survive a lost disk.
- The script does not copy `secret.key` or `config.local.php`.
- A second run in the same second prints "already exists" and exits 0.

## 3. Schedule and retention

Documented schedule (`CLAUDE.md`, "Backing up app.db"):

```cron
17 3 * * * cd ~/voroave.ro && php api/_backup.php >> ~/voroave-private/backup.log 2>&1
```

UNVERIFIED: whether this line is installed, which user owns it, and whether the host lets cron run PHP.

Retention proposal:

| Tier | Keep | How |
|---|---|---|
| Local, same host | 14 daily (script default) | `_backup.php --keep 14` |
| Off-machine | 30 daily, 12 weekly, 12 monthly | Rotation done by the off-machine tool |
| Before a migration, merge or deploy | One named snapshot, kept until the change is verified | `php api/_backup.php --dir <dir>` before the change |

The `--keep` value counts files, not days. If the cron job fails for 14 days, the pruning never runs, and the files do not go stale silently. If the job runs twice a day, 14 files are 7 days. Keep one run per day unless the owner sets another objective.

## 4. Off-machine copy (no service chosen)

Requirements for any option:

- The copy is encrypted before it leaves the host, or the remote store encrypts it with a key the owner holds.
- Access is limited to the owner. Use a write-only credential on the host, so a host break-in cannot delete old copies.
- The copy includes `app.db` snapshots, `secret.key` and `config.local.php`.
- The copy is on a different machine and, preferably, a different provider and place than the host.
- Failure is observable (section 5).

Options, without a choice:

| Option | Strength | Weakness |
|---|---|---|
| Host provider's own backup, if it covers `~/voroave-private/` | No setup | UNVERIFIED that it covers the path. Same provider. Restore speed unknown. |
| `rsync` or `rclone` to storage the owner owns, run after the cron job | Simple. Uses ssh keys. | Needs an ssh key on the host. Needs append-only or versioned storage. |
| `age` or `gpg` encrypt, then upload | Encryption independent of the store | Key management by the owner |
| Pull from the owner's own machine (`rsync` over ssh from a laptop or home server) | No credential for the backup store on the host | The pulling machine must be on. A pull is a read-only role. |

Preferred shape: a pull from a machine the owner controls, because the host then holds no write key to the backup. The owner decides. No service was chosen and none was configured.

Do not copy a live `app.db` and `app.db-wal` with a file copy. Copy only snapshots from `_backup.php`.

## 5. Observable failure reporting (proposal only)

Problem: a cron job that fails prints to `backup.log`, and nobody reads it.

Proposed check: the newest `app-*.db` in the backup directory must be less than 26 hours old. 26 is 24 plus a 2 hour margin for one late run.

Sketch (for the owner to approve; not installed):

1. A small script, run by cron one hour after the backup, finds the newest snapshot. If its modified time is older than 26 hours, or the directory is empty, it exits 1 and writes one line to a log.
2. The owner already has an alert mechanism in `health_check.py` (`_alert()`, with `OTZIOS_ALERT_URL` for a webhook and `OTZIOS_ALERT_EMAIL`; it also appends to `data/logs/alerts.log`). That script runs where the pipeline runs, not on the web host. So either: (a) the web host runs a tiny script that posts to the same `OTZIOS_ALERT_URL`, or (b) an external monitor pulls the age of the newest off-machine copy.
3. A "dead man's switch" is stronger than a failure alert. The backup job pings a monitor URL on success. The monitor alerts when pings stop. This also catches a cron job that never ran.
4. Report on: no snapshot, snapshot too old, integrity check failed (already exit 1 in `_backup.php`), off-machine copy older than 26 hours, and the backup directory above a size limit.

Alerts fire once per new problem, as `health_check.py` does. This proposal does not change `health_check.py` or any cron entry.

## 6. Recovery objectives (proposals)

| Objective | Proposal | Reason |
|---|---|---|
| RPO (data loss allowed) | 24 hours | One daily snapshot. Annotations also live in each browser's `localStorage`, so recent marks usually return by sync. Lists, nicknames, scores and game events do not. |
| RTO (time to serve again) | 4 hours for the read-only site, 1 working day for full user data | The static data (`ui.db`) rebuilds from the pipeline. The restore of `app.db` is a file copy. The host and DNS steps depend on access that does not exist here. |
| Restore drill | Every quarter, and after any change to the backup path | A backup nobody restored is not proven. |
| Maximum snapshot age at alert time | 26 hours | Section 5. |

The owner may tighten these. A smaller RPO needs a more frequent snapshot, which is cheap: `VACUUM INTO` of a database of about 1.5 MB takes well under a second (measured size of the development file: 1,531,904 bytes; production size is UNVERIFIED).

## 7. Restore drill (disposable environment)

Never replace production. Never point a restore at `private/` or at the live private directory.
Run every step on a scratch machine or in a scratch directory. Replace `$D` with an empty directory.

1. Get the newest encrypted off-machine copy to the scratch machine. Decrypt it. Do this with the owner's key.
2. Record the file name and its modified time. Compare with the expected daily time.
3. Make the layout:
   ```bash
   D=$(mktemp -d); mkdir -p $D/priv
   cp app-YYYYMMDD-HHMMSS.db $D/priv/app.db && chmod 600 $D/priv/app.db
   ```
4. Check the file:
   ```bash
   sqlite3 $D/priv/app.db "PRAGMA integrity_check; PRAGMA user_version;"
   ```
   Expect `ok` and the current schema version (4 at the time of writing, `APP_DB_VERSION` in `_appdb.php:26`).
5. Count rows in `users`, `devices`, `annotations`, `lists`, `list_items`, `game_events`, `game_stats`. Compare with the source database if it is still available, or with the numbers in the previous drill. Expect a small, explainable difference (new activity since the snapshot).
6. Stage a copy of `public/` in `$D/pub`. Do NOT copy the production `config.local.php`. Write a new one:
   ```bash
   printf "<?php\ndefine('OTIOS_PRIVATE_DIR', '%s');\n" "$D/priv" > $D/pub/api/config.local.php
   ```
   Add a test admin token line if the moderation page is part of the drill.
7. Optional: put a test `secret.key` in `$D/priv`, or let the app make one. Confirm that this resets sessions and does not touch data.
8. Open the restored database through the app code (CLI, no web server needed):
   ```bash
   php -r 'require "'$D'/pub/api/_appdb.php"; echo app_db()->query("select count(*) from annotations")->fetchColumn(), "\n";'
   ```
9. If a web check is needed, start `php -S 127.0.0.1:<free port> -t $D/pub tools/dev-router.php` from the repository, but only with the staged copy as the document root. Page loads mint devices, so never point it at the real `public/`. Stop the server when done.
10. Check one known list slug and one known user's annotation count, if the owner can name them.
11. Delete `$D`. Record the date, the snapshot name, the checks, the time taken, and any problem.

Pass criteria: integrity `ok`; schema version as expected; row counts within the expected difference; the app opens the file without error; the drill took less than the RTO.
Fail action: report to the owner. Do not "fix" production.

## 8. Measured rehearsal (local, synthetic data)

Date: 2026-10-05. Local only. This is not evidence about production.

Method:

1. Copy `public/` (without `config.local.php` and without `data/*.db`) to a scratch directory. Write a new `config.local.php` that sets `OTIOS_PRIVATE_DIR` to a scratch directory.
2. Create `app.db` with the application's own code (`app_db()` runs the migrations). Insert synthetic rows: 50 users, 50 devices, 1,000 annotations, 50 game events.
3. From the staged copy run `php api/_backup.php --dir <scratch>/bak`.
4. Copy the snapshot to a second scratch directory as `app.db`. Run `PRAGMA integrity_check` and compare counts. Open the restored file through the application's code from a second staged copy.

Results:

| Check | Source | Restored snapshot |
|---|---|---|
| `PRAGMA integrity_check` | ok | ok |
| `user_version` | 4 | 4 |
| users | 50 | 50 |
| devices | 50 | 50 |
| annotations | 1,000 | 1,000 |
| game_events | 50 | 50 |
| lists | 0 | 0 |
| `journal_mode` of the file | wal | delete (switches to WAL when the app opens it) |
| App opens restored file and counts annotations | n/a | 1,000 |

`_backup.php` printed `app-20261005-142639.db  240.0 KB  ok` and `--list` showed one snapshot. The file mode was `-rw-------`.

Not measured: restore time on production-size data, pruning (`--keep` was not exercised past one file), cron, off-machine copy, `secret.key` and `config.local.php` handling, concurrent writes during the snapshot.

Safety check: `private/app.db` had size 1,531,904 and modified time 1791208393 before and after the work. The rehearsal never used `private/`.

## 9. Verified facts, missing access, assumptions

| Statement | Class | Evidence or what is missing |
|---|---|---|
| `_backup.php` makes a consistent, integrity-checked snapshot with mode 0600 | Verified (local, synthetic) | Section 8 |
| A snapshot restores and the app opens it | Verified (local, synthetic) | Section 8 |
| `_backup.php` is CLI-only and never runs migrations | Verified by reading code | `_backup.php:23-26, 67-72` |
| `secret.key` is generated on first use with mode 0600, unless `OTIOS_QUIZ_SECRET` is set | Verified by reading code | `_appdb.php:64-78` |
| Pruning keeps the newest N files by name sort | Verified by reading code | `_backup.php:41-45, 112-117` |
| The cron line is installed on the host | UNVERIFIED | Needs `crontab -l` on the host |
| The cron job ran last night, and the newest snapshot is under 26 hours old | UNVERIFIED | Needs the host file listing or `backup.log` |
| Retention on the host is 14 files | UNVERIFIED | Needs the cron line (`--keep` value) |
| An off-machine copy exists, and it is encrypted | UNVERIFIED | Needs the host provider's backup settings or the owner's own job |
| The host provider's backup covers `~/voroave-private/` | UNVERIFIED | Needs the provider's panel |
| `secret.key` and `config.local.php` are saved somewhere else | UNVERIFIED | Needs the owner |
| WAL mode is active on production, or the fallback is used | UNVERIFIED | Open backlog item "Verify WAL on the production host" |
| Production `app.db` size and growth rate | UNVERIFIED | The development file is 1,531,904 bytes only |
| PHP and SQLite versions on the host support `VACUUM INTO` | UNVERIFIED | Needs `php -v` and the SQLite version on the host. The script reports it at run time. |
| The git remote holds `word_ids.tsv` and `editorial.tsv` on another machine | Assumption | Owner confirms |
| Restore on the host takes under 4 hours | Assumption | Needs a drill with access |
| A daily snapshot meets the owner's data-loss tolerance | Assumption | Product decision |

Access needed to close the UNVERIFIED rows: read access to the host's crontab and backup directory listing (names, sizes, dates only, no contents), the provider's backup settings, and the owner's statement about where `secret.key` and `config.local.php` are kept.

## 10. Owner actions (none done here)

1. Confirm or install the cron line. Show `crontab -l` and `php api/_backup.php --list` output.
2. Choose an off-machine option (section 4) and set it up.
3. Approve or change the 26 hour check (section 5).
4. Approve the recovery objectives (section 6).
5. Run the restore drill (section 7) once with real access. Record the result here in section 8 as a new dated block.
