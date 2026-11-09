#!/usr/bin/env python3
"""
Count DEX word occurrences in Wikisource Romanian (historical literary corpus).

Fixes the P0 bug from process_corpus.py: loads all ~315k DEX forms from
lexemes.db as the lookup set, not just the 1.9k curated candidates.

Usage:
    python process_wikisource.py              # full run
    python process_wikisource.py --test       # first 500 documents
    python process_wikisource.py --resume     # skip already-processed docs

Output: data/processed/corpus_frequencies.db (same schema as process_corpus.py)
        corpus_name = 'wikisource_ro'
"""

import argparse
import json
import re
import sqlite3
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from constants import model_types_sql

LEXEMES_DB   = Path('data/processed/lexemes.db')
FREQ_DB      = Path('data/processed/corpus_frequencies.db')
CHECKPOINT   = Path('data/processed/wikisource_checkpoint.json')


def use_db(db: Path) -> None:
    """Point FREQ_DB at `db`. A non-default DB gets its own checkpoint beside it."""
    global FREQ_DB, CHECKPOINT
    if Path(db) != FREQ_DB:
        CHECKPOINT = Path(db).with_name(Path(db).stem + '.' + CHECKPOINT.name)
    FREQ_DB = Path(db)
CORPUS_NAME  = 'wikisource_ro'
COMMIT_EVERY = 2000   # documents between DB commits


def normalize(text: str) -> str:
    return unicodedata.normalize('NFC',
        text.lower().replace('ş', 'ș').replace('ţ', 'ț'))


def tokenize(text: str) -> list[str]:
    text = normalize(text)
    tokens = re.findall(r"[a-zăâîșț](?:[a-zăâîșț\-']*[a-zăâîșț])?", text)
    return [t for t in tokens if len(t) > 2 and not t.isdigit()]


def load_dex_words(lexemes_db: Path) -> set[str]:
    conn = sqlite3.connect(lexemes_db)
    c = conn.cursor()
    # Accept words that have a POS description OR a word-class modelType prefix.
    # Many canonical entries (e.g. "jurnalism", "ziar") have empty description
    # but a valid modelType (N=noun, F=fem., A=adj., V/VT/VI=verb, etc.; constants.CORPUS_LOOKUP_MODEL_TYPES) — they
    # must be included or their corpus occurrences are silently discarded.
    c.execute("""
        SELECT DISTINCT lower(formNoAccent)
        FROM Lexeme
        WHERE typeof(frequency) = 'real'
          AND frequency > 0.01
          AND LENGTH(formNoAccent) > 2
          AND (
            (description != '' AND description IS NOT NULL)
            OR modelType IN """ + model_types_sql() + """
          )
    """)
    words = {normalize(r[0]) for r in c.fetchall()}
    conn.close()
    return words


def init_freq_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS corpus_word_frequency (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            word          TEXT NOT NULL,
            corpus_name   TEXT NOT NULL,
            occurrence_count  INTEGER DEFAULT 0,
            document_count    INTEGER DEFAULT 0,
            last_updated  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
    ts = datetime.now().isoformat()
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


def save_checkpoint(docs_done: int) -> None:
    CHECKPOINT.write_text(json.dumps({'docs_processed': docs_done}))


def load_checkpoint() -> int:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text()).get('docs_processed', 0)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--test',   action='store_true', help='First 500 documents only')
    parser.add_argument('--resume', action='store_true', help='Skip already-processed docs')
    parser.add_argument('--db', type=Path, default=FREQ_DB, help="Output database (default: %(default)s). A non-default path also gets its own checkpoint beside it, so a recount never reads or overwrites the main run's checkpoint.")
    args = parser.parse_args()
    use_db(args.db)

    limit  = 500 if args.test else None
    skip   = load_checkpoint() if args.resume else 0

    if args.resume and skip:
        print(f'Resuming from document {skip:,}')

    print('Loading DEX word list from lexemes.db...')
    dex_words = load_dex_words(LEXEMES_DB)
    print(f'  {len(dex_words):,} unique lookup forms')

    conn = init_freq_db(FREQ_DB)

    print('Loading Wikisource RO dataset (streaming)...')
    try:
        from datasets import load_dataset
    except ImportError:
        print('datasets not installed — run: pip install datasets')
        return 1

    try:
        ds = load_dataset('wikimedia/wikisource', '20231201.ro',
                          split='train', streaming=True, trust_remote_code=False)
    except Exception as e:
        print(f'Failed to load dataset: {e}')
        return 1

    word_counts: dict = defaultdict(int)
    doc_counts:  dict = defaultdict(int)
    total_tokens = 0
    docs_done    = 0
    start        = time.time()

    print(f'Processing{"  (test: 500 docs)" if args.test else ""}...\n')

    for idx, doc in enumerate(ds):
        if skip and idx < skip:
            if idx % 10000 == 0:
                print(f'  Skipping {idx:,}/{skip:,}...', end='\r')
            continue

        if limit and docs_done >= limit:
            break

        tokens = tokenize(doc.get('text', ''))
        total_tokens += len(tokens)

        doc_words: set = set()
        for tok in tokens:
            if tok in dex_words:
                word_counts[tok] += 1
                doc_words.add(tok)
        for w in doc_words:
            doc_counts[w] += 1

        docs_done += 1

        if docs_done % COMMIT_EVERY == 0:
            batch_unique = len(word_counts)
            flush(conn, word_counts, doc_counts)
            save_checkpoint(skip + docs_done)
            elapsed = time.time() - start
            rate = docs_done / elapsed
            print(f'  {docs_done:,} docs | {total_tokens:,} tokens | '
                  f'{rate:.0f} docs/s | {batch_unique:,} unique dex forms this batch')

    flush(conn, word_counts, doc_counts)
    save_checkpoint(skip + docs_done)

    elapsed = time.time() - start
    conn.execute("""
        INSERT INTO processing_stats
            (corpus_name, documents_processed, tokens_processed, unique_words_found,
             processing_time_seconds, completed_at, status)
        VALUES (?, ?, ?, ?, ?, ?, 'completed')
    """, (CORPUS_NAME, docs_done, total_tokens,
          conn.execute("SELECT COUNT(DISTINCT word) FROM corpus_word_frequency WHERE corpus_name=?",
                       (CORPUS_NAME,)).fetchone()[0],
          elapsed, datetime.now()))
    conn.commit()

    print(f'\nDone: {docs_done:,} docs, {total_tokens:,} tokens in {elapsed:.0f}s')
    print(f'Results in {FREQ_DB}  (corpus_name = {CORPUS_NAME!r})')

    # Quick summary
    rows = conn.execute("""
        SELECT word, occurrence_count, document_count
        FROM corpus_word_frequency
        WHERE corpus_name = ?
        ORDER BY occurrence_count DESC
        LIMIT 20
    """, (CORPUS_NAME,)).fetchall()
    if rows:
        print('\nTop 20 DEX words in Wikisource RO:')
        print(f'  {"word":<25} {"occurrences":>12} {"documents":>10}')
        for w, oc, dc in rows:
            print(f'  {w:<25} {oc:>12,} {dc:>10,}')

    conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
