# Developer Guide — UFT to PyAutoGUI Framework

Architecture, class-by-class explanation, and platform behaviour.
Read this before editing the framework or adding new tests.

---

## 1. How the Whole Thing Works (Big Picture)

```
┌──────────────────────────────────────────────────────────────────┐
│  INPUT  source/qfl/  (5 UFT VBScript files)                      │
│  TEST_188001_MEMBER_LOGIN.qfl                                    │
│  TEST_188002_MEMBER_SEARCH.qfl                                   │
│  TEST_188003_COVERAGE_VERIFY.qfl                                 │
│  TEST_188004_NEW_ENROLLMENT.qfl                                  │
│  TEST_188005_COVERAGE_CHANGE.qfl                                 │
└───────────────────────────┬──────────────────────────────────────┘
                            │  python3 tools/qfl_to_pyautogui.py --all
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  CONVERTER  (tools/qfl_to_pyautogui.py)                          │
│  Reads VBScript line by line                                     │
│  Emits Python code + YAML object repository stub                │
└───────────┬──────────────────────────────────────────────────────┘
            │
            ▼
  output/flows/                         ← raw converter output
  ├── member_login/
  │   ├── flow_test_188001_member_login.py   ← review & fix TODOs
  │   └── task_member_login.py
  ├── member_search/
  │   ├── flow_test_188002_member_search.py
  │   └── task_member_search.py
  ├── coverage_verify/
  │   ├── flow_test_188003_coverage_verify.py
  │   └── task_coverage_verify.py
  ├── new_enrollment/
  │   ├── flow_test_188004_new_enrollment.py
  │   └── task_new_enrollment.py
  └── coverage_change/
      ├── flow_test_188005_coverage_change.py
      └── task_coverage_change.py
            │
            │  copy reviewed files to automation/tests/
            ▼
  automation/tests/flows/<screen>/      ← reviewed, run by pytest
  automation/tests/tasks/<screen>/      ← reviewed task stubs
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│  FRAMEWORK LAYERS  (pytest runs these)                         │
│                                                                 │
│  conftest.py                                                    │
│    └─ loads app_or.yaml → VisualOR (or_loader.py)              │
│    └─ builds Context(or_repo, reporter, logger)                 │
│                                                                 │
│  flow_test_XXXXXX.py  (converted from QFL)                     │
│    └─ row.require("MemberID")       reads CSV data             │
│    └─ _screen_exists(or_repo, "epic_home.header_label")        │
│    └─ actions.click("member_login.sign_in")                    │
│    └─ ocr.read_target("member_search.patient_banner_text")     │
│    └─ ctx.reporter.passed("Step 3", "MRN confirmed")           │
│                                                                 │
│  Core layer                                                     │
│    actions.click("member_login.sign_in")                       │
│      → or_loader: looks up ObjectSpec (image, region, conf)   │
│      → citrix:    focuses Citrix window (Windows) / no-op (Mac)│
│      → finder:    screenshot region → OpenCV match → (x, y)   │
│      → pyautogui: pyautogui.click(x, y)                        │
│                                                                 │
│    ocr.read_target("member_search.patient_banner_text")        │
│      → or_loader: looks up OCR target (region, preprocess)    │
│      → ImageGrab: PIL screenshot of region                     │
│      → preprocess: grayscale → upscale_2x → otsu_threshold    │
│      → Tesseract: pytesseract → extracted text + confidence    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Platform Behaviour — Mac vs Windows

The framework runs on both platforms. One layer (Citrix) behaves differently:

| Layer | macOS | Windows |
|---|---|---|
| `actions.click()` | PyAutoGUI — full | PyAutoGUI — full |
| `finder.py` OpenCV matching | Full | Full |
| `ocr.py` Tesseract OCR | Full (`brew install tesseract`) | Full (UB-Mannheim installer) |
| `waits.py` | Full | Full |
| `citrix.ensure_citrix_focused()` | Logs warning, returns immediately | Finds Citrix window, activates it |
| `citrix.get_session_state()` | Returns `ACTIVE` (safe default) | Checks actual Citrix session |
| `citrix.get_session_rect()` | Returns full screen `(0,0,w,h)` | Returns Citrix window rect |
| `pygetwindow` import | Skipped — not imported on Mac | Imported — used to find window |
| `pywinauto` import | Skipped — not imported on Mac | Optional — advanced window control |
| All 218 unit tests | Pass | Pass |

The platform check is one line in `citrix.py`:
```python
_IS_WINDOWS = platform.system() == "Windows"
```

All Citrix functions check this flag and skip gracefully on Mac.

**Mac is the right machine for:** writing flows, running the converter, unit testing,
code review, CI without a real screen.

**Windows (Citrix VDI) is the right machine for:** running tests against the real
Epic system inside a Citrix/VDI session.

---

## 3. Every Python File Explained

### `tools/qfl_to_pyautogui.py` — The Converter

**Purpose:** Reads a UFT `.qfl` VBScript file and writes Python PyAutoGUI code.

**Why it exists:** UFT uses VBScript, a Windows-only COM-based scripting language.
Python cannot run VBScript. The converter bridges the gap by parsing the
VBScript source text and emitting equivalent Python statements.

**Key functions:**

| Function | Role |
|---|---|
| `snake(name)` | PascalCase / CamelCase → snake_case. `MemberLogin` → `member_login` |
| `py_var(vb)` | Strip Hungarian notation prefix. `sUsername` → `username`, `bIsValid` → `is_valid` |
| `_translate_vbfunc(vb)` | Translate a VBScript built-in call: `Len`, `Left`, `Right`, `Mid`, `UCase`, `LCase`, `Trim`, `Replace`, type casts (`CStr`, `CInt`, `CDbl`), `Now()`, `Date()`, `Time()`, `Abs`, `Round`, `Environment("Var")` |
| `py_expr(vb)` | Translate a VBScript expression to Python. Handles string literals, booleans, numbers, `DataTable("Col")`, `&` concatenation, all `_translate_vbfunc` calls |
| `py_cond(vb)` | Translate a VBScript Boolean condition. Handles `InStr`, `.Exist(n)`, `IsNull`, `IsEmpty`, `IsNumeric`, `<>`, `And`, `Or`, `Not`, Hungarian variable names |
| `translate_stmt(line, screen)` → `StmtResult` | Translate one VBScript statement. Covers 40+ UFT patterns across Web, Win, Java, System, Reporter categories. Returns a `StmtResult` with `lines`, `confidence`, and `pattern` fields |
| `translate_function(lines, fn_name, screen)` → `FunctionResult` | Translate a full VBScript function body. Handles `If/End If`, `For/Next`, `For Each/Next`, `Do While/Until/Loop`, `Select Case`, `With/End With`, `On Error Resume Next/GoTo 0`. Collapses consecutive blank lines and suppresses dead `return` after `raise`. |
| `_build_confidence_report(frs)` | Compute confidence statistics across all `FunctionResult` objects. Returns `{total, avg, quality, by_tier, todos}` |
| `_format_report_text(report)` | Format the confidence report as a multi-line string for terminal display |
| `infer_screen(fn_name)` | Derive snake_case screen name from function name. Strips numeric IDs and prefixes (TEST, UFT, RUN). `TEST_188001_MemberLogin` → `member_login` |
| `build_flow_py(frs, qfl_stem, report)` | Render the complete flow Python file. Embeds the confidence summary in the docstring |
| `build_task_py(frs, qfl_stem)` | Render the task stub module |
| `build_or_yaml(frs)` | Render the YAML object repository snippet |
| `parse_qfl(path)` | Read the `.qfl` file and extract `(fn_name, body_lines)` for every Function/Sub. Falls back to treating the whole file as one pseudo-function when no Function/Sub wrapper is present (top-level scripts) |
| `_conf_comment(confidence, pattern)` | Render the inline `# confidence: TIER (NN) - pattern` line that is emitted above each translated statement. Controlled by the module-level `EMIT_CONF_COMMENTS` flag (toggled by `--no-conf-comments`) |
| `_convert_one(qfl_path, screen, out_dir, dry_run)` | Run the full pipeline for one QFL: parse → translate → report → render → write. Returns `(flow_path, avg_conf, total_stmts, quality)` so the batch driver can build a summary |
| `main()` | CLI entry point — handles `--qfl` (single) and `--all` (batch) modes, plus `--screen`, `--out-dir`, `--dry-run`, `--no-conf-comments` |

