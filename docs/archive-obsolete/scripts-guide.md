> Archived on 2026-10-05. This describes the retired Wikipedia/OSCAR workflow.
> Use [the current guide](../scripts-guide.md) for executable instructions.

# Scripts Guide - Oțios Project

Complete documentation for all scripts in the Romanian Forgotten Words project.

---

## Overview

The project uses a multi-stage pipeline to identify forgotten Romanian words:

```
Phase 1: Dictionary Analysis
Raw MySQL Dump → Sample DB → SQLite Conversion → Analysis → Curated List

Phase 2: Corpus Validation
Wikipedia + OSCAR → Tokenization → Frequency Counting → Validation → Final List
```

**Phase 1 Scripts (Dictionary Analysis):**
1. `create_sample_db.py` - Create manageable sample (optional but recommended)
2. `mysql_to_sqlite.py` - Convert to SQLite (alternative approach)
3. `extract_lexemes.py` - Extract lexeme data to CSV/SQLite (recommended)
4. `analyze_forgotten_words.py` - Generate initial analysis
5. `create_curated_list.py` - Create final curated list

**Phase 2 Scripts (Corpus Validation):**
6. `download_wikipedia_ro.py` - Download Wikipedia Romanian dataset
7. `process_corpus.py` - Count word occurrences in corpora ⭐
8. `validate_forgotten_words.py` - Cross-reference and validate

**Utility scripts:**
- `explore_dex.py` - Database structure documentation (reference only)

---

## Scripts Documentation

### 1. `explore_dex.py`

**Purpose**: Documentation and exploration of DEX Online database structure.

**Type**: Reference/Documentation

**Usage**:
```bash
python explore_dex.py
```

**What it does**:
- Documents the structure of the DEX Online database
- Lists key tables (Lexeme, Entry, Abbreviation, etc.)
- Shows important fields for forgotten word detection
- Displays sample data examples
- **Does not modify any files** - purely informational

**When to use**:
- When you need to understand the database schema
- As a reference for table structures and relationships
- Before writing custom queries

**Output**: Console output only (no files created)

---

### 2. `create_sample_db.py`

**Purpose**: Create a development-friendly sample of the large DEX database.

**Input**:
- `data/dictionaries/dex-database.sql` (1.2 GB MySQL dump)

**Output**:
- `data/dictionaries/dex-database-sample.sql` (~285 MB)

**Strategy**:
- Keeps 100% of critical tables (Lexeme, Entry, Abbreviation)
- Samples 10% of supporting tables
- Skips large unnecessary tables (FullTextIndex, CrawlerData)
- Preserves all schema (CREATE TABLE statements)

**Usage**:
```bash
python create_sample_db.py
```

**What it does**:
1. Reads the full 1.2 GB MySQL dump file
2. Identifies table types (critical/supporting/skip)
3. Selectively copies INSERT statements:
   - **100% retention**: Lexeme, Entry, Abbreviation (essential for forgotten words)
   - **10% sample**: Other supporting tables
   - **Skipped**: FullTextIndex (500+ MB of search indexes)
4. Creates a smaller but functional database

**Performance**:
- Processing time: 2-5 minutes
- Size reduction: 1.2 GB → ~285 MB (76% reduction)

**When to use**:
- First time setup (before any other scripts)
- When the full database is too large to work with
- For development and testing

**Critical tables kept at 100%**:
- `Lexeme` - Word forms with frequency data (essential!)
- `Entry` - Dictionary entries
- `Abbreviation` - Archaic markers like 'înv.'
- `EntryLexeme` - Links between entries and lexemes
- `Meaning` - Word meanings
- `Definition` - Full definitions

**Note**: If you have plenty of disk space and RAM, you can skip this and work with the full database.

---

### 3. `mysql_to_sqlite.py`

**Purpose**: Convert MySQL dump to SQLite database (alternative to extract_lexemes.py).

**Input**:
- `data/dictionaries/dex-database-sample.sql`

**Output**:
- `data/dictionaries/dex-sample.db` (SQLite database)

**Usage**:
```bash
python mysql_to_sqlite.py
```

**What it does**:
1. Reads MySQL SQL dump file
2. Converts MySQL syntax to SQLite:
   - Removes MySQL-specific commands (LOCK TABLES, SET)
   - Converts data types (int→INTEGER, varchar→TEXT)
   - Handles AUTO_INCREMENT → AUTOINCREMENT
   - Removes ENGINE, CHARSET clauses
