# How to Convert a UFT QFL File to PyAutoGUI

Complete step-by-step guide — from installing the tools to running your first
converted test. Covers both **macOS** and **Windows**.

---

## Part 1 — Install Everything

### macOS

```bash
# Step 1: Install Homebrew (skip if already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Step 2: Install Tesseract (OCR engine)
brew install tesseract

# Step 3: Verify Python 3.9+ is available
python3 --version   # must print 3.9 or higher
# If lower, install a newer Python:
brew install python@3.13

# Step 4: Create a virtual environment in the project
cd /path/to/uft-2-pyautogui
python3 -m venv automation/.venv
source automation/.venv/bin/activate

# Step 5: Install the package
pip install -e "automation/.[test]"

# Step 6: Confirm everything works
pytest automation/tests/unit/ -v
# Expected: 218 passed, 4 skipped (skipped = Tesseract-binary tests, safe to ignore)
```

**macOS one-time permissions** — open System Settings and grant:
- `Privacy & Security → Screen Recording → Terminal` (for screenshots)
- `Privacy & Security → Accessibility → Terminal` (for mouse/keyboard control)

Without these two permissions, the framework cannot capture screenshots or click
on other application windows.

---

### Windows (Citrix VDI)

```powershell
# Step 1: Install Python 3.11+ from https://python.org
#         Check "Add Python to PATH" during install

# Step 2: Install Tesseract OCR engine
#         Download from: https://github.com/UB-Mannheim/tesseract/wiki
#         Install to default location: C:\Program Files\Tesseract-OCR\

# Step 3: Verify
python --version       # must print 3.11+
tesseract --version    # must print a version number

# Step 4: Create a virtual environment
cd C:\path\to\uft-2-pyautogui
python -m venv automation\.venv
automation\.venv\Scripts\activate

# Step 5: Install the package (include [windows] for Citrix window management)
pip install -e "automation\.[test,windows]"

# Step 6: Confirm
pytest automation\tests\unit\ -v
```

---

## Part 2 — Place Your QFL File

Copy your UFT `.qfl` file into the `source/qfl/` folder:

```
uft-2-pyautogui/
└── source/
    └── qfl/
        └── TEST_188001_MEMBER_LOGIN.qfl   ← your file goes here
```

**Recommended filename format:**
```
TEST_<6-digit-ID>_<DESCRIPTION_IN_CAPS>.qfl
```

Examples:
```
TEST_188001_MEMBER_LOGIN.qfl
TEST_188005_COVERAGE_CHANGE.qfl
TEST_200012_NEW_ENROLLMENT.qfl
```

The `TEST_` prefix and the 6-digit numeric ID are automatically stripped when
deriving the Python screen name. `TEST_188001_MemberLogin` becomes screen
`member_login`, function `flow_test_188001_member_login`.

---

## Part 3 — Run the Converter

From the project root (`uft-2-pyautogui/`):

```bash
# macOS — single file
python3 tools/qfl_to_pyautogui.py --qfl source/qfl/TEST_188001_MEMBER_LOGIN.qfl

# Windows — single file
python tools\qfl_to_pyautogui.py --qfl source\qfl\TEST_188001_MEMBER_LOGIN.qfl

# Convert ALL .qfl files under source/qfl/ in one shot (cross-platform)
python3 tools/qfl_to_pyautogui.py --all

# …or point --all at any other directory
python3 tools/qfl_to_pyautogui.py --all path/to/my/qfls

# Preview output without writing any files
python3 tools/qfl_to_pyautogui.py --qfl source/qfl/TEST_188001_MEMBER_LOGIN.qfl --dry-run

# Override the inferred screen name
python3 tools/qfl_to_pyautogui.py --qfl source/qfl/MY_TEST.qfl --screen epic_login

# Suppress the inline `# confidence: …` comments in the generated code
python3 tools/qfl_to_pyautogui.py --qfl source/qfl/MY_TEST.qfl --no-conf-comments
```

### CLI flag reference

| Flag | Required? | Purpose |
|---|---|---|
| `--qfl PATH` | one of these | Convert one .qfl file |
| `--all [DIR]` | one of these | Convert every `*.qfl` under DIR (default: `source/qfl`) |
| `--screen NAME` | optional | Override the inferred snake_case screen name (single-file only) |
| `--out-dir DIR` | optional | Write the flow file somewhere other than `output/flows/<screen>/` |
| `--dry-run` | optional | Print generated code + report, write nothing |
| `--no-conf-comments` | optional | Suppress inline `# confidence: TIER (NN) - pattern` lines |

