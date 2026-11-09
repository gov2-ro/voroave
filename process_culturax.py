#!/usr/bin/env python3
"""
Count DEX word occurrences in CulturaX Romanian (modern web corpus).

Uses per-parquet-file checkpointing with row-group-level resume to survive
repeated SIGKILL restarts. Reads the 64 parquet shards directly via
HfFileSystem + pyarrow, avoiding the HuggingFace ds.skip(N) cycling bug
that triggers when N exceeds the total dataset size.

Checkpoint schema (culturax_checkpoint.json):
  completed_files           — filenames fully processed
  current_file              — filename in progress (or null)
  current_file_rows_done    — rows of current_file counted so far
  current_file_tokens_done  — tokens of current_file counted so far
  docs_in_completed_files   — total docs across all completed files
  tokens_in_completed_files — total tokens across all completed files

Total docs = docs_in_completed_files + current_file_rows_done
On SIGKILL the last COMMIT_EVERY rows are lost (re-processed on next run).
On SIGTERM/SIGHUP the current batch is flushed cleanly before exit.

Usage:
    python process_culturax.py              # full run (hours)
    python process_culturax.py --test       # first 1000 docs, no resume
    python process_culturax.py --limit N    # stop after N total docs
    python process_culturax.py --resume     # pick up from checkpoint

Restart loop (stop automatically on success):
    while true; do
        python -u process_culturax.py --resume
        [ $? -eq 0 ] && break
        echo "[$(date)] restarting in 15s..." && sleep 15
    done

Output: data/processed/corpus_frequencies.db  (corpus_name = 'culturax_ro')
"""

import argparse
import json
import re
import signal
import sqlite3
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from constants import model_types_sql

_shutdown = False


def _handle_signal(sig, frame):
    global _shutdown
    print(f'\n[{datetime.now()}] Signal {sig} — flushing and exiting after current batch',
          flush=True)
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGHUP, _handle_signal)


LEXEMES_DB      = Path('data/processed/lexemes.db')
FREQ_DB         = Path('data/processed/corpus_frequencies.db')
CHECKPOINT      = Path('data/processed/culturax_checkpoint.json')


def use_db(db: Path) -> None:
    """Point FREQ_DB at `db`. A non-default DB gets its own checkpoint beside it."""
    global FREQ_DB, CHECKPOINT
    if Path(db) != FREQ_DB:
        CHECKPOINT = Path(db).with_name(Path(db).stem + '.' + CHECKPOINT.name)
    FREQ_DB = Path(db)
CORPUS_NAME     = 'culturax_ro'
COMMIT_EVERY    = 5_000
HF_PARQUET_DIR  = 'datasets/uonlp/CulturaX/ro'


# ---------------------------------------------------------------------------
# Text processing
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    return unicodedata.normalize('NFC',
        text.lower().replace('ş', 'ș').replace('ţ', 'ț'))


def tokenize(text: str) -> list[str]:
    text = normalize(text)
    tokens = re.findall(r"[a-zăâîșț](?:[a-zăâîșț\-']*[a-zăâîșț])?", text)
    return [t for t in tokens if len(t) > 2 and not t.isdigit()]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def load_dex_words(lexemes_db: Path) -> set[str]:
    conn = sqlite3.connect(lexemes_db)
    # Accept words that have a POS description OR a word-class modelType prefix.
    # Many canonical entries (e.g. "jurnalism", "ziar") have empty description
    # but a valid modelType (N=noun, F=fem., A=adj., V/VT/VI=verb, etc.; constants.CORPUS_LOOKUP_MODEL_TYPES) — they
    # must be included or their corpus occurrences are silently discarded.
    rows = conn.execute("""
        SELECT DISTINCT lower(formNoAccent)
        FROM Lexeme
        WHERE typeof(frequency) = 'real'
          AND frequency > 0.01
          AND LENGTH(formNoAccent) > 2
          AND (
            (description != '' AND description IS NOT NULL)
            OR modelType IN """ + model_types_sql() + """
          )
    """).fetchall()
    conn.close()
    return {normalize(r[0]) for r in rows}


