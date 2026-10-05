#!/usr/bin/env python3
"""Shared numeric thresholds for the Oțios pipeline.

Single source of truth for DEX ``frequency``-based cutoffs and rarity bins.
These literals used to be duplicated — and to disagree — across
``analyze_forgotten_words.py``, ``create_curated_list.py``, and
``validate_forgotten_words.py``. See docs/BACKLOG.md (#5).

The current pipeline treats DEX ``frequency`` in [0.0, 1.0] as a
lexicographic-prominence signal, not measured usage frequency. This is an
empirical interpretation. The legacy rarity-bin names remain for compatibility.
``0.0`` means *no data*, NOT "rarest" — filter with ``frequency > MIN_FREQUENCY``.
"""

# --- Shared across all stages -------------------------------------------------

# Floor: 0.0 / near-zero is missing data, not rarity. Exclude it everywhere.
MIN_FREQUENCY = 0.01

# Minimum headword length for a candidate (drops 1–3 char noise/abbreviations).
MIN_FORM_LENGTH = 3


# --- Canonical rarity bins (create_curated_list.py) ---------------------------
#
# Half-open bins over DEX frequency, evaluated low-to-high (first match wins):
#   very_rare : (MIN_FREQUENCY, VERY_RARE_MAX)
#   rare      : [VERY_RARE_MAX,  RARE_MAX)
#   uncommon  : [RARE_MAX,       UNCOMMON_MAX)
#   standard  : [UNCOMMON_MAX,   1.0)        DEX-canonical; corpus may disagree
VERY_RARE_MAX = 0.30
RARE_MAX = 0.50
UNCOMMON_MAX = 0.60

# Candidate ceiling for the curated list: excludes only the ~14k core-vocabulary
# entries (frequency == 1.0).
CURATED_FREQ_CEILING = 1.0


def rarity_category(freq):
    """Map a DEX frequency to a canonical rarity label.

    Returns one of 'very_rare' / 'rare' / 'uncommon' / 'standard', or ``None``
    when ``freq`` is missing data (``<= MIN_FREQUENCY``).
    """
    if freq is None or freq <= MIN_FREQUENCY:
        return None
    if freq < VERY_RARE_MAX:
        return 'very_rare'
    if freq < RARE_MAX:
        return 'rare'
    if freq < UNCOMMON_MAX:
        return 'uncommon'
    return 'standard'


# --- Legacy thresholds (Phase 2 legacy path) ----------------------------------
#
# These belong to the older, known-buggy pipeline (see BACKLOG P0). They are
# intentionally distinct from the canonical bins above because each is coupled
# to its own candidate ceiling; do not silently fold them into the canonical
# values without re-checking the affected script's binning logic.

# analyze_forgotten_words.py: words below this are "candidates".
ANALYZE_FREQ_THRESHOLD = 0.70

# validate_forgotten_words.py: candidate band ceiling.
VALIDATION_FREQ_CEILING = 0.60
