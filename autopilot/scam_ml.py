"""scam_ml.py — Load and apply ML scam model (optional; graceful fallback)."""

import os
from pathlib import Path
from typing import Optional

_MODEL_PATH = Path(__file__).parent.parent / "models" / "scam.joblib"

_model = None
_ml_available = False
_ml_f1: Optional[float] = None


def load_model() -> bool:
    """Try to load the saved model. Returns True if successful."""
    global _model, _ml_available, _ml_f1
    if not _MODEL_PATH.exists():
        _ml_available = False
        return False
    try:
        import joblib
        loaded = joblib.load(_MODEL_PATH)
        # Expect dict with 'pipeline' and optional 'f1'
        if isinstance(loaded, dict):
            _model = loaded.get("pipeline")
            _ml_f1 = loaded.get("f1")
        else:
            _model = loaded
        _ml_available = _model is not None
        return _ml_available
    except Exception as e:
        print(f"[scam_ml] Failed to load model: {e}")
        _ml_available = False
        return False


def predict_proba(text: str) -> float:
    """
    Return ML scam probability for text.
    Returns 0.0 if ML is unavailable.
    """
    if not _ml_available or _model is None:
        return 0.0
    try:
        prob = _model.predict_proba([text])[0][1]
        return float(prob)
    except Exception:
        return 0.0


def is_available() -> bool:
    return _ml_available


def get_f1() -> Optional[float]:
    return _ml_f1


# Try loading on import (silent fail)
load_model()
