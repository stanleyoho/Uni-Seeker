"""Cross-repo API contract test: prediction_engine.

Uni-Seeker's prediction service (``app/api/v1/predictions.py``) calls the
following surface of the upstream ``prediction_engine`` package
(monorepo path-dep ``adaptive-alpha-engine/packages/prediction_engine``):

  - ``from prediction_engine.models import Base, PredictionRecord``
  - ``from prediction_engine.store import PredictionStore``
  - ``PredictionStore(sess).save_prediction(
        domain=..., entity_id=..., model_version=...,
        prediction_value=..., confidence=..., shap_values=...)``
  - ``PredictionStore(sess).resolve_prediction(prediction_id, actual_value=...)``
  - ``PredictionStore(sess).get_performance_window(domain=..., days=...)``

This test pins those public-symbol names and keyword-argument names so an
upstream refactor that renames/reorders them fails this test instead of
silently breaking Uni-Seeker at runtime.

Scope note: signatures *not* invoked by Uni-Seeker are intentionally NOT
pinned — that would make this an upstream test, not a contract test.
"""

from __future__ import annotations

import inspect

import pytest


@pytest.fixture(scope="module")
def pe():
    """Import upstream lazily; fail loudly if the path-dep is not installed."""
    return pytest.importorskip("prediction_engine")


# ── public symbol presence ──────────────────────────────────────────────────


def test_top_level_exports_PredictionStore(pe):
    """Uni-Seeker does ``from prediction_engine.store import PredictionStore``;
    it also relies on the top-level package re-exporting it."""
    assert hasattr(pe, "PredictionStore"), "prediction_engine.PredictionStore missing"


def test_submodule_store_has_PredictionStore():
    pass


def test_submodule_models_has_Base_and_PredictionRecord():
    pass


# ── signature pinning: PredictionStore methods Uni-Seeker calls ─────────────


def test_PredictionStore_init_signature():
    """Uni-Seeker calls ``PredictionStore(sess)`` — one positional ``session``."""
    from prediction_engine.store import PredictionStore

    params = list(inspect.signature(PredictionStore.__init__).parameters.keys())
    assert params[:2] == ["self", "session"], f"got {params}"


def test_PredictionStore_save_prediction_signature():
    """Uni-Seeker passes these kwargs to save_prediction()."""
    from prediction_engine.store import PredictionStore

    params = list(inspect.signature(PredictionStore.save_prediction).parameters.keys())
    expected_kwargs = {
        "self",
        "domain",
        "entity_id",
        "model_version",
        "prediction_value",
        "confidence",
        "shap_values",
    }
    missing = expected_kwargs - set(params)
    assert not missing, f"save_prediction missing kwargs: {missing}; got {params}"


def test_PredictionStore_resolve_prediction_signature():
    """Uni-Seeker calls ``store.resolve_prediction(prediction_id, actual_value=...)``."""
    from prediction_engine.store import PredictionStore

    params = list(inspect.signature(PredictionStore.resolve_prediction).parameters.keys())
    expected = {"self", "prediction_id", "actual_value"}
    missing = expected - set(params)
    assert not missing, f"resolve_prediction missing kwargs: {missing}; got {params}"


def test_PredictionStore_get_performance_window_signature():
    """Uni-Seeker calls ``store.get_performance_window(domain=..., days=...)``."""
    from prediction_engine.store import PredictionStore

    params = list(inspect.signature(PredictionStore.get_performance_window).parameters.keys())
    expected = {"self", "domain", "days"}
    missing = expected - set(params)
    assert not missing, f"get_performance_window missing kwargs: {missing}; got {params}"


# ── PredictionRecord column / attribute presence ────────────────────────────


def test_PredictionRecord_has_error_and_is_correct_attrs():
    """Uni-Seeker reads ``rec.error`` and ``rec.is_correct`` after resolution."""
    from prediction_engine.models import PredictionRecord

    for attr in ("error", "is_correct"):
        assert hasattr(PredictionRecord, attr), f"PredictionRecord.{attr} missing"
