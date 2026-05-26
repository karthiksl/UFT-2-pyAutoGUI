# UFT One → PyAutoGUI Migration Framework

Convert UFT VBScript (`.qfl`) test scripts into Python automation tests that run
on **both Windows and macOS** using PyAutoGUI, OpenCV image matching, and
pytesseract OCR.

---

## Platform Support

| Feature | macOS | Windows |
|---|---|---|
| QFL converter (`tools/qfl_to_pyautogui.py`) | Full | Full |
| Unit tests (218 tests) | Full | Full |
| PyAutoGUI mouse/keyboard | Full | Full |
| OpenCV image matching | Full | Full |
| pytesseract OCR | Full (needs `brew install tesseract`) | Full (needs Tesseract installer) |
| Screenshot capture | Full | Full |
| Running tests against local apps | Full | Full |
| Citrix / VDI window focus | Skipped gracefully (logs warning) | Full — finds and focuses Citrix window |
| Running against Epic in Citrix | Development / review only | **Production — recommended** |

**Mac** is the right machine for: writing flows, running the converter, unit testing,
reviewing generated code.

**Windows (Citrix VDI)** is the right machine for: running tests against the real Epic
system inside a Citrix session.

---

## What This Project Does

```
Your UFT .qfl file    →   tools/qfl_to_pyautogui.py   →   Python test files
(VBScript)                     (converter)                  + YAML OR stub
```

The generated Python code uses:

| Library | Replaces in UFT |
|---|---|
| **PyAutoGUI** | Mouse clicks, keyboard input, `WebButton.Click`, `WebEdit.Set` |
| **OpenCV** | Image-based element finding — replaces UFT Object Repository |
| **pytesseract** | Read text from screen — replaces `GetROProperty("innerText")` |
| **pytest** | Test runner — replaces UFT driver scripts and Test Lab |

---

## Directory Layout

```
uft-2-pyautogui/
│
├── source/
│   └── qfl/                            ← PUT YOUR .qfl FILES HERE
│       ├── TEST_188001_MEMBER_LOGIN.qfl
│       ├── TEST_188002_MEMBER_SEARCH.qfl
│       ├── TEST_188003_COVERAGE_VERIFY.qfl
│       ├── TEST_188004_NEW_ENROLLMENT.qfl
│       └── TEST_188005_COVERAGE_CHANGE.qfl
│
├── fixtures/
│   └── sample_uft/                     ← offline mock app for the e2e_sample demo
│       ├── screen_player.py
│       ├── generate_mock_screens.py
│       ├── screens/                    ← generated mock PNGs
│       └── data/
│           └── SAMPLE_TEST_000001.csv
│
├── tools/
│   └── qfl_to_pyautogui.py             ← CONVERTER — run this first
│
├── automation/                         ← generated code + framework live here
│   ├── or/
│   │   └── app_or.yaml                 ← Object Repository (fill in real regions)
│   ├── assets/
│   │   ├── images/                     ← reference PNG crops (one folder per screen)
│   │   ├── logs/                       ← test run logs
│   │   └── screenshots/                ← failure screenshots (auto-captured)
│   ├── core/                           ← framework engine (do not edit)
│   ├── common/                         ← shared Epic business logic
│   ├── tests/
│   │   ├── flows/                      ← generated flow files (one per QFL)
│   │   └── tasks/                      ← generated task stubs (one per screen)
│   └── pyproject.toml
│
└── docs/
    ├── HOW_TO_CONVERT.md               ← step-by-step conversion guide
    └── DEVELOPER_GUIDE.md              ← architecture deep-dive
```

---

## Installation

### macOS

```bash
# 1 — Install Homebrew Python 3.11+ and Tesseract
brew install tesseract

# 2 — Create a virtual environment (recommended)
python3 -m venv automation/.venv
source automation/.venv/bin/activate

# 3 — Install the package
pip install -e "automation/.[test]"

# 4 — Verify
pytest automation/tests/unit/ -v
```

**macOS permissions required** (one-time setup):
- `System Settings → Privacy & Security → Screen Recording` → enable Terminal
- `System Settings → Privacy & Security → Accessibility` → enable Terminal