3. Executes SQL statements in SQLite
4. Verifies data integrity
5. Shows sample forgotten word candidates

**Processing details**:
- Commits every 100 statements for performance
- Handles Romanian diacritics properly (UTF-8)
- Skips incompatible statements gracefully
- Progress indicators every 1000 lines

**When to use**:
- If you need the complete database structure (all tables)
- If you want to query beyond just Lexeme data
- For exploring table relationships

**Note**: Most users should use `extract_lexemes.py` instead, which is faster and more focused.

---

### 4. `extract_lexemes.py` ⭐ **Recommended**

**Purpose**: Fast extraction of Lexeme table to CSV and SQLite (recommended approach).

**Input**:
- `data/dictionaries/dex-database-sample.sql` (or full SQL dump)

**Output**:
- `data/processed/lexemes.csv` (~30 MB)
- `data/processed/lexemes.db` (~26 MB SQLite)

**Usage**:
```bash
# Activate virtual environment first!
source ~/devbox/envs/otzios/bin/activate

python extract_lexemes.py
```

**What it does**:
1. **Parses MySQL INSERT statements** directly (no database conversion needed)
2. **Extracts only Lexeme table** data (faster than full conversion)
3. **Creates CSV file** with all lexeme data
4. **Creates SQLite database** from CSV
5. **Verifies data** and shows sample forgotten words

**Why use this instead of mysql_to_sqlite.py?**
- Much faster (only processes Lexeme table)
- Smaller output (~26 MB vs full database)
- CSV export for easy inspection in spreadsheets
- Focused on forgotten words task

**Lexeme table columns**:
- `id` - Unique identifier
- `form` - Word with diacritics (e.g., "țară")
- `formNoAccent` - Word without diacritics
- `frequency` - Usage frequency (0.0-1.0) - **CRITICAL for forgotten words!**
- `description` - Part of speech (adj., s.m., vb., etc.)
- `modelType`, `modelNumber` - Morphological information
- And 15+ other metadata fields

**Sample output**:
```
Extracted 315,247 lexemes to data/processed/lexemes.csv
✅ Database created with 315,247 lexemes

Sample forgotten word candidates (low frequency):
  - bucle (adj.): frequency=0.030
  - poținel (adv.): frequency=0.030
  - precoace (adj.): frequency=0.030
```

**Performance**:
- Processing time: 1-3 minutes
- Memory usage: Low (<500 MB)
- Output size: CSV ~30 MB, DB ~26 MB

**When to use**:
- **Always use this as your primary data extraction method**
- First step after creating sample database
- When you need CSV export for analysis in Excel/pandas

---

### 5. `analyze_forgotten_words.py`

**Purpose**: Generate comprehensive analysis and initial forgotten words list.

**Input**:
- `data/processed/lexemes.db` (from extract_lexemes.py)

**Output**:
- `data/processed/forgotten_words_v1.csv` (~187k words - raw unfiltered)
- `data/processed/statistics.txt` (summary statistics)

**Usage**:
```bash
source ~/devbox/envs/otzios/bin/activate
python analyze_forgotten_words.py
```

**What it does**:
1. **Analyzes entire lexeme database** (315k words)
2. **Generates frequency distribution statistics**:
   - Very rare (0.01-0.25): 66k words
   - Rare (0.25-0.50): 69k words
   - Uncommon (0.50-0.70): 55k words
   - Common (0.70-0.85): 42k words
   - Very common (0.85-1.0): 45k words
3. **Part-of-speech distribution** for rare words
4. **Exports forgotten word candidates** (frequency < 0.70)
5. **Categorizes by rarity**
6. **Saves summary statistics** to text file

**Selection criteria**:
- Frequency > 0.01 (exclude zeros/errors)
- Frequency < 0.70 (rare/uncommon threshold)
- Word length > 2 characters (exclude abbreviations)

**Output format (CSV)**:
```csv
word,word_no_accent,frequency,category,description,model_type,create_date,mod_date
bucle,bucle,0.0300,very_rare,adj.,,1234567890,1234567890
griere,griere,0.3000,rare,s.m.,,1234567890,1234567890
```

**Statistics generated**:
- Total lexemes count
- Frequency distributions
- Part-of-speech breakdown
- Category counts (very_rare, rare, uncommon)

