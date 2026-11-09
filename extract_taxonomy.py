#!/usr/bin/env python3
"""
Extract Tag, ObjectTag, EntryLexeme, TreeEntry, and MeaningTree tables from the DEX MySQL dump
into lexemes.db.  Run once after extract_lexemes.py; required before validate_diachronic.py
emits taxonomy columns.

Usage:
    python extract_taxonomy.py                                            # full dump
    python extract_taxonomy.py --sql data/dictionaries/dex-database-sample.sql --db /tmp/lexemes-sample.db

The default is the full dump, like every other extractor. The sampled dump omits rows of
the relation tables, so its output must not replace data/processed/lexemes.db.
"""

import argparse
import re
import sqlite3
from extract_lexemes import parse_mysql_insert

# Tables handled via parse_mysql_insert (integer-only columns).
TARGET_TABLES = {'Tag', 'ObjectTag', 'EntryLexeme', 'TreeEntry'}

SCHEMAS = {
    'Tag': """
        CREATE TABLE IF NOT EXISTS Tag (
            id INTEGER PRIMARY KEY,
            parentId INTEGER,
            value TEXT,
            color INTEGER,
            icon TEXT,
            iconOnly INTEGER,
            tooltip TEXT,
            public INTEGER,
            isPos INTEGER,
            createDate INTEGER,
            modDate INTEGER
        )
    """,
    'ObjectTag': """
        CREATE TABLE IF NOT EXISTS ObjectTag (
            id INTEGER PRIMARY KEY,
            objectId INTEGER,
            objectType INTEGER,
            tagId INTEGER,
            createDate INTEGER,
            modDate INTEGER
        )
    """,
    'EntryLexeme': """
        CREATE TABLE IF NOT EXISTS EntryLexeme (
            id INTEGER PRIMARY KEY,
            entryId INTEGER,
            lexemeId INTEGER,
            entryRank INTEGER,
            lexemeRank INTEGER,
            main INTEGER,
            createDate INTEGER,
            modDate INTEGER
        )
    """,
    'TreeEntry': """
        CREATE TABLE IF NOT EXISTS TreeEntry (
            id INTEGER PRIMARY KEY,
            treeId INTEGER,
            entryId INTEGER,
            treeRank INTEGER,
            entryRank INTEGER,
            createDate INTEGER,
            modDate INTEGER
        )
    """,
    # MeaningTree is extracted separately (Meaning rows contain longtext that breaks the
    # parse_mysql_insert regex).  We only store the two columns needed for the join.
    'MeaningTree': """
        CREATE TABLE IF NOT EXISTS MeaningTree (
            meaning_id INTEGER PRIMARY KEY,
            tree_id INTEGER
        )
    """,
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_objecttag_objectid  ON ObjectTag(objectId)",
    "CREATE INDEX IF NOT EXISTS idx_objecttag_tagid     ON ObjectTag(tagId)",
    "CREATE INDEX IF NOT EXISTS idx_entrylexeme_lexid   ON EntryLexeme(lexemeId)",
    "CREATE INDEX IF NOT EXISTS idx_entrylexeme_entid   ON EntryLexeme(entryId)",
    "CREATE INDEX IF NOT EXISTS idx_treeentry_entryid   ON TreeEntry(entryId)",
    "CREATE INDEX IF NOT EXISTS idx_treeentry_treeid    ON TreeEntry(treeId)",
    "CREATE INDEX IF NOT EXISTS idx_meaningtree_treeid  ON MeaningTree(tree_id)",
]

PLACEHOLDERS = {
    'Tag':        '(?,?,?,?,?,?,?,?,?,?,?)',
    'ObjectTag':  '(?,?,?,?,?,?)',
    'EntryLexeme':'(?,?,?,?,?,?,?,?)',
    'TreeEntry':  '(?,?,?,?,?,?,?)',
    'MeaningTree':'(?,?)',
}

# Meaning columns: id, parentId, type, displayOrder, breadcrumb(varchar), userId, treeId, internalRep(longtext), ...
# We match the first 7 fields and capture id (col 1) and treeId (col 7), stopping before internalRep.
# Using (?:\'(?:[^\'\\]|\\.)*\'|NULL) to handle the quoted breadcrumb field.
_MEANING_PATTERN = re.compile(
    r'\((\d+),\d+,\d+,\d+,(?:\'(?:[^\'\\]|\\.)*\'|NULL),\d+,(\d+),'
)