Without these, screenshots and mouse clicks cannot interact with other app windows.

### Windows (Citrix VDI)

```powershell
# 1 — Install Python 3.11+ from https://python.org
# 2 — Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki
#     During install, note the path (e.g. C:\Program Files\Tesseract-OCR\tesseract.exe)

# 3 — Create a virtual environment
python -m venv automation\.venv
automation\.venv\Scripts\activate

# 4 — Install the package (include [windows] for Citrix window management)
pip install -e "automation\.[test,windows]"

# 5 — Point pytesseract at the binary
# Add to your .env or set in config.yaml:
#   tesseract_cmd: "C:/Program Files/Tesseract-OCR/tesseract.exe"

# 6 — Verify
pytest automation\tests\unit\ -v
```

---

## Where to Put Your UFT File

```
uft-2-pyautogui/
└── source/
    └── qfl/
        └── YOUR_TEST_FILE.qfl    ← drop it here
```

Naming convention (recommended):
```
TEST_<6-digit-ID>_<DESCRIPTION>.qfl
TEST_188001_MEMBER_LOGIN.qfl
TEST_188005_COVERAGE_CHANGE.qfl
```

---

## Where the Generated Files Land

Run the converter and it writes these files automatically:

```
automation/tests/flows/<screen>/
    flow_test_<id>_<name>.py     ← MAIN OUTPUT — edit this to fix TODOs

automation/tests/tasks/<screen>/
    task_<screen>.py             ← atomic action stubs — flesh these out
```

The terminal also prints a **YAML block** to copy into `automation/or/app_or.yaml`.

Full output map:

| What | Where |
|---|---|
| Source QFL file | `source/qfl/TEST_XXXXXX_NAME.qfl` |
| Generated flow (Python) | `automation/tests/flows/<screen>/flow_test_XXXXXX_name.py` |
| Generated task stub | `automation/tests/tasks/<screen>/task_<screen>.py` |
| Object Repository YAML | Printed to terminal — paste into `automation/or/app_or.yaml` |
| Reference PNG images | `automation/assets/images/<screen>/<element>.png` (you capture these) |
| Test data CSV | `automation/data/TEST_XXXXXX/TEST_XXXXXX.csv` (you create this) |
| Test logs | `automation/assets/logs/test_run.log` |
| Failure screenshots | `automation/assets/screenshots/` |
| OCR debug images | `automation/assets/ocr_debug/` |

---

## Converter Confidence Levels

Every translated statement receives a numeric confidence score (0–100). The
converter records this confidence in three places so reviewers can find the
weak spots at a glance:

1. A live visual report printed to the terminal after each conversion.
2. A compact summary embedded in the generated file's docstring.
3. A `# confidence: TIER (NN) - pattern` comment above each translated
   statement in the generated `.py` file. Disable with `--no-conf-comments`
   when you want a leaner output.

### Six confidence tiers

| Score | Tier | Meaning |
|---|---|---|
| 100 | **EXACT** | Perfect 1-to-1 — no changes needed |
| 90 | **HIGH** | Correct — add element to `app_or.yaml` |
| 75 | **GOOD** | `# TODO` to resolve — 1–2 min each |
| 55 | **MEDIUM** | Partial — dropdown / table logic manual |
| 30 | **LOW** | Placeholder — write manually |
| 10 | **FALLBACK** | Unrecognised — raw VBScript kept |

### EXACT (100) — auto-translated, zero review