### What the converter prints

```
[1/4] Parsing: TEST_188001_MEMBER_LOGIN.qfl
       Found 1 function(s): ['TEST_188001_MemberLogin']
       Translating 'TEST_188001_MemberLogin' → screen='member_login'
         DataTable cols : ['Username', 'Password', 'ExpectedTitle']
         Objects found  : ['member_login.username', 'member_login.sign_in']
         OCR targets    : []

[2/4] Generated flow file:    ← Python test logic
[3/4] Generated task stub:    ← atomic action stubs
[4/4] YAML OR entries:        ← paste into app_or.yaml
```

### What the converter writes to disk

Each QFL file produces three files under `output/flows/<screen>/`:

```
output/flows/
├── member_login/
│   ├── __init__.py
│   ├── flow_test_188001_member_login.py    ← resolve all # TODO items here
│   └── task_member_login.py
├── member_search/
│   ├── __init__.py
│   ├── flow_test_188002_member_search.py
│   └── task_member_search.py
├── coverage_verify/
│   ├── __init__.py
│   ├── flow_test_188003_coverage_verify.py
│   └── task_coverage_verify.py
├── new_enrollment/
│   ├── __init__.py
│   ├── flow_test_188004_new_enrollment.py
│   └── task_new_enrollment.py
└── coverage_change/
    ├── __init__.py
    ├── flow_test_188005_coverage_change.py
    └── task_coverage_change.py
```

After reviewing and fixing all `# TODO` items, copy to `automation/tests/`:

```bash
cp output/flows/member_login/flow_test_188001_member_login.py automation/tests/flows/member_login/
cp output/flows/member_login/task_member_login.py             automation/tests/tasks/member_login/
```

---

## Part 4 — Understand the Converter Confidence Levels

Every translated statement gets a numeric score (0–100) that measures how
reliably the converter handled that pattern. The score is recorded in three
places:

1. The terminal report printed after every conversion (also a per-file
   summary table when you run `--all`).
2. A compact summary block at the top of every generated flow `.py` file
   (inside the docstring).
3. An inline `# confidence: TIER (NN) - pattern` comment above each
   translated statement in the generated `.py` file. Pass
   `--no-conf-comments` to suppress these when you want a leaner output.

### The six confidence tiers

| Score | Tier | Meaning |
|---|---|---|
| 100 | **EXACT** | Perfect 1-to-1 translation — no changes needed |
| 90 | **HIGH** | Correct translation — add the element to `app_or.yaml` |
| 75 | **GOOD** | Translated with a guiding `# TODO` — 1–2 minutes to resolve |
| 55 | **MEDIUM** | Partial — dropdown or table logic must be written manually |
| 30 | **LOW** | Placeholder emitted — must be written manually |
| 10 | **FALLBACK** | Pattern unrecognised — raw VBScript kept as a comment |

### Terminal report (printed after every conversion)

```
────────────────────────────────────────────────────────────────────
  CONVERSION CONFIDENCE REPORT
────────────────────────────────────────────────────────────────────
  Statements translated : 44
  Overall score         : 96.1%  →  EXCELLENT

  EXACT    (100%) :  33  (  75%)  ███████████████
  HIGH     ( 90%) :   3  (   7%)  █
  GOOD     ( 75%) :   7  (  16%)  ███
  MEDIUM   ( 55%) :   1  (   2%)

  Items needing attention (7 total):
    [Wait N                       ]  Wait 2
    [Wait N                       ]  Wait 1
    [WebList.Select               ]  WebList("PlanDropdown").Select sPlan
────────────────────────────────────────────────────────────────────
```

### Confidence summary in the generated file

The generated flow `.py` file's docstring also contains a compact summary:

```python
"""
Flow    : TEST_188005_CoverageChange
Source  : TEST_188005_COVERAGE_CHANGE.qfl

AUTO-GENERATED by tools/qfl_to_pyautogui.py
Search for  # TODO  and resolve every item before running in CI.

Conversion Report
  Statements   : 51
  Score        : 94%  → EXCELLENT
  EXACT        :  41  (80%)
  HIGH         :   3  (6%)
  GOOD         :   7  (14%)
  TODOs to fix : 9  (search '# TODO' below)
"""
```

### Inline per-statement confidence comments