**Key data structures:**

```python
@dataclass
class StmtResult:
    lines:       list[str]   # generated Python lines
    confidence:  int         # 0–100 conversion confidence
    pattern:     str         # human label of the matched UFT pattern
    is_data_load: bool       # True → DataTable read (hoisted to data section)
    data_col:    str         # CSV column name (if is_data_load)
    data_var:    str         # Python variable name (if is_data_load)
    obj_name:    str         # logical OR name (e.g. "member_login.sign_in")
    obj_type:    str         # "button" | "input" | "label"
    ocr_name:    str         # OCR target name (e.g. "member_search.mrn_text")

@dataclass
class FunctionResult:
    fn_name:      str
    screen:       str
    data_columns: list[tuple[str, str]]       # (CSV_col, python_var)
    objects:      dict[str, str]              # logical_name → type
    ocr_targets:  list[str]                   # OCR target names
    body_lines:   list[str]                   # generated Python body
    stmt_report:  list[tuple[int, str, str]]  # (confidence, pattern, original_vbscript)
```

**Confidence tier system:**

Every statement gets one of six tiers. The converter records this confidence
in three places: the terminal report after each run, a compact summary block
inside the generated file's docstring, and an inline
`# confidence: TIER (NN) - pattern` comment above each translated statement
(suppress with `--no-conf-comments`).

