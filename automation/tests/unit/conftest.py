"""Shared fixtures for automation/tests/unit/.

Invariants guaranteed for every test in this package:
  - _resolve_region    → identity pass-through (autouse monkeypatch).
  - _save_debug_image  → writes to pytest tmp_path (autouse monkeypatch).
  - _run_tesseract     → returns a well-formed empty dict (autouse monkeypatch).
  - _ocr_targets_cache → reset to None before each test (autouse monkeypatch).

Tests that need the real Tesseract binary:
  1. Decorate with @requires_tesseract (skips at collection when binary absent).
  2. Request the ``real_tesseract`` fixture to un-stub _run_tesseract.

Tests that need the real _resolve_region logic:
  Request the ``real_resolve_region`` fixture, which returns the original
  function saved at module import time (before any autouse patching).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

import automation.core.ocr as _ocr_mod

# ---------------------------------------------------------------------------
# Save originals at import time — BEFORE any autouse fixture can patch them.
# These are referenced by the real_tesseract and real_resolve_region fixtures.
# ---------------------------------------------------------------------------
_REAL_RUN_TESSERACT = _ocr_mod._run_tesseract
_REAL_RESOLVE_REGION = _ocr_mod._resolve_region

# Check Tesseract binary availability once at collection time.
_TESSERACT_AVAILABLE = False
try:
    import pytesseract as _tess  # noqa: F401
    _tess.get_tesseract_version()
    _TESSERACT_AVAILABLE = True
except Exception:  # noqa: BLE001
    pass

# Decorator: skip a test at collection time when Tesseract is absent.
requires_tesseract = pytest.mark.skipif(
    not _TESSERACT_AVAILABLE,
    reason="Tesseract binary not available — install tesseract-ocr to run",
)


# ---------------------------------------------------------------------------
# Synthetic image helpers — importable by test modules
# ---------------------------------------------------------------------------


def make_clean_pil(text: str = "HELLO 123") -> Image.Image:
    """Black text on white background; large enough for reliable Tesseract output."""
    h, w = 100, 600
    canvas = np.ones((h, w, 3), dtype=np.uint8) * 255
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, font, 2.0, 3)
    x = max(10, (w - tw) // 2)
    y = max(th + 10, (h + th) // 2)
    cv2.putText(canvas, text, (x, y), font, 2.0, (0, 0, 0), 3, cv2.LINE_AA)
    return Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))


def make_inverted_pil(text: str = "HELLO 123") -> Image.Image:
    """White text on black background — requires 'invert' preprocessing."""
    h, w = 100, 600
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, font, 2.0, 3)
    x = max(10, (w - tw) // 2)
    y = max(th + 10, (h + th) // 2)
    cv2.putText(canvas, text, (x, y), font, 2.0, (255, 255, 255), 3, cv2.LINE_AA)
    return Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))


def make_noise_pil(seed: int = 42) -> Image.Image:
    """Random noise — OCR should produce near-zero confidence."""
    rng = np.random.default_rng(seed)
    data = rng.integers(0, 256, (80, 400, 3), dtype=np.uint8)
    return Image.fromarray(data.astype(np.uint8))


def make_blurred_pil(text: str = "HELLO 123", ksize: int = 7, sigma: float = 3.0) -> Image.Image:
    """Gaussian-blurred version of make_clean_pil."""
    arr = cv2.cvtColor(np.array(make_clean_pil(text)), cv2.COLOR_RGB2BGR)
    blurred = cv2.GaussianBlur(arr, (ksize, ksize), sigma)
    return Image.fromarray(cv2.cvtColor(blurred, cv2.COLOR_BGR2RGB))


# ---------------------------------------------------------------------------
# Autouse fixtures — applied to every test in this package automatically
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def passthrough_resolve_region(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace _resolve_region with an identity lambda; no Citrix window needed."""
    monkeypatch.setattr(_ocr_mod, "_resolve_region", lambda r: r)


@pytest.fixture(autouse=True)
def redirect_debug_images(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect OCR debug image writes to pytest's tmp_path."""
    counter = {"n": 0}

    def _fake_save(img: np.ndarray, prefix: str = "ocr") -> Path:
        counter["n"] += 1
        dest = tmp_path / f"{prefix}_{counter['n']}.png"
        cv2.imwrite(str(dest), img)
        return dest

    monkeypatch.setattr(_ocr_mod, "_save_debug_image", _fake_save)


@pytest.fixture(autouse=True)
def reset_ocr_target_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the module-level OCR target cache before each test."""
    monkeypatch.setattr(_ocr_mod, "_ocr_targets_cache", None)


@pytest.fixture(autouse=True)
def stub_run_tesseract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub _run_tesseract so no Tesseract binary is required.

    Returns a well-formed but empty pytesseract output dict so that
    _compute_confidence produces ("", 0.0).  Tests that want a non-empty
    result must patch _compute_confidence directly; tests that need the
    real Tesseract binary must use @requires_tesseract + real_tesseract.
    """
    def _stub(img: np.ndarray, lang: str, psm: int) -> dict:
        return {"text": [], "conf": [], "word_num": [], "page_num": []}

    monkeypatch.setattr(_ocr_mod, "_run_tesseract", _stub)


# ---------------------------------------------------------------------------
# Optional fixtures — requested explicitly by individual tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def real_tesseract():
    """Restore the real _run_tesseract for the duration of one test.

    Use together with @requires_tesseract so the test is skipped cleanly
    when the Tesseract binary is absent.  Does NOT use monkeypatch so there
    is no teardown conflict with the autouse stub_run_tesseract fixture.
    """
    # autouse stub_run_tesseract has already run; _run_tesseract is the stub.
    # Save the stub so we can re-install it in teardown.
    _current_stub = _ocr_mod._run_tesseract
    _ocr_mod._run_tesseract = _REAL_RUN_TESSERACT
    yield
    # Restore the stub; the autouse monkeypatch will then restore the
    # original on its own teardown cycle.
    _ocr_mod._run_tesseract = _current_stub


@pytest.fixture()
def real_resolve_region():
    """Return the original _resolve_region saved before any autouse patching.

    Use this fixture when a test needs to exercise the real offset logic
    without calling the Citrix window manager.
    """
    return _REAL_RESOLVE_REGION


@pytest.fixture()
def fake_ocr_targets(monkeypatch: pytest.MonkeyPatch) -> dict[str, _ocr_mod._OcrTarget]:
    """Inject a minimal in-memory OCR target dict; no YAML file read."""
    targets = {
        "test_screen.label": _ocr_mod._OcrTarget(
            name="test_screen.label",
            screen="test_screen",
            region=(0, 0, 600, 100),
            expected_pattern=r"HELLO\s+\d+",
            lang="eng",
            preprocess=["grayscale", "upscale_2x", "otsu_threshold"],
            min_confidence=0.50,
        ),
    }
    monkeypatch.setattr(_ocr_mod, "_ocr_targets_cache", targets)
    return targets
