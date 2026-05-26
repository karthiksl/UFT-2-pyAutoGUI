"""
OCR validation layer — pytesseract with preprocessing, retries, and triage artifacts.

Known OCR limitations on Epic Hyperdrive / Citrix
==================================================
- Blurry text from Citrix JPEG compression
    → mitigated by ``upscale_2x`` / ``upscale_3x`` in the preprocess pipeline.
- Low-resolution captures
    → always capture the full logical region from the Citrix window, never a
      scaled-down thumbnail; the Citrix session frame is the coordinate origin.
- Special Epic fonts, icons, and non-Latin glyphs
    → NOT reliably OCR-able.  Use image-anchor matching (core/finder.py) for
      those elements instead.
- Dark theme or coloured backgrounds
    → use ``invert`` followed by ``adaptive_threshold`` or ``otsu_threshold``.
- DPI scaling drift between capture machine and execution machine
    → regions are defined relative to ``citrix.session_frame`` and are offset
      at runtime by ``_resolve_region``; never embed absolute display coords in
      business code.
- Citrix session stabilisation lag
    → ``assert_text`` retries up to ``retries`` times with exponential backoff
      before raising ``OcrLowConfidenceError``.  It NEVER silently passes.

When OCR cannot reach ``min_confidence`` after all retries the framework raises
``OcrLowConfidenceError`` deterministically.  A silent pass is not permitted.
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import pytesseract
import yaml
from loguru import logger
from PIL import Image, ImageGrab

from automation.core.config import get_config
from automation.core.exceptions import (
    ConfigError,
    OcrLowConfidenceError,
    OcrTextMismatchError,
)

# ---------------------------------------------------------------------------
# Tesseract binary location — set TESSERACT_CMD env var to override
# ---------------------------------------------------------------------------
_TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "")
if _TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD

_DEFAULT_PIPELINE: list[str] = ["grayscale", "upscale_2x", "otsu_threshold"]

# Thread-safe lazy cache for ocr_targets loaded from the OR YAML
_ocr_targets_cache: dict[str, "_OcrTarget"] | None = None
_ocr_targets_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _OcrTarget:
    """Internal representation of one ocr_targets entry from app_or.yaml."""

    name: str
    screen: str
    region: tuple[int, int, int, int]
    expected_pattern: str
    lang: str
    preprocess: list[str]
    min_confidence: float


@dataclass
class OcrResult:
    """Result of a single OCR extraction call."""

    text: str                        # normalised extracted text
    confidence: float                # mean token confidence, 0.0–1.0
    raw_data: dict                   # full pytesseract image_to_data output
    image_path: Path                 # saved preprocessed image for triage


# ---------------------------------------------------------------------------
# Preprocessing pipeline
# ---------------------------------------------------------------------------

def _step_grayscale(img: np.ndarray) -> np.ndarray:
    """Convert BGR/RGB image to single-channel grayscale."""
    if len(img.shape) == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def _step_upscale(img: np.ndarray, factor: int) -> np.ndarray:
    """Resize image by integer *factor* using bicubic interpolation."""
    h, w = img.shape[:2]
    return cv2.resize(img, (w * factor, h * factor), interpolation=cv2.INTER_CUBIC)


def _step_denoise(img: np.ndarray) -> np.ndarray:
    """Apply fast non-local means denoising to reduce Citrix JPEG artifacts."""
    if len(img.shape) == 3:
        return cv2.fastNlMeansDenoisingColored(img, None, h=10, hColor=10)
    return cv2.fastNlMeansDenoising(img, None, h=10)


def _step_otsu(img: np.ndarray) -> np.ndarray:
    """Binarise using Otsu's method; converts to grayscale first if needed."""
    gray = _step_grayscale(img) if len(img.shape) == 3 else img
    _, result = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return result


def _step_adaptive(img: np.ndarray) -> np.ndarray:
    """Adaptive Gaussian threshold — better for uneven lighting."""
    gray = _step_grayscale(img) if len(img.shape) == 3 else img
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )


def _step_invert(img: np.ndarray) -> np.ndarray:
    """Invert pixel values — required for light text on dark backgrounds."""
    return cv2.bitwise_not(img)


def _step_dilate(img: np.ndarray) -> np.ndarray:
    """Morphological dilation — thickens strokes, helps thin fonts."""
    kernel = np.ones((2, 2), np.uint8)
    return cv2.dilate(img, kernel, iterations=1)


def _step_erode(img: np.ndarray) -> np.ndarray:
    """Morphological erosion — removes small noise pixels."""
    kernel = np.ones((2, 2), np.uint8)
    return cv2.erode(img, kernel, iterations=1)


