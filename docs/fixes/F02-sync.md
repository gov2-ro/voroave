# F02 — Preserve and acknowledge annotation edits correctly

Status: open. Priority: P1.

## Evidence and target

`public/assets/store.js` clears every word in the sent snapshot after a successful response.
If that word changes during the request, its newer pending edit is also deleted.
Reproduced with the real script in a VM and a deferred fetch response.
The local note survives; the server never receives it unless another action queues it.
`public/api/sync.php` also slices input to 5,000 rows. The client clears the full queue
and ignores rejected rows. Every removed queue entry must have a corresponding acknowledgement.

## Scope and decisions

Own `store.js`, `api/sync.php`, and focused sync tests. Coordinate harness changes through F07.
Preserve local-first writes, tombstones, per-user sequence cursors, and last-write-wins behavior.
Capture the actual submitted values and a local revision for each queued word.
Clear an entry only when the server acknowledges that submitted revision and it remains current.
Use a revision scheme that distinguishes same-millisecond edits; timestamps alone are insufficient.
Apply the same rule to edits, deletions, and re-creations during an in-flight request.
Chunk pushes to the server limit. Keep unsent changes queued and schedule the next batch.
Specify per-word response outcomes for stored, already-current, invalid, and quota-rejected changes.
Do not treat a database no-op as a newly applied update in response accounting.
Transient failures remain queued. Permanent rejection must be visible and must not retry forever.
Retain recoverable local data when a word is rejected. Do not silently discard annotations.
Handle malformed responses before modifying queue state or advancing the pull cursor.
Prevent an old remote echo from resurrecting a newer locally queued tombstone.
Document compatibility when client and server versions differ during deployment.
Do not introduce account claiming, change identity, or change public vote semantics.

## Acceptance

- Edit A, begin a push, edit A again, resolve the first push: the second revision remains queued.
- Repeat with delete/re-create and two edits sharing a clock millisecond.
- A subsequent push sends the newest value and drains only its acknowledged revision.
- Edits to another word during the request survive.
- At least 5,001 queued changes are sent in bounded batches without loss.
- Invalid words and quota rejection do not look like successful saves or cause endless retries.
- Offline/network failure, 429, 500, and malformed JSON preserve pending data.
- New local tombstones beat older remote updates; replay remains idempotent.
- Pull pagination advances only to the rows delivered.
- Run unit race tests and the repaired integration sync suite against an isolated app database.

## Deliverables and boundary

Deliver protocol documentation, client/server changes, and regression tests.
The existing integration fixture uses `abecedar` and `zăbavă`, absent from the audited `ui.db`.
Replace brittle fixtures without weakening assertions. Never test against production accounts.
Stop if implementation requires a new identity model or changes existing stored timestamp semantics.
