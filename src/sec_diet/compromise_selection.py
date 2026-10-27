"""Reference-based menu selection with explicit absence of a joint improvement."""
from __future__ import annotations

import numpy as np


def reference_gains(values, reference):
    """Signed improvements in physical N/C/W/D outcomes relative to observed means.

    N uses the remaining attainment headroom to 100%; C/W/D use their positive
    observed means. Positive values denote improvement in every coordinate.
    """
    values = np.asarray(values, dtype=float)
    reference = np.asarray(reference, dtype=float)
    if (values.ndim != 2 or values.shape[1] != 4 or reference.shape != (4,)
            or not np.isfinite(values).all() or not np.isfinite(reference).all()
            or not 0 <= reference[0] < 100 or (reference[1:] <= 0).any()):
        raise ValueError('Finite N/C/W/D outcomes and positive reference scales are required')
    gains = (reference - values) / reference.clip(min=1e-12)
    gains[:, 0] = (values[:, 0] - reference[0]) / (100 - reference[0])
    return gains


def select_reference_compromise(values, reference, candidate_indices, protect_departure=False):
    """Return a row index or None, never substitute a worsening menu.

    Strictly improve N/C/W, optionally also D, relative to the profile's
    observed means. Maximize the smallest relative gain; ties prefer the sum
    of gains and then the smaller original candidate identifier.
    """
    gains = reference_gains(values, reference)[:, :4 if protect_departure else 3]
    candidates = np.asarray(candidate_indices, dtype=int)
    if candidates.shape != (len(gains),):
        raise ValueError('One candidate identifier per menu is required')
    eligible = np.flatnonzero((gains > 1e-12).all(axis=1))
    if not len(eligible):
        return None
    ranked = np.lexsort((candidates[eligible], -gains[eligible].sum(axis=1),
                         -gains[eligible].min(axis=1)))
    return int(eligible[ranked[0]])


def select_reference_distance(values, normalized, reference, candidate_indices):
    """Strictly improve all four outcomes, then minimize the fixed ideal distance.

    The candidate pool may contain all energy-feasible evaluated menus. None
    means that the pool contains no joint improvement; there is no fallback.
    """
    gains = reference_gains(values, reference)
    normalized = np.asarray(normalized, dtype=float)
    ids = np.asarray(candidate_indices, dtype=int)
    if normalized.shape != gains.shape or ids.shape != (len(gains),) or not np.isfinite(normalized).all():
        raise ValueError('Aligned finite normalized coordinates and candidate identifiers are required')
    eligible = np.flatnonzero((gains > 1e-12).all(axis=1))
    if not len(eligible):
        return None
    order = np.lexsort((ids[eligible], np.linalg.norm(normalized[eligible], axis=1)))
    return int(eligible[order[0]])