**When to use**:
- After extracting lexemes with `extract_lexemes.py`
- When you need comprehensive statistics
- To generate the initial unfiltered candidate list

**Note**: This produces ~187k candidates including proper nouns, technical terms, compounds. Use `create_curated_list.py` for filtered results.

---

### 6. `create_curated_list.py` ⭐ **Final Output**

**Purpose**: Create high-quality, filtered list of forgotten Romanian words.

**Input**:
- `data/processed/lexemes.db`

**Output**:
- `data/processed/forgotten_words_curated.csv` (1,884 high-quality words)

**Usage**:
```bash
source ~/devbox/envs/otzios/bin/activate
python create_curated_list.py
```

**What it does**:
1. **Queries low-frequency words** (frequency < 0.60)
2. **Applies quality filters**:
   - ✅ Has meaningful linguistic description
   - ✅ Not a proper noun (excludes "București", "Einstein")
   - ✅ Traditional Romanian vocabulary (excludes Latin phrases)
   - ✅ Not a compound/multi-word phrase
   - ✅ Minimum length > 3 characters
3. **Categorizes by rarity**:
   - Very rare (0.01-0.30): 413 words
   - Rare (0.30-0.50): 543 words
   - Uncommon (0.50-0.60): 928 words
4. **Exports curated list** with metadata

**Quality filters in detail**:

**Proper noun filter**:
- Removes: "București", "Einstein", "Paris"
- Keeps: "bucle", "griere", "jălitor"

**Romanian word filter**:
- Removes: Multi-word Latin phrases, foreign terms
- Removes: Strange hyphenation patterns
- Keeps: Traditional Romanian vocabulary

**Meaningful description filter**:
- Requires: adj., s.m., s.f., vb., adv., interj.
- Requires: Or archaic markers (înv., reg., arh.)
- Removes: Empty descriptions, pure model codes

**Output format (CSV)**:
```csv
word,word_no_accent,frequency,rarity_category,description,model_type,notes
bucle,bucle,0.0300,very_rare,adj.,,
băt'ârn,bat'arn,0.0500,very_rare,adj./s.m.,,
jălitor,jalitor,0.0700,very_rare,adj./s.m.,,
```

**Final counts**:
- Initial candidates: ~187k
- Filtered out proper nouns: 1,278
- Filtered out foreign/technical: 1
- Filtered out no description: 2,743
- **Final curated list: 1,884 words**

**When to use**:
- **Final step in the pipeline**
- When you need the highest quality forgotten words list
- For publication, research, or presentation

**This is the primary output of Phase 1!**

---

## Phase 2 Scripts Documentation

### 7. `download_wikipedia_ro.py`

**Purpose**: Download Romanian Wikipedia dataset from HuggingFace.

**Input**: None (downloads from internet)

**Output**:
- Wikipedia Romanian dataset cached in `~/.cache/huggingface/datasets/`
- Size: ~1.2-1.5 GB

**Usage**:
```bash
source ~/devbox/envs/otzios/bin/activate
python download_wikipedia_ro.py
```

**What it does**:
1. Connects to HuggingFace datasets
2. Downloads Wikipedia Romanian (20220301.ro snapshot)
3. Caches dataset locally
4. Shows sample article
5. Reports dataset statistics

**When to use**:
- Before running `process_corpus.py`
- First time setup for Phase 2
- Optional: `process_corpus.py` can auto-download

**Download time**: 5-15 minutes (depending on connection speed)

**Storage**: ~1.5 GB in HuggingFace cache

**Note**: This is optional - `process_corpus.py` will auto-download if needed.

---

### 8. `process_corpus.py` ⭐ **Phase 2 Main Script**

**Purpose**: Count occurrences of forgotten words in Romanian text corpora.

**Input**:
- `data/processed/forgotten_words_curated.csv` (1,884 words from Phase 1)
- Wikipedia Romanian dataset (HuggingFace)
- OSCAR Romanian dataset (streaming from HuggingFace)

**Output**:
- `data/processed/corpus_frequencies.db` (SQLite database ~100 MB)
- Progress logs and statistics

**Usage**:
```bash
source ~/devbox/envs/otzios/bin/activate

# Test mode: 1000 articles only (fast, for testing)
python process_corpus.py --test

# Sample mode: 50k Wikipedia + 50k OSCAR
python process_corpus.py --sample

# Full mode: All Wikipedia + 250k OSCAR (recommended)
python process_corpus.py --full

# Process only Wikipedia (skip OSCAR)
python process_corpus.py --full --wikipedia-only

# Process only OSCAR (skip Wikipedia)
python process_corpus.py --full --oscar-only
```

