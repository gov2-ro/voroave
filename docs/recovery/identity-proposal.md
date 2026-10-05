# Identity and account recovery: proposal

Status: proposal ready for owner decision. Implementation is BLOCKED on the owner's product decision.
Scope: planning only (brief [F10](../fixes/F10-recovery.md)). No account was merged. No Google account was connected.
No credential was rotated. No code changed.

## 1. Current identity lifecycle (as the code implements it)

The device cookie is the account. There is no login.

| Step | Behaviour | Source |
|---|---|---|
| Mint | A request with no valid cookie creates a new `users` row and a new `devices` row. | `public/api/_auth.php:51-98` |
| Token | 32 random bytes, base64url, no padding (`random_bytes(32)`). | `_auth.php:77` |
| Public id | 8 random bytes in hex, stored in `users.public_id`. | `_auth.php:78` |
| Storage on server | Only `sha256(token)` is stored in `devices.token_hash` (UNIQUE). A leaked database holds no usable token. | `_auth.php:47-50, 84-90`; `_appdb.php:257-265` |
| Lookup | Cookie must be 32 characters or longer. Join `devices` to `users` on the hash. | `_auth.php:59-73` |
| Cookie name | `otios_dev`. | `_auth.php:12` |
| Cookie flags | `HttpOnly`, `SameSite=Lax`, `Secure` only when the request is HTTPS (or `X-Forwarded-Proto: https`). | `_auth.php:35-44, 15-18` |
| Cookie path | `BASE` as a percent-encoded path (`/` on a root deploy). | `_auth.php:29-33` |
| Lifetime | 400 days. Every valid request re-sets the cookie (sliding expiry). | `_auth.php:13, 71` |
| Unknown token | A cookie whose hash is not in `devices` is ignored. The server mints a new user. | `_auth.php:76-98` |
| Request body | No endpoint trusts a user id from the body. | `_auth.php:47-50` (comment) |
| Other writes | `last_seen_at` is updated on both `devices` and `users` on every request. | `_auth.php:62-70` |

Schema facts that matter for recovery (`public/api/_appdb.php:244-390`):

- `users.nickname`, `email`, `auth_provider`, `auth_subject` exist and are nullable. `idx_users_auth` is unique on `(auth_provider, auth_subject)`.
- `devices.user_id` is a foreign key. Several devices can point to one user. Today every user has exactly one device.
- `annotations` has primary key `(user_id, word)`. Columns: `bookmarked`, `note`, `tags`, `updated_at`, `seq`, `deleted`.
- `lists.slug` is UNIQUE across all users. `lists.user_id` owns the list. `lists.source_tag` names the bucket it snapshots.
- `game_events` is an append-only log. `game_stats` is a derived cache with primary key `(user_id, mode)`.
- `feed_decisions` has primary key `(user_id, word)`. `reports` has a unique index on `(list_id, user_id)`. `rate_limits` has primary key `(user_id, bucket)`.

### What survives what

Data lives in two places. `app.db` on the server is the store of record. `localStorage` is an offline-first cache
(`public/assets/store.js:1-15`). Keys: `otios.research` (words), `otios.pending` (push queue), `otios.sync` (cursor), `otios.rev`.
Sync runs through `api/sync.php`, which resolves conflicts per word by last write wins on `updated_at` (`sync.php:15-18, 102-109`).

| Event | Annotations | Lists, scores, nickname | Result |
|---|---|---|---|
| localStorage cleared, cookie kept | Survive on the server. The next sync with `since=0` restores them. | Survive. | Full recovery, automatic. |
| Cookie lost (cleared, new browser, 400 days idle), localStorage kept | Server rows stay under the old user. The browser gets a NEW user on the next request. The old local cache then pushes to the new user (the one-time legacy push in `store.js:402-412` marks stored words dirty). | Stay with the old, now unreachable, user. | Annotations are copied by accident. Lists, nickname, scores and game history are stranded. Published lists stay public under the old user. |
| Both lost | Server rows exist but nobody can reach them. | Same. | Total loss for that person. No warning is shown. |
| New device, no data | Empty new user. | Empty. | The person cannot bring data over. |
| Server `app.db` lost, no backup | localStorage can refill annotations only. | Gone. | Partial. See the backup runbook. |