| UFT VBScript | Generated Python |
|---|---|
| `DataTable("Col", dtLocalSheet)` | `row.require("Col")` |
| `WebEdit("Name").Set value` | `actions.type_text("screen.name", value)` |
| `WebButton("Name").Click` | `actions.click("screen.name")` |
| `WebElement("Name").Click` | `actions.click("screen.name")` |
| `WebLink("Name").Click` | `actions.click("screen.name")` |
| `Browser(…).Page(…).WebButton(…).Click` | `actions.click("screen.name")` |
| `Reporter.ReportEvent micPass, "label", msg` | `ctx.reporter.passed("label", msg)` |
| `Reporter.ReportEvent micFail, "label", msg` | `ctx.reporter.failed(…)` + `raise AssertionError` |
| `Reporter.ReportEvent micWarning/micInfo` | `ctx.reporter.warning/info(…)` |
| `Dim sVar` | silently removed |
| `Exit Function` after micFail | silently removed (dead code after raise) |
| `If … Then … End If` | `if …:` block with correct Python indentation |
| `ElseIf … Then` / `Else` | `elif …:` / `else:` |
| `sVar`, `bFlag`, `iCount` (Hungarian) | `var`, `flag`, `count` (snake_case) |
| `"text" & sVar & "more"` | `"text" + var + "more"` |
| `InStr(a, b) > 0` | `b in a` |
| `<>`, `And`, `Or`, `Not` | `!=`, `and`, `or`, `not` |
| Line continuation ` _` | joined to next line automatically |
| `For i = 1 To n / Next` | `for i in range(1, n+1):` |
| `For Each item In coll / Next` | `for item in coll:` |
| `Select Case var / Case val / End Select` | `if/elif/else` chain |
| `With obj / End With` | inline prefix expansion |
| `Set obj = Nothing` | `obj = None` |

### HIGH (90) — correct, add YAML entry

| UFT VBScript | Generated Python |
|---|---|
| `WebEdit("Name").GetROProperty("value")` | `ocr.read_target("screen.name_text")` |
| `WebCheckBox("Name").Set "ON"` | `actions.click("screen.name")  # sets to checked` |
| `WebElement("Name").FireEvent "onclick"` | `actions.click("screen.name")` |
| `WinButton("Name").Click` | `actions.click("screen.name")` |
| `WinEdit("Name").Set val` | `actions.type_text("screen.name", val)` |
| `JavaButton("Name").Click` | `actions.click("screen.name")` |
| `JavaEdit("Name").SetText val` | `actions.type_text("screen.name", val)` |
| `Dialog("Name").WinButton("OK").Click` | `actions.click("screen.ok")` |
| `SwfButton("Name").Click` | `actions.click("screen.name")` |
| `Browser(…).Sync` | `waits.wait_for_screen_stable(region=…)` |
| `Environment("Var")` | `os.environ.get("Var", "")` |

### GOOD (75) — `# TODO` to resolve, 1–2 min each

| UFT VBScript | Generated Python | Fix |
|---|---|---|
| `Wait 2` | `# TODO: Wait 2 — replace with:` `# waits.wait_for_screen_stable(…)` | Delete TODO line, uncomment wait |
| `Page("X").Exist(n)` in condition | `_screen_exists(or_repo, "x.header_label", timeout=n)` | Add anchor to `app_or.yaml` |
| `WebElement("X").Exist(n)` | `_screen_exists(or_repo, "screen.x", timeout=n)` | Add element to `app_or.yaml` |
| `WebRadioGroup("Name").Select val` | `actions.click(…)  # TODO: locate by OCR` | Find option via OCR |
| `Call FunctionName(args)` | `function_name(args)  # TODO: ensure imported` | Add import |
| `On Error Resume Next` | `try:  # On Error Resume Next` | Review except block |

### MEDIUM (55) — partial, manual work required

| UFT VBScript | Generated Python |
|---|---|
| `WebList("Name").Select val` | `actions.click(…)` + `# TODO: dropdown select` |
| `WinList("Name").Select val` | Same as above |
| `JavaList("Name").Select val` | Same as above |
| `WebElement("Name").SetAttribute attr, val` | `actions.type_text(…)  # TODO: SetAttribute` |
| `SystemUtil.Run path` | `subprocess.Popen([path])  # TODO` |
| `WebTable("Name").ChildItem(r,c).Click` | `# TODO: table cell click` |

### LOW (30) / FALLBACK (10) — written manually

| UFT VBScript | Placeholder |
|---|---|
| `Browser(…).Page(…).GetROProperty("title")` | `title = "TODO_window_title"` |
| `Window("Name").Activate` | `# TODO: bring window to foreground` |
| Complex VBScript expressions | `# TODO: translate expression: …` |
| Unrecognised pattern | `# TODO: translate → <raw VBScript>` |

### VBScript built-ins translated automatically

