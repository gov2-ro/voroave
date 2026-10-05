# Annotation sync protocol

Client: `public/assets/store.js`. Server: `public/api/sync.php`. Brief: `docs/fixes/F02-sync.md`.
Tests: `tests/test_store_sync_race.js` (client, VM) and `tests/test_store_sync.js` (real endpoint).

## Request and reply

```
POST api/sync.php
{ since: <int>, changes: [ {word, rev, bookmarked, note, tags[], updated_at, deleted} ] }

{ server_seq, server_time, changes: [ ...rows with seq > since... ],
  applied, rejected, unchanged,
  outcomes: [ {word, rev, status} ],      // one per submitted change, in order
  has_more }
```

The server reads at most `SYNC_PAGE` (5,000) changes per request. The client sends at most
`SYNC_BATCH` (1,000).

## Revisions (client)

Each edit of a word gets a new `rev` from one counter. The counter only grows. It is stored in
`otios.rev` and is never reused. The queue (`otios.pending`) holds `{ word: { rev, ts, rejected? } }`.
`ts` is the change's `updated_at`. A deleted word keeps a tombstone `ts`.

`updated_at` of a word is always later than its previous `updated_at` and its queued `ts`.
Two edits in one millisecond therefore get timestamps one millisecond apart.
The server keeps a row only if `updated_at` is later than the stored one. Last-write-wins and
the stored timestamp format are unchanged.

## Outcome statuses

| status | meaning | client action |
|---|---|---|
| `stored` | The server wrote the row. | Clear the entry if its `rev` is still current. |
| `current` | Valid, but the server holds the same or a newer `updated_at`. No row changed. | Clear the entry if its `rev` is still current. |
| `invalid` | Unknown word or malformed entry. | Keep the data. Mark the entry `rejected`. Stop retrying. |
| `quota` | New live word while the user is at `MAX_WORDS_PER_USER`. | Keep the data. Mark the entry `rejected`. Stop retrying. |
| `deferred` | Beyond the 5,000-change slice. Not read. | Keep the entry queued. |
| anything else, or missing | Not acknowledged. | Keep the entry queued. |

The server counts a change as `applied` only when `rowCount() > 0`. A refused upsert is `unchanged`.
Deletions are accepted at the quota. The quota counts live words through the whole batch.

A rejected entry is sent again only after a new edit of the word. A new edit clears the mark.
The signal for the user: `<html data-sync-rejected="N">`, the `otios:sync-rejected` event,
and `getRejected()`. No UI was added.

## Client rules

1. Build the batch from the oldest `rev` first. Remember `{word: rev}` for the request.
2. Check the reply first: it must be an object with an array `changes` and a numeric `server_seq`.
   A bad reply changes nothing (queue, data, cursor).
3. Clear a word only if its sent `rev` was acknowledged and the queue still holds that `rev`.
4. Apply remote rows with the queue as it was before the acknowledgements. A queued tombstone
   blocks a remote row whose `updated_at` is not newer than the tombstone.
5. Set the cursor to `server_seq`. The server sets it to the last row it delivered.
6. Schedule the next request (200 ms) if this one made progress and more is queued, or if
   `has_more` and rows or the cursor moved. No progress means no reschedule.
7. Transient failure (offline, HTTP 429/5xx, malformed JSON, bad reply): keep everything.
   The next edit, page load or `visibilitychange` retries. There is no automatic backoff loop.

## Compatibility during deploy

| client | server | result |
|---|---|---|
| old | new | Works. New fields (`outcomes`, `unchanged`) are extra. `rev` is not sent, so outcomes carry `rev: null`. The old client clears its whole snapshot as before. `applied` now excludes no-ops (the old client ignores it). |
| new | old | The reply has no `outcomes`. If `rejected` is 0, the client treats every sent change as stored. Otherwise it cannot tell which word failed, so it clears nothing and does not loop. Old servers read 5,000 changes, and the client sends 1,000. |
| new queue format | old client (same browser) | A browser keeps its `localStorage` across the deploy. An old client reads a new-format queue as `{word: {rev, ts}}` and sends the object as `updated_at`. The server then uses the current time. Avoid by deploying the server and the client files together. |
| old queue format | new client | Entries that are strings load as `rev: 0` and sync normally. |

Deploy the server first, then the client files.

## Known limits

- A change from a device with a clock far behind loses to newer rows. That is last-write-wins.
- An acknowledged tombstone is forgotten locally. An old remote row arriving later (not possible
  in the current server, which keeps one row per word) would recreate the word.
- Quota rejection is tested against the real endpoint only by reasoning, not by a test:
  the cap is 20,000 words.