**What it does**:
1. **Loads forgotten words** from curated CSV (1,884 words)
2. **Creates fast lookup set** for O(1) token checking
3. **Streams Wikipedia Romanian**:
   - Tokenizes each article
   - Normalizes Romanian text (handles diacritics)
   - Counts word occurrences
   - Tracks document frequency
4. **Streams OSCAR Romanian** (web corpus):
   - Samples documents without full download
   - Same tokenization and counting
5. **Stores results** in SQLite database
6. **Shows top results** and statistics

**Processing modes**:

| Mode | Wikipedia | OSCAR | Time | Purpose |
|------|-----------|-------|------|---------|
| `--test` | 1,000 articles | 1,000 docs | ~2-5 min | Quick test |
| `--sample` | 50,000 articles | 50,000 docs | ~30 min | Representative sample |
| `--full` | All (~500k) | 250,000 docs | ~2-3 hours | Complete analysis |

**Performance**:
- Wikipedia: ~100-200 articles/sec
- OSCAR: ~50-100 docs/sec
- Memory usage: <1 GB RAM
- Storage: ~100 MB database + ~3-5 GB HuggingFace cache

**Romanian text normalization**:
```python
# Handles:
- Diacritics: preserves ă, â, î, ș, ț
- Legacy diacritics: converts ş→ș, ţ→ț
- Case: lowercase normalization
- Unicode: NFC normalization
- Tokenization: splits on whitespace/punctuation
```

**Database schema created**:
```sql
corpus_word_frequency (
    word, corpus_name,
    occurrence_count, document_count,
    last_updated
)

processing_stats (
    corpus_name, documents_processed,
    tokens_processed, processing_time
)
```

**Example output**:
```
Processing Wikipedia Romanian
✅ Wikipedia processing complete!
   Articles processed: 500,234
   Total tokens: 245,823,156
   Processing time: 2,521.3 seconds
   Rate: 198.5 articles/sec

Processing OSCAR Romanian (Streaming Sample)
✅ OSCAR processing complete!
   Documents processed: 250,000
   Total tokens: 189,456,823
   Processing time: 3,128.7 seconds
   Rate: 79.9 docs/sec

Top 20 Forgotten Words Found in Corpora:
----------------------------------------------------------------
Word                           Occurrences     Documents
----------------------------------------------------------------
celadon                                 234           156
comptabil                               189           142
contribuitor                            167           128
...
```

**When to use**:
- **After Phase 1** (after `create_curated_list.py`)
- **Before validation** (before `validate_forgotten_words.py`)
- Use `--test` first to verify everything works
- Use `--full` for final results

**Resume capability**: The script commits to database every 1000-5000 documents, so you can safely interrupt and resume.

---

### 9. `validate_forgotten_words.py`

**Purpose**: Cross-reference DEX frequency with corpus frequency to validate forgotten words.

**Input**:
- `data/processed/lexemes.db` (DEX frequency data)
- `data/processed/corpus_frequencies.db` (corpus counts from `process_corpus.py`)

**Output**:
- `data/processed/forgotten_words_validated.csv` ⭐ **FINAL VALIDATED LIST**
- `data/processed/validation_report.txt` (detailed analysis)
- `data/processed/false_positives.csv` (words to remove)

**Usage**:
```bash
source ~/devbox/envs/otzios/bin/activate
python validate_forgotten_words.py
```

**What it does**:
1. **Loads DEX frequency data** for all candidate words
2. **Loads corpus frequency data** from Wikipedia + OSCAR
3. **Calculates frequency per million words** for normalization
4. **Determines validation status** for each word:
   - **confirmed_forgotten**: < 0.1 per million (very rare)
   - **likely_forgotten**: < 1.0 per million (rare)
   - **uncommon**: < 10.0 per million (somewhat rare)
   - **questionable**: < 50.0 per million (not that rare)
   - **false_positive**: >= 50.0 per million (actually common!)
5. **Calculates confidence scores** (0-1 scale)
6. **Generates validation report** with statistics
7. **Exports validated list** and false positives