def _step_deskew(img: np.ndarray) -> np.ndarray:
    """Correct minor rotation using minAreaRect on dark pixel coordinates.

    Skips rotation when angle is < 0.5° to avoid resampling artefacts on
    already-straight text.
    """
    gray = _step_grayscale(img) if len(img.shape) == 3 else img
    # Find dark (text) pixel coordinates
    coords = np.column_stack(np.where(gray < 128))
    if len(coords) < 5:
        return img
    rect = cv2.minAreaRect(coords)
    angle = float(rect[-1])
    # minAreaRect angle is in [-90, 0); normalise to [-45, 45)
    if angle < -45.0:
        angle += 90.0
    if abs(angle) < 0.5:
        return img
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


# Map of step name → callable; populated after all _step_* are defined
_PIPELINE_STEPS: dict[str, object] = {
    "grayscale":          _step_grayscale,
    "upscale_2x":         lambda img: _step_upscale(img, 2),
    "upscale_3x":         lambda img: _step_upscale(img, 3),
    "denoise":            _step_denoise,
    "otsu_threshold":     _step_otsu,
    "adaptive_threshold": _step_adaptive,
    "invert":             _step_invert,
    "dilate":             _step_dilate,
    "erode":              _step_erode,
    "deskew":             _step_deskew,
}


def _preprocess(pil_img: Image.Image, steps: list[str]) -> np.ndarray:
    """Convert *pil_img* to numpy and apply each named step in order."""
    # PIL images from grab are RGB; convert to BGR for OpenCV
    img: np.ndarray = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
    for step in steps:
        fn = _PIPELINE_STEPS.get(step)
        if fn is None:
            logger.warning("ocr._preprocess: unknown step {!r} — skipping", step)
            continue
        img = fn(img)  # type: ignore[operator]
    return img


# ---------------------------------------------------------------------------
# Screen capture — abstracted for monkeypatching in tests
# ---------------------------------------------------------------------------


def _grab_region(region: tuple[int, int, int, int]) -> Image.Image:
    """Capture *region* (x, y, w, h) and return a PIL RGB Image.

    Do NOT call PyAutoGUI here.  PIL.ImageGrab works on Windows and macOS.
    On headless Linux runners the monkeypatch in conftest replaces this.
    """
    x, y, w, h = region
    return ImageGrab.grab(bbox=(x, y, x + w, y + h))


# ---------------------------------------------------------------------------
# Citrix session offset
# ---------------------------------------------------------------------------


