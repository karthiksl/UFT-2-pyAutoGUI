# CLAUDE.md — UFT One → PyAutoGUI Migration Framework

This file gives Claude Code the project context needed to work on this codebase
without re-explaining it every session.

---

## What This Project Does

Converts UFT One VBScript (`.qfl`) test scripts into Python automation tests
that run on **both macOS and Windows** using PyAutoGUI, OpenCV, and pytesseract.

```
source/qfl/TEST_XXXXXX_NAME.qfl
        │
        │  python3 tools/qfl_to_pyautogui.py --qfl <file>
        ▼
output/flows/<screen>/flow_test_XXXXXX_name.py   ← main output
output/flows/<screen>/task_<screen>.py            ← action stubs
Terminal: YAML block → paste into automation/or/app_or.yaml
```

---

## Project Layout

```
uft-2-pyautogui/
├── source/qfl/                         ← source UFT .qfl files go HERE
│   ├── TEST_188001_MEMBER_LOGIN.qfl
│   ├── TEST_188002_MEMBER_SEARCH.qfl
│   ├── TEST_188003_COVERAGE_VERIFY.qfl
│   ├── TEST_188004_NEW_ENROLLMENT.qfl
│   └── TEST_188005_COVERAGE_CHANGE.qfl
├── output/                             ← ALL CONVERTER OUTPUT goes here (next to source/)
│   └── flows/
│       ├── member_login/               ← flow_test_188001_member_login.py + task_member_login.py
│       ├── member_search/              ← flow_test_188002_member_search.py + task_member_search.py
│       ├── coverage_verify/            ← flow_test_188003_coverage_verify.py + task_coverage_verify.py
│       ├── new_enrollment/             ← flow_test_188004_new_enrollment.py + task_new_enrollment.py
│       └── coverage_change/            ← flow_test_188005_coverage_change.py + task_coverage_change.py
├── fixtures/sample_uft/ ← offline mock app + screens for the e2e_sample demo
├── tools/
│   └── qfl_to_pyautogui.py   ← THE CONVERTER — entry point for all conversions
├── automation/
│   ├── core/             ← framework engine (actions, finder, ocr, waits, citrix)
│   ├── common/           ← shared Epic business logic (Context, DataRow, reporter)
│   ├── or/app_or.yaml    ← Visual Object Repository — fill regions + capture PNGs
│   ├── assets/images/    ← reference PNG crops, one folder per screen
│   ├── tests/
│   │   ├── flows/        ← reviewed/finalised flow files (copied from output/)
│   │   ├── tasks/        ← reviewed/finalised task stubs (copied from output/)
│   │   └── unit/         ← 218 unit tests, no screen required
│   └── pyproject.toml
└── docs/
    ├── HOW_TO_CONVERT.md     ← step-by-step user guide
    └── DEVELOPER_GUIDE.md    ← architecture + every file explained
```

---

## Tech Stack

| Library | Purpose |
|---|---|
| **PyAutoGUI** | Mouse clicks, keyboard input |
| **OpenCV** | Image-based element finding (replaces UFT Object Repository) |
| **pytesseract** | OCR — read text from screen (replaces `GetROProperty("innerText")`) |
| **pytest** | Test runner |
| **loguru** | Structured logging |
| **Pillow (PIL)** | Screenshots via `ImageGrab` |
| **pygetwindow** | Window title reads (Windows only) |
| **pywinauto** | Advanced window management (Windows only) |

Python version: **3.9+** (venv at `automation/.venv`).

---

## Key Rules — Always Follow These

1. **Never use `pyautogui.click(x, y)` directly in flow or task files.**
   Always use `actions.click("screen.element")` — raw coordinates break on
   resolution changes.

2. **Never use `time.sleep()` in flow or task files.**
   Use `waits.wait_for_screen_stable(region=…)` or
   `waits.wait_for_object_exists(spec, timeout=…)` only.

3. **`waits.wait_for_object_exists` raises — it never returns False.**
   Always wrap conditional checks in `_screen_exists(or_repo, anchor, timeout=n)`,
   which is auto-generated into every flow file.