**Validation logic**:
```python
# Factors considered:
- DEX frequency (dictionary usage)
- Corpus occurrences (real-world usage)
- Document frequency (spread across texts)
- Frequency per million words (normalized)

# Confidence score (0-1):
confidence = (
    dex_score * 0.3 +       # Low DEX freq is good
    corpus_score * 0.5 +     # Low corpus freq confirms it
    doc_score * 0.2          # Appearing in few docs is better
)
```

**Expected results** (estimates):

From 1,884 candidates:
- **Confirmed forgotten**: 800-1,000 words (< 0.1 per million)
- **Likely forgotten**: 400-600 words (< 1.0 per million)
- **Uncommon**: 200-300 words (< 10.0 per million)
- **Questionable**: 100-200 words (need manual review)
- **False positives**: 50-150 words (remove from list)

**Total validated**: ~1,400-1,900 words

**Output format (CSV)**:
```csv
word,dex_frequency,description,corpus_occurrences,corpus_documents,frequency_per_million,validation_status,confidence_score,wikipedia_count,oscar_count
bucle,0.0300,adj.,0,0,0.000000,confirmed_forgotten,0.985,0,0
jălitor,0.0700,adj./s.m.,1,1,0.002341,confirmed_forgotten,0.912,0,1
griere,0.3000,s.m.,5,3,0.011701,likely_forgotten,0.805,2,3
...
```

**Validation report includes**:
- Corpus processing statistics
- Validation category breakdown
- Top 30 confirmed forgotten words (zero occurrences)
- Top 20 false positives (actually common)
- Confidence score distribution

**When to use**:
- **After `process_corpus.py`** completes
- Final step of Phase 2
- To generate the definitive validated list

**Processing time**: 2-5 minutes

**This produces the final, validated forgotten words list!**

---

## Complete Workflow

### Phase 1: Dictionary Analysis (Recommended Path)

```bash
# 1. Activate virtual environment
source ~/devbox/envs/otzios/bin/activate

# 2. Create sample database (optional but recommended)
python create_sample_db.py

# 3. Extract lexeme data
python extract_lexemes.py

# 4. Generate analysis
python analyze_forgotten_words.py

# 5. Create curated list
python create_curated_list.py
```

**Result**: `data/processed/forgotten_words_curated.csv` (1,884 candidates)

### Phase 2: Corpus Validation (NEW!)

```bash
# Activate virtual environment
source ~/devbox/envs/otzios/bin/activate

# 1. (Optional) Download Wikipedia dataset ahead of time
python download_wikipedia_ro.py

# 2. Test processing with small sample (recommended first step)
python process_corpus.py --test

# 3. Run full corpus processing (2-3 hours)
python process_corpus.py --full

# 4. Validate forgotten words against corpus data
python validate_forgotten_words.py
```

**Result**: `data/processed/forgotten_words_validated.csv` (~1,400-1,900 validated words)

### Full Database Path (Alternative)

If you want to work with the complete database:

```bash
source ~/devbox/envs/otzios/bin/activate

# Skip sampling, work with full database
python extract_lexemes.py  # Use full SQL file

# Or convert full database
python mysql_to_sqlite.py

# Then continue with analysis
python analyze_forgotten_words.py
python create_curated_list.py
```

---

## Output Files Summary

### Generated Files

| File | Size | Description | Script |
|------|------|-------------|--------|
| `dex-database-sample.sql` | 285 MB | Sampled MySQL dump | `create_sample_db.py` |
| `dex-sample.db` | Varies | Full SQLite conversion | `mysql_to_sqlite.py` |
| `lexemes.csv` | 30 MB | Lexeme data in CSV | `extract_lexemes.py` |
| `lexemes.db` | 26 MB | Lexeme SQLite database | `extract_lexemes.py` |
| `forgotten_words_v1.csv` | Large | Raw unfiltered list (187k) | `analyze_forgotten_words.py` |
| `statistics.txt` | Small | Summary statistics | `analyze_forgotten_words.py` |
| `forgotten_words_curated.csv` | Small | Phase 1 output (1,884 candidates) | `create_curated_list.py` |
| `corpus_frequencies.db` | ~100 MB | Corpus word frequencies | `process_corpus.py` |
| `forgotten_words_validated.csv` | Small | **FINAL VALIDATED LIST** ⭐ | `validate_forgotten_words.py` |
| `validation_report.txt` | Small | Validation analysis | `validate_forgotten_words.py` |
| `false_positives.csv` | Small | Words to remove | `validate_forgotten_words.py` |

### Key Outputs