| Score | Tier | When assigned |
|---|---|---|
| 100 | EXACT | Perfect 1-to-1: `WebButton.Click`, `WebEdit.Set`, `DataTable`, `Reporter`, `Dim`, `Set Nothing`, assignments |
| 90 | HIGH | Correct but needs an OR YAML entry: `GetROProperty`, `WebCheckBox.Set`, `WinButton`, `Browser.Sync`, `Environment` |
| 75 | GOOD | Translated with `# TODO` that takes 1–2 minutes: `Wait N`, `Page.Exist`, `WebRadioGroup`, `Call function`, `On Error` |
| 55 | MEDIUM | Partial — dropdown/table needs manual work: `WebList.Select`, `WinList.Select`, `WebTable.ChildItem`, `SystemUtil.Run` |
| 30 | LOW | Placeholder only: `Window.Activate`, `Browser.Page.GetROProperty("title")`, unknown properties |
| 10 | FALLBACK | Unrecognised pattern — raw VBScript kept as `# TODO: translate →` comment |

**Pattern coverage — 40+ UFT object types handled:**

*Web:* `WebEdit`, `WebButton`, `WebLink`, `WebElement`, `WebCheckBox`,
`WebRadioGroup`, `WebList`, `WebFile`, `WebTable`, `Browser.Page.*`,
`Browser.Sync`, `Page.Exist`

*Win / Java / Dialog:* `WinButton`, `WinEdit`, `WinList`, `JavaButton`,
`JavaEdit`, `JavaList`, `Dialog.WinButton`, `SwfButton`, `Window.Activate`

*System:* `SystemUtil.Run`, `SystemUtil.CloseProcessByName`, `MsgBox`,
`Call function`, `Set Nothing`, `Environment("Var")`

*Reporter:* `micPass`, `micFail`, `micWarning`, `micInfo`

*Block structures (each recorded as EXACT or HIGH and tagged with its own
inline confidence comment):* `If/ElseIf/Else/End If`, `For/Next`,
`For Each/Next`, `Do While/Until/Loop`, `Select Case/Case/Case Else/End Select`,
`With/End With`, `On Error Resume Next/GoTo 0`

*VBScript built-ins (translated inline):* `Len`, `Left`, `Right`, `Mid`,
`UCase`, `LCase`, `Trim`, `LTrim`, `RTrim`, `Replace`, `CStr`, `CInt`, `CLng`,
`CDbl`, `CSng`, `CBool`, `Now`, `Date`, `Time`, `Abs`, `Round`, `IsNull`,
`IsEmpty`, `IsNumeric`, `InStr`

Typical result for the 5 sample QFL files: **93–98% EXCELLENT** (EXACT + HIGH
statements account for 80–85% of every file).

---

### `automation/core/` — Framework Engine

Business logic never goes here. These files are the mechanical foundation.

---

#### `automation/core/actions.py`

**Purpose:** Single entry point for all UI interactions.

Every click, keystroke, and text input in a flow goes through here. Centralises
logging, Citrix focus guard, and retry logic so flow files stay clean.

**Key functions:**

