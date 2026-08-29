"""pipelines.model.similarity — dispatch from a measure name to a similarity matrix.

The seam that let P5 add distance correlation without touching ``model.train``: ``train.py``
never imports a similarity implementation directly, it names a measure and calls
:func:`similarity`. The string it names is exactly ``model_runs.similarity_measure``, validated
here against the same set the schema's CHECK constraint enforces
(``pipelines.artifact.schema.SIMILARITY_MEASURES``), so an unknown measure fails before a run is
built rather than after.
"""

from __future__ import annotations

import numpy as np

from pipelines.artifact.schema import SIMILARITY_MEASURES
from pipelines.factor.model import residual_similarity
from pipelines.model.dcor import residual_dcor2


def similarity(E: np.ndarray, measure: str) -> np.ndarray:
    """P = the similarity matrix for residuals ``E`` (T×N) under ``measure``.

    ``"pearson_rho2"`` — squared Pearson correlation (docs/01 §4).
    ``"dcor2"`` — squared distance correlation, V-statistic (docs/01 §7, D-5). Only this branch
    differs between the two measures: both consume the identical ``E`` from the identical
    factor-model fit, which is what "only §4 changes" (docs/01 §7) means in code.
    """
    if measure not in SIMILARITY_MEASURES:
        raise ValueError(f"unknown similarity measure {measure!r}; expected one of "
                         f"{sorted(SIMILARITY_MEASURES)}")
    if measure == "pearson_rho2":
        return residual_similarity(E)
    return residual_dcor2(E)