**Phase 1 Output**: `data/processed/forgotten_words_curated.csv`
- 1,884 forgotten word candidates
- Based on DEX frequency data only
- Filtered for quality (no proper nouns, technical terms)
- Categorized by rarity level

**Phase 2 Output** (FINAL): `data/processed/forgotten_words_validated.csv`
- ~1,400-1,900 validated forgotten words
- Cross-referenced with modern Romanian corpora
- Includes corpus frequency data and confidence scores
- False positives removed

---

## Troubleshooting

### Virtual Environment Issues

**Problem**: `command not found: python3` or missing modules

**Solution**:
```bash
# Always activate virtual environment first
source ~/devbox/envs/otzios/bin/activate

# Verify it's activated (should show venv path)
which python
```

### File Not Found Errors

**Problem**: `FileNotFoundError: data/dictionaries/dex-database.sql`

**Solution**:
- Ensure you've downloaded the DEX database to `data/dictionaries/`
- Check the file path in the script matches your setup
- Run scripts from project root directory

### Memory Issues

**Problem**: Script crashes with memory error

**Solution**:
- Use `create_sample_db.py` to reduce database size first
- Use `extract_lexemes.py` instead of `mysql_to_sqlite.py` (more efficient)
- Close other applications to free RAM

### Encoding Issues

**Problem**: Romanian diacritics appear corrupted

**Solution**:
- All scripts use UTF-8 encoding by default
- Ensure your terminal supports UTF-8
- Check input files are UTF-8 encoded

### Empty Results

**Problem**: No forgotten words found

**Solution**:
- Verify `lexemes.db` has data: `sqlite3 data/processed/lexemes.db "SELECT COUNT(*) FROM Lexeme;"`
- Check frequency threshold settings in scripts
- Ensure database was created successfully

---

## Data Quality Notes

### Frequency Score Interpretation

The `frequency` field (0.0-1.0) represents usage in DEX's internal corpus:

- **0.85-1.0**: Very common everyday words (de, a, și, cu)
- **0.70-0.85**: Common words (known to most speakers)
- **0.50-0.70**: Uncommon but recognized
- **0.25-0.50**: Rare - candidates for forgotten words
- **0.01-0.25**: Very rare - likely forgotten
- **< 0.01**: Extremely rare or data errors

### Limitations

1. **Frequency is DEX-internal**: Not based on modern Romanian corpora
2. **No temporal data**: Can't determine when words fell out of use
3. **No definitions yet**: Need to join with Definition table (future work)
4. **Technical terms**: Some may slip through filters
5. **Regional variations**: May include valid dialectal words

### Next Steps (Phase 2)

To improve accuracy:
- Download modern Romanian corpora (Wikipedia, OSCAR)
- Cross-reference DEX frequency with corpus frequency
- Extract definition text from database
- Identify archaic markers in definitions
- Add temporal analysis using historical texts

---

## Script Development Notes

### Adding New Filters

To add custom filters in `create_curated_list.py`:

```python
def my_custom_filter(word_data):
    """Add your filter logic here."""
    form, frequency, description = word_data[0], word_data[2], word_data[3]
    # Your filter logic
    return True  # or False to filter out

# Add to filtering loop:
if not my_custom_filter(word_data):
    continue
```

### Custom Queries

To write custom SQL queries against the database:

```bash
sqlite3 data/processed/lexemes.db

# Example queries:
SELECT form, frequency FROM Lexeme WHERE description LIKE '%înv%' LIMIT 10;
SELECT COUNT(*) FROM Lexeme WHERE frequency < 0.5;
SELECT description, COUNT(*) FROM Lexeme GROUP BY description LIMIT 20;
```

### Performance Optimization

- Use streaming for large files
- Commit SQLite transactions in batches (every 100 records)
- Use CSV as intermediate format for inspection
- Index frequently queried columns

---

## Additional Resources

- **Database schema**: See [docs/dex-database-analysis.md](dex-database-analysis.md)
- **Project spec**: See [docs/romanian-forgotten-words-spec.md](romanian-forgotten-words-spec.md)
- **Results summary**: See [docs/results-summary.md](results-summary.md)
- **DEX Online wiki**: https://wiki.dexonline.ro/
- **GitHub schema docs**: https://github.com/dexonline/dexonline/wiki/Database-Schema

---

---

## Tools Scripts (`tools/`)

### `tools/build_ui_db.py` ⭐ **Run before deploying the web UI**

