"""Tests for global reproducibility and seed determinism (R6)."""

import random

from backend.app.core.seed import set_global_seed


def test_seed_determinism():
    """Verify that set_global_seed produces identical pseudo-random outputs across runs."""
    set_global_seed(42)
    sequence_a = [random.random() for _ in range(10)]
    integers_a = [random.randint(0, 1000) for _ in range(10)]

    # Reset seed to 42
    set_global_seed(42)
    sequence_b = [random.random() for _ in range(10)]
    integers_b = [random.randint(0, 1000) for _ in range(10)]

    assert sequence_a == sequence_b, "Random float sequence must be identical when re-seeded"
    assert integers_a == integers_b, "Random integer sequence must be identical when re-seeded"


def test_seed_changes_output():
    """Verify different seeds produce different sequences."""
    set_global_seed(42)
    seq_42 = [random.random() for _ in range(5)]

    set_global_seed(99)
    seq_99 = [random.random() for _ in range(5)]

    assert seq_42 != seq_99, "Different seeds must produce different sequences"