Above every translated statement in the generated file you'll see a one-line
marker pointing back to the matched UFT pattern and its tier:

```python
# confidence: EXACT (100) - WebEdit.Set
actions.type_text("member_login.username", username)

# confidence: GOOD (75) - Wait 1
# TODO: Wait 1 — replace with:
# waits.wait_for_screen_stable(region=(0, 0, 1280, 800))

# confidence: LOW (30) - Browser.Page.GetROProperty(title)
# TODO: get page/window title — use pygetwindow or OCR on title bar
actual_title = "TODO_window_title"
```

Pass `--no-conf-comments` to suppress these lines.

### Typical results for the 5 sample QFL files (after the latest refresh)

| QFL File | Statements | Score | Quality |
|---|---|---|---|
| TEST_188001_MEMBER_LOGIN | 23 | 93.7% | EXCELLENT |
| TEST_188002_MEMBER_SEARCH | 34 | 96.8% | EXCELLENT |
| TEST_188003_COVERAGE_VERIFY | 31 | 98.2% | EXCELLENT |
| TEST_188004_NEW_ENROLLMENT | 40 | 93.8% | EXCELLENT |
| TEST_188005_COVERAGE_CHANGE | 51 | 94.2% | EXCELLENT |

(Statement counts changed because the new block-aware confidence tracking
now records every If/For/Else/On Error branch — previously these block
openers were silent.)

---

### EXACT (100) — auto-translated, zero review needed

#### Web elements

| UFT VBScript | Generated Python |
|---|---|
| `WebButton("SignIn").Click` | `actions.click("screen.sign_in")` |
| `WebEdit("Username").Set sUser` | `actions.type_text("screen.username", username)` |
| `WebEdit("Username").Click` | `actions.click("screen.username")` |
| `WebElement("Tab").Click` | `actions.click("screen.tab")` |
| `WebLink("ForgotPassword").Click` | `actions.click("screen.forgot_password")` |
| `Browser(…).Page(…).WebButton(…).Click` | `actions.click("screen.element")` |
| `Browser(…).Page(…).WebEdit(…).Set val` | `actions.type_text("screen.element", val)` |
| `Browser(…).Page(…).WebElement(…).Click` | `actions.click("screen.element")` |

#### Data and reporting

| UFT VBScript | Generated Python |
|---|---|
| `DataTable("Col")` / `DataTable("Col", dtLocalSheet)` | `row.require("Col")` |
| `sVar = DataTable("Col")` | `var = row.require("Col")` |
| `Reporter.ReportEvent micPass, "label", msg` | `ctx.reporter.passed("label", msg)` |
| `Reporter.ReportEvent micFail, "label", msg` | `ctx.reporter.failed(…)` + `raise AssertionError` |
| `Reporter.ReportEvent micWarning, "label", msg` | `ctx.reporter.warning("label", msg)` |
| `Reporter.ReportEvent micInfo, "label", msg` | `ctx.reporter.info("label", msg)` |
| `Set obj = Nothing` | `obj = None` |

#### Code structure

| UFT VBScript | Generated Python |
|---|---|
| `Dim sVar` | silently removed |
| `Exit Function` / `Exit Sub` after `micFail` | silently removed (dead code after `raise`) |
| `If … Then … End If` | `if …:` block |
| `ElseIf … Then` | `elif …:` |
| `Else` | `else:` |
| Hungarian prefixes `sVar`, `bFlag`, `iCount` | `var`, `flag`, `count` |
| `"text" & sVar & "more"` | `"text" + var + "more"` |
| `InStr(hay, ndl) > 0` | `ndl in hay` |
| `<>`, `And`, `Or`, `Not` | `!=`, `and`, `or`, `not` |
| Line continuation `_` at end of line | joined to next line automatically |

---

### HIGH (90) — correct translation, wire up YAML entry

