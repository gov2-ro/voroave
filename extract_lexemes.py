#!/usr/bin/env python3
"""
Extract lexeme data directly from MySQL dump without full database conversion.
Parse INSERT statements and create a simple CSV/SQLite database.
"""

import re
import sqlite3
import csv

from dump_parser import parse_rows, strip_line_prefix

_INSERT_RE = re.compile(r'INSERT INTO `(\w+)` VALUES ')


def parse_mysql_insert(line, tables=None):
    """Parse one `INSERT INTO `T` VALUES (...),(...);` line into (table, rows).

    Uses `dump_parser.parse_rows`, which tracks quoting and escaping. The earlier regex
    splitter (`findall` on parentheses around `[^)]+`) dropped or column-shifted every
    row with a `)` inside a quoted field. Each row is a list of fields: str, or None for NULL.

    With `tables`, rows are parsed only for those table names; for any other table the
    result is (name, []). That skips the large `Definition` lines cheaply.
    """
    m = _INSERT_RE.match(line)
    if not m or not line.rstrip('\n').endswith(';'):
        return None, []
    table_name = m.group(1)
    if tables is not None and table_name not in tables:
        return table_name, []
    return table_name, list(parse_rows(strip_line_prefix(line, m.group(0))))


def extract_lexemes_to_csv(input_sql, output_csv):
    """Extract Lexeme table to CSV."""
    print(f"Extracting Lexeme data from {input_sql}")
    print(f"Output: {output_csv}")
    print()

    lexeme_count = 0

    with open(input_sql, 'r', encoding='utf-8') as infile, \
         open(output_csv, 'w', encoding='utf-8', newline='') as outfile:

        writer = csv.writer(outfile)

        # Write header (Lexeme table columns)
        writer.writerow([
            'id', 'form', 'formNoAccent', 'formUtf8General', 'reverse',
            'number', 'description', 'noAccent', 'consistentAccent',
            'frequency', 'hyphenations', 'pronunciations', 'stopWord',
            'compound', 'modelType', 'modelNumber', 'restriction',
            'staleParadigm', 'notes', 'hasApheresis', 'hasApocope',
            'createDate', 'modDate'
        ])

        for line_num, line in enumerate(infile, 1):
            if line_num % 500 == 0:
                print(f"  Processed {line_num} lines, extracted {lexeme_count} lexemes...")

            table_name, records = parse_mysql_insert(line, tables=('Lexeme',))

            if table_name == 'Lexeme':
                for record in records:
                    writer.writerow(record)
                    lexeme_count += 1

    print()
    print(f"✅ Extracted {lexeme_count} lexemes to {output_csv}")
    return lexeme_count

def create_sqlite_from_csv(csv_file, db_file):
    """Create SQLite database from CSV file."""
    print(f"\nCreating SQLite database from CSV...")

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Create Lexeme table (drop first so re-runs are idempotent)
    cursor.execute('DROP TABLE IF EXISTS Lexeme')
    cursor.execute('''
        CREATE TABLE Lexeme (
            id INTEGER PRIMARY KEY,
            form TEXT NOT NULL,
            formNoAccent TEXT,
            formUtf8General TEXT,
            reverse TEXT,
            number INTEGER,
            description TEXT,
            noAccent INTEGER,
            consistentAccent INTEGER,
            frequency REAL,
            hyphenations TEXT,
            pronunciations TEXT,
            stopWord INTEGER,
            compound INTEGER,
            modelType TEXT,
            modelNumber TEXT,
            restriction TEXT,
            staleParadigm INTEGER,
            notes TEXT,
            hasApheresis INTEGER,
            hasApocope INTEGER,
            createDate INTEGER,
            modDate INTEGER
        )
    ''')

    # Load CSV
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header

        count = 0
        skipped = 0
        for row in reader:
            if len(row) != 23:
                skipped += 1
                continue
            cursor.execute('''
                INSERT INTO Lexeme VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', row)
            count += 1

            if count % 10000 == 0:
                print(f"  Loaded {count} records...")
                conn.commit()
        if skipped:
            print(f"  Skipped {skipped} malformed rows (apostrophe in form field)")

    conn.commit()

    # Verify
    cursor.execute("SELECT COUNT(*) FROM Lexeme")
    total = cursor.fetchone()[0]
    print(f"  ✅ Database created with {total:,} lexemes")

    # Sample forgotten words
    cursor.execute("""
        SELECT form, frequency, description
        FROM Lexeme
        WHERE frequency < 0.7 AND frequency > 0
        ORDER BY frequency ASC
        LIMIT 10
    """)

    print(f"\n  Sample forgotten word candidates (low frequency):")
    for form, freq, desc in cursor.fetchall():
        print(f"    - {form} ({desc}): frequency={freq:.3f}")

    conn.close()
    print(f"\n✅ Database saved to: {db_file}")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--sql', default='data/dictionaries/dex-database.sql')
    p.add_argument('--csv', default='data/processed/lexemes.csv')
    p.add_argument('--db',  default='data/processed/lexemes.db')
    args = p.parse_args()

    input_sql  = args.sql
    output_csv = args.csv
    output_db  = args.db

    print("=" * 60)
    print("DEX Lexeme Extractor")
    print("=" * 60)
    print()

    # Extract to CSV first
    count = extract_lexemes_to_csv(input_sql, output_csv)

    if count > 0:
        # Create SQLite database
        create_sqlite_from_csv(output_csv, output_db)
    else:
        print("⚠️  No lexemes found!")
        sys.exit(1)