| Function | What it does |
|---|---|
| `click(logical_name)` | OR lookup → Citrix focus → OpenCV locate → `pyautogui.click(x, y)` |
| `type_text(logical_name, text)` | Click the field first, then `pyautogui.typewrite(text)` |
| `hotkey(*keys)` | `pyautogui.hotkey()` — e.g. `hotkey("ctrl", "a")` |
| `press(key, presses)` | `pyautogui.press()` — used for arrow-key dropdown navigation |
| `set_or_repo(or_repo)` | Inject the loaded OR. Called once by `conftest.py` |

**Detailed click flow:**
```
actions.click("member_login.sign_in")
  Step 1: or_repo.get("member_login.sign_in") → ObjectSpec(image, region, confidence)
  Step 2: citrix.ensure_citrix_focused()       → Windows: focus Citrix / Mac: warning
  Step 3: finder.locate(spec) → Phase 1        → screenshot → OpenCV match → (x, y)
  Step 4: finder.locate(spec) → Phase 2        → re-locate (guards against animation)
  Step 5: pyautogui.click(x, y)                → OS-level mouse click
```

---

#### `automation/core/finder.py`

**Purpose:** Locates a UI element on screen using OpenCV template matching.

**Why it exists:** UFT used COM to identify elements by their DOM properties.
PyAutoGUI cannot do this. Instead, the framework takes a screenshot and finds
the element visually by matching it against a reference PNG crop.

**How it works:**
```
finder.locate(spec)
  Step 1: pyautogui.screenshot(region=(x, y, w, h))  → PIL Image of search area
  Step 2: cv2.matchTemplate(screenshot, reference_png) → confidence matrix
  Step 3: cv2.minMaxLoc(result)                        → peak match location
  Step 4: if peak < spec.min_confidence                → raise ConfidenceTooLowError
  Step 5: return Match(center_x, center_y, confidence)
```

**`min_confidence` guidelines:**

| Value | Use case |
|---|---|
| `0.95` | Pixel-perfect, stable UI with no Citrix compression |
| `0.82` | Recommended default — tolerates minor rendering differences |
| `0.70` | Loose — use when Citrix JPEG compression degrades images |

---

#### `automation/core/waits.py`

**Purpose:** Wait for UI state changes before acting.

**Why it exists:** Screens take time to load. Clicking before the element appears
causes false failures. Waits replace `Wait 2` bare sleeps with intelligent polling.

**Key functions:**

| Function | What it does |
|---|---|
| `wait_for_object_exists(spec, timeout)` | Polls every 0.5s until the element appears. **Raises `TimeoutError` on failure — never returns False.** |
| `wait_for_screen_stable(region, timeout)` | Takes repeated screenshots. Returns when two consecutive frames are identical. |

**Critical note:** Because `wait_for_object_exists` raises instead of returning
False, the generated flows use a wrapper for conditional checks:

```python
def _screen_exists(or_repo, anchor: str, *, timeout: float) -> bool:
    try:
        waits.wait_for_object_exists(or_repo.get(anchor), timeout=timeout)
        return True
    except Exception:
        return False
```

This helper is auto-generated into every flow file by the converter.

---

#### `automation/core/ocr.py`

**Purpose:** Read text from the screen using Tesseract OCR.

**Why it exists:** UFT used `GetROProperty("innerText")` to read text via COM.
PyAutoGUI cannot do this. OCR reads the text visually — the same way a human
would look at the screen.

**How it works:**
```
ocr.read_target("member_search.patient_banner_text")
  Step 1: Look up OCR target in app_or.yaml    → region, preprocess, min_confidence
  Step 2: PIL.ImageGrab.grab(bbox=region)       → screenshot of that area only
  Step 3: Preprocessing pipeline:
           grayscale     → single channel
           upscale_2x   → 2x resize (helps Tesseract read small fonts)
           otsu_threshold → binarise (black text, white background)
  Step 4: pytesseract.image_to_data(processed)  → word tokens + confidence scores
  Step 5: if mean_confidence < min_confidence    → OcrLowConfidenceError (retried 3x)
  Step 6: return OcrResult(text, confidence)
```

**Key functions:**

| Function | What it does |
|---|---|
| `read_target(name)` | Read text from a named OCR target defined in `app_or.yaml` |
| `assert_text(image, expected, mode)` | Assert extracted text matches expected. Modes: `"contains"`, `"equals"`, `"regex"` |

