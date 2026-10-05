#!/usr/bin/env python3
"""Permanent word ids — the dictionary behind the compact ``?w=`` share URLs.

A share URL carries base36 word ids, not the words themselves, because Romanian
diacritics percent-encode to six characters each (``ă`` → ``%C4%83``) and a
twenty-word playlist runs past 300 characters. Ids are 1–3 base36 characters, so
the same list fits in about 70.

That only works if an id means the same word forever. ``ui.db`` is deleted and
rebuilt by ``build_ui_db.py`` on every data refresh, so the id cannot come from
row order, a rowid, or anything else the rebuild decides — it has to come from a
registry that outlives the database.

Hence ``data/word_ids.tsv``: append-only, force-tracked in git despite the
blanket ``data/*`` ignore. Words are only ever added, never renumbered and never
removed (a word dropped from a later shortlist keeps its id, so old links to it
still resolve). An accidental renumbering shows up as a 25k-line diff instead of
silently repointing every link that was ever shared.
"""
import contextlib
import fcntl
import os
from pathlib import Path

REGISTRY_PATH = Path('data/word_ids.tsv')


class RegistryLocked(RuntimeError):
    """Another process holds the registry lock."""


@contextlib.contextmanager
def registry_lock(path: Path = REGISTRY_PATH):
    """Hold an exclusive, non-blocking ``flock`` on ``<registry>.lock``.

    Id allocation reads the registry, picks ``max + 1`` and appends. Two processes
    doing that at once hand out the same id to different words. The lock makes the
    read-pick-append sequence one step. ``flock`` is released by the kernel when the
    process dies, so a killed run cannot strand it. Raises ``RegistryLocked`` at once
    when another process holds it.
    """
    path = Path(path)
    lock_path = path.with_name(path.name + '.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open('a+', encoding='utf-8')
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.seek(0)
            holder = handle.read().strip() or 'holder unknown'
            raise RegistryLocked(f'{lock_path} is held by {holder}') from None
        handle.seek(0)
        handle.truncate()
        handle.write(f'pid {os.getpid()}\n')
        handle.flush()
        yield
    finally:
        handle.close()


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, int]:
    """Read word → id. Returns {} when the registry does not exist yet."""
    registry: dict[str, int] = {}
    if not path.exists():
        return registry

    with open(path, encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip('\n')
            if not line:
                continue
            id_str, _, word = line.partition('\t')
            if not word:
                raise ValueError(f'{path}:{lineno}: expected "<id>\\t<word>", got {line!r}')
            registry[word] = int(id_str)
    return registry


def assign(words, registry: dict[str, int], path: Path = REGISTRY_PATH) -> dict[str, int]:
    """Give every word an id, appending the ones the registry has not seen.

    New words are sorted before they are numbered, so two runs over the same
    input produce the same file regardless of the order `words` arrived in.
    Mutates and returns `registry`.
    """
    unseen = sorted({w for w in words if w and w not in registry})
    if not unseen:
        return registry

    next_id = max(registry.values(), default=0) + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for word in unseen:
        lines.append(f'{next_id}\t{word}\n')
        next_id += 1
    # One write, then fsync: a crash leaves the whole batch or (at worst) a torn tail,
    # never ids interleaved with another writer. Memory is updated only after the
    # append succeeded, so a failed write leaves `registry` equal to the file.
    with open(path, 'a', encoding='utf-8') as f:
        f.write(''.join(lines))
        f.flush()
        os.fsync(f.fileno())
    for line in lines:
        id_str, _, word = line.rstrip('\n').partition('\t')
        registry[word] = int(id_str)

    return registry


def apply_to_db(conn, path: Path = REGISTRY_PATH, hold_lock: bool = True) -> int:
    """Assign ids to every word in `conn` and write them to the `word_id` column.

    Shared by build_ui_db.py (full rebuild) and migrate_ui_db_word_ids.py
    (backfill of an already-deployed ui.db), so both go through the same
    registry. Idempotent: a second run assigns nothing new and rewrites the same
    values.

    Takes the registry lock around load + assign. A caller that already holds it
    (``build_ui_db.build``) passes ``hold_lock=False``: ``flock`` locks are per open
    file, so taking it twice in one process would fail.
    """
    words = [w for (w,) in conn.execute('SELECT word FROM words')]
    if hold_lock:
        with registry_lock(path):
            registry = assign(words, load_registry(path), path)
    else:
        registry = assign(words, load_registry(path), path)

    conn.executemany(
        'UPDATE words SET word_id = ? WHERE word = ?',
        [(registry[w], w) for w in words],
    )
    return len(words)
