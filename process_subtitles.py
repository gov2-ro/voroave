#!/usr/bin/env python3
"""
Count DEX word occurrences in the DEX Subtitle corpus (modern spoken Romanian).

Source: Subtitle table in data/dictionaries/dex-database.sql — ~13M pre-tokenised
word tokens from 966 YouTube clips (Digi24 news content). Each row:
  (id, clipId, start, word)
One word per row; clipId is the natural document unit (966 clips total).

No checkpoint needed — the source is a local file; the full pass takes ~1 minute.

Usage:
    python process_subtitles.py              # full run
    python process_subtitles.py --dry-run    # count only, no writes
    python process_subtitles.py --wipe       # clear subtitle_ro rows first, then run

Output: data/processed/corpus_frequencies.db  (corpus_name = 'subtitle_ro')
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from constants import model_types_sql

DUMP_PATH   = Path('data/dictionaries/dex-database.sql')
LEXEMES_DB  = Path('data/processed/lexemes.db')
FREQ_DB     = Path('data/processed/corpus_frequencies.db')
CORPUS_NAME = 'subtitle_ro'

# Matches one value tuple: (id, clipId, start, 'word')  or  (...,NULL)
_ROW_RE = re.compile(r"\(\d+,(\d+),\d+,'((?:[^'\\]|\\.)*)'\)")


def normalize(text: str) -> str:
    return unicodedata.normalize('NFC',
        text.lower().replace('ş', 'ș').replace('ţ', 'ț'))


def load_dex_words(lexemes_db: Path) -> set[str]:
    conn = sqlite3.connect(lexemes_db)
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


def wipe(conn: sqlite3.Connection) -> None:
    conn.execute('DELETE FROM corpus_word_frequency WHERE corpus_name = ?', (CORPUS_NAME,))
    conn.execute('DELETE FROM processing_stats WHERE corpus_name = ?', (CORPUS_NAME,))
    conn.commit()
    print(f'Wiped existing {CORPUS_NAME} rows.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true',
                        help='Count tokens only; write nothing')
    parser.add_argument('--wipe', action='store_true',
                        help='Clear existing subtitle_ro data before running')
    args = parser.parse_args()

    if not DUMP_PATH.exists():
        print(f'Dump not found: {DUMP_PATH}')
        return 1

    print(f'Loading DEX word list from {LEXEMES_DB}...')
    dex_words = load_dex_words(LEXEMES_DB)
    print(f'  {len(dex_words):,} lookup forms')

    conn = init_freq_db(FREQ_DB)

    if args.wipe and not args.dry_run:
        wipe(conn)

    # occurrence_count per word; set of clipIds per word for document_count
    occ:   dict[str, int]       = defaultdict(int)
    clips: dict[str, set[int]]  = defaultdict(set)

    total_tokens = 0
    insert_lines = 0
    start = time.time()

    print(f'Streaming {DUMP_PATH} for Subtitle rows...')
    with DUMP_PATH.open(encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if not line.startswith("INSERT INTO `Subtitle`"):
                continue
            insert_lines += 1
            for clip_id_str, raw_word in _ROW_RE.findall(line):
                total_tokens += 1
                word = normalize(raw_word)
                if word in dex_words:
                    clip_id = int(clip_id_str)
                    occ[word] += 1
                    clips[word].add(clip_id)

    elapsed = time.time() - start
    unique_clips = len({c for cs in clips.values() for c in cs})

    print(f'\nDone streaming in {elapsed:.1f}s')
    print(f'  INSERT lines processed : {insert_lines:,}')
    print(f'  Total tokens           : {total_tokens:,}')
    print(f'  DEX words matched      : {len(occ):,} unique forms')
    print(f'  Clips seen             : {unique_clips:,}')

    if args.dry_run:
        print('\nDry run — nothing written.')
        return 0

    print(f'\nWriting to {FREQ_DB} (corpus_name={CORPUS_NAME!r})...')
    ts = datetime.now().isoformat()
    conn.executemany("""
        INSERT INTO corpus_word_frequency
            (word, corpus_name, occurrence_count, document_count, last_updated)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(word, corpus_name) DO UPDATE SET
            occurrence_count = occurrence_count + excluded.occurrence_count,
            document_count   = document_count   + excluded.document_count,
            last_updated     = excluded.last_updated
    """, [(w, CORPUS_NAME, occ[w], len(clips[w]), ts) for w in occ])

    conn.execute("""
        INSERT INTO processing_stats
            (corpus_name, documents_processed, tokens_processed,
             unique_words_found, processing_time_seconds, completed_at, status)
        VALUES (?, ?, ?, ?, ?, ?, 'completed')
    """, (CORPUS_NAME, unique_clips, total_tokens, len(occ), elapsed, ts))

    conn.commit()
    conn.close()
    print(f'Wrote {len(occ):,} word rows. Done.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