**Preprocessing pipeline options** (set in `preprocess:` list in YAML):

| Step | Effect | When to use |
|---|---|---|
| `grayscale` | Convert to single channel | Always use first |
| `upscale_2x` | 2× resize | Small fonts, Citrix compression |
| `upscale_3x` | 3× resize | Very small fonts (under 10pt) |
| `otsu_threshold` | Auto binarise | Most cases — dark text on light background |
| `adaptive_threshold` | Local binarise | Uneven or gradient backgrounds |
| `invert` | Flip black/white | Light text on dark background |
| `denoise` | Remove JPEG noise | Heavy Citrix compression artifacts |
| `deskew` | Correct rotation | Misaligned or rotated text |
| `dilate` | Thicken strokes | Thin or faint fonts |
| `erode` | Remove noise pixels | Noisy background |

On failure, Tesseract debug images are saved to `automation/assets/ocr_debug/`
so you can see exactly what the OCR engine received.

---

#### `automation/core/or_loader.py`

**Purpose:** Reads `app_or.yaml` and provides `or_repo.get("screen.element")`.

**Why it exists:** All element definitions (image path, region, confidence) live
in a central YAML file rather than scattered across Python code. Change an
element's coordinates in one place and all tests pick up the change automatically.

```yaml
# app_or.yaml
objects:
  - name: member_login.sign_in      # logical name used in Python
    image: member_login/sign_in.png  # relative to automation/assets/images/
    region: [800, 600, 200, 60]      # [x, y, width, height] in screen pixels
    min_confidence: 0.82
```

```python
# Python usage
spec = or_repo.get("member_login.sign_in")
# spec.image_path     → Path("automation/assets/images/member_login/sign_in.png")
# spec.region         → (800, 600, 200, 60)
# spec.min_confidence → 0.82
```

---

#### `automation/core/citrix.py`

**Purpose:** Ensure the Citrix/VDI window is in the foreground before every action.

**Why it exists:** On Windows, PyAutoGUI clicks land on whatever window is
currently active. If the test runner's terminal is in front, clicks go to the
terminal instead of Epic. The Citrix guard prevents this.

**Platform behaviour:**

| Method | macOS | Windows |
|---|---|---|
| `ensure_citrix_focused()` | Logs warning, returns immediately | Finds Citrix window by title, activates it, waits up to 5s |
| `get_session_state()` | Returns `SessionState.ACTIVE` | Checks if Citrix window is minimised → RECONNECTING, else ACTIVE |
| `get_session_rect()` | Returns `(0, 0, screen_w, screen_h)` | Returns actual Citrix window `(left, top, width, height)` |

Configure the Citrix window title in `app_or.yaml`:
```yaml
citrix_window_title: "Citrix Viewer"   # must match the actual title bar text
```

---

#### `automation/core/config.py`

**Purpose:** Single source of truth for all configuration values.

Loads `config.yaml` and merges with environment variable overrides.
All framework modules call `get_config()` rather than reading config files directly.

```bash
# Override without editing files
AUTOMATION_LOG_LEVEL=DEBUG pytest automation/tests/unit/ -v
AUTOMATION_OR_PATH=or/my_or.yaml pytest automation/tests/flows/ -v
```

---

#### `automation/core/exceptions.py`

**Purpose:** All custom error types with structured fields for triage.

| Exception | When raised |
|---|---|
| `ConfigError` | OR YAML missing, bad region, image file not found |
| `UiNotFoundError` | Element not found in region within timeout |
| `ConfidenceTooLowError` | Best OpenCV match below `min_confidence` |
| `AmbiguousMatchError` | Two or more elements matched — tighten region |
| `TimeoutError` | `wait_for_object_exists` exceeded timeout |
| `OcrLowConfidenceError` | Tesseract confidence below threshold after retries |
| `OcrTextMismatchError` | Text extracted but does not match expected value |
| `CitrixNotFocusedError` | Citrix window not found or could not be activated |
| `CitrixSessionError` | Citrix session disconnected or locked |

Every exception carries `logical_name`, `screen`, and `details` for structured
log messages and failure screenshots.

---

#### `automation/core/retries.py`

**Purpose:** `@retry` decorator with exponential backoff and failure screenshots.

```python
@retry(attempts=3, base_delay=0.5)
def fragile_step():
    actions.click("epic_home.coverage_tab")
```

