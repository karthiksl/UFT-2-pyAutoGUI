"""Unit tests for automation/core/ocr.py.

Test matrix
-----------
Class                    Needs Tesseract?  Needs Citrix?
─────────────────────────────────────────────────────────
TestPreprocessingSteps   No               No
TestComputeConfidence    No               No
TestReadText (most)      No  (stub)       No
TestReadText (4 tests)   Yes (@mark)      No
TestAssertText           No  (mock comp.) No
TestAssertTextWithTarget No  (mock comp.) No
TestRetryBehaviour       No  (mock comp.) No
TestReadTarget           No  (stub)       No
TestResolveRegion        No  (direct fn.) No

All autouse fixtures in conftest.py are applied automatically:
  - _run_tesseract  → stub (empty dict)
  - _resolve_region → identity lambda
  - _save_debug_image → writes to tmp_path
  - _ocr_targets_cache → reset to None
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from PIL import Image

# pytesseract package must be importable; binary absence is handled per-test.
pytest.importorskip("pytesseract", reason="pytesseract package not installed")

import automation.core.ocr as ocr_mod
from automation.core.exceptions import OcrLowConfidenceError, OcrTextMismatchError
from automation.tests.unit.conftest import (
    _REAL_RESOLVE_REGION,
    make_blurred_pil,
    make_clean_pil,
    make_inverted_pil,
    make_noise_pil,
    requires_tesseract,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _patch_grab(monkeypatch: pytest.MonkeyPatch, pil_img: Image.Image) -> None:
    """Inject *pil_img* as the return value of every _grab_region call."""
    monkeypatch.setattr(ocr_mod, "_grab_region", lambda _region: pil_img)


def _inject_ocr(monkeypatch: pytest.MonkeyPatch, text: str, confidence: float) -> None:
    """Stub _compute_confidence to return (*text*, *confidence*) regardless of input."""
    monkeypatch.setattr(ocr_mod, "_compute_confidence", lambda _data: (text, confidence))


# ---------------------------------------------------------------------------
# 1. Preprocessing step unit tests
# ---------------------------------------------------------------------------


class TestPreprocessingSteps:
    """Exercise each _step_* function in isolation; no Tesseract required."""

    def _bgr(self, h: int = 80, w: int = 200) -> np.ndarray:
        rng = np.random.default_rng(0)
        return rng.integers(0, 256, (h, w, 3), dtype=np.uint8)

    def test_grayscale_reduces_to_single_channel(self) -> None:
        """3-channel BGR → 2-channel gray."""
        assert ocr_mod._step_grayscale(self._bgr()).ndim == 2

    def test_grayscale_is_idempotent_on_2d_input(self) -> None:
        """Passing an already-gray array returns a 2D array unchanged."""
        gray = ocr_mod._step_grayscale(self._bgr())
        assert ocr_mod._step_grayscale(gray).ndim == 2

    def test_upscale_2x_doubles_both_dimensions(self) -> None:
        img = self._bgr(40, 100)
        up = ocr_mod._step_upscale(img, 2)
        assert up.shape[:2] == (80, 200)

    def test_upscale_3x_triples_both_dimensions(self) -> None:
        img = self._bgr(30, 60)
        up = ocr_mod._step_upscale(img, 3)
        assert up.shape[:2] == (90, 180)

    def test_otsu_produces_strictly_binary_output(self) -> None:
        result = ocr_mod._step_otsu(self._bgr())
        assert set(np.unique(result)) <= {0, 255}

    def test_adaptive_threshold_produces_strictly_binary_output(self) -> None:
        result = ocr_mod._step_adaptive(self._bgr())
        assert set(np.unique(result)) <= {0, 255}

    def test_invert_is_bitwise_complement(self) -> None:
        """For every pixel: original + inverted == 255."""
        img = self._bgr()
        inv = ocr_mod._step_invert(img)
        assert np.all(img.astype(np.int16) + inv.astype(np.int16) == 255)

    def test_dilate_preserves_array_shape(self) -> None:
        img = ocr_mod._step_grayscale(self._bgr())
        assert ocr_mod._step_dilate(img).shape == img.shape

    def test_erode_preserves_array_shape(self) -> None:
        img = ocr_mod._step_grayscale(self._bgr())
        assert ocr_mod._step_erode(img).shape == img.shape

    def test_deskew_noop_on_horizontal_line(self) -> None:
        """A perfectly horizontal line has 0° skew — output shape unchanged."""
        img = np.ones((80, 200), dtype=np.uint8) * 255
        cv2.line(img, (10, 40), (190, 40), 0, 2)
        assert ocr_mod._step_deskew(img).shape == img.shape

    def test_denoise_preserves_array_shape(self) -> None:
        img = self._bgr()
        assert ocr_mod._step_denoise(img).shape == img.shape

    def test_unknown_step_is_silently_skipped(self) -> None:
        """An unrecognised step name is skipped; no exception raised; array survives."""
        img = self._bgr()
        # _preprocess converts PIL → BGR numpy; the unknown step is a no-op.
        result = ocr_mod._preprocess(
            Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)),
            ["nonexistent_step"],
        )
        # Pipeline entry-point converts to BGR; unknown step is skipped, so
        # the output is still a 3-channel BGR array.
        assert result.shape[2] == 3

    def test_pipeline_grayscale_then_otsu_produces_binary(self) -> None:
        """grayscale → otsu yields a 2-D binary (0/255) array."""
        result = ocr_mod._preprocess(make_clean_pil("TEST"), ["grayscale", "otsu_threshold"])
        assert result.ndim == 2
        assert set(np.unique(result)) <= {0, 255}

    def test_pipeline_invert_then_otsu_on_dark_background(self) -> None:
        """invert → otsu on a dark-background image yields valid binary output."""
        result = ocr_mod._preprocess(
            make_inverted_pil("TEST"), ["grayscale", "invert", "otsu_threshold"]
        )
        assert result.ndim == 2
        assert set(np.unique(result)) <= {0, 255}

    def test_all_named_steps_present_in_pipeline_map(self) -> None:
        """Every step documented in the spec must exist in _PIPELINE_STEPS."""
        required = {
            "grayscale", "upscale_2x", "upscale_3x", "denoise",
            "otsu_threshold", "adaptive_threshold", "invert",
            "dilate", "erode", "deskew",
        }
        missing = required - ocr_mod._PIPELINE_STEPS.keys()
        assert not missing, f"Missing pipeline steps: {missing}"


# ---------------------------------------------------------------------------
# 2. _compute_confidence unit tests
# ---------------------------------------------------------------------------


class TestComputeConfidence:
    """Test pytesseract dict → (text, confidence) extraction in isolation."""

    @staticmethod
    def _d(words: list[str], confs: list[int]) -> dict:
        return {"text": words, "conf": confs}

    def test_empty_input_returns_empty_text_and_zero(self) -> None:
        text, conf = ocr_mod._compute_confidence(self._d([], []))
        assert text == "" and conf == 0.0

    def test_single_kept_token(self) -> None:
        text, conf = ocr_mod._compute_confidence(self._d(["HELLO"], [90]))
        assert text == "HELLO"
        assert pytest.approx(conf, abs=0.01) == 0.90

    def test_layout_tokens_with_conf_minus1_excluded(self) -> None:
        """Tokens with conf == -1 are layout blocks — excluded from mean."""
        text, conf = ocr_mod._compute_confidence(self._d(["", "HELLO", ""], [-1, 80, -1]))
        assert text == "HELLO"
        assert pytest.approx(conf, abs=0.01) == 0.80

    def test_whitespace_only_tokens_excluded(self) -> None:
        text, conf = ocr_mod._compute_confidence(self._d(["   ", "WORLD", "\t"], [70, 85, 70]))
        assert text == "WORLD"
        assert pytest.approx(conf, abs=0.01) == 0.85

    def test_mean_over_multiple_tokens(self) -> None:
        _, conf = ocr_mod._compute_confidence(self._d(["A", "B", "C"], [80, 60, 100]))
        assert pytest.approx(conf, abs=0.01) == (80 + 60 + 100) / 3 / 100

    def test_consecutive_whitespace_collapsed_to_single_space(self) -> None:
        text, _ = ocr_mod._compute_confidence(self._d(["HELLO", "WORLD"], [90, 90]))
        assert "  " not in text
        assert text == "HELLO WORLD"

    def test_confidence_scaled_to_0_1(self) -> None:
        """pytesseract returns 0–100; we normalise to 0–1."""
        _, conf = ocr_mod._compute_confidence(self._d(["X"], [100]))
        assert 0.0 <= conf <= 1.0
        assert pytest.approx(conf) == 1.0


# ---------------------------------------------------------------------------
# 3. read_text — structural tests (no Tesseract binary needed)
# ---------------------------------------------------------------------------


CLEAN_TEXT = "HELLO 123"


class TestReadText:
    """read_text with monkeypatched _grab_region and stubbed _run_tesseract."""

    def test_returns_ocr_result_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """read_text always returns an OcrResult regardless of image content."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        result = ocr_mod.read_text((0, 0, 600, 100))
        assert isinstance(result, ocr_mod.OcrResult)

    def test_result_image_path_is_an_existing_png(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OcrResult.image_path must point to a real PNG file written during the call."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        result = ocr_mod.read_text((0, 0, 600, 100))
        assert result.image_path.exists()
        assert result.image_path.suffix == ".png"

    def test_confidence_is_in_0_1_range(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Confidence must always be in [0.0, 1.0]."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        result = ocr_mod.read_text((0, 0, 600, 100))
        assert 0.0 <= result.confidence <= 1.0

    def test_raw_data_contains_expected_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """raw_data is the full pytesseract image_to_data output dict."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        result = ocr_mod.read_text((0, 0, 600, 100))
        for key in ("text", "conf", "word_num", "page_num"):
            assert key in result.raw_data, f"Missing key {key!r} in raw_data"

    def test_injected_compute_result_surfaces_in_ocr_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When _compute_confidence is mocked, read_text exposes those values."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        _inject_ocr(monkeypatch, CLEAN_TEXT, 0.91)
        result = ocr_mod.read_text((0, 0, 600, 100))
        assert result.text == CLEAN_TEXT
        assert pytest.approx(result.confidence, abs=0.01) == 0.91

    def test_custom_preprocess_steps_are_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Passing an explicit preprocess list does not raise."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        result = ocr_mod.read_text(
            (0, 0, 600, 100),
            preprocess=["grayscale", "upscale_2x", "otsu_threshold"],
        )
        assert isinstance(result, ocr_mod.OcrResult)

    # -- Tests that require a real Tesseract binary (skipped when absent) --

    @requires_tesseract
    def test_clean_image_has_high_confidence(
        self, monkeypatch: pytest.MonkeyPatch, real_tesseract: None
    ) -> None:
        """A crisp black-on-white image should yield confidence > 0.5."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        result = ocr_mod.read_text(
            (0, 0, 600, 100),
            preprocess=["grayscale", "upscale_2x", "otsu_threshold"],
        )
        assert result.confidence > 0.50, (
            f"Expected confidence > 0.50, got {result.confidence:.3f}; text={result.text!r}"
        )

    @requires_tesseract
    def test_noise_image_has_low_confidence(
        self, monkeypatch: pytest.MonkeyPatch, real_tesseract: None
    ) -> None:
        """Random noise should produce near-zero confidence."""
        _patch_grab(monkeypatch, make_noise_pil())
        result = ocr_mod.read_text((0, 0, 400, 80), preprocess=["grayscale", "otsu_threshold"])
        assert result.confidence < 0.50

    @requires_tesseract
    def test_invert_pipeline_reads_light_on_dark(
        self, monkeypatch: pytest.MonkeyPatch, real_tesseract: None
    ) -> None:
        """White text on black is readable after invert preprocessing."""
        _patch_grab(monkeypatch, make_inverted_pil(CLEAN_TEXT))
        result = ocr_mod.read_text(
            (0, 0, 600, 100),
            preprocess=["grayscale", "invert", "upscale_2x", "otsu_threshold"],
        )
        assert len(result.text) > 0

    @requires_tesseract
    def test_upscale_does_not_reduce_confidence_on_blurred_image(
        self, monkeypatch: pytest.MonkeyPatch, real_tesseract: None
    ) -> None:
        """Confidence with upscale_2x >= confidence without upscale (minus tolerance)."""
        blurred = make_blurred_pil(CLEAN_TEXT)

        _patch_grab(monkeypatch, blurred)
        without_upscale = ocr_mod.read_text(
            (0, 0, 600, 100), preprocess=["grayscale", "otsu_threshold"]
        )
        _patch_grab(monkeypatch, blurred)
        with_upscale = ocr_mod.read_text(
            (0, 0, 600, 100), preprocess=["grayscale", "upscale_2x", "otsu_threshold"]
        )
        assert with_upscale.confidence >= without_upscale.confidence - 0.05, (
            f"upscale conf={with_upscale.confidence:.3f} unexpectedly lower than "
            f"no-upscale conf={without_upscale.confidence:.3f}"
        )


# ---------------------------------------------------------------------------
# 4. assert_text — modes, case sensitivity, error paths
# ---------------------------------------------------------------------------


class TestAssertText:
    """assert_text with region tuple input.

    All tests mock _compute_confidence to inject controlled text+confidence,
    so no Tesseract binary is needed.
    retries=1 throughout to keep the suite fast; retry logic is in §6.
    """

    def test_contains_mode_passes_for_substring(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """'contains' mode passes when expected is a case-folded substring."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        _inject_ocr(monkeypatch, "HELLO 123", 0.85)
        result = ocr_mod.assert_text(
            (0, 0, 600, 100), "HELLO", mode="contains", min_confidence=0.50, retries=1
        )
        assert isinstance(result, ocr_mod.OcrResult)

    def test_contains_mode_is_case_insensitive_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lowercase expected matches uppercase extracted text (default case_sensitive=False)."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        _inject_ocr(monkeypatch, "HELLO 123", 0.85)
        # Should not raise
        ocr_mod.assert_text(
            (0, 0, 600, 100), "hello", mode="contains", min_confidence=0.50, retries=1
        )

    def test_equals_mode_passes_on_exact_match(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """'equals' mode passes when extracted text == expected (case-folded)."""
        _patch_grab(monkeypatch, make_clean_pil("ABC"))
        _inject_ocr(monkeypatch, "ABC", 0.90)
        result = ocr_mod.assert_text(
            (0, 0, 600, 100), "ABC", mode="equals", min_confidence=0.50, retries=1
        )
        assert result.text == "ABC"

    def test_equals_mode_fails_on_whitespace_mismatch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """'equals' mode raises when extracted text has trailing space."""
        _patch_grab(monkeypatch, make_clean_pil("ABC"))
        _inject_ocr(monkeypatch, "ABC ", 0.90)  # trailing space
        # assert_text strips both sides, so this should pass
        ocr_mod.assert_text(
            (0, 0, 600, 100), "ABC", mode="equals", min_confidence=0.50, retries=1
        )

    def test_regex_mode_passes_on_matching_pattern(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """'regex' mode passes when re.search finds the pattern."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        _inject_ocr(monkeypatch, "HELLO 123", 0.90)
        result = ocr_mod.assert_text(
            (0, 0, 600, 100),
            r"HELLO\s+\d+",
            mode="regex",
            min_confidence=0.50,
            retries=1,
        )
        assert result is not None

    def test_regex_mode_is_case_insensitive_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regex flag re.IGNORECASE is applied when case_sensitive=False."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        _inject_ocr(monkeypatch, "HELLO 123", 0.90)
        ocr_mod.assert_text(
            (0, 0, 600, 100),
            r"hello\s+\d+",       # lowercase pattern against uppercase text
            mode="regex",
            min_confidence=0.50,
            retries=1,
        )

    def test_text_mismatch_raises_ocr_text_mismatch_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OcrTextMismatchError is raised with extracted/expected in details."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        _inject_ocr(monkeypatch, "HELLO 123", 0.90)
        with pytest.raises(OcrTextMismatchError) as exc_info:
            ocr_mod.assert_text(
                (0, 0, 600, 100), "GOODBYE", mode="contains", min_confidence=0.50, retries=1
            )
        assert exc_info.value.details["extracted"] == "HELLO 123"
        assert exc_info.value.details["expected"] == "GOODBYE"

    def test_mismatch_error_carries_screenshot_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """screenshot_path on OcrTextMismatchError points to the debug image."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        _inject_ocr(monkeypatch, "HELLO", 0.90)
        with pytest.raises(OcrTextMismatchError) as exc_info:
            ocr_mod.assert_text(
                (0, 0, 600, 100), "NOPE", min_confidence=0.50, retries=1
            )
        assert exc_info.value.screenshot_path is not None

    def test_low_confidence_raises_ocr_low_confidence_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OcrLowConfidenceError is raised when confidence stays below threshold."""
        _patch_grab(monkeypatch, make_noise_pil())
        # stub returns confidence 0.0; threshold is 0.99 → always fails
        with pytest.raises(OcrLowConfidenceError) as exc_info:
            ocr_mod.assert_text(
                (0, 0, 400, 80), "anything", min_confidence=0.99, retries=1
            )
        assert exc_info.value.details["threshold"] == 0.99

    def test_invalid_mode_raises_value_error_before_ocr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ValueError is raised immediately for an unknown mode string."""
        _patch_grab(monkeypatch, make_clean_pil("X"))
        with pytest.raises(ValueError, match="mode must be"):
            ocr_mod.assert_text(
                (0, 0, 600, 100),
                "X",
                mode="fuzzy",  # type: ignore[arg-type]
                retries=1,
            )

    def test_case_sensitive_equals_fails_on_case_difference(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """case_sensitive=True: 'hello' != 'HELLO' in equals mode."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        _inject_ocr(monkeypatch, "HELLO", 0.90)
        with pytest.raises(OcrTextMismatchError):
            ocr_mod.assert_text(
                (0, 0, 600, 100),
                "hello",
                mode="equals",
                case_sensitive=True,
                min_confidence=0.50,
                retries=1,
            )

    def test_min_confidence_override_takes_precedence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit min_confidence kwarg overrides the target default."""
        _patch_grab(monkeypatch, make_noise_pil())
        _inject_ocr(monkeypatch, "X", 0.40)
        # With default min_confidence=0.65 this would fail; override to 0.30
        ocr_mod.assert_text(
            (0, 0, 400, 80),
            "X",
            mode="contains",
            min_confidence=0.30,
            retries=1,
        )


# ---------------------------------------------------------------------------
# 5. assert_text — with named OCR target (YAML lookup path)
# ---------------------------------------------------------------------------


class TestAssertTextWithTarget:
    """assert_text when a string target name is passed (fake_ocr_targets fixture)."""

    def test_target_name_is_resolved_from_cache(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_ocr_targets: dict,
    ) -> None:
        """assert_text looks up the name and uses its region/pipeline settings."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        _inject_ocr(monkeypatch, "HELLO 123", 0.90)
        result = ocr_mod.assert_text(
            "test_screen.label", "HELLO", mode="contains", retries=1
        )
        assert result is not None

    def test_unknown_target_raises_config_error(
        self,
        fake_ocr_targets: dict,
    ) -> None:
        """ConfigError is raised when the target name is not in the OR."""
        from automation.core.exceptions import ConfigError

        with pytest.raises(ConfigError, match="not found in Visual OR"):
            ocr_mod.assert_text("nonexistent.target", "anything", retries=1)

    def test_target_min_confidence_is_used_when_no_kwarg_override(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_ocr_targets: dict,
    ) -> None:
        """Target's min_confidence (0.50) applies when no kwarg override is given."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        # Inject confidence of 0.55 — above target's 0.50, so should pass
        _inject_ocr(monkeypatch, "HELLO 123", 0.55)
        ocr_mod.assert_text("test_screen.label", "HELLO", mode="contains", retries=1)

    def test_min_confidence_kwarg_overrides_target_threshold(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_ocr_targets: dict,
    ) -> None:
        """Passing min_confidence kwarg overrides the target's own threshold."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        # Inject confidence 0.30 — below target's 0.50 but above kwarg 0.20
        _inject_ocr(monkeypatch, "HELLO 123", 0.30)
        ocr_mod.assert_text(
            "test_screen.label", "HELLO", mode="contains", min_confidence=0.20, retries=1
        )


# ---------------------------------------------------------------------------
# 6. Retry loop behaviour
# ---------------------------------------------------------------------------


class TestRetryBehaviour:
    """Verify retry count, backoff calls, and exception propagation."""

    def test_succeeds_on_third_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Third call returns matching text at sufficient confidence."""
        call_n = {"n": 0}
        conf_seq  = [0.10, 0.15, 0.92]
        text_seq  = ["",   "",    "TARGET"]

        def _seq_compute(_data):
            i = min(call_n["n"], 2)
            call_n["n"] += 1
            return text_seq[i], conf_seq[i]

        monkeypatch.setattr(ocr_mod, "_grab_region", lambda _: make_noise_pil())
        monkeypatch.setattr(ocr_mod, "_compute_confidence", _seq_compute)

        result = ocr_mod.assert_text(
            (0, 0, 600, 100),
            "TARGET",
            mode="contains",
            min_confidence=0.80,
            retries=3,
            backoff=0.01,
        )
        assert result.text == "TARGET"
        assert call_n["n"] == 3

    def test_exhausted_retries_re_raise_ocr_low_confidence_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OcrLowConfidenceError is raised after all attempts with retries in details."""
        monkeypatch.setattr(ocr_mod, "_grab_region", lambda _: make_noise_pil())
        monkeypatch.setattr(ocr_mod, "_compute_confidence", lambda _: ("", 0.05))

        with pytest.raises(OcrLowConfidenceError) as exc_info:
            ocr_mod.assert_text(
                (0, 0, 400, 80), "x", min_confidence=0.80, retries=3, backoff=0.01
            )
        assert exc_info.value.details["retries"] == 3

    def test_text_mismatch_is_retried_and_re_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OcrTextMismatchError triggers retries and is re-raised after exhaustion."""
        call_count = {"n": 0}

        def _always_wrong(_data):
            call_count["n"] += 1
            return "WRONG", 0.90

        monkeypatch.setattr(ocr_mod, "_grab_region", lambda _: make_clean_pil("x"))
        monkeypatch.setattr(ocr_mod, "_compute_confidence", _always_wrong)

        with pytest.raises(OcrTextMismatchError):
            ocr_mod.assert_text(
                (0, 0, 600, 100), "CORRECT", min_confidence=0.50, retries=2, backoff=0.01
            )
        assert call_count["n"] == 2

    def test_sleep_not_called_after_final_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """time.sleep is invoked retries-1 times (never after the last attempt)."""
        sleep_calls: list[float] = []
        monkeypatch.setattr("automation.core.ocr.time.sleep", sleep_calls.append)
        monkeypatch.setattr(ocr_mod, "_grab_region", lambda _: make_noise_pil())
        monkeypatch.setattr(ocr_mod, "_compute_confidence", lambda _: ("", 0.05))

        with pytest.raises(OcrLowConfidenceError):
            ocr_mod.assert_text(
                (0, 0, 400, 80), "x", min_confidence=0.80, retries=3, backoff=0.01
            )
        # retries=3 → sleep called 2 times (after attempt 1 and 2, not after 3)
        assert len(sleep_calls) == 2

    def test_backoff_delay_increases_per_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each sleep duration equals backoff × attempt_number."""
        sleep_calls: list[float] = []
        monkeypatch.setattr("automation.core.ocr.time.sleep", sleep_calls.append)
        monkeypatch.setattr(ocr_mod, "_grab_region", lambda _: make_noise_pil())
        monkeypatch.setattr(ocr_mod, "_compute_confidence", lambda _: ("", 0.05))

        with pytest.raises(OcrLowConfidenceError):
            ocr_mod.assert_text(
                (0, 0, 400, 80), "x", min_confidence=0.80, retries=3, backoff=0.5
            )
        # backoff=0.5: sleep(0.5*1)=0.5 then sleep(0.5*2)=1.0
        assert len(sleep_calls) == 2
        assert pytest.approx(sleep_calls[0]) == 0.5
        assert pytest.approx(sleep_calls[1]) == 1.0


# ---------------------------------------------------------------------------
# 7. read_target
# ---------------------------------------------------------------------------


class TestReadTarget:
    def test_read_target_resolves_name_from_cache(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_ocr_targets: dict,
    ) -> None:
        """read_target uses the target's region/lang/preprocess settings."""
        _patch_grab(monkeypatch, make_clean_pil(CLEAN_TEXT))
        result = ocr_mod.read_target("test_screen.label")
        assert isinstance(result, ocr_mod.OcrResult)

    def test_read_target_unknown_name_raises_config_error(
        self,
        fake_ocr_targets: dict,
    ) -> None:
        from automation.core.exceptions import ConfigError

        with pytest.raises(ConfigError):
            ocr_mod.read_target("does.not.exist")


# ---------------------------------------------------------------------------
# 8. _resolve_region — real logic via real_resolve_region fixture
# ---------------------------------------------------------------------------


class TestResolveRegion:
    """Test the actual _resolve_region offset logic.

    ``real_resolve_region`` returns the function saved at conftest import
    time, BEFORE the autouse passthrough fixture replaces it.  We call
    it directly rather than through the module attribute.
    """

    def test_offsets_region_by_citrix_session_origin(
        self,
        monkeypatch: pytest.MonkeyPatch,
        real_resolve_region,
    ) -> None:
        """(10, 20, 200, 100) with session at (100, 50) → (110, 70, 200, 100)."""
        import automation.core.citrix as citrix_mod

        monkeypatch.setattr(citrix_mod, "get_session_rect", lambda: (100, 50, 1820, 1030))
        result = real_resolve_region((10, 20, 200, 100))
        assert result[0] == 110, f"x: expected 110, got {result[0]}"
        assert result[1] == 70,  f"y: expected  70, got {result[1]}"
        assert result[2] == 200
        assert result[3] == 100

    def test_identity_when_session_origin_is_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        real_resolve_region,
    ) -> None:
        """Session at (0, 0) means region is returned unchanged (non-Windows dev)."""
        import automation.core.citrix as citrix_mod

        monkeypatch.setattr(citrix_mod, "get_session_rect", lambda: (0, 0, 1920, 1080))
        result = real_resolve_region((50, 60, 300, 150))
        assert result[0] == 50
        assert result[1] == 60

    def test_clamps_negative_coordinates_to_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        real_resolve_region,
    ) -> None:
        """Negative absolute coordinates are clamped to 0."""
        import automation.core.citrix as citrix_mod

        # Session offset pushes the region into negative territory
        monkeypatch.setattr(citrix_mod, "get_session_rect", lambda: (0, 0, 1920, 1080))
        result = real_resolve_region((0, 0, 200, 100))
        assert result[0] >= 0
        assert result[1] >= 0

    def test_width_height_remain_positive(
        self,
        monkeypatch: pytest.MonkeyPatch,
        real_resolve_region,
    ) -> None:
        """Width and height after clamping must be at least 1 pixel."""
        import automation.core.citrix as citrix_mod

        monkeypatch.setattr(citrix_mod, "get_session_rect", lambda: (0, 0, 1920, 1080))
        result = real_resolve_region((0, 0, 400, 300))
        assert result[2] >= 1
        assert result[3] >= 1