Measured facts from the backlog (not re-measured here): 858 users and 858 devices at the time of the 2026-08-12 note, one each.
The remote `app.db` holds three `pax1` users, which is one person with three tokens (`docs/BACKLOG.md`, entry "Remote app.db has three `pax1` users").

### What several devices mean for community counts

Community counts are per `user_id` (`vote_counts_subquery()`, `mark_counts_subquery()`, `_appdb.php:182-236`).
One person with a phone and a laptop is two users, so a word they mark on both counts twice in `n_up`, `n_fav` and `votes`.
Two effects follow:

1. Honest inflation: one person can count as N voters for N devices or cookie clears.
2. Dilution of identity: `export_editorial.py --user N` must pick one id, and marks split over several ids.

Votes only reorder (`populare`, damped). They never hide a word. So the damage is bounded. A merge reduces it. It does not remove it,
because an abuser can still clear cookies on purpose. That is a known limit of anonymous identity, and the project accepts it.

## 2. Hard constraints for any option

1. Never expose the `otios_dev` token to JavaScript. Keep it `HttpOnly`.
2. Never use browser fingerprinting, user-agent matching or IP matching as a recovery or merge signal. The earlier assessment in `docs/BACKLOG.md` ("Historical transferable link code assessment") already rejected it. It causes false merges (shared laptop, one NAT) and false splits (UA changes), and it is tracking.
3. Never hand out the device token itself. It is a 400-day account key.
4. A merge never runs without proof of control of BOTH sides, or an explicit, logged owner action.
5. Votes can only reorder. Keep this rule after a merge.

## 3. Option A: recovery code / device link

### Flow

Two sub-flows share one table.

- Link a new device. On the device that holds the data, the person presses "Leagă alt dispozitiv". The server creates a one-time link code. The person types it on the new device. The new device receives its own new device token, attached to the SAME user. Nothing is copied.
- Recover after loss. Before the loss, the person saved a long recovery code (shown once, like a backup code). After the loss, the person enters it on a new browser. The server attaches a new device to the old user. This is the only path that helps with a lost cookie.

A recovery code and a link code are different things.

| Property | Link code | Recovery code |
|---|---|---|
| Purpose | Add a device while the old one still works | Regain the account after losing every device |
| Entropy | At least 50 bits. Example: 10 characters from a 32-letter alphabet, grouped `XXXXX-XXXXX`. | At least 128 bits (26 characters base32, or 6 to 8 words). |
| Lifetime | 10 minutes, single use | No expiry. The owner may rotate it. Using it burns it and shows a new one. |
| Server storage | `sha256(code)` plus `expires_at`, `used_at`, `user_id`. Never the code. | Same, with a slow hash allowed. At 128 bits a plain `sha256` is enough. |
| Creation | Needs a live device. | Needs a live device. Shown once, never again. |

### Proposed storage (for a future migration, not applied)

`user_version` 5 would add `link_codes(id, user_id, code_hash UNIQUE, kind, created_at, expires_at, used_at, used_by_device)`.
No change to `users` or `devices` is needed. This matches the upgrade path named in the `_auth.php` header.

### Abuse cases

| Case | Mitigation |
|---|---|
| Code guessing | 50 bits and 10 minutes make a blind guess about 1 in 10^15 per try. Add a per-IP and a global rate limit on redemption, because attackers can mint many anonymous users (see below). |
| Brute force from many users | `rate_limit()` is keyed on `user_id` (`_appdb.php:527`). An attacker clears cookies to get a new `user_id` each time. A redemption limit MUST be keyed on IP (hashed, short retention) and on a global counter. This is a new key type. It is not fingerprinting, because it is a rate limit that decides nothing about identity. |
| Replay | Single use. Set `used_at` in the same transaction that attaches the device. |
| Code in a screenshot or chat | A link code dies in 10 minutes. A recovery code is a permanent secret. The UI must say so. Offer "rotate recovery code". |
| Phishing | No third party is involved. A fake site cannot receive a code usefully unless the person types it there. Show the code only on the real domain. Do not send it by email. |
| Shared device | The person logs out of a shared device with "ieși de pe acest dispozitiv". This deletes that `devices` row. Add a device list (`user_agent`, `last_seen_at`) with revoke buttons. |
| Enumeration | The redemption reply is identical for "wrong" and "expired". |
| Stolen cookie | Out of scope for both options. Revoking a device row fixes it. |