Used internally by `ocr.py`. Can be applied to any flow step that is
susceptible to transient timing failures.

---

#### `automation/core/logging_setup.py`

**Purpose:** Configures Loguru for structured, coloured log output.

Writes to both the console and `automation/assets/logs/test_run.log`.
All framework modules use `from loguru import logger`.

---

#### `automation/core/screen.py`

**Purpose:** Screen-level utilities — full screenshot, current screen resolution,
scroll actions.

---

### `automation/common/` — Shared Business Layer

Epic-specific logic shared across multiple tests. Unlike `core/`, these files
know what Epic is.

---

#### `automation/common/__init__.py` → `Context`

**Purpose:** The `Context` dataclass is the single object passed to every flow function.

```python
@dataclass
class Context:
    or_repo:  VisualOR         # look up UI elements
    row:      DataRow          # read test data from CSV
    logger:   Logger           # write to log file
    reporter: ReporterAdapter  # record pass/fail events
    extra:    dict             # arbitrary flow-specific state
```

Every converted flow function has this signature:
```python
def flow_test_188001_member_login(ctx: Context, row: DataRow) -> None:
```

---

#### `automation/common/data.py` → `DataRow`

**Purpose:** Wraps one CSV row with safe, descriptive column access.

```python
row = DataRow(suite="TEST_188001", jira="TEST-001", payload=csv_dict)

member_id = row.require("MemberID")   # raises DataError with column name if missing
last_name  = row.get("LastName", "")  # returns default if missing — no error
```

`DataRow` is frozen after creation — no accidental mutation during a test.
`iter_rows_csv(path)` iterates all rows in a CSV as `DataRow` objects.

---

#### `automation/common/reporting_legacy.py` → `ReporterAdapter`

**Purpose:** Maps UFT-style `micPass`/`micFail` calls to Python pass/fail tracking.

The converter translates `Reporter.ReportEvent micPass, "Step 1", msg` to
`ctx.reporter.passed("Step 1", msg)`. `ReporterAdapter` collects these events
so `assert not reporter.has_failures()` at the end of each test works correctly.

```python
reporter.passed("Step 1", "Login screen appeared")
reporter.failed("Step 2", "Sign-in button not found")
reporter.has_failures()  # True
reporter.events          # list of all recorded events
reporter.reset()         # clear all events for next test case
```

---

#### `automation/common/domain.py`

**Purpose:** Epic-specific business logic shared across tests.