| UFT VBScript | Generated Python |
|---|---|
| `WebEdit("Name").GetROProperty("value")` | `ocr.read_target("screen.name_text")` |
| `WebElement("Name").GetROProperty("innerText")` | `ocr.read_target("screen.name_text")` |
| `WebList("Name").GetROProperty("value")` | `ocr.read_target("screen.name_text")` |
| `WebCheckBox("Name").Set "ON"` | `actions.click("screen.name")  # sets to checked` |
| `WebCheckBox("Name").Set "OFF"` | `actions.click("screen.name")  # sets to unchecked` |
| `WebElement("Name").FireEvent "onclick"` | `actions.click("screen.name")  # NOTE: FireEvent` |
| `WinButton("OK").Click` | `actions.click("screen.ok")` |
| `WinEdit("Name").Set val` | `actions.type_text("screen.name", val)` |
| `WinEdit("Name").GetROProperty("value")` | `ocr.read_target("screen.name_text")` |
| `JavaButton("Submit").Click` | `actions.click("screen.submit")` |
| `JavaEdit("Name").SetText val` | `actions.type_text("screen.name", val)` |
| `Dialog("Name").WinButton("OK").Click` | `actions.click("screen.ok")` |
| `SwfButton("Name").Click` | `actions.click("screen.name")  # Silverlight/Flash` |
| `Browser(…).Sync` | `waits.wait_for_screen_stable(region=(0, 0, 1280, 800))` |
| `Browser(…).Page(…).WebCheckBox(…).Set` | `actions.click("screen.element")` |
| `Browser(…).Page(…).WebElement(…).GetROProperty` | `ocr.read_target("screen.element_text")` |
| `Page("X").Exist(n)` standalone | `waits.wait_for_object_exists(or_repo.get("x.header_label"), …)` |
| `MsgBox "text"` | `ctx.logger.info("MsgBox: " + str("text"))` |
| `Environment("Var")` | `os.environ.get("Var", "")` |
| `WebEdit("Name").SetSecure val` | `actions.type_text("screen.name", val)  # NOTE: masked` |

**What you must do:** Add the element to `automation/or/app_or.yaml` and capture
its reference PNG. The logical name in the generated code is already correct.

---

### GOOD (75) — translated with `# TODO`, 1–2 minutes to resolve

| UFT VBScript | Generated Python | Fix |
|---|---|---|
| `Wait 2` | `# TODO: Wait 2 — replace with:` `# waits.wait_for_screen_stable(…)` | Delete the `# TODO` line; uncomment the wait |
| `Page("X").Exist(n)` in If condition | `_screen_exists(or_repo, "x.header_label", timeout=n)` | Add anchor to `app_or.yaml` |
| `WebElement("X").Exist(n)` in If | `_screen_exists(or_repo, "screen.x", timeout=n)` | Add element to `app_or.yaml` |
| `WebRadioGroup("Name").Select val` | `actions.click("screen.name")  # TODO: locate by OCR` | Find radio option via OCR |
| `WebFile("Name").Set path` | `actions.type_text(…)` + `actions.press("enter")` | Test file picker works |
| `WebElement("Name").FireEvent "event"` | `actions.click(…)  # NOTE: FireEvent` | Verify click triggers the event |
| `Call FunctionName(args)` | `function_name(args)  # TODO: ensure imported` | Add the import |
| `On Error Resume Next` | `try:  # On Error Resume Next` | Review the except block |
| `For i = 1 To n` | `for i in range(1, n + 1):` | Check range bounds |
| `For Each item In coll` | `for item in coll:` | Ensure `coll` is a Python iterable |
| `Do While cond / Loop` | `while cond:` | Verify loop termination |

---

### MEDIUM (55) — partial translation, manual work required

| UFT VBScript | Generated Python | Fix |
|---|---|---|
| `WebList("Name").Select val` | `actions.click(…)` + `actions.type_text(…)` + `# TODO` | Replace with arrow-key navigation or OCR select |
| `WinList("Name").Select val` | Same as above | Same fix |
| `JavaList("Name").Select val` | Same as above | Same fix |
| `Browser(…).Page(…).WebList(…).Select val` | Same as above | Same fix |
| `WebElement("Name").SetAttribute attr, val` | `# TODO: SetAttribute` + `actions.type_text(…)` | Use JS injection or OCR verify |
| `SystemUtil.Run path` | `subprocess.Popen([path])  # TODO` | Adjust process args as needed |
| `SystemUtil.CloseProcessByName name` | `subprocess.run(["taskkill", …])  # TODO` | Verify process name on target OS |
| `WebTable("Name").ChildItem(r, c).Click` | `# TODO: table cell click` | Use OCR to find row, then click |

---

### LOW (30) — placeholder only, must be written manually