### UX

- No sign-up. A "cont" block in the footer or a small settings page. This is a design decision for the owner.
- The person must act BEFORE the loss to get a recovery code. Most people will not. That is the main weakness. A first-time nudge after N marks helps.
- Language: Romanian, short. The warning "fără cod, datele se pierd" must be plain.

### Data protection

- No new personal data. The server stores only hashes of codes and the device `user_agent` it already stores.
- A new retention rule is needed for hashed IP rate-limit rows (suggest 24 hours).
- Deleting a user deletes the codes (`ON DELETE CASCADE`).

### Operational cost

Small. One table, three endpoints (create, redeem, revoke), one settings view. No external service. No secret to rotate. About 300 lines of PHP plus tests.

## 4. Option B: OAuth (Google)

### Flow

The person presses "Conectează cu Google". The server runs an authorization-code flow with PKCE and a signed `state`. It reads the stable `sub` claim and the email. It stores `auth_provider='google'`, `auth_subject=sub`, `email`. On a new browser the person signs in and the server attaches a new device to that user.

### Abuse cases

| Case | Notes |
|---|---|
| Account takeover of the Google account | The project inherits the risk. Google's own controls apply. |
| CSRF on the callback | Needs `state` bound to the session. Today there is no session besides the device cookie. Bind `state` to a short-lived sealed token (`seal_token()` exists in `_appdb.php:455`). |
| Phishing | Lower risk for the user (Google owns the login page). The site then needs a real consent screen and a verified domain. |
| Two Google accounts for one person | Still two users. A merge is still needed. |
| Merge by email | Never merge on email alone. Merge on `(provider, sub)`. |
| Shared device | The device stays signed in for 400 days unless the person logs out. |
| Rate limits | Google rate-limits the flow. The callback endpoint still needs an IP-keyed limit. |

### UX

Easiest for the user. Works after a total loss with no earlier preparation. Needs an account on a third-party service. Many visitors will not want to sign in to read a dictionary site.

### Data protection (GDPR)

