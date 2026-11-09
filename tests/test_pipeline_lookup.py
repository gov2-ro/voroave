"""Regression tests for four pipeline fixes (2026-11-09).

1. `extract_lexemes.parse_mysql_insert` keeps rows with `)` inside quoted fields.
2. `extract_taxonomy.py` defaults to the full dump, not the sample.
3. The corpus lookup set includes `modelType = 'V'` in all four processors.
4. `create_curated_list` and `validate_diachronic` classify DEX tags the same way,
   including the root tags 6 (`rar`), 17 (`regional`) and 239 (`ieșit din uz`).

All databases are tiny synthetic files under `tmp_path`.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import constants  # noqa: E402
import create_curated_list  # noqa: E402
import dump_parser  # noqa: E402
import extract_lexemes  # noqa: E402
import extract_taxonomy  # noqa: E402
import process_culturax  # noqa: E402
import process_lumro  # noqa: E402
import process_subtitles  # noqa: E402
import process_wikisource  # noqa: E402
import validate_diachronic  # noqa: E402


# ---- 1. tuple parser ---------------------------------------------------------------------

def test_parser_keeps_rows_with_a_paren_inside_a_quoted_field():
    line = ("INSERT INTO `Lexeme` VALUES (1,'cal','cal',0.96,'s.m.'),"
            "(2,'a)b','x (y)',0.5,'(înv.)'),(3,'mâț',NULL,0.4,'');\n")
    table, rows = extract_lexemes.parse_mysql_insert(line)
    assert table == 'Lexeme'
    assert rows == [['1', 'cal', 'cal', '0.96', 's.m.'],
                    ['2', 'a)b', 'x (y)', '0.5', '(înv.)'],
                    ['3', 'mâț', None, '0.4', '']]


def test_parser_decodes_mysql_escapes_and_commas():
    line = r"INSERT INTO `T` VALUES (1,'it\'s, ok','a\\b','x\ny','q\"z');" + '\n'
    _, rows = extract_lexemes.parse_mysql_insert(line)
    assert rows == [['1', "it's, ok", 'a\\b', 'x\ny', 'q"z']]


def test_parser_table_filter_and_non_insert_lines():
    line = "INSERT INTO `Definition` VALUES (1,'x');\n"
    assert extract_lexemes.parse_mysql_insert(line, tables=('Lexeme',)) == ('Definition', [])
    assert extract_lexemes.parse_mysql_insert('-- comment\n') == (None, [])
    assert extract_lexemes.parse_mysql_insert("INSERT INTO `T` VALUES (1,'x')\n") == (None, [])


def test_parse_rows_does_not_change_the_existing_helpers():
    # parse_tuples is used by three other extractors; its behavior stays as it was.
    assert list(dump_parser.parse_tuples("(1,'a)b',3)", max_index=1)) == [['1', 'a)b']]


# ---- 2. extract_taxonomy default ---------------------------------------------------------

def test_extract_taxonomy_defaults_to_the_full_dump():
    args = extract_taxonomy.parse_args([])
    assert args.sql == 'data/dictionaries/dex-database.sql'
    assert 'sample' not in args.sql


# ---- 3. corpus lookup set ----------------------------------------------------------------

def make_lexemes(path, rows):
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE Lexeme (id INTEGER, form TEXT, formNoAccent TEXT, '
                 'frequency REAL, description TEXT, modelType TEXT)')
    conn.executemany('INSERT INTO Lexeme VALUES (?,?,?,?,?,?)', rows)
    conn.commit()
    conn.close()


@pytest.mark.parametrize('module', [process_wikisource, process_culturax,
                                    process_lumro, process_subtitles],
                         ids=lambda m: m.__name__)
def test_every_processor_counts_verbs_with_modeltype_v(tmp_path, module):
    db = tmp_path / 'lexemes.db'
    make_lexemes(db, [
        (1, 'râde', 'râde', 0.99, '', 'V'),        # the reported case
        (2, 'cânta', 'cânta', 0.9, '', 'VT'),
        (3, 'formă', 'formă', 0.9, '', 'T'),       # inflected form: still excluded
        (4, 'ziar', 'ziar', 0.9, None, 'N'),
    ])
    words = module.load_dex_words(db)
    assert {'râde', 'cânta', 'ziar'} <= words
    assert 'formă' not in words


def test_lookup_set_is_shared():
    assert 'V' in constants.CORPUS_LOOKUP_MODEL_TYPES
    assert {'VT', 'VI'} <= set(constants.CORPUS_LOOKUP_MODEL_TYPES)
    assert 'T' not in constants.CORPUS_LOOKUP_MODEL_TYPES


# ---- 4. tag families ---------------------------------------------------------------------

def make_taxonomy(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE Lexeme (id INTEGER, formNoAccent TEXT);
        CREATE TABLE Tag (id INTEGER, parentId INTEGER, isPos INTEGER, value TEXT);
        CREATE TABLE ObjectTag (objectId INTEGER, objectType INTEGER, tagId INTEGER);
        CREATE TABLE EntryLexeme (lexemeId INTEGER, entryId INTEGER);
        CREATE TABLE TreeEntry (entryId INTEGER, treeId INTEGER);
        CREATE TABLE MeaningTree (meaning_id INTEGER, tree_id INTEGER);
        INSERT INTO Lexeme VALUES (10, 'zapciu');
        INSERT INTO EntryLexeme VALUES (10, 100);
        INSERT INTO TreeEntry VALUES (100, 1000);
        INSERT INTO MeaningTree VALUES (5000, 1000);
        INSERT INTO Tag VALUES (6, 0, 0, 'rar'), (239, 0, 0, 'ieșit din uz'),
                               (17, 0, 0, 'regional'), (18, 17, 0, 'Moldova'),
                               (42, 0, 0, 'registru'), (43, 42, 0, 'învechit'),
                               (41, 0, 0, 'domeniu'), (44, 41, 0, 'istorie'),
                               (1, 0, 0, 'etimologie'), (45, 1, 0, 'turcă'),
                               (99, 0, 0, 'altceva');
        INSERT INTO ObjectTag VALUES (5000, 3, 6), (5000, 3, 239), (5000, 3, 17),
                                     (5000, 3, 18), (5000, 3, 43), (5000, 3, 44),
                                     (5000, 3, 45), (5000, 3, 99);
    """)
    conn.commit()
    conn.close()


