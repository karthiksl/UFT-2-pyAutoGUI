# SAMPLE_TEST_000001 — E2E Dry-Run Execution Guide

Self-contained end-to-end dry run against the synthetic screen simulator.
No Citrix connection required.

---

## Prerequisites (one-time)

```bash
# Install Python deps (if not already done)
pip install Pillow pytesseract opencv-python-headless pyautogui loguru pytest pyyaml strenum

# macOS — Tesseract OCR engine
brew install tesseract

# Generate the mock PNG screens + OR image crops
python fixtures/sample_uft/generate_mock_screens.py
```

Expected output of the generator:
```
Generating mock screens …
  saved → fixtures/sample_uft/screens/app_frame.png
  saved → fixtures/sample_uft/screens/login.png
  saved → fixtures/sample_uft/screens/home.png
  saved → fixtures/sample_uft/screens/coverage.png
  crop  → automation/assets/images/sample/frame_titlebar.png
  ...
Done.  All PNGs written.
```

---

## Step 1 — Start the screen simulator

Open **Terminal 1** and keep it running throughout the test session:

```bash
cd /path/to/UFTToPyAutoGUI
python fixtures/sample_uft/screen_player.py
```

The window opens at (0, 0) showing `login.png`.

| Key / action | Effect |
|---|---|
| `F8` | Advance to the next screen |
| Click **Login button** | Login → Home (auto-advance) |
| Click **Coverage tab** | Home → Coverage (auto-advance) |
| `Escape` | Quit |

> **macOS Retina note:** If your display is 2× (Retina), set
> `PYAUTOGUI_SCALE=2` before running pytest, or switch System Preferences
> → Displays → Scaled → "Looks like 1280×800".

---

## Step 2 — Run the E2E tests

Open **Terminal 2** (screen_player must still be running):

```bash
cd /path/to/UFTToPyAutoGUI/automation
pytest -m e2e_sample -q
```

Expected output:

```
[self-check] Forbidden-call scan:
  PASS  no pyautogui.click or time.sleep in tasks/sample/ or flows/sample/
[screen_player] showing screen 0: login
[screen_player] click at (640, 387) screen=login
[screen_player] hot zone 'Login button' triggered → screen 1
[screen_player] showing screen 1: home
[screen_player] click at (242, 154) screen=home
[screen_player] hot zone 'Coverage tab' triggered → screen 2
[screen_player] showing screen 2: coverage
..
2 passed in N.Ns
```

---

## Step 3 — Failure injection (optional)

Verify the failure path writes screenshots and raises the right exception:

```bash
SAMPLE_FORCE_FAIL=1 pytest -m e2e_sample -q
```

Expected: **2 failed** with `OcrTextMismatchError`.
Artifacts written to:
- `automation/assets/screenshots/` — full-screen PNGs on each retry
- `automation/assets/ocr_debug/` — preprocessed OCR input images

---

## Verify the OR loads (quick sanity check)

```bash
python3 -c "
from automation.core.or_loader import load_or
or_repo = load_or('automation/or/sample_or.yaml')
print(or_repo)
for name in sorted(or_repo._index):
    print(' ', name)
"
```

Expected:
```
VisualOR(8 objects)
  sample_coverage.effective_date_field
  sample_coverage.header_label
  sample_home.banner_label
  sample_home.coverage_tab
  sample_login.header_label
  sample_login.login_button
  sample_login.password_field
  sample_login.username_field
```

---

## Triage: what to do if it fails

| Failure mode | Log signature to find | Cause | Fix |
|---|---|---|---|
| **Anchor not found** | `UiNotFoundError … Phase 1` | Screen player not running, or window not at (0,0), or PNG not generated | Confirm `screen_player.py` is running; re-run `generate_mock_screens.py`; check that the window is un-obscured at (0,0) |
| **OCR low confidence** | `OcrLowConfidenceError … conf=0.xxx < 0.60` | Retina 2× scaling causes physical/logical pixel mismatch, or wrong preprocess pipeline | Set `PYAUTOGUI_SCALE=2`; check `ocr_debug/` PNG for blank or over-exposed image; verify `invert` step is present in MRN target |
| **Region drift** | `OcrTextMismatchError … extracted=''` or garbage text | Absolute region coords in `sample_or.yaml` don't match where the mock screen renders | Re-run `generate_mock_screens.py`, confirm `W=1280 H=800`, check the OR region values against the generator geometry comments |
| **Post-click anchor not reached** | `PostActionStateNotReachedError … expected 'sample_home.banner_label'` | Click landed outside the hot zone, OR `expect_after` OR name doesn't match the OR | Check screen_player output for `click at (x, y)` vs hot-zone bounds `(570,366)–(710,408)`; verify OR confidence threshold |
