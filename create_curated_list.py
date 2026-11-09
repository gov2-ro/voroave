#!/usr/bin/env python3
"""
Create a curated list of forgotten Romanian words.

Filters:
1. Has meaningful description or a word-class model type
2. Proper Romanian words (not proper nouns, technical terms, compounds)
3. DEX frequency < 1.0 (excludes only the 14k core-vocabulary entries)
4. Exclude very short words
5. Focus on traditional Romanian vocabulary
"""

import sqlite3
import csv
import re

from constants import (
    MIN_FREQUENCY,
    MIN_FORM_LENGTH,
    CURATED_FREQ_CEILING,
    VERY_RARE_MAX,
    RARE_MAX,
    UNCOMMON_MAX,
    rarity_category,
    tag_family,
)

DB_PATH = "data/processed/lexemes.db"
OUTPUT_CSV = "data/processed/forgotten_words_curated.csv"

# Tag families (register / domain / etymology) come from constants.tag_family(), the
# same rule validate_diachronic.load_taxonomy() uses. It includes the root tags 6
# (`rar`), 17 (`regional`) and 239 (`ieșit din uz`), which a parent-only rule misses.


def fetch_all_tags(conn, lexeme_ids):
    """Bulk-fetch Tag values for a list of lexeme IDs.

    Queries both join paths (objectType=2 direct, objectType=3 via entry) and
    returns {lexeme_id: {'register': str, 'domain': str, 'etymology': str}}
    where each value is a sorted semicolon-separated list of tag labels.
    """
    if not lexeme_ids:
        return {}
    placeholders = ','.join('?' * len(lexeme_ids))
    raw = []
    # Direct path: ObjectTag.objectId = Lexeme.id
    raw.extend(conn.execute(f"""
        SELECT ot.objectId, t.id, t.value, t.parentId
        FROM ObjectTag ot JOIN Tag t ON t.id = ot.tagId
        WHERE ot.objectType = 2 AND ot.objectId IN ({placeholders})
    """, lexeme_ids).fetchall())
    # Entry path: Lexeme → EntryLexeme → TreeEntry → MeaningTree → ObjectTag(objectType=3)
    raw.extend(conn.execute(f"""
        SELECT el.lexemeId, t.id, t.value, t.parentId
        FROM EntryLexeme el
        JOIN TreeEntry te ON te.entryId = el.entryId
        JOIN MeaningTree m ON m.tree_id = te.treeId
        JOIN ObjectTag ot ON ot.objectId = m.meaning_id AND ot.objectType = 3
        JOIN Tag t ON t.id = ot.tagId
        WHERE el.lexemeId IN ({placeholders})
    """, lexeme_ids).fetchall())

    buckets = {}
    for lid, tag_id, value, parent_id in raw:
        entry = buckets.setdefault(int(lid), {'register': set(), 'domain': set(), 'etymology': set()})
        family = tag_family(tag_id, parent_id)
        if family:
            entry[family].add(value)

    return {
        lid: {cat: '; '.join(sorted(vals)) for cat, vals in cats.items()}
        for lid, cats in buckets.items()
    }

def is_proper_noun(word):
    """Check if word looks like a proper noun."""
    # Starts with capital letter (except first letter of sentence)
    return word[0].isupper() if word else False

def is_romanian_word(word):
    """Check if word looks like a traditional Romanian word."""
    # Exclude Latin phrases, foreign words, technical terms
    foreign_patterns = [
        r'^[A-Z][a-z]+ [A-Z]',  # "El Alamein" pattern
        r' ',  # Multi-word phrases (many are Latin/foreign)
        r"^[a-z]+-[a-z]+",  # Hyphenated multi-word expressions
    ]

    for pattern in foreign_patterns:
        if re.search(pattern, word):
            return False

    return True

# Model type prefixes that unambiguously identify a word class in DEX
_WORD_CLASS_TYPES = {'A', 'N', 'F', 'M', 'VT', 'VI', 'IL', 'PT', 'P'}

def has_meaningful_description(desc, model_type=''):
    """Check if description or model type identifies a word class."""
    if desc and desc.strip():
        meaningful_markers = [
            'adj', 's.m', 's.f', 's.n', 'vb', 'adv', 'interj',
            'înv', 'reg', 'pop', 'dial', 'arh',
        ]
        if any(marker in desc.lower() for marker in meaningful_markers):
            return True
    # Fall back to model type when description is absent
    prefix = re.match(r'^([A-Z]+)', model_type or '')
    return bool(prefix and prefix.group(1) in _WORD_CLASS_TYPES)