| Function | What it does |
|---|---|
| `parse_member_id(mrn)` | Validate and normalise a 7-digit MRN |
| `format_date_for_epic(date)` | Format a date as `MM/DD/YYYY` (Epic's required format) |
| `normalize_coverage_type(value)` | Map raw string to canonical coverage type |
| `normalize_plan_tier(plan_name)` | Extract HMO / PPO / EPO tier from plan name |
| `normalize_change_reason(reason)` | Validate a coverage change reason code |

---

#### `automation/common/elements.py`

**Purpose:** Registry of shared element specs used on multiple screens
(e.g. global navigation bar, common error dialogs that appear on every screen).

---

#### `automation/common/element_utils.py`

**Purpose:** Utility functions for element names — normalisation, fuzzy matching,
best-candidate selection. Used internally by `elements.py`.

---

#### `automation/common/steps.py`

**Purpose:** BDD-style step registry. Lets you register reusable high-level steps
by name and execute them by string matching.

```python
@step("login as {username}")
def step_login(ctx, username, password):
    actions.type_text("epic_login.username", username)
    ...

steps.execute("login as jsmith", ctx, password="secret")
```

---

#### `automation/common/suite.py` / `suite_source.py`

**Purpose:** Suite-level setup and teardown — login once at the start of a test
suite, logout at the end. Avoids re-logging in for every single parametrized
test case.

---

#### `automation/common/utils.py`

**Purpose:** General-purpose utilities used across the project.

| Function | What it does |
|---|---|
| `normalize_name(s)` | Strip whitespace, collapse spaces, fold Unicode to ASCII |
| `mask_sensitive(value, visible_tail)` | Mask a password/MRN — shows only last N characters |
| `parse_date(s)` | Parse `MM/DD/YYYY`, ISO, or `YYYYMMDD` to a `date` object |
| `format_date_epic(d)` | Format a `date` as `MM/DD/YYYY` |
| `safe_int(value, default)` | Cast to int without raising on failure |
| `safe_float(value, default)` | Cast to float without raising |
| `retry_with_jitter(fn, attempts)` | Retry a callable with randomised backoff |

---

#### `automation/common/constants.py`

**Purpose:** Shared constants — default timeouts, date formats, coverage types,
plan tiers. Frozen (immutable) after module load.

---

#### `automation/common/poms/` — Page Object Model Constants

Each file defines **string constants** for one Epic screen.
No code, no logic — just named strings.

```python
# automation/common/poms/epic_login.py
SCREEN         = "epic_login"
HEADER_LABEL   = "epic_login.header_label"
USERNAME_FIELD = "epic_login.username_field"
PASSWORD_FIELD = "epic_login.password_field"
LOGIN_BUTTON   = "epic_login.login_button"
```

**Why they exist:** Instead of typing `"epic_login.login_button"` in ten different
flow files, you import the constant. If the OR name ever changes, you update it
in one file and all tests pick up the change.

| POM file | Screen it represents |
|---|---|
| `epic_login.py` | Epic Hyperdrive login screen |
| `epic_home.py` | Epic home / dashboard |
| `member_search.py` | Member search bar |
| `member_chart.py` | Opened member chart |
| `member_demographics.py` | Demographics tab |
| `enrollment.py` | New enrollment dialog |
| `plan_selection.py` | Plan selection screen |
| `coverage_change.py` | Coverage change dialog |
| `dependent_management.py` | Dependent management screen |
| `notes.py` | Notes / comments panel |
| `confirmation.py` | Confirmation dialogs |
| `error_dialog.py` | Error and warning dialogs |
| `sample_login.py` / `sample_home.py` / `sample_coverage.py` | Offline sample fixture |

---

### `automation/or/` — Object Repository

#### `app_or.yaml` — Most Important File to Edit After Conversion

Maps every logical element name to a reference PNG, screen region, and confidence
threshold. One entry per clickable or readable UI element.

```yaml
objects:
  - name: epic_login.login_button     # "screen.element" naming convention
    screen: epic_login
    type: button                       # button | input | label | tab | dropdown
    image: epic_login/login_button.png # path relative to automation/assets/images/
    region: [800, 600, 200, 60]        # [x, y, width, height] in screen pixels
    min_confidence: 0.82               # 0.0–1.0 — OpenCV match strictness

ocr_targets:
  - name: epic_home.mrn_text
    screen: epic_home
    region: [20, 98, 500, 30]
    expected_pattern: "MRN:\\s*\\d{7}"
    preprocess: [grayscale, upscale_2x, otsu_threshold]
    min_confidence: 0.60
```

#### `sample_or.yaml`

Pre-filled OR for the offline sample fixture. Used by `pytest -m e2e_sample`.
All PNG paths point to real reference images in `automation/assets/images/sample/`.

#### `SCHEMA.md`

Documents every allowed field and its accepted values.

---

### `automation/tests/` — Test Layer

#### `conftest.py` (session-level)

pytest session fixtures shared across every test.

| Fixture | What it provides |
|---|---|
| `or_repo` | Loads `app_or.yaml` into a `VisualOR` and makes it available to all tests |
| `citrix` | Checks Citrix is connected (Windows) / no-op (Mac) |
| Autouse failure hook | Captures a failure screenshot automatically when any test fails |

#### `tests/flows/conftest.py` (flow-level)

| Fixture | What it provides |
|---|---|
| `or_repo` | Loads `sample_or.yaml` for offline sample tests |
| `screen_player` | Skips the test if the mock Epic window is not running |

#### `tests/flows/<screen>/flow_test_XXXXXX.py`

The reviewed UFT test logic — copied here from `output/flows/<screen>/` after
all `# TODO` items have been resolved. Structure:

```python
# 1. Imports
from automation.core import actions, ocr, waits

# 2. _screen_exists helper — auto-generated, do not remove
def _screen_exists(or_repo, anchor, *, timeout): ...

# 3. The flow function
def flow_test_188001_member_login(ctx: Context, row: DataRow) -> None:
    or_repo = ctx.or_repo

    # Data section — reads CSV columns
    username = row.require("Username")
    password = row.require("Password")

    # Steps — translated from VBScript
    if not _screen_exists(or_repo, "epic_login.header_label", timeout=15):
        ctx.reporter.failed("Step 1", "Login screen not found")
        raise AssertionError("Step 1 failed")
    ctx.reporter.passed("Step 1", "Login screen visible")

    actions.type_text("member_login.username", username)
    waits.wait_for_screen_stable(region=(0, 0, 1280, 800))
    ...
```

#### `tests/tasks/<screen>/task_<screen>.py`

Atomic action stubs — one function per UI element. Also output of the converter.
Flesh these out with element-specific sequences when you need reusable sub-steps
that multiple flows share.

#### `tests/unit/`

Fast unit tests for the framework itself. No screen required. Tests cover:
`DataRow`, `domain.py`, OCR preprocessing pipeline, `ReporterAdapter`, POM
constants, `element_utils`, `steps`, `utils`, `constants`.

Run these first on any machine to confirm the installation is correct:
```bash
pytest automation/tests/unit/ -v
# Expected result: 218 passed, 4 skipped
# (4 skipped = Tesseract binary integration tests — safe to ignore until tesseract is installed)
```

---

## 4. Key Rules — Do Not Break These

| Rule | Why |
|---|---|
| No `pyautogui.click(x, y)` in flow/task files | Raw coordinates break when resolution changes — always use `actions.click("logical.name")` |
| No `time.sleep()` in flow/task files | Only `waits.py` may sleep — so all timeouts are consistent and logged |
| No hardcoded pixel coordinates in Python | Regions belong in `app_or.yaml` — not in code |
| No real PHI in test data CSV files | Synthetic data only — enforce with git-secrets pre-commit hook |
| One `or_repo.get()` per action | Never cache coordinates between actions — the screen may have scrolled |
| `wait_for_object_exists` raises, never returns False | Always wrap in `_screen_exists()` for conditional checks |

---

## 5. Adding a New Test End to End

```
Step 1: Drop QFL file       source/qfl/TEST_XXXXXX_MY_TEST.qfl

Step 2: Run converter        # single file:
                             python3 tools/qfl_to_pyautogui.py \
                                 --qfl source/qfl/TEST_XXXXXX_MY_TEST.qfl
                             # or convert all at once:
                             python3 tools/qfl_to_pyautogui.py --all
                             Output lands in output/flows/<screen>/

Step 3: Fix # TODO items    output/flows/<screen>/flow_test_XXXXXX_my_test.py
         - Replace Wait N comments with waits.wait_for_screen_stable(...)
         - Fix dropdown selects to use arrow-key navigation
         - Add page anchor entries to app_or.yaml

Step 3b: Copy to automation  cp output/flows/<screen>/flow_test_XXXXXX_my_test.py \
                                    automation/tests/flows/<screen>/
                              cp output/flows/<screen>/task_<screen>.py \
                                    automation/tests/tasks/<screen>/

Step 4: Capture PNGs        automation/assets/images/<screen>/<element>.png
         - python3 -c "import pyautogui; pyautogui.screenshot('full.png')"
         - Crop each element and save

Step 5: Fill YAML regions   automation/or/app_or.yaml
         - Paste the converter's YAML output
         - Update region: [x, y, w, h] for every entry

Step 6: Create CSV          automation/data/TEST_XXXXXX/TEST_XXXXXX.csv
         - One row per test case
         - Column names must match row.require("ColName") calls

Step 7: Write test module   automation/tests/flows/<screen>/test_XXXXXX.py
         - See HOW_TO_CONVERT.md Part 9 for the template

Step 8: Run unit tests      pytest automation/tests/unit/ -v

Step 9: Run the flow        pytest automation/tests/flows/<screen>/ -v
```

---

## 6. Exception Hierarchy

```
AutomationError
├── ConfigError               OR YAML missing, bad region, image not found
├── UiNotFoundError           Element not found within timeout
├── AmbiguousMatchError       Two+ elements matched — tighten region or raise confidence
├── ConfidenceTooLowError     Best OpenCV match below min_confidence
├── TimeoutError              wait_for_object_exists exceeded timeout
├── OcrLowConfidenceError     Tesseract confidence below threshold after retries
├── OcrTextMismatchError      Text extracted but doesn't match expected
├── CitrixNotFocusedError     Citrix window not found or could not be activated
└── CitrixSessionError        Citrix session disconnected or locked
```

Every exception carries `logical_name`, `screen`, and `details` for structured
log messages and consistent failure screenshots.