def extract(sql_path, db_path):
    print(f"Source: {sql_path}")
    print(f"Target: {db_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    for ddl in SCHEMAS.values():
        cur.execute(ddl)
    conn.commit()

    counts = {t: 0 for t in TARGET_TABLES | {'MeaningTree'}}

    with open(sql_path, encoding='utf-8') as fh:
        for lineno, line in enumerate(fh, 1):
            if lineno % 10_000 == 0:
                done = ', '.join(f'{t}: {counts[t]:,}' for t in sorted(counts))
                print(f"  line {lineno:,}  [{done}]", end='\r', flush=True)

            # Meaning rows contain longtext (internalRep) that breaks parse_mysql_insert;
            # use a targeted regex to extract just meaning_id and tree_id.
            if line.startswith("INSERT INTO `Meaning`"):
                matches = _MEANING_PATTERN.findall(line)
                if matches:
                    rows = [(int(m[0]), int(m[1])) for m in matches]
                    cur.executemany('INSERT OR REPLACE INTO MeaningTree VALUES (?,?)', rows)
                    counts['MeaningTree'] += len(rows)
                    if counts['MeaningTree'] % 50_000 == 0:
                        conn.commit()
                continue

            table, records = parse_mysql_insert(line, tables=TARGET_TABLES)
            if table not in TARGET_TABLES:
                continue

            ph = PLACEHOLDERS[table]
            cur.executemany(f'INSERT OR REPLACE INTO {table} VALUES {ph}', records)
            counts[table] += len(records)

            if sum(counts.values()) % 50_000 == 0:
                conn.commit()

    conn.commit()

    print()
    print()
    for table in sorted(counts):
        print(f"  {table}: {counts[table]:,} rows")

    print("\nBuilding indexes…")
    for idx in INDEXES:
        cur.execute(idx)
    conn.commit()
    print("  done")

    _sanity_check(conn)
    conn.close()


def _sanity_check(conn):
    print("\nSanity check — tags for 'isihie':")
    try:
        rows = conn.execute("""
            SELECT DISTINCT t.value, t.parentId
            FROM Lexeme l
            JOIN EntryLexeme el ON el.lexemeId = l.id
            JOIN TreeEntry te ON te.entryId = el.entryId
            JOIN MeaningTree m ON m.tree_id = te.treeId
            JOIN ObjectTag ot ON ot.objectId = m.meaning_id AND ot.objectType = 3
            JOIN Tag t ON t.id = ot.tagId
            WHERE lower(l.formNoAccent) = 'isihie'
              AND t.parentId IN (1, 41, 42)
        """).fetchall()
        if rows:
            for value, pid in rows:
                family = {1: 'etymology', 41: 'domain', 42: 'register'}.get(pid, f'pid={pid}')
                print(f"  [{family}] {value}")
        else:
            print("  (no taxonomy tags found for 'isihie' via Meaning join)")
            _debug_join_counts(conn)
    except sqlite3.OperationalError as e:
        print(f"  query failed: {e}")


def _debug_join_counts(conn):
    """Print row counts to help diagnose a missing-tags result."""
    for label, sql in [
        ("TreeEntry rows", "SELECT COUNT(*) FROM TreeEntry"),
        ("MeaningTree rows", "SELECT COUNT(*) FROM MeaningTree"),
        ("ObjectTag objectType=3 rows", "SELECT COUNT(*) FROM ObjectTag WHERE objectType=3"),
    ]:
        try:
            n = conn.execute(sql).fetchone()[0]
            print(f"  {label}: {n:,}")
        except sqlite3.OperationalError as e:
            print(f"  {label}: query failed — {e}")


DEX_SQL_PATH = 'data/dictionaries/dex-database.sql'


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Extract DEX taxonomy tables into lexemes.db')
    parser.add_argument('--sql', default=DEX_SQL_PATH,
                        help=f'Path to DEX MySQL dump (default: the full dump, {DEX_SQL_PATH})')
    parser.add_argument('--db', default='data/processed/lexemes.db',
                        help='Path to lexemes.db (must already exist with Lexeme table)')
    return parser.parse_args(argv)


if __name__ == '__main__':
    args = parse_args()
    extract(args.sql, args.db)