| UFT VBScript | Generated placeholder | What to write |
|---|---|---|
| `Browser(…).Page(…).GetROProperty("title")` | `title = "TODO_window_title"` | `gw.getActiveWindow().title` or OCR on title bar |
| `WebElement("Name").GetROProperty("disabled")` | `name = "TODO_name_disabled"` | Use OCR to check visual state |
| `Window("Name").Activate` | `# TODO: bring window to foreground` | `gw.getWindowsWithTitle("Name")[0].activate()` |
| Complex VBScript expression | `# TODO: translate expression: …` | Write Python equivalent manually |

---

### FALLBACK (10) — unrecognised, raw VBScript kept

Any statement the converter cannot recognise at all produces:

```python
# TODO: translate → OriginalVBScriptLineHere
```

Search for `# TODO: translate →` in the generated file. These need manual
translation — they are rare for standard UFT patterns.

---

### Block structures translated automatically

These block-level constructs are translated without any confidence penalty:

| VBScript | Python |
|---|---|
| `If cond Then / ElseIf / Else / End If` | `if / elif / else:` |
| `For i = 1 To n [Step s] / Next` | `for i in range(1, n+1[, s]):` |
| `For Each item In collection / Next` | `for item in collection:` |
| `Do While cond / Loop` | `while cond:` |
| `Do Until cond / Loop` | `while not (cond):` |
| `Do / Loop While cond` | `while True: … if not (cond): break` |
| `Select Case var / Case val / Case Else / End Select` | `if var == val: / elif: / else:` |
| `With obj / End With` | prefix all `.Property` lines with `obj` inline |
| `On Error Resume Next` | `try:` |
| `On Error GoTo 0` | `except Exception: pass` |

---

### VBScript built-in functions translated automatically

All of these are translated inside assignments and conditions:

| VBScript | Python |
|---|---|
| `Len(s)` | `len(s)` |
| `UCase(s)` | `s.upper()` |
| `LCase(s)` | `s.lower()` |
| `Trim(s)` | `s.strip()` |
| `LTrim(s)` | `s.lstrip()` |
| `RTrim(s)` | `s.rstrip()` |
| `Left(s, n)` | `s[:n]` |
| `Right(s, n)` | `s[-n:]` |
| `Mid(s, start, len)` | `s[start-1:start-1+len]` |
| `Replace(s, find, rep)` | `s.replace(find, rep)` |
| `CStr(v)` | `str(v)` |
| `CInt(v)` / `CLng(v)` | `int(v)` |
| `CDbl(v)` / `CSng(v)` | `float(v)` |
| `CBool(v)` | `bool(v)` |
| `Now()` | `datetime.now()` |
| `Date()` | `datetime.now().date()` |
| `Time()` | `datetime.now().time()` |
| `Abs(v)` | `abs(v)` |
| `Round(v, n)` | `round(v, n)` |
| `IsNull(v)` | `v is None` |
| `IsEmpty(v)` | `(v is None or v == "")` |
| `IsNumeric(v)` | `str(v).isnumeric()` |
| `Environment("Var")` | `os.environ.get("Var", "")` |

---

## Part 5 — Fix Every `# TODO` in the Flow File

Open the generated flow file and work through each `# TODO` from top to bottom.

### Fix: Wait N

```python
# BEFORE (generated):
actions.click("coverage_change.activity_menu")
# TODO: Wait 1 — replace with:
# waits.wait_for_screen_stable(region=(0, 0, 1280, 800))

# AFTER (you fix it — delete TODO line, uncomment the wait):
actions.click("coverage_change.activity_menu")
waits.wait_for_screen_stable(region=(0, 0, 1280, 800))
```

### Fix: Dropdown select

```python
# BEFORE (generated — non-functional):
# TODO: dropdown select — click to open, then locate option by OCR
actions.click("coverage_change.new_plan_dropdown")
actions.type_text("coverage_change.new_plan_dropdown", new_plan_code)

# AFTER — Option A: navigate by arrow keys
actions.click("coverage_change.new_plan_dropdown")
actions.press("down", presses=3)   # press down until correct option is highlighted
actions.press("enter")

# AFTER — Option B: type to filter, then Enter
actions.click("coverage_change.new_plan_dropdown")
actions.type_text("coverage_change.new_plan_dropdown", new_plan_code)
actions.press("enter")
```

### Fix: Page title

```python
# BEFORE (generated):
# TODO: get page/window title — use pygetwindow or OCR on title bar
actual_title = "TODO_window_title"

# AFTER — Option A: read window title via pygetwindow (Windows)
import pygetwindow as gw
actual_title = gw.getActiveWindow().title

# AFTER — Option B: read title bar text via OCR (Mac or Windows)
actual_title = ocr.read_target("epic_home.title_bar_text").text
```