`Len`, `Left`, `Right`, `Mid`, `UCase`, `LCase`, `Trim`, `LTrim`, `RTrim`,
`Replace`, `CStr`, `CInt`, `CLng`, `CDbl`, `CSng`, `CBool`, `Now()`, `Date()`,
`Time()`, `Abs`, `Round`, `IsNull`, `IsEmpty`, `IsNumeric`, `InStr`

**Typical conversion result for the 5 sample QFL files: 93–98% EXCELLENT.**
EXACT + HIGH statements account for 80–85% of every generated file.

---

## Quick Start: Convert and Run in 5 Commands

```bash
# 1 — Convert a single QFL file
python3 tools/qfl_to_pyautogui.py --qfl source/qfl/TEST_188001_MEMBER_LOGIN.qfl

# 1b — …or convert every QFL in source/qfl/ in one shot
python3 tools/qfl_to_pyautogui.py --all

# 2 — Review and fix TODOs in the generated flow
open automation/tests/flows/member_login/flow_test_188001_member_login.py

# 3 — Run unit tests (no screen needed)
cd automation && pytest tests/unit/ -v

# 4 — Run the offline sample demo (no Epic needed)
python fixtures/sample_uft/screen_player.py &
pytest -m e2e_sample -v

# 5 — Run against real Epic (Windows/Citrix only)
pytest tests/flows/member_login/ -v
```

### Converter CLI flags

| Flag | Purpose |
|---|---|
| `--qfl PATH` | Convert one .qfl file |
| `--all [DIR]` | Convert every `*.qfl` in DIR (default: `source/qfl`) |
| `--screen NAME` | Override the inferred snake_case screen name (single-file mode) |
| `--out-dir DIR` | Write the flow file somewhere other than `automation/tests/flows/<screen>/` |
| `--dry-run` | Print the generated code + report without writing files |
| `--no-conf-comments` | Suppress the inline `# confidence: …` comments in the output |

---

## UFT → Python Quick Reference

| UFT VBScript | Generated Python |
|---|---|
| `DataTable("Col", dtLocalSheet)` | `row.require("Col")` |
| `WebEdit("Name").Set value` | `actions.type_text("screen.name", value)` |
| `WebButton("Name").Click` | `actions.click("screen.name")` |
| `Page("X").Exist(10)` | `_screen_exists(or_repo, "x.header_label", timeout=10)` |
| `Wait 2` | `waits.wait_for_screen_stable(region=(0,0,1280,800))` |
| `GetROProperty("innerText")` | `ocr.read_target("screen.element_text").text` |
| `Reporter.ReportEvent micPass` | `ctx.reporter.passed(label, message)` |
| `Reporter.ReportEvent micFail` | `ctx.reporter.failed(label, message)` + `raise AssertionError` |

---

## Troubleshooting

**`ConfigError: Reference image not found`**
→ The PNG crop for this element does not exist yet.
→ Take a screenshot, crop the element, save to `automation/assets/images/<screen>/<element>.png`.

**`OcrTextMismatchError`**
→ The OCR region coordinates are wrong, or preprocessing needs tuning.
→ Check `automation/assets/ocr_debug/` for the image Tesseract actually saw.

**`UiNotFoundError`**
→ The reference PNG does not match the current screen (resolution difference, zoom level, theme change).
→ Re-capture the PNG on the same machine and resolution as the CI runner.

**macOS: clicks do nothing on the target app**
→ Grant Accessibility permission: `System Settings → Privacy & Security → Accessibility → Terminal`.

**macOS: screenshots are blank or black**
→ Grant Screen Recording permission: `System Settings → Privacy & Security → Screen Recording → Terminal`.

**Windows: Citrix window not found**
→ Check `citrix_window_title` in `automation/or/app_or.yaml` matches the actual Citrix window title bar text.

**`ModuleNotFoundError: strenum`**
→ Run `pip install strenum` inside your virtual environment.

---

## Full Documentation

| Document | What it covers |
|---|---|
| [docs/HOW_TO_CONVERT.md](docs/HOW_TO_CONVERT.md) | Step-by-step conversion: from QFL file to running test |
| [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Every Python class and file explained, architecture diagrams |