def create_curated_list(db_path, output_csv):
    """Create curated forgotten words list."""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 70)
    print("Creating Curated Forgotten Words List")
    print("=" * 70)
    print()

    # Query with better filters
    cursor.execute("""
        SELECT
            id,
            form,
            formNoAccent,
            frequency,
            description,
            modelType,
            notes
        FROM Lexeme
        WHERE typeof(frequency) = 'real'
          AND frequency > ?
          AND frequency < ?
          AND LENGTH(form) > ?
        ORDER BY frequency ASC
    """, (MIN_FREQUENCY, CURATED_FREQ_CEILING, MIN_FORM_LENGTH))

    all_candidates = cursor.fetchall()
    print(f"Initial candidates: {len(all_candidates):,}")

    # Apply filters
    curated = []
    filtered_counts = {
        'proper_noun': 0,
        'foreign': 0,
        'no_description': 0,
        'kept': 0
    }

    for word_data in all_candidates:
        lexeme_id, form, form_no_accent, freq, desc, model_type, notes = word_data

        # Filter proper nouns
        if is_proper_noun(form):
            filtered_counts['proper_noun'] += 1
            continue

        # Filter foreign/technical words
        if not is_romanian_word(form):
            filtered_counts['foreign'] += 1
            continue

        # Filter non-meaningful descriptions
        if not has_meaningful_description(desc, model_type):
            filtered_counts['no_description'] += 1
            continue

        curated.append(word_data)
        filtered_counts['kept'] += 1

    print()
    print("FILTERING RESULTS")
    print("-" * 70)
    print(f"  Filtered (proper nouns):       {filtered_counts['proper_noun']:>8,}")
    print(f"  Filtered (foreign/technical):  {filtered_counts['foreign']:>8,}")
    print(f"  Filtered (no description):     {filtered_counts['no_description']:>8,}")
    print(f"  ✅ Kept for final list:        {filtered_counts['kept']:>8,}")

    # Bulk-fetch taxonomy tags for all curated words
    print()
    print("FETCHING DEX TAXONOMY TAGS")
    print("-" * 70)
    curated_ids = [row[0] for row in curated]
    tag_map = fetch_all_tags(conn, curated_ids)
    tagged_count = sum(1 for lid in curated_ids if lid in tag_map)
    print(f"  Words with at least one tag: {tagged_count:,} / {len(curated):,}")

    # Categorize by frequency (canonical bins live in constants.py)
    categories = {
        'very_rare': [],
        'rare': [],
        'uncommon': [],
        'standard': [],
    }

    for word_data in curated:
        categories[rarity_category(word_data[3])].append(word_data)

    print()
    print("CATEGORIZATION")
    print("-" * 70)
    print(f"  Very rare ({MIN_FREQUENCY}-{VERY_RARE_MAX}):  {len(categories['very_rare']):>8,}")
    print(f"  Rare ({VERY_RARE_MAX}-{RARE_MAX}):       {len(categories['rare']):>8,}")
    print(f"  Uncommon ({RARE_MAX}-{UNCOMMON_MAX}):   {len(categories['uncommon']):>8,}")
    print(f"  Standard ({UNCOMMON_MAX}-{CURATED_FREQ_CEILING}):    {len(categories['standard']):>8,}")

    # Show samples
    print()
    print("SAMPLE FORGOTTEN WORDS")
    print("-" * 70)

    for cat_name, cat_words in categories.items():
        if not cat_words:
            continue

        print(f"\n{cat_name.upper().replace('_', ' ')} (first 15):")
        for _, form, _, freq, desc, _, _ in cat_words[:15]:
            print(f"  {form:.<30} {desc:.<20} freq={freq:.3f}")

    # Export to CSV
    print()
    print("EXPORTING TO CSV")
    print("-" * 70)
    print(f"Output: {output_csv}")

    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'word',
            'word_no_accent',
            'frequency',
            'rarity_category',
            'description',
            'model_type',
            'notes',
            'dex_register',
            'dex_domain',
            'dex_etymology',
        ])

        # Write curated words
        for word_data in curated:
            lexeme_id, form, form_no_accent, freq, desc, model_type, notes = word_data

            # Determine category (canonical bins live in constants.py)
            category = rarity_category(freq)

            tags = tag_map.get(lexeme_id, {})
            writer.writerow([
                form,
                form_no_accent,
                f"{freq:.4f}",
                category,
                desc,
                model_type,
                notes or '',
                tags.get('register', ''),
                tags.get('domain', ''),
                tags.get('etymology', ''),
            ])

    print(f"✅ Exported {len(curated):,} curated forgotten words")

    conn.close()

    print()
    print("=" * 70)
    print("✅ CURATION COMPLETE")
    print("=" * 70)
    print()
    print(f"Output file: {output_csv}")
    print()
    print("These are high-quality forgotten word candidates with:")
    print("  - Meaningful linguistic descriptions or word-class model types")
    print("  - Traditional Romanian vocabulary")
    print("  - DEX frequency < 1.0 (corpus validation is the real gate)")
    print()

if __name__ == "__main__":
    create_curated_list(DB_PATH, OUTPUT_CSV)