### Fix: Screen anchor not in OR

The generated code already has the correct anchor name — you just need to add
the entry to `app_or.yaml`:

```python
# Generated (already correct):
if not _screen_exists(or_repo, "epic_home.header_label", timeout=20):
```

Add to `automation/or/app_or.yaml`:
```yaml
objects:
  - name: epic_home.header_label
    screen: epic_home
    type: label
    image: epic_home/header_label.png   # capture this PNG (see Part 6)
    region: [0, 60, 800, 40]
    min_confidence: 0.82
```

---

## Part 6 — Capture Reference PNG Images

Every element the framework interacts with needs a PNG crop saved as a reference.
OpenCV uses this image to locate the element on screen.

### macOS

```bash
# Take a full screenshot while Epic (or the target app) is open
python3 -c "import pyautogui; pyautogui.screenshot('full.png')"

# Open full.png in Preview
open full.png

# In Preview: Tools → Rectangular Selection → drag around the element
# File → Export → save as:
#   automation/assets/images/member_login/username.png
```

### Windows

```powershell
# Take a full screenshot
python -c "import pyautogui; pyautogui.screenshot('full.png')"

# Open full.png in Paint (or any image editor)
# Select the element tightly, copy and paste into a new image, save as:
#   automation\assets\images\member_login\username.png
```

### Get pixel coordinates for regions

```bash
# Run this — hover over the element corner while it prints coordinates
python3 -c "
import pyautogui, time
for _ in range(15):
    print(pyautogui.position())
    time.sleep(1)
"
```

Note the (x, y) of the top-left corner of the element and measure its width and
height. Enter as `region: [x, y, width, height]` in the YAML.

---

## Part 7 — Update the Object Repository YAML

Copy the `[4/4] YAML OR entries` block from the converter output and paste it
into `automation/or/app_or.yaml`. Then fill in real values:

```yaml
objects:

  - name: member_login.username       # logical name — used in Python code
    screen: member_login
    type: input
    image: member_login/username.png  # path relative to automation/assets/images/
    region: [448, 174, 384, 60]       # [x, y, width, height] in screen pixels
    min_confidence: 0.82              # 0.0–1.0 — how close PNG must match screen
    # delete the "status: todo" line once the entry is complete

ocr_targets:

  - name: member_search.patient_banner_text
    screen: member_search
    region: [20, 98, 600, 30]          # where on screen to look for text
    expected_pattern: "MRN:\\s*\\d{7}" # regex to validate — set something specific
    lang: eng
    preprocess: [grayscale, upscale_2x, otsu_threshold]
    min_confidence: 0.60               # Tesseract confidence threshold 0.0–1.0
```

**Preprocessing options for OCR** (`preprocess:` list in YAML):

| Step | When to use |
|---|---|
| `grayscale` | Always use first |
| `upscale_2x` | Small fonts, Citrix compression |
| `upscale_3x` | Very small fonts (under 10pt) |
| `otsu_threshold` | Most cases — dark text on light background |
| `adaptive_threshold` | Uneven or gradient backgrounds |
| `invert` | Light text on dark background |
| `denoise` | Heavy JPEG artifacts from Citrix |
| `deskew` | Misaligned or rotated text |

---

## Part 8 — Create the Test Data CSV

Create a CSV file with one row per test case. Column names must match what the
flow calls with `row.require("ColumnName")`.

```
automation/data/TEST_188001/TEST_188001.csv
```

```csv
TestCaseID,Username,Password,ExpectedTitle
TEST-001,jsmith,Password1!,Epic Home
TEST-002,ajones,Password2!,Epic Home
```

---

## Part 9 — Write the pytest Test Module

After copying the reviewed flow file to `automation/tests/flows/member_login/`,
create a `test_*.py` file alongside it:

```python
# automation/tests/flows/member_login/test_188001_member_login.py

import csv
import logging
from pathlib import Path

import pytest

from automation.common import Context
from automation.common.data import DataRow
from automation.common.reporting_legacy import ReporterAdapter
from .flow_test_188001_member_login import flow_test_188001_member_login

_CSV  = Path(__file__).parents[3] / "data" / "TEST_188001" / "TEST_188001.csv"
_ROWS = list(csv.DictReader(_CSV.open()))
logger = logging.getLogger(__name__)


@pytest.mark.regression
@pytest.mark.parametrize("csv_row", _ROWS, ids=[r["TestCaseID"] for r in _ROWS])
def test_188001_member_login(csv_row, or_repo, citrix):
    row      = DataRow(suite="TEST_188001", jira=csv_row["TestCaseID"], payload=csv_row)
    reporter = ReporterAdapter()
    ctx      = Context(or_repo=or_repo, row=row, logger=logger, reporter=reporter)
    flow_test_188001_member_login(ctx, row)
    assert not reporter.has_failures()
```