def _resolve_region(region: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Offset a YAML-defined region by the Citrix session window origin.

    Clamps the result to screen bounds so capture calls never overflow.
    On non-Windows dev boxes ``get_session_rect`` returns (0, 0, w, h) so
    this function is effectively a pass-through.
    """
    try:
        from automation.core.citrix import get_session_rect
        sx, sy, _sw, _sh = get_session_rect()
    except Exception:  # noqa: BLE001 — non-Windows or window not found
        sx, sy = 0, 0

    rx, ry, rw, rh = region
    ax = max(0, sx + rx)
    ay = max(0, sy + ry)

    try:
        import pyautogui  # type: ignore[import]
        screen_w, screen_h = pyautogui.size()
    except Exception:  # noqa: BLE001
        screen_w, screen_h = 1920, 1080

    rw = min(rw, screen_w - ax)
    rh = min(rh, screen_h - ay)
    return (ax, ay, max(1, rw), max(1, rh))


# ---------------------------------------------------------------------------
# Triage artifact storage
# ---------------------------------------------------------------------------


def _save_debug_image(img: np.ndarray, prefix: str = "ocr") -> Path:
    """Write *img* to the OCR debug directory and return the path."""
    try:
        cfg = get_config()
        base = Path(cfg.get("assets_dir", "assets/images")).parent
    except Exception:  # noqa: BLE001
        base = Path("assets")
    debug_dir = base / "ocr_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    tid = threading.current_thread().ident or 0
    dest = debug_dir / f"{ts}_{tid}_{prefix}.png"
    cv2.imwrite(str(dest), img)
    return dest


# ---------------------------------------------------------------------------
# Tesseract runner
# ---------------------------------------------------------------------------


def _run_tesseract(img: np.ndarray, lang: str, psm: int) -> dict:
    """Run pytesseract image_to_data on *img*; return output dict."""
    config = f"--psm {psm} --oem 3"
    if len(img.shape) == 2:  # grayscale
        pil_img = Image.fromarray(img)
    else:
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    return pytesseract.image_to_data(
        pil_img,
        lang=lang,
        config=config,
        output_type=pytesseract.Output.DICT,
    )


def _compute_confidence(data: dict) -> tuple[str, float]:
    """Extract normalised text and mean confidence from pytesseract output.

    Returns (text, confidence) where confidence is in [0.0, 1.0].
    Tokens with confidence == -1 (layout segments) are excluded.
    """
    words: list[str] = []
    confs: list[int] = []
    for word, conf in zip(data.get("text", []), data.get("conf", [])):
        conf_int = int(conf)
        if conf_int >= 0 and str(word).strip():
            words.append(str(word))
            confs.append(conf_int)
    text = re.sub(r"\s+", " ", " ".join(words)).strip()
    confidence = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    return text, confidence


# ---------------------------------------------------------------------------
# OCR target cache
# ---------------------------------------------------------------------------


def _load_ocr_targets() -> dict[str, _OcrTarget]:
    """Load and cache ocr_targets from app_or.yaml; thread-safe."""
    global _ocr_targets_cache
    # Fast path — already loaded
    if _ocr_targets_cache is not None:
        return _ocr_targets_cache
    with _ocr_targets_lock:
        # Double-checked locking
        if _ocr_targets_cache is not None:
            return _ocr_targets_cache
        cfg = get_config()
        or_path = Path(cfg.get("or_path", "or/app_or.yaml"))
        if not or_path.is_absolute():
            or_path = Path(__file__).parent.parent / or_path
        try:
            with or_path.open() as fh:
                doc = yaml.safe_load(fh) or {}
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(
                f"Cannot load Visual OR for OCR targets: {exc}",
                logical_name=str(or_path),
            ) from exc
        result: dict[str, _OcrTarget] = {}
        for entry in doc.get("ocr_targets", []):
            name: str = entry["name"]
            rl = entry["region"]
            result[name] = _OcrTarget(
                name=name,
                screen=entry.get("screen", ""),
                region=(int(rl[0]), int(rl[1]), int(rl[2]), int(rl[3])),
                expected_pattern=entry.get("expected_pattern", ""),
                lang=entry.get("lang", "eng"),
                preprocess=list(entry.get("preprocess", _DEFAULT_PIPELINE)),
                min_confidence=float(entry.get("min_confidence", 0.65)),
            )
        _ocr_targets_cache = result
        logger.debug("ocr: loaded {} ocr_targets from {}", len(result), or_path)
        return result


def _invalidate_ocr_target_cache() -> None:
    """Clear the ocr_target cache — call after reloading the OR YAML."""
    global _ocr_targets_cache
    with _ocr_targets_lock:
        _ocr_targets_cache = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_text(
    region: tuple[int, int, int, int],
    *,
    lang: str = "eng",
    preprocess: list[str] | None = None,
    psm: int = 6,
) -> OcrResult:
    """Capture *region*, run the preprocessing pipeline, and return OCR output.

    Args:
        region:     (x, y, w, h) in YAML/Citrix-relative coordinates.
        lang:       Tesseract language code, default ``"eng"``.
        preprocess: Named pipeline steps; defaults to
                    ``["grayscale", "upscale_2x", "otsu_threshold"]``.
        psm:        Tesseract page segmentation mode (``--psm``).
                    6 = assume a uniform block of text (default).
                    7 = treat the image as a single text line.
    """
    steps = list(preprocess) if preprocess is not None else list(_DEFAULT_PIPELINE)
    resolved = _resolve_region(region)
    pil_img = _grab_region(resolved)
    proc_img = _preprocess(pil_img, steps)
    image_path = _save_debug_image(proc_img)
    data = _run_tesseract(proc_img, lang, psm)
    text, confidence = _compute_confidence(data)
    logger.debug(
        "ocr.read_text: region={} steps={} text={!r} conf={:.3f} img={}",
        region, steps, text, confidence, image_path.name,
    )
    return OcrResult(text=text, confidence=confidence, raw_data=data, image_path=image_path)


def read_target(name: str) -> OcrResult:
    """Read an ``ocr_target`` defined in ``app_or.yaml`` by its logical name.

    The target's ``region``, ``lang``, and ``preprocess`` settings are used
    automatically.
    """
    targets = _load_ocr_targets()
    if name not in targets:
        raise ConfigError(
            f"OCR target {name!r} not found in Visual OR",
            logical_name=name,
        )
    t = targets[name]
    logger.debug("ocr.read_target: name={!r} region={}", name, t.region)
    return read_text(t.region, lang=t.lang, preprocess=t.preprocess)


def assert_text(
    target_or_region: str | tuple[int, int, int, int],
    expected: str,
    *,
    mode: Literal["contains", "equals", "regex"] = "contains",
    min_confidence: float | None = None,
    case_sensitive: bool = False,
    retries: int = 3,
    backoff: float = 0.75,
) -> OcrResult:
    """Assert that OCR-extracted text from *target_or_region* matches *expected*.

    Args:
        target_or_region: Logical OCR target name (str) or raw region tuple.
        expected:         Value to match against the extracted text.
        mode:             ``"contains"`` — substring match (default).
                          ``"equals"``   — exact match after strip.
                          ``"regex"``    — ``re.search`` match; *expected* is
                                          the pattern.
        min_confidence:   Override the target's configured threshold.
        case_sensitive:   Default False — both sides lowercased before compare.
        retries:          Total attempts before raising (default 3).
        backoff:          Sleep seconds multiplied by attempt number between
                          retries (default 0.75 → sleeps 0.75 s, 1.5 s, …).

    Raises:
        OcrLowConfidenceError:  Confidence stayed below threshold after all retries.
        OcrTextMismatchError:   Confidence was sufficient but text did not match.
        ConfigError:            Named target not found in the Visual OR.
    """
    if mode not in ("contains", "equals", "regex"):
        raise ValueError(f"assert_text: mode must be 'contains', 'equals', or 'regex'; got {mode!r}")

    # Resolve region + extraction parameters from target name or raw tuple
    if isinstance(target_or_region, str):
        targets = _load_ocr_targets()
        if target_or_region not in targets:
            raise ConfigError(
                f"OCR target {target_or_region!r} not found in Visual OR",
                logical_name=target_or_region,
            )
        t = targets[target_or_region]
        region = t.region
        lang = t.lang
        preprocess = t.preprocess
        threshold = min_confidence if min_confidence is not None else t.min_confidence
        label = target_or_region
    else:
        region = target_or_region
        lang = "eng"
        preprocess = None
        threshold = min_confidence if min_confidence is not None else 0.65
        label = str(region)

    last_exc: OcrLowConfidenceError | OcrTextMismatchError | None = None
    last_result: OcrResult | None = None

    for attempt in range(1, retries + 1):
        try:
            result = read_text(region, lang=lang, preprocess=preprocess)
            last_result = result

            # ── Confidence gate ──────────────────────────────────────────
            if result.confidence < threshold:
                raise OcrLowConfidenceError(
                    f"OCR confidence {result.confidence:.3f} < {threshold:.3f} "
                    f"for target {label!r} (attempt {attempt}/{retries})",
                    screenshot_path=result.image_path,
                    details={
                        "text": result.text,
                        "confidence": result.confidence,
                        "threshold": threshold,
                        "attempt": attempt,
                        "retries": retries,
                    },
                )

            # ── Text match gate ──────────────────────────────────────────
            extracted = result.text if case_sensitive else result.text.casefold()
            compare = expected if case_sensitive else expected.casefold()

            if mode == "contains":
                matched = compare in extracted
            elif mode == "equals":
                matched = extracted.strip() == compare.strip()
            else:  # regex
                flags = 0 if case_sensitive else re.IGNORECASE
                matched = bool(re.search(expected, result.text, flags))

            if not matched:
                raise OcrTextMismatchError(
                    f"OCR text {result.text!r} did not {mode!r}-match "
                    f"{expected!r} for target {label!r} "
                    f"(attempt {attempt}/{retries})",
                    screenshot_path=result.image_path,
                    details={
                        "extracted": result.text,
                        "expected": expected,
                        "mode": mode,
                        "case_sensitive": case_sensitive,
                        "confidence": result.confidence,
                        "attempt": attempt,
                    },
                )

            logger.info(
                "ocr.assert_text: PASS target={!r} conf={:.3f} attempt={}",
                label, result.confidence, attempt,
            )
            return result

        except (OcrLowConfidenceError, OcrTextMismatchError) as exc:
            last_exc = exc
            if attempt < retries:
                sleep_s = backoff * attempt
                logger.warning(
                    "ocr.assert_text: attempt {}/{} failed ({}) — retrying in {:.2f}s",
                    attempt, retries, type(exc).__name__, sleep_s,
                )
                time.sleep(sleep_s)
            else:
                logger.error(
                    "ocr.assert_text: all {} attempts exhausted for {!r}",
                    retries, label,
                )

    # Attach final screenshot path to the exception and re-raise
    assert last_exc is not None
    if last_result is not None:
        last_exc.screenshot_path = str(last_result.image_path)
    raise last_exc
