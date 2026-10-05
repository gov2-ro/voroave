#!/usr/bin/env python3
"""
Scrape synonyms and antonyms for shortlist words from dexonline.ro.

**Why the *Litera dictionaries* can't come from the dump.** The DEX dump carries
`Definition.internalRep` in full only for sourceId 1 (DEX '98) and 2 (DEX '96) — not "the
Academy dictionaries" as a class, corrected 2026-08-17 (see CLAUDE.md's Synonyms section
and docs/DEFINITIONS_ANALYSIS.md): other Academy titles like DEX '84/'75/DEX-S are
truncated too. The Litera Internațional titles — `Sinonime` (2002), `Sinonime82` (1982),
`Antonime` (2002) — are redacted the same way as everything else outside DEX '98/'96, to
~23 characters plus an ellipsis:

    sourceId 1 (DEX '98)   max length 15,873   mean 192.0
    sourceId 6 (Sinonime)  max length     23   mean  23.0   →  "@AB'A@ s. dimie, păn..."

So the words are known to be in those dictionaries (that is where `dict_count` comes
from) but their contents are not distributed. The rendered page has them.

**This heading used to read "why this can't come from the dump", and that overstatement
is why the `Relation` table went unread for a year.** The dump *does* carry a complete
synonym graph — dexonline's own community-curated one, 158,860 rows, unredacted — which
yields 164,399 word-level synonym pairs over 63,049 words in ~15s with no HTTP. It is a
different artefact by different authors, and the redaction above says nothing about it.
The two sources are complementary: on the 1,542 words both cover, 59% of what this
scraper returns is not in the graph, and 524 of its 2,066 words are absent from the graph
entirely. Keep scraping — but for the gap, not for everything. The graph and its
measurements now live in the separate Sinonime project (~/devbox/sinonime, docs/).

One request per word, against the same URL `scrape_definitions.py` already uses. Be
polite to dexonline.ro — it is community-run — and keep `--delay >= 1.2`.

Output: data/processed/scraped_synonyms.csv
        (word, synonyms, antonyms, source_url, scraped_at, status)
        `status ∈ {ok, not_found, error}`; `ok` means at least one synonym or antonym.
With `--merge`, ok rows are upserted into data/processed/synonyms.db, which
`tools/build_ui_db.py` then folds into `words.synonyms` / `words.antonyms`.

Resume is automatic: re-running skips words already in the checkpoint. Ctrl+C is safe —
each row is flushed immediately.

Usage:
    python scrape_synonyms.py --dry-run --limit 5        # smoke test, no HTTP
    python scrape_synonyms.py --limit 20 --delay 1.2     # small live run
    python scrape_synonyms.py --seam relevant --merge    # the ~2.8k default-view words
    python scrape_synonyms.py --merge                    # everything on the shortlist
    python scrape_synonyms.py --merge-only               # just upsert the checkpoint

    # The Sinonime gap (Sinonime docs/spec.md Phase 4): words with band >= 3 and no
    # synonym edge in its syn.db, ~22,107 words. Sinonime's tools/gap_words.py writes the
    # list; this script only scrapes it. (Until 2026-10-06 this was `--gap`, which read
    # Sinonime's relations.db and syn.db from here.)
    python scrape_synonyms.py --input ../sinonime/data/gap_words.csv --delay 3.0 --merge \
        --output data/processed/scraped_synonyms_gap.csv
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import os
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

DEFAULT_INPUT      = Path('data/processed/forgotten_words_shortlist.csv')
DEFAULT_OUTPUT     = Path('data/processed/scraped_synonyms.csv')
DEFAULT_DB         = Path('data/processed/synonyms.db')
DEXONLINE_LOCK     = Path('data/.dexonline.lock')
DEXONLINE_URL_TMPL = 'https://dexonline.ro/definitie/{}'
USER_AGENT         = 'otios-scraper/0.1 (Romanian linguistic research)'
FIELDNAMES         = ['word', 'synonyms', 'antonyms', 'source_url', 'scraped_at', 'status']

SYNONYM_SOURCES = ('Sinonime', 'Sinonime82')
ANTONYM_SOURCES = ('Antonime',)

# Parenthesised groups are either register markers — (livr.), (rar), (înv. și pop.) — or
# usage examples: (Om ~.), (S-a luptat ~.). Neither is a synonym, and both are always
# parenthesised, so one rule removes both.
_PARENS   = re.compile(r'\([^)]*\)')
_SENSE_NO = re.compile(r'\b\d+\s*\.')
# Grammatical abbreviations that head a sense: "1. adj. brav, cutezător, …"
_POS_ABBR = re.compile(
    r'\b(?:adj|adv|s|sf|sm|sn|vb|vt|vi|interj|art|pron|prep|conj|num|pl|sg)\s*\.', re.I)
# "v. cutare" is a cross-reference to another entry, not a synonym.
_SEE_ALSO = re.compile(r'\bv\s*\.\s*[^,;.]+', re.I)
_SPLIT    = re.compile(r'[,;.]')
# A headword run: capitals, possibly several words, followed by whitespace. One letter is
# enough — DEX has single-letter headwords (A, Î, O) — and synonyms are lowercase, so a
# leading capital is a headword rather than content.
_LEADING_CAPS = re.compile(r"^[A-ZĂÂÎȘȚ][A-ZĂÂÎȘȚ0-9'\- ]*\s+")
_HAS_LOWER    = re.compile(r'[a-zăâîșț]')


def normalize(text: str) -> str:
    return unicodedata.normalize(
        'NFC', text.lower().replace('ş', 'ș').replace('ţ', 'ț'))


def _strip_stress(text: str) -> str:
    """Drop acute/grave accents used to mark stress, keeping Romanian ă/â/î/ș/ț."""
    out = []
    for ch in unicodedata.normalize('NFD', text):
        if ch in ('́', '̀'):      # combining acute / grave
            continue
        out.append(ch)
    return unicodedata.normalize('NFC', ''.join(out))


def parse_word_list(text: str, headword: str) -> list[str]:
    """Turn one Sinonime/Antonime entry body into a clean list of words.

        "CURAJOS adj., adv. 1. adj. brav, cutezător, dârz, …, (livr.) intrepid,
         …, (înv.) hrăbor, neînfricoșat. (Om ~.) 2. adj. bărbătesc, viteaz, …"
      → ['brav', 'cutezător', 'dârz', …, 'intrepid', …, 'hrăbor', 'neînfricoșat',
         'bărbătesc', 'viteaz', …]

    Order is preserved and duplicates dropped, so the first sense's synonyms — the ones
    a reader most likely wants — come first.
    """
    text = _PARENS.sub(' ', text)
    text = _SEE_ALSO.sub(' ', text)

    text = _SENSE_NO.sub(' ', text)
    text = _POS_ABBR.sub(' ', text)

    hw = normalize(_strip_stress(headword))
    out: list[str] = []
    seen: set[str] = set()
    for part in _SPLIT.split(text):
        w = _strip_stress(part).strip(' \t\n -–—*≠~')
        if not w or '~' in w:
            continue
        # One page carries several Sinonime entries and each opens with its own headword
        # in capitals — sometimes mid-token, because the markup does not fence it off:
        # "ROZĂ     trandafir, rug", "CELE ZECE PORUNCI     decalogul". Strip a leading
        # all-caps run, then drop whatever is still all-caps. Romanian synonyms are
        # lowercase; headwords are not.
        w = ' '.join(_LEADING_CAPS.sub('', w).split())
        if not w or not _HAS_LOWER.search(w):
            continue
        # Multi-word synonyms are real ("a-și da duhul"), but anything this long is a
        # sentence fragment the markup did not fence off.
        if len(w) > 40 or len(w.split()) > 4:
            continue
        key = normalize(w)
        if key == hw or key in seen or len(key) < 2:
            continue
        seen.add(key)
        out.append(w)
    return out


def _entry_source(wrapper) -> str:
    """The dictionary a `.defWrapper` came from, e.g. 'Sinonime (2002)'."""
    details = wrapper.select_one('.defDetails')
    if details is None:
        return ''
    text = details.get_text(' ', strip=True)
    m = re.search(r'sursa:\s*([^,]+?)\s*(?:\(|adăugată|acțiuni|$)', text)
    return m.group(1).strip() if m else ''


_DIACRITICS = str.maketrans('ăâîșțĂÂÎȘȚ', 'aaistAAIST')


def _fold(text: str) -> str:
    """Fold for headword comparison: stress marks, diacritics and case all removed."""
    return normalize(_strip_stress(text)).translate(_DIACRITICS).lower()


def _entry_headword(text: str) -> str:
    """The headword an entry opens with, e.g. 'ROZĂ' or 'CELE ZECE PORUNCI'.

    Antonime entries are formatted `Curajos ≠ fricos, laș` — headword in ordinary case,
    so the all-caps pattern misses it and everything before the ≠ is the headword.
    """
    if '≠' in text:
        return text.split('≠', 1)[0].strip()
    m = _LEADING_CAPS.match(text)
    return m.group(0).strip() if m else ''


def parse_relations(html: str, word: str) -> tuple[list[str], list[str]]:
    """Return (synonyms, antonyms) from a dexonline definition page.

    A dexonline page shows every entry it considers related, not only the one asked for:
    `/definitie/roză` also renders `ROZ` (the colour), whose synonyms — trandafiriu,
    rozatic, pembe — belong to a different word. Entries are therefore matched on their
    headword first.

    The fallback matters more than it looks: archaic spellings are the whole point of
    this project, and dexonline normalises them. `/definitie/poronci` returns entries
    headed `PORUNCĂ` and `PORUNCI` and none headed `PORONCI`, so a strict match would
    return nothing for exactly the words we care about. When no entry matches, take them
    all — the page is dexonline's own answer to that query.
    """
    soup = BeautifulSoup(html, 'lxml')
    target = _fold(word)
    syns: list[str] = []
    ants: list[str] = []
    # (is_synonym, headword, text) per relation entry on the page
    entries: list[tuple[bool, str, str]] = []
    for wrapper in soup.select('#tab_0 .defWrapper'):
        source = _entry_source(wrapper)
        if not source:
            continue
        is_syn = source.startswith(SYNONYM_SOURCES)
        if not is_syn and not source.startswith(ANTONYM_SOURCES):
            continue
        body = wrapper.select_one('p')
        if body is None:
            continue
        # '' rather than ' ': dexonline wraps the stressed vowel in its own element, so a
        # separator turns "CURAJOS" into "CURAJ O S".
        text = ' '.join(body.get_text('').split())
        entries.append((is_syn, _fold(_entry_headword(text)), text))

    strict = [e for e in entries if e[1] == target]
    # Entries whose headword could not be read are kept alongside the matches rather than
    # discarded — an unreadable headword is not evidence of a different word.
    keep = [e for e in entries if e[1] == target or not e[1]] if strict else entries
    for is_syn, _hw, text in keep:
        if is_syn:
            syns.extend(parse_word_list(text, word))
        else:
            # "Curajos ≠ fricos, laș" — everything after the ≠ is the antonym list.
            ants.extend(parse_word_list(text.split('≠', 1)[-1], word))

    def dedupe(items: list[str]) -> list[str]:
        seen, out = set(), []
        for w in items:
            k = normalize(w)
            if k not in seen:
                seen.add(k)
                out.append(w)
        return out

    return dedupe(syns), dedupe(ants)


def fetch(session: requests.Session, word: str) -> tuple[str, list[str], list[str], str]:
    """Fetch one word. Returns (status, synonyms, antonyms, url)."""
    url = DEXONLINE_URL_TMPL.format(quote(word, safe=''))
    for attempt in (1, 2):
        try:
            resp = session.get(url, timeout=20)
        except requests.RequestException as exc:
            if attempt == 1:
                print(f'  Network error ({type(exc).__name__}); retrying in 30s…')
                time.sleep(30)
                continue
            print(f'  Network error for "{word}": {exc}. Skipping.')
            return 'error', [], [], url

        if resp.status_code in (429, 503):
            if attempt == 1:
                print(f'  HTTP {resp.status_code}; sleeping 30s then retrying…')
                time.sleep(30)
                continue
            return 'error', [], [], url
        if resp.status_code != 200:
            return 'error', [], [], url

        syns, ants = parse_relations(resp.text, word)
        return ('ok' if (syns or ants) else 'not_found'), syns, ants, url

    return 'error', [], [], url


def load_checkpoint(output_path: Path, retry_not_found: bool = False) -> set[str]:
    if not output_path.exists():
        return set()
    done: set[str] = set()
    with output_path.open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            if retry_not_found and row.get('status') == 'not_found':
                continue
            if row.get('word'):
                done.add(row['word'])
    return done


def load_words(input_path: Path, seam: str | None) -> list[str]:
    words: list[str] = []
    with input_path.open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            if seam and (row.get('seam') or '') != seam:
                continue
            w = (row.get('word') or '').strip()
            if w:
                words.append(w)
    return words


def merge_into_db(csv_path: Path, db_path: Path) -> int:
    if not csv_path.exists():
        print(f'Nothing to merge: {csv_path} not found')
        return 0
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS synonyms (
            word     TEXT PRIMARY KEY,
            synonyms TEXT,
            antonyms TEXT
        )
    """)
    n = 0
    with csv_path.open(encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            if row.get('status') != 'ok':
                continue
            conn.execute('INSERT OR REPLACE INTO synonyms VALUES (?,?,?)',
                         (row['word'], row.get('synonyms') or None,
                          row.get('antonyms') or None))
            n += 1
    conn.commit()
    conn.close()
    return n


class LockHeld(Exception):
    """Another process is already making requests to dexonline.ro."""


def acquire_host_lock(path: Path = DEXONLINE_LOCK):
    """
    Serialise every process that makes requests to dexonline.ro.

    `--delay` is a *per-process* guard, so two copies of this script each politely
    waiting 3s still hit a community-run site every 1.5s — which is exactly what
    happened on 2026-08-08. The lock makes the delay mean what it says.

    Keyed on the **host**, not on this script: `scrape_definitions.py` talks to the
    same site, so it interlocks with this one by adopting the same two lines rather
    than getting a lock of its own that permits the same doubling.

    `flock`, not a PID file: the kernel releases it when the process dies, so a
    SIGKILLed run cannot strand a stale lock that someone has to `rm` by hand. The
    pid written inside is only ever read back to name the holder in the error.

    Returns the open handle — **keep a reference for the duration of the run**,
    since closing it releases the lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+', encoding='utf-8')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.seek(0)
        holder = handle.read().strip() or 'holder unknown'
        handle.close()
        raise LockHeld(holder) from None
    handle.seek(0)
    handle.truncate()
    handle.write(f'pid {os.getpid()} since '
                 f'{datetime.now(timezone.utc).isoformat(timespec="seconds")}\n')
    handle.flush()
    return handle


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--input',  type=Path, default=DEFAULT_INPUT)
    ap.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument('--db',     type=Path, default=DEFAULT_DB)
    ap.add_argument('--seam', choices=['relevant', 'curiosity'], default=None,
                    help='Only scrape one seam (relevant = the ~2.8k default view)')
    ap.add_argument('--limit', type=int, default=None, help='Cap words this run')
    ap.add_argument('--delay', type=float, default=1.2,
                    help='Seconds between requests (default: %(default)s)')
    ap.add_argument('--dry-run', action='store_true',
                    help='Print URLs only; no HTTP requests, no output written')
    ap.add_argument('--merge', action='store_true',
                    help='Upsert ok rows into the synonyms DB when the run finishes')
    ap.add_argument('--merge-only', action='store_true',
                    help='Skip scraping; just merge an existing checkpoint into the DB')
    ap.add_argument('--retry-not-found', action='store_true',
                    help='Re-queue words previously recorded as not_found')
    args = ap.parse_args()

    min_delay = 1.2
    if args.delay < min_delay and not args.dry_run:
        print(f'Refusing --delay {args.delay}: dexonline.ro is community-run, keep it '
              f'at {min_delay}s or more.', file=sys.stderr)
        return 1

    if args.merge_only:
        n = merge_into_db(args.output, args.db)
        print(f'Merged {n:,} rows → {args.db}')
        return 0

    if not args.input.exists():
        print(f'Missing: {args.input} — run make_shortlist.py first.', file=sys.stderr)
        return 1

    # Taken before the queue is planned, so a second run hears why it is stopping
    # instead of a plan it will not carry out. Dry runs make no requests and so stay
    # lock-free: inspecting the queue while a scrape is going is legitimate.
    # Held for the rest of the run — `lock` looks unused, but closing it unlocks.
    lock = None                                                       # noqa: F841
    if not args.dry_run:
        try:
            lock = acquire_host_lock()                                # noqa: F841
        except LockHeld as held:
            print(f'Another dexonline scrape is already running ({held}).\n'
                  f'Two at once halve the interval between requests, which is the '
                  f'one thing --delay exists to prevent. Wait for it, or stop it '
                  f'first.', file=sys.stderr)
            return 1

    words = load_words(args.input, args.seam)
    done  = load_checkpoint(args.output, args.retry_not_found)
    todo  = [w for w in words if w not in done]
    if args.limit:
        todo = todo[:args.limit]

    scope = f' (seam={args.seam})' if args.seam else ''
    print(f'{len(words):,} words{scope}; {len(done):,} already done; '
          f'{len(todo):,} to fetch')
    if not todo:
        print('Nothing to do.')
        if args.merge:
            print(f'Merged {merge_into_db(args.output, args.db):,} rows → {args.db}')
        return 0

    if args.dry_run:
        for w in todo:
            print(f'  {DEXONLINE_URL_TMPL.format(quote(w, safe=""))}')
        eta = len(todo) * args.delay / 3600
        print(f'\nDry run: {len(todo):,} URLs, 0 requests made. '
              f'A live run would take ~{eta:.1f}h at {args.delay}s.')
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    new_file = not args.output.exists()
    session = requests.Session()
    session.headers['User-Agent'] = USER_AGENT

    counts = {'ok': 0, 'not_found': 0, 'error': 0}
    with args.output.open('a', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if new_file:
            writer.writeheader()
        for i, word in enumerate(todo, 1):
            status, syns, ants, url = fetch(session, word)
            counts[status] += 1
            writer.writerow({
                'word': word,
                'synonyms': ', '.join(syns),
                'antonyms': ', '.join(ants),
                'source_url': url,
                'scraped_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'status': status,
            })
            f.flush()
            print(f'  [{i}/{len(todo)}] {word:<24} {status:<10} '
                  f'{len(syns)} syn, {len(ants)} ant')
            if i < len(todo):
                time.sleep(args.delay)

    print(f'\nok {counts["ok"]:,} · not_found {counts["not_found"]:,} · '
          f'error {counts["error"]:,}  →  {args.output}')
    if args.merge:
        print(f'Merged {merge_into_db(args.output, args.db):,} rows → {args.db}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