**Purpose**: Build `public/data/ui.db` — the single SQLite file that powers the PHP web interface.

**Input**:
- `data/processed/forgotten_words_shortlist.csv`
- `data/processed/diachronic_shortlist_web_validated.csv` (optional — adds web score columns)
- `data/processed/definitions.db` (optional — adds definition text)

**Output**:
- `public/data/ui.db` (~11 MB)

**Usage**:
```bash
# Run from repo root
python tools/build_ui_db.py
```

**What it does**:
1. Merges the shortlist CSV + web-validated CSV + definitions.db into a single `words` table (19,780 rows, 20 columns).
2. Builds a `vocab` table with distinct pipe-split values for `register`, `domain`, `etymology`, `pos` + occurrence counts, so PHP dropdown rendering is a simple `SELECT` instead of a full scan.
3. Creates four indexes: `idx_words_verdict`, `idx_words_tier`, `idx_words_word`, `idx_words_modern`.

Re-run after any pipeline update that changes the shortlist or definitions.

---

### `tools/export_research_to_json.py`

**Purpose**: Export server-side bookmarks/notes/tags from `data/research.db` (Flask app) into the localStorage JSON format used by the PHP UI.

**Usage**:
```bash
python tools/export_research_to_json.py > research_export.json
```

Then in the browser console on the PHP site:
```js
localStorage.setItem('otios.research', JSON.stringify(/* paste JSON */))
```

Only needed once when migrating from the Flask app. The PHP UI stores all research data in browser localStorage — no server writes.

---

## Web UI (`public/`)

The PHP web interface lives under `public/` and is equivalent to the Flask UI (`ui/`), but deployable on any shared host without Python.

**Deploy**:
1. `python tools/build_ui_db.py` → `public/data/ui.db`
2. Upload `public/` to the web root.
3. **PHP 8.0+** with `pdo_sqlite`, `mbstring` and `openssl` (default on most shared hosts).
   The earlier "7.4+" here was wrong — the code uses `str_starts_with()` (`api/search.php`)
   and `mixed` type hints (`api/_lib.php`), both 8.0-only.
4. Ensure a **writable directory one level above the web root**. On first request the app
   creates `<web root>/../private/` containing `app.db` (all user data) and `secret.key`.
   Override the location with `public/api/config.local.php`:
   ```php
   <?php define('OTIOS_PRIVATE_DIR', '/home/you/voroave-private');
   ```

**Two databases, and why**:

| File | Written by | Contents | Backup |
|---|---|---|---|
| `public/data/ui.db` | `tools/build_ui_db.py`, offline | words, definitions, taxonomy | not needed — regenerable |
| `<web root>/../private/app.db` | the app, at runtime | accounts, annotations, lists, game results | **required — irreplaceable** |

`ui.db` is replaced wholesale on every data refresh, so user data must never live in it.
It is also opened `query_only`; writes go through a separate connection in
`api/_appdb.php`. Keep `app.db` outside the web root: `public/data/` is directly
fetchable over HTTP (`public/data/.htaccess` blocks `.db` on Apache, but that is a
second line of defence, not the first).

**Run locally**:
```bash
php -S localhost:8000 -t public/
```

**Tests** (need a server running):
```bash
php -S localhost:8777 -t public/ &
node tests/test_store_sync.js     # annotation sync, offline queue, cross-device merge
node tests/test_game_api.js       # quiz secrecy, replay rejection, streak counters
node tests/test_search_scope.js   # a typed query ignores the filter sheet and any playlist
```

**Architecture**:
- `public/index.php` — page chrome, filter form, server-rendered vocab dropdowns
- `public/api/search.php` — paginated word list (HTML partial, HTMX)
- `public/api/word.php` — word detail panel (HTML partial, HTMX)
- `public/api/_lib.php` — shared PDO helpers
- `public/api/_partials/` — PHP equivalents of the Jinja partials
- `public/assets/app.css` — all styles
- `public/assets/app.js` — localStorage research store + HTMX hydration + keyboard shortcuts
- `public/metodologie.html` — static methodology page
- `public/data/ui.db` — generated; not committed

**Bookmarks, notes, tags** are stored in browser `localStorage` under the key `otios.research` (JSON, version 1). No server writes. Export/import is manual for now — use `tools/export_research_to_json.py` to seed from the Flask `research.db`.

---

**Last updated**: 2026-05-19