4. **No hardcoded pixel coordinates in Python files.**
   Regions belong in `automation/or/app_or.yaml` only.

5. **No real PHI (patient data) in CSV test data files.**
   Use synthetic data only.

6. **Do not edit `automation/core/` files unless fixing a framework bug.**
   Business logic belongs in `automation/common/` and `automation/tests/flows/`.
   New generated files land in `output/flows/` first — copy to `automation/tests/flows/` after review.

7. **Screen names are always snake_case.**
   `MemberLogin` → `member_login`, `CoverageVerify` → `coverage_verify`.

8. **Logical element names follow the pattern `screen.element_name`.**
   Example: `member_login.sign_in`, `member_search.patient_search_bar`.

---

## The Converter (`tools/qfl_to_pyautogui.py`)

### How to run

```bash
# Convert a single QFL file
python3 tools/qfl_to_pyautogui.py --qfl source/qfl/TEST_188001_MEMBER_LOGIN.qfl

# Dry run — print output without writing files
python3 tools/qfl_to_pyautogui.py --qfl source/qfl/TEST_188001_MEMBER_LOGIN.qfl --dry-run

# Override the inferred screen name
python3 tools/qfl_to_pyautogui.py --qfl source/qfl/MY_TEST.qfl --screen epic_login

# Convert all QFL files at once
for qfl in source/qfl/*.qfl; do python3 tools/qfl_to_pyautogui.py --qfl "$qfl"; done
```

### Confidence scoring system

Every statement is scored 0–100. After conversion the terminal prints a visual
report, and the generated file's docstring contains a compact summary.

| Score | Tier | Meaning |
|---|---|---|
| 100 | EXACT | Perfect 1-to-1, no review needed |
| 90 | HIGH | Correct, add element to `app_or.yaml` |
| 75 | GOOD | `# TODO` to resolve — 1–2 min each |
| 55 | MEDIUM | Partial — dropdown/table needs manual work |
| 30 | LOW | Placeholder — write manually |
| 10 | FALLBACK | Unrecognised — raw VBScript kept as comment |

Typical result for the 5 sample QFL files: **93–98% EXCELLENT**.

### Patterns the converter handles

**Web:** `WebEdit.Set/Click/GetROProperty`, `WebButton.Click`, `WebLink.Click`,
`WebElement.Click/FireEvent/SetAttribute/GetROProperty/Exist`,
`WebCheckBox.Set`, `WebRadioGroup.Select`, `WebList.Select/GetROProperty`,
`WebFile.Set`, `WebTable.ChildItem.Click`, `Browser.Page.*`, `Browser.Sync`,
`Page.Exist`

**Win/Java/Dialog:** `WinButton.Click`, `WinEdit.Set/GetROProperty`, `WinList.Select`,
`JavaButton.Click`, `JavaEdit.SetText`, `JavaList.Select`,
`Dialog.WinButton.Click`, `SwfButton.Click`, `Window.Activate`

**System:** `SystemUtil.Run`, `SystemUtil.CloseProcessByName`, `MsgBox`,
`Call function`, `Set Nothing`, `Environment("Var")`

**Reporter:** `micPass`, `micFail`, `micWarning`, `micInfo`

**Block structures:** `If/ElseIf/Else/End If`, `For/Next`, `For Each/Next`,
`Do While/Until/Loop`, `Select Case/Case/End Select`, `With/End With`,
`On Error Resume Next/GoTo 0`

**VBScript built-ins (translated inline):** `Len`, `Left`, `Right`, `Mid`,
`UCase`, `LCase`, `Trim`, `LTrim`, `RTrim`, `Replace`, `CStr`, `CInt`, `CLng`,
`CDbl`, `CSng`, `CBool`, `Now()`, `Date()`, `Time()`, `Abs`, `Round`,
`IsNull`, `IsEmpty`, `IsNumeric`, `InStr`

---

## Platform Behaviour