def init_freq_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS corpus_word_frequency (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            word              TEXT NOT NULL,
            corpus_name       TEXT NOT NULL,
            occurrence_count  INTEGER DEFAULT 0,
            document_count    INTEGER DEFAULT 0,
            last_updated      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(word, corpus_name)
        );
        CREATE INDEX IF NOT EXISTS idx_corpus_word
            ON corpus_word_frequency(word, corpus_name);
        CREATE TABLE IF NOT EXISTS processing_stats (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            corpus_name             TEXT NOT NULL,
            documents_processed     INTEGER DEFAULT 0,
            tokens_processed        INTEGER DEFAULT 0,
            unique_words_found      INTEGER DEFAULT 0,
            processing_time_seconds REAL,
            completed_at            TIMESTAMP,
            status                  TEXT DEFAULT 'in_progress'
        );
    """)
    conn.commit()
    return conn


def flush(conn: sqlite3.Connection, word_counts: dict, doc_counts: dict) -> None:
    if not word_counts:
        return
    ts = datetime.now()
    conn.executemany("""
        INSERT INTO corpus_word_frequency
            (word, corpus_name, occurrence_count, document_count, last_updated)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(word, corpus_name) DO UPDATE SET
            occurrence_count = occurrence_count + excluded.occurrence_count,
            document_count   = document_count   + excluded.document_count,
            last_updated     = excluded.last_updated
    """, [(w, CORPUS_NAME, c, doc_counts[w], ts) for w, c in word_counts.items()])
    conn.commit()
    word_counts.clear()
    doc_counts.clear()


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------

def _empty_checkpoint() -> dict:
    return {
        'completed_files': [],
        'current_file': None,
        'current_file_rows_done': 0,
        'current_file_tokens_done': 0,
        'docs_in_completed_files': 0,
        'tokens_in_completed_files': 0,
    }


def load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        try:
            data = json.loads(CHECKPOINT.read_text())
            cp = _empty_checkpoint()
            cp.update(data)
            return cp
        except (json.JSONDecodeError, ValueError):
            print('Warning: corrupted checkpoint, starting fresh')
    return _empty_checkpoint()


def save_checkpoint(cp: dict) -> None:
    tmp = CHECKPOINT.with_suffix('.tmp')
    tmp.write_text(json.dumps(cp, indent=2))
    tmp.replace(CHECKPOINT)


# ---------------------------------------------------------------------------
# Parquet processing
# ---------------------------------------------------------------------------

def list_parquet_files() -> list[str]:
    from huggingface_hub import HfFileSystem
    fs = HfFileSystem()
    paths = fs.ls(HF_PARQUET_DIR, detail=False)
    return sorted(p for p in paths if p.endswith('.parquet'))


def process_file(
    hf_path: str,
    dex_words: set,
    conn: sqlite3.Connection,
    cp: dict,
    start_row: int,
    limit: int | None,
    global_start: float,
) -> tuple[int, int, bool]:
    """
    Process one remote parquet file starting at start_row.

    Updates cp['current_file_rows_done'] and cp['current_file_tokens_done']
    to absolute values (rows/tokens in THIS file across all sessions) at each
    COMMIT_EVERY boundary and at function exit. Callers must not touch those
    fields while this function runs.

    Returns (session_docs, session_tokens, shutdown_requested).
    """
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem

    global _shutdown
    fname      = hf_path.rsplit('/', 1)[-1]
    fs         = HfFileSystem()

    word_counts: dict = defaultdict(int)
    doc_counts:  dict = defaultdict(int)
    session_docs   = 0
    session_tokens = 0
    tokens_base    = cp['current_file_tokens_done']  # already counted in prior sessions

    with fs.open(hf_path, 'rb') as fh:
        pf         = pq.ParquetFile(fh)
        num_groups = pf.metadata.num_row_groups
        total_rows = pf.metadata.num_rows

        # Find which row group to start from (O(num_groups) metadata scan)
        start_group   = num_groups   # default: nothing to process
        skip_in_group = 0
        rows_before   = 0
        for g in range(num_groups):
            rg_rows = pf.metadata.row_group(g).num_rows
            if rows_before + rg_rows <= start_row:
                rows_before += rg_rows
            else:
                start_group   = g
                skip_in_group = start_row - rows_before
                break

        if start_row == 0:
            print(f'  [{fname}] {total_rows:,} rows, {num_groups} groups', flush=True)
        elif start_group < num_groups:
            print(f'  [{fname}] resuming row {start_row:,}/{total_rows:,} '
                  f'(group {start_group}/{num_groups})', flush=True)
        # start_row >= total_rows: nothing to do, loop below is a no-op

        for g in range(start_group, num_groups):
            if _shutdown:
                flush(conn, word_counts, doc_counts)
                cp['current_file_rows_done']   = start_row + session_docs
                cp['current_file_tokens_done'] = tokens_base + session_tokens
                save_checkpoint(cp)
                return session_docs, session_tokens, True

            try:
                texts = pf.read_row_group(g).column('text').to_pylist()
            except Exception as exc:
                flush(conn, word_counts, doc_counts)
                cp['current_file_rows_done']   = start_row + session_docs
                cp['current_file_tokens_done'] = tokens_base + session_tokens
                save_checkpoint(cp)
                print(f'  [{fname}] network error at group {g}: {exc}', flush=True)
                print(f'  checkpoint saved at {start_row + session_docs:,} rows — restart with --resume', flush=True)
                return session_docs, session_tokens, True
            if g == start_group and skip_in_group:
                texts = texts[skip_in_group:]

            for text in texts:
                total_so_far = (cp['docs_in_completed_files']
                                + start_row + session_docs)
                if limit is not None and total_so_far >= limit:
                    flush(conn, word_counts, doc_counts)
                    cp['current_file_rows_done']   = start_row + session_docs
                    cp['current_file_tokens_done'] = tokens_base + session_tokens
                    save_checkpoint(cp)
                    return session_docs, session_tokens, False

                tokens = tokenize(text or '')
                session_tokens += len(tokens)

                doc_words: set = set()
                for tok in tokens:
                    if tok in dex_words:
                        word_counts[tok] += 1
                        doc_words.add(tok)
                for w in doc_words:
                    doc_counts[w] += 1
                session_docs += 1

                if session_docs % COMMIT_EVERY == 0:
                    flush(conn, word_counts, doc_counts)
                    cp['current_file_rows_done']   = start_row + session_docs
                    cp['current_file_tokens_done'] = tokens_base + session_tokens
                    save_checkpoint(cp)
                    elapsed    = time.time() - global_start
                    total_done = (cp['docs_in_completed_files']
                                  + cp['current_file_rows_done'])
                    rate = total_done / elapsed if elapsed > 0 else 0
                    print(f'  [{fname}] {cp["current_file_rows_done"]:,}/{total_rows:,}'
                          f' | {total_done:,} total | {rate:.0f} docs/s', flush=True)

    # File exhausted normally — write final position
    flush(conn, word_counts, doc_counts)
    cp['current_file_rows_done']   = start_row + session_docs
    cp['current_file_tokens_done'] = tokens_base + session_tokens
    save_checkpoint(cp)
    return session_docs, session_tokens, False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--test',   action='store_true',
                        help='Process first 1000 documents only')
    parser.add_argument('--limit',  type=int,
                        help='Stop after N total documents')
    parser.add_argument('--resume', action='store_true',
                        help='Resume from checkpoint (required for restart loop)')
    parser.add_argument('--db', type=Path, default=FREQ_DB, help="Output database (default: %(default)s). A non-default path also gets its own checkpoint beside it, so a recount never reads or overwrites the main run's checkpoint.")
    args = parser.parse_args()
    use_db(args.db)

    limit = 1000 if args.test else args.limit

    print('Loading DEX word list...')
    dex_words = load_dex_words(LEXEMES_DB)
    print(f'  {len(dex_words):,} unique lookup forms')

    conn = init_freq_db(FREQ_DB)

    cp = load_checkpoint() if args.resume else _empty_checkpoint()

    completed_set = set(cp['completed_files'])
    total_done    = cp['docs_in_completed_files'] + cp['current_file_rows_done']
    if args.resume and total_done:
        print(f'Resuming: {len(completed_set)} files done, {total_done:,} docs so far')

    print('Listing CulturaX Romanian parquet files...')
    all_files = list_parquet_files()
    remaining = sum(1 for f in all_files if f.rsplit('/', 1)[-1] not in completed_set)
    print(f'  {len(all_files)} total shards, {remaining} remaining\n')

    global_start = time.time()

    for hf_path in all_files:
        fname = hf_path.rsplit('/', 1)[-1]
        if fname in completed_set:
            continue

        # Determine resume position within this file
        if cp['current_file'] == fname:
            start_row = cp['current_file_rows_done']
        else:
            start_row = 0
            cp['current_file']              = fname
            cp['current_file_rows_done']    = 0
            cp['current_file_tokens_done']  = 0
            save_checkpoint(cp)

        _session_docs, _session_tokens, shutdown = process_file(
            hf_path, dex_words, conn, cp, start_row, limit, global_start)

        if shutdown:
            return 1

        # Check limit reached mid-file
        if limit is not None:
            total = cp['docs_in_completed_files'] + cp['current_file_rows_done']
            if total >= limit:
                print(f'\nLimit of {limit:,} docs reached.')
                return 0

        # Mark file complete
        cp['completed_files'].append(fname)
        cp['docs_in_completed_files']   += cp['current_file_rows_done']
        cp['tokens_in_completed_files'] += cp['current_file_tokens_done']
        cp['current_file']              = None
        cp['current_file_rows_done']    = 0
        cp['current_file_tokens_done']  = 0
        completed_set.add(fname)
        save_checkpoint(cp)

        elapsed = time.time() - global_start
        print(f'  [{fname}] complete — {len(completed_set)}/{len(all_files)} files, '
              f'{cp["docs_in_completed_files"]:,} docs, {elapsed / 3600:.1f}h elapsed\n')

    # All files done
    elapsed      = time.time() - global_start
    total_docs   = cp['docs_in_completed_files']
    total_tokens = cp['tokens_in_completed_files']

    unique_words = conn.execute(
        "SELECT COUNT(DISTINCT word) FROM corpus_word_frequency WHERE corpus_name=?",
        (CORPUS_NAME,)
    ).fetchone()[0]

    conn.execute("""
        INSERT INTO processing_stats
            (corpus_name, documents_processed, tokens_processed, unique_words_found,
             processing_time_seconds, completed_at, status)
        VALUES (?, ?, ?, ?, ?, ?, 'completed')
    """, (CORPUS_NAME, total_docs, total_tokens, unique_words, elapsed, datetime.now()))
    conn.commit()

    print(f'\nDone: {total_docs:,} docs, {total_tokens:,} tokens in '
          f'{elapsed:.0f}s ({elapsed / 3600:.1f}h)')
    print(f'Unique DEX words found: {unique_words:,}')

    rows = conn.execute("""
        SELECT word, occurrence_count, document_count
        FROM corpus_word_frequency
        WHERE corpus_name = ?
        ORDER BY occurrence_count DESC
        LIMIT 20
    """, (CORPUS_NAME,)).fetchall()
    if rows:
        print('\nTop 20 DEX words in CulturaX RO:')
        print(f'  {"word":<25} {"occurrences":>12} {"documents":>10}')
        for w, oc, dc in rows:
            print(f'  {w:<25} {oc:>12,} {dc:>10,}')

    conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