def test_curated_and_diachronic_tag_families_agree(tmp_path):
    db = tmp_path / 'lexemes.db'
    make_taxonomy(db)
    diachronic = validate_diachronic.load_taxonomy(db)['zapciu']
    conn = sqlite3.connect(db)
    curated = create_curated_list.fetch_all_tags(conn, [10])[10]
    conn.close()

    expected_register = {'rar', 'ieșit din uz', 'regional', 'Moldova', 'învechit'}
    assert diachronic['register'] == expected_register
    assert set(curated['register'].split('; ')) == expected_register
    assert set(curated['domain'].split('; ')) == diachronic['domain'] == {'istorie'}
    assert set(curated['etymology'].split('; ')) == diachronic['etymology'] == {'turcă'}


# ---- 5. --db: a recount writes to its own database and checkpoint ------------------------

DEFAULT_DB = Path('data/processed/corpus_frequencies.db')


@pytest.mark.parametrize('module', [process_wikisource, process_culturax, process_lumro],
                         ids=lambda m: m.__name__)
def test_default_db_is_unchanged(module):
    assert module.FREQ_DB == DEFAULT_DB


@pytest.mark.parametrize('module', [process_wikisource, process_culturax],
                         ids=lambda m: m.__name__)
def test_other_db_gets_its_own_checkpoint(module, monkeypatch, tmp_path):
    monkeypatch.setattr(module, 'FREQ_DB', module.FREQ_DB)
    monkeypatch.setattr(module, 'CHECKPOINT', module.CHECKPOINT)
    main_checkpoint = module.CHECKPOINT

    module.use_db(DEFAULT_DB)
    assert module.CHECKPOINT == main_checkpoint     # the main run keeps its checkpoint

    module.use_db(tmp_path / 'corpus_frequencies.v2.db')
    assert module.FREQ_DB == tmp_path / 'corpus_frequencies.v2.db'
    assert module.CHECKPOINT == tmp_path / ('corpus_frequencies.v2.' + main_checkpoint.name)
    assert module.CHECKPOINT != main_checkpoint     # --resume cannot read the old run's progress


def test_lumro_db_option(monkeypatch, tmp_path):
    monkeypatch.setattr(process_lumro, 'FREQ_DB', process_lumro.FREQ_DB)
    process_lumro.use_db(tmp_path / 'v2.db')
    assert process_lumro.FREQ_DB == tmp_path / 'v2.db'