| Feature | macOS | Windows |
|---|---|---|
| `actions.click()` | Full | Full |
| OpenCV image matching | Full | Full |
| Tesseract OCR | Full (`brew install tesseract`) | Full (UB-Mannheim installer) |
| `citrix.ensure_citrix_focused()` | Logs warning, no-op | Finds + focuses Citrix window |
| `citrix.get_session_state()` | Returns `ACTIVE` (safe default) | Checks real session |
| `citrix.get_session_rect()` | Returns full screen `(0,0,w,h)` | Returns Citrix window rect |
| Running against Epic in Citrix | Development/review only | **Production — use this** |

Platform detection is one line in `citrix.py`:
```python
_IS_WINDOWS = platform.system() == "Windows"
```

**Mac** = writing flows, running the converter, unit testing.
**Windows (Citrix VDI)** = running tests against the real Epic system.

---

## Running Tests

```bash
# Activate venv first (macOS)
source automation/.venv/bin/activate

# Unit tests — no screen required, run on any machine
pytest automation/tests/unit/ -v
# Expected: 218 passed, 4 skipped (Tesseract binary tests — safe to ignore)

# A generated flow test (requires screen + OR YAML populated)
pytest automation/tests/flows/member_login/ -v

# All regression tests
pytest -m regression -v
```

---

## Adding a New UFT Pattern to the Converter

When `translate_stmt()` in `tools/qfl_to_pyautogui.py` doesn't recognise a
VBScript pattern, it falls back to FALLBACK (score 10). To add a new pattern:

1. Add a new `re.match(...)` block in `translate_stmt()` before the fallback.
2. Return a `StmtResult` with `lines`, `confidence` (use `CONF["EXACT"]` etc.),
   `pattern` (short human label), and optionally `obj_name`/`ocr_name`.
3. Write a unit test in `automation/tests/unit/` for the new pattern.
4. Re-run the converter on the affected QFL files to regenerate their flow files.
5. Update `docs/HOW_TO_CONVERT.md` to list the new pattern in the correct tier table.

---

## Common Tasks

### Re-generate a flow after changing the converter

```bash
python3 tools/qfl_to_pyautogui.py --qfl source/qfl/TEST_XXXXXX_NAME.qfl
# Output lands in output/flows/<screen>/flow_test_XXXXXX_<name>.py
# Copy to automation/tests/flows/<screen>/ when ready
```

### Add a new QFL file

```bash
# 1. Drop the .qfl file in source/qfl/
# 2. Convert it — output goes to output/flows/<screen>/
python3 tools/qfl_to_pyautogui.py --qfl source/qfl/TEST_XXXXXX_MY_TEST.qfl
# 3. Fix all # TODO items in output/flows/<screen>/flow_test_XXXXXX_my_test.py
# 4. Copy the reviewed file to automation/tests/flows/<screen>/
# 5. Capture reference PNGs for each element
# 6. Paste the YAML block into automation/or/app_or.yaml
# 7. Create automation/data/TEST_XXXXXX/TEST_XXXXXX.csv
```

### Run the confidence report for all 5 sample QFLs

```bash
for qfl in source/qfl/*.qfl; do
    python3 tools/qfl_to_pyautogui.py --qfl "$qfl" --dry-run 2>&1 \
        | grep -E "(Score|Statements|EXACT|HIGH|GOOD|MEDIUM|LOW|FALL)"
done
```

---

## File Naming Conventions

| File | Convention | Example |
|---|---|---|
| QFL source | `TEST_<6-digit-ID>_<DESC_CAPS>.qfl` | `TEST_188001_MEMBER_LOGIN.qfl` |
| Generated flow | `flow_test_<id>_<desc>.py` | `flow_test_188001_member_login.py` |
| Generated task stub | `task_<screen>.py` | `task_member_login.py` |
| Reference PNG | `<screen>/<element>.png` | `member_login/sign_in.png` |
| Test data CSV | `TEST_XXXXXX/TEST_XXXXXX.csv` | `TEST_188001/TEST_188001.csv` |

---

## Docs

| Doc | When to read |
|---|---|
| `docs/HOW_TO_CONVERT.md` | Step-by-step: install → convert → fix TODOs → run test |
| `docs/DEVELOPER_GUIDE.md` | Architecture, every Python file explained, adding tests |
| `README.md` | Quick-start, platform table, full UFT→Python reference |