- It adds personal data: email and Google `sub`. The site now needs a privacy notice, a lawful basis, a deletion path and a processor record. The site currently stores no email.
- It sends data to Google (a transfer outside the project's control). The owner must decide if that fits the project.
- The anonymous design is a feature of the site today. OAuth changes the product.

### Operational cost

Higher. A Google Cloud project, a consent screen, verification, client secret in `config.local.php`, secret rotation, redirect URI per deploy, an extra dependency on an external service that can change its terms. About 120 lines of PHP plus the merge (the backlog estimate), but the non-code work is larger.

## 5. Comparison and recommendation

| Criterion | A: code / link | B: Google OAuth |
|---|---|---|
| Works after total loss | Only if a recovery code was saved | Yes |
| New personal data | None | Email, Google subject |
| External dependency | None | Google |
| Setup effort by owner | Low | Medium to high |
| User effort before loss | Must save a code | None |
| Fits the anonymous design | Yes | No |
| Abuse surface | Code guessing, rate limits | Third-party takeover, CSRF |

Recommendation: Option A. Build the link code first. Add the recovery code in the same release.
Reason: it needs no new personal data, no external service and no new legal basis. It keeps the anonymous model.
Option B can be added later as one more way to attach a device to a user, because the schema already has the columns.

This is a recommendation only. IMPLEMENTATION IS BLOCKED until the owner decides:

1. Option A, Option B, both, or neither.
2. Whether a recovery code (pre-loss) is in scope, or only the link code.
3. Which merge policy in section 6 applies when the new browser already holds data.
4. Where the "cont" screen lives.

## 6. Future merge specification

A merge moves the data of a SOURCE user into a TARGET user and re-points the source's devices. It runs once, in one SQLite transaction, after a snapshot (see the backup runbook). It is never run by a script on production without the owner's authorization.

Preconditions: proof of control of the target (live device or valid code) and, for the source, a redeemed code or a signed-in provider subject.
Choose the target as the OLDER user by `created_at`, unless the owner decides otherwise. The target keeps its `public_id`, so old share links and the admin view stay stable.

### Annotations

Primary key `(user_id, word)` can collide.

- Per word, keep the row with the greater `updated_at` (the same last write wins rule that `sync.php` uses). Tie: keep the target's row.
- Copy tombstones (`deleted = 1`) as ordinary rows. A newer tombstone beats an older live row. This stops a deleted mark from returning after a merge. Keep tombstones at least until every device has synced; the proposal is to keep them for the life of the user (they are small).
- Give every merged row a fresh `seq` above the target's current maximum, so other devices of the target pick the changes up on the next delta sync. Do not copy the source's `seq`.
- Do not merge `note` text or `tags` between two rows. Mixing makes a result nobody wrote. The chosen row wins whole.
- Respect `MAX_WORDS_PER_USER` (20,000). If the union exceeds it, keep the newest rows and report the count dropped in the merge log.

### Lists

- All of the source's lists move to the target: `UPDATE lists SET user_id = :target`.
- `slug` is globally UNIQUE, so slugs never collide. Slugs and share URLs stay valid.
- `publish_bucket` assumes one list per `(user_id, source_tag)`. After the move there may be two `fav` lists. Keep both rows. Keep the one with the newer `updated_at` as the live bucket list and set the other's `source_tag` to `''` (hand-assembled). It then appears under "Alte liste" and nothing is lost. The owner can delete it by hand.
- Respect `MAX_LISTS_PER_USER` (50). Excess lists stay with the source user and are listed in the merge log, so the owner can decide. No list is deleted.
- `reports`: unique `(list_id, user_id)`. When the source reported a list the target already reported, drop the duplicate. Keep all others.
- A moderation decision (`removed`, `dismissed`) is attached to the list and stays.

### Game data

- `game_events`: append-only, so `UPDATE game_events SET user_id = :target`. No collision.
- `game_stats`: primary key `(user_id, mode)`. Rebuild the target's rows from the merged `game_events` rather than adding numbers. Rebuild `total` and `correct` by count. Compute `best_streak` as the maximum of the two stored values, because a streak is not recoverable from a mixed log. Set `streak` to the value of the row with the later `updated_at`.
- `feed_decisions`: per word, keep the later `created_at`.
- `rate_limits`, `quiz_nonces`: do not merge. Delete the source's rate-limit rows.

### Nickname

- Keep the target's nickname if it has one. Otherwise take the source's.
- `users.nickname` has no unique index today, so no collision error occurs. A person can see two identical nicknames on the leaderboard. Out of scope here; note it as an open item.

### Devices and the source user

- `UPDATE devices SET user_id = :target WHERE user_id = :source`.
- Do not delete the source user row in the same step. Mark it merged (a future column `merged_into`) and keep it for 30 days for undo, then delete. Deletion cascades, so everything must have been moved first. Check that counts match before deleting.

### Community counts

- After the merge there is one `user_id` per person, so the `(user_id, word)` primary key gives one vote per person per word. Counts drop on words both users marked. This is the intended correction.
- Vote deduplication across people is NOT attempted. Two real people stay two voters. Identity stays anonymous.
- The tracked file `data/editorial.tsv` is exported per user (`--user N`). After a merge, re-run the export with the target id and check the diff. The owner decides which id is canonical. This is the `pax1` case.
- `/colectii` ranks distinct people. A merge lowers some ranks. This needs no code change, only a note in the release text.

### Audit and undo

- Write a merge log row (source, target, counts moved, counts dropped, time). Use a new table or a file under the private directory.
- Take a `VACUUM INTO` snapshot immediately before the merge. Undo is a restore of that snapshot into a disposable copy and a targeted re-import. There is no in-place undo.

### Tests the future implementation needs

Conflicting annotation (older versus newer, tombstone versus live), slug preserved, two `fav` lists, over-quota union, `game_stats` rebuild, vote count before and after, idempotent second run, and a rollback when any step fails.

## 7. Open items for the owner

- Choose among the options in section 5.
- Decide the policy for a new browser that already holds data (section 3 step 2 of the earlier backlog note: abandon, merge, or refuse). This proposal specifies "merge with last write wins", which is the second choice. The first choice (abandon the new user's data) is simpler and safer for a first release. The owner may prefer it.
- Decide the retention of hashed IP rate-limit rows.
- Decide whether the three duplicate `pax1` users are merged by hand with this procedure.