---

## Part 10 — Run the Test

### macOS

```bash
# Activate the virtual environment
source automation/.venv/bin/activate

# Unit tests only (no screen needed — runs on any machine)
pytest automation/tests/unit/ -v

# One specific flow test
pytest automation/tests/flows/member_login/ -v

# One specific CSV row
pytest automation/tests/flows/member_login/ -k "TEST-001" -v

# All regression tests
pytest -m regression -v

# With full log output
pytest automation/tests/flows/ -v -s

# Save an HTML report
pytest automation/tests/flows/ --html=report.html -v
```

### Windows (from Command Prompt or PowerShell)

```powershell
# Activate the virtual environment
automation\.venv\Scripts\activate

# Unit tests
pytest automation\tests\unit\ -v

# One specific flow
pytest automation\tests\flows\member_login\ -v

# All regression tests
pytest -m regression -v
```

### Environment variable overrides

```bash
# Change log level without editing files
AUTOMATION_LOG_LEVEL=DEBUG pytest automation/tests/unit/ -v

# Point to a different OR file
AUTOMATION_OR_PATH=or/my_custom_or.yaml pytest automation/tests/flows/ -v

# Force an OCR failure in the sample test (for testing the reporter)
SAMPLE_FORCE_FAIL=1 pytest -m e2e_sample -v
```

---

## Summary: Input → Output Map

```
source/qfl/                               output/flows/
├── TEST_188001_MEMBER_LOGIN.qfl    ──►   ├── member_login/
├── TEST_188002_MEMBER_SEARCH.qfl   ──►   ├── member_search/
├── TEST_188003_COVERAGE_VERIFY.qfl ──►   ├── coverage_verify/
├── TEST_188004_NEW_ENROLLMENT.qfl  ──►   ├── new_enrollment/
└── TEST_188005_COVERAGE_CHANGE.qfl ──►   └── coverage_change/
          │
          │  python3 tools/qfl_to_pyautogui.py --all
          │
          │  Each screen folder contains:
          │    flow_test_XXXXXX_<name>.py  ← resolve # TODO items here
          │    task_<screen>.py            ← wire up atomic actions here
          │
          │  Terminal also prints:
          │    YAML block ──► paste into automation/or/app_or.yaml
          │
          │  review & fix TODOs, then copy to automation/tests/
          ▼
automation/tests/flows/<screen>/   ← reviewed flow, ready to run
automation/tests/tasks/<screen>/   ← reviewed task stubs
          │
          │  capture PNGs, fill YAML regions, create CSV, write test module
          ▼
pytest automation/tests/flows/<screen>/ -v
    → runs against Epic on screen
    → writes logs to automation/assets/logs/test_run.log
    → saves failure screenshots to automation/assets/screenshots/
```

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `ConfigError: Reference image not found` | PNG crop missing | Capture element with screenshot tool, save to `assets/images/<screen>/` |
| `UiNotFoundError` | PNG doesn't match screen | Re-capture PNG at same resolution as target machine |
| `OcrTextMismatchError` | Wrong region or wrong preprocessing | Check `assets/ocr_debug/` for what Tesseract saw; adjust region or add `upscale_2x` |
| `TimeoutError` inside `_screen_exists` | Element never appeared | Check screen is on the right page; increase timeout |
| Blank screenshots on macOS | Missing Screen Recording permission | `System Settings → Privacy → Screen Recording → Terminal` |
| Clicks land on wrong window on macOS | Missing Accessibility permission | `System Settings → Privacy → Accessibility → Terminal` |
| `ModuleNotFoundError: strenum` | Python < 3.11 needs the backport | `pip install strenum` inside your venv |
| `tesseract is not installed` | Tesseract binary missing | macOS: `brew install tesseract` / Windows: UB-Mannheim installer |
| Citrix window not found (Windows) | Wrong window title in config | Set `citrix_window_title` in `app_or.yaml` to match actual Citrix title bar |
