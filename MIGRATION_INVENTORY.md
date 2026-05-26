# UFT One → PyAutoGUI + pytesseract Migration Inventory

**Suite:** UFT_E2E_Hyperdrive_Automation  
**Target runtime:** Epic Hyperdrive inside Citrix / VDI  
**Migration pass:** Initial discovery  
**Date:** 2026-05-25

---

## 1. Classification Table

| UFT File | Classification | Target Python Location | Notes |
|---|---|---|---|
| `FunctionLibrary/<CommonLib1>.qfl` | `framework-helper` | `automation/framework/element_resolution.py` | Element lookup, locator strategies → becomes region-based image anchoring |
| `FunctionLibrary/<CommonLib2>.qfl` | `framework-helper` | `automation/framework/utils.py` | General utility wrappers; expect string/date/format helpers |
| `FunctionLibrary/CommonFunctions.qfl` | `framework-helper` | `automation/framework/waits.py` + `automation/framework/retries.py` | Waits, retries, logging — highest-risk file; likely contains implicit `Wait`/`WaitProperty` calls that must become explicit polling |
| `FunctionLibrary/Constants.qfl` | `framework-helper` | `automation/config/constants.py` | Global constants → Python module-level constants or `enum`; review for hard-coded timeouts and paths |
| `FunctionLibrary/<DataLib>.qfl` | `framework-helper` | `automation/framework/data_reader.py` | Excel/CSV read-write → `openpyxl` + `csv`; preserve column-name contract for data-driven flows |
| `FunctionLibrary/<DomainSpecific>_Functions.qfl` | `framework-helper` | `automation/framework/domain_helpers.py` | Domain-specific shared business logic; keep thin and reusable |
| `FunctionLibrary/ReportingFunctions.qfl` | `framework-helper` | `automation/framework/reporter.py` | UFT HTML report wrappers → `pytest` + `Allure` or custom HTML; screenshot attachment is mandatory |
| `FunctionLibrary/StepDefinitions.qfl` | `framework-helper` | `automation/framework/step_definitions.py` | BDD-style step glue → `pytest-bdd` or plain fixture wrappers depending on chosen runner |
| `FunctionLibrary/<SuiteName>_Functions.qfl` | `framework-helper` | `automation/framework/suite_helpers.py` | Suite-level orchestration glue; review for setup/teardown logic |
| `FunctionLibrary/<SuiteName>_<DataSource>.qfl` | `framework-helper` | `automation/framework/suite_data_helpers.py` | Suite + data-source coupling; likely thin; may collapse into `data_reader.py` |
| `POM/<Screen1>.qfl` | `screen-anchor` | `automation/screens/screen1.py` | Visual Object Repository entry → becomes region definitions + reference image paths |
| `POM/<Screen2>.qfl` | `screen-anchor` | `automation/screens/screen2.py` | Same pattern as Screen1 |
| `POM/ImagePOM/` (image assets) | `screen-anchor` | `automation/assets/images/` | Raw `.png` reference crops; must be re-captured at target Citrix DPI |
| `FunctionLibrary/BusinessFunctions/<TEST_CASE_ID_001>.qfl` | `business-flow` | `automation/tests/test_<id_001>.py` | One pytest module per business flow |
| `FunctionLibrary/BusinessFunctions/<TEST_CASE_ID_002>.qfl` | `business-flow` | `automation/tests/test_<id_002>.py` | — |
| `Data/<DataSource1>/` | `data` | `automation/data/<datasource1>/` | Preserve directory structure; convert `.xlsx` paths to config constants |
| `Data/<DataSource2>/` | `data` | `automation/data/<datasource2>/` | — |
| `DriverScript/TestCaseDriverScript/` | `runner` | `automation/runner/` + `pytest.ini` | UFT driver → `pytest` entry point with parametrize or suite markers |

---

## 2. Business Flow Map

Each row below infers purpose from the JIRA-style numeric suffix and standard Hyperdrive workflows. Confidence reflects how unambiguously the ID maps to a known workflow without seeing file contents.

| Test Case File | Inferred Business Purpose | Confidence |
|---|---|---|
| `<TEST_CASE_ID_001>.qfl` | **Member Enrollment — New Member Add**: opens Hyperdrive member record, navigates to enrollment panel, enters coverage effective date and plan selection, confirms save | `medium` |
| `<TEST_CASE_ID_002>.qfl` | **Coverage Change — Plan Modification**: locates existing member, initiates coverage change transaction, selects new plan, validates effective date rules, submits | `medium` |

> **Note:** Replace placeholder IDs with actual `TEST_188xxx` identifiers. Confidence will be upgraded to `high` once file names are confirmed and contents reviewed.

---

## 3. Cross-Cutting Concerns

Every concern listed here must be absorbed by the framework layer. Business flows must not re-implement any of these.

### 3.1 Citrix Focus and Session-State Detection
- Citrix windows can lose input focus silently between actions.
- Before any mouse or keyboard action, the framework must assert that the Citrix ICA / MFRMVIEWER window is foreground-focused.
- A `CitrixSessionGuard` context manager should wrap every action block; if focus is lost it re-asserts, waits up to a configurable timeout, and raises `SessionLostError` if recovery fails.
- Session state enum: `ACTIVE | RECONNECTING | DISCONNECTED | LOCKED`.

### 3.2 Image-Anchor Matching with Bounded Regions
- Full-screen `pyautogui.locateOnScreen` is too slow and DPI-sensitive on Citrix.
- Every screen anchor must define a named `Region(x, y, w, h)` that constrains the search area.
- Regions are stored in screen definition files and validated on framework startup via a region-sanity screenshot.
- Match confidence threshold must be configurable per anchor (default `0.85`).
- On failure: log the expected anchor name, the region bounds, and save a cropped region screenshot.

### 3.3 OCR Validation Wrapper
- `pytesseract.image_to_string` is sensitive to font rendering, anti-aliasing, and Citrix JPEG compression artifacts.
- The wrapper must: (1) crop to a tight bounding box, (2) apply a preprocessing pipeline (grayscale → threshold → optional resize), (3) normalize whitespace in the extracted string, (4) retry up to N times with small waits between attempts.
- Fallback: if OCR confidence is below threshold after retries, capture a screenshot and raise `OCRAssertionError` with the raw image path attached to the report.
- Epic-specific: Hyperdrive uses a custom sans-serif font at small point sizes; Tesseract `--psm 7` (single line) or `--psm 6` (block) modes must be benchmarked; `--oem 3` (LSTM) preferred.

### 3.4 Explicit Waits
- UFT `WaitProperty`, `Wait`, and `Exist` calls must be replaced with polling loops capped by a timeout.
- Standard wait predicates to implement: `wait_for_image(anchor, region, timeout)`, `wait_for_image_gone(anchor, region, timeout)`, `wait_for_screen_stable(region, timeout, threshold)`, `wait_for_spinner_gone(spinner_anchor, region, timeout)`.
- All waits must accept a `poll_interval` parameter (default `0.5 s`) and log elapsed time on success.
- No `time.sleep` calls permitted in business flows — only in framework wait primitives.

### 3.5 Time-Bounded Retries with Screenshot-on-Failure
- Retry decorator `@retry(max_attempts, exceptions, screenshot=True)` wraps any action prone to transient Citrix lag.
- On every failed attempt: capture full Citrix window screenshot, stamp with attempt number and timestamp, attach to Allure/report.
- Final failure raises the original exception with all attempt screenshots listed in the message.

### 3.6 Deterministic Failure Classification
- All framework exceptions must be subclasses of `AutomationError` with a `FailureCategory` enum:
  - `SESSION_LOST` — Citrix disconnected or locked
  - `ELEMENT_NOT_FOUND` — image anchor not located in region within timeout
  - `OCR_ASSERTION_FAILED` — extracted text does not match expected
  - `NAVIGATION_TIMEOUT` — screen transition did not complete in time
  - `UNEXPECTED_DIALOG` — modal or banner intercepted the flow
  - `DATA_ERROR` — test data missing or malformed
  - `FRAMEWORK_ERROR` — internal framework failure
- Category must be logged and stored in the test result for triage dashboards.

### 3.7 Data-Driven Test Parameters
- `data_reader.py` must expose a `load_cases(source, sheet_or_file)` function returning a list of `dict`.
- `pytest.mark.parametrize` (or `pytest-bdd` examples) drives test execution per row.
- Sensitive fields (SSN, DOB) must be masked in logs and reports.
- Data files must never be committed with real PHI; fixture files use synthetic data.

### 3.8 Reporting
- `ReportingFunctions.qfl` UFT HTML reports → `Allure` report with per-step screenshots.
- Every framework action logs a structured step: `action`, `anchor`, `region`, `elapsed_ms`, `status`.
- On failure: report includes failure category, last screenshot, OCR raw output (if applicable), retry history.
- `reporter.py` must be callable independently of `pytest` for smoke-test runs.

### 3.9 Test Orchestration / Runner
- `DriverScript/TestCaseDriverScript/` → `pytest.ini` + `conftest.py` with session-scoped Citrix session fixture.
- Test selection by marker: `@pytest.mark.smoke`, `@pytest.mark.regression`, `@pytest.mark.suite_<name>`.
- Parallel execution via `pytest-xdist` is **not safe** on a single Citrix session; disable by default, enable only when multi-session VDI provisioning is confirmed.
- Pre-run health check: assert Citrix window visible, assert Epic Hyperdrive login screen reachable.

---

## 4. Proposed Python Package Layout

```
automation/
│
├── assets/
│   └── images/                  # Reference PNG crops for image anchoring
│       ├── <screen1>/           # One subdirectory per screen
│       └── <screen2>/
│
├── config/
│   ├── constants.py             # Migrated from Constants.qfl; timeouts, thresholds, paths
│   └── settings.py              # Environment-specific config (loaded from env vars or .env)
│
├── data/
│   ├── <datasource1>/           # Test data files (synthetic / masked)
│   └── <datasource2>/
│
├── framework/
│   ├── __init__.py
│   ├── citrix_guard.py          # CitrixSessionGuard, focus assertion, session state enum
│   ├── data_reader.py           # Excel + CSV loader; load_cases() interface
│   ├── domain_helpers.py        # Migrated from <DomainSpecific>_Functions.qfl
│   ├── element_resolution.py    # Region definitions, image anchor lookup helpers
│   ├── errors.py                # AutomationError hierarchy, FailureCategory enum
│   ├── ocr.py                   # pytesseract wrapper with preprocessing, retries, fallback
│   ├── reporter.py              # Allure step logger; screenshot attachment; summary builder
│   ├── retries.py               # @retry decorator; screenshot-on-attempt logic
│   ├── step_definitions.py      # BDD-style step glue (mirrors StepDefinitions.qfl)
│   ├── suite_helpers.py         # Suite-level setup/teardown glue
│   ├── utils.py                 # String, date, format helpers from <CommonLib2>.qfl
│   └── waits.py                 # Explicit wait predicates; no bare time.sleep
│
├── screens/
│   ├── __init__.py
│   ├── base_screen.py           # Abstract base: region map, common navigation helpers
│   ├── <screen1>.py             # Migrated from POM/<Screen1>.qfl; region + anchor defs
│   └── <screen2>.py             # Migrated from POM/<Screen2>.qfl
│
├── tests/
│   ├── conftest.py              # Session fixture: Citrix launch, Epic login, teardown
│   ├── test_<id_001>.py         # Business flow 001; thin orchestration only
│   └── test_<id_002>.py         # Business flow 002
│
├── runner/
│   ├── __init__.py
│   └── health_check.py          # Pre-run assertions: Citrix window, Epic reachability
│
├── pytest.ini                   # Markers, default options, Allure output dir
└── requirements.txt             # pyautogui, pytesseract, pillow, openpyxl, allure-pytest, pytest
```

---

## 5. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | **Citrix JPEG compression degrades image-match confidence** | High | High | Capture reference images inside the Citrix session at runtime resolution; tune per-anchor confidence thresholds; use region cropping to reduce noise surface area |
| 2 | **Hidden `Wait` / `sleep` calls in `CommonFunctions.qfl` replaced naively** | High | High | Audit every `Wait`/`WaitProperty`/`Sync` call during migration; replace with explicit polling predicates; run timing regression after first migration pass |
| 3 | **Epic Hyperdrive modal dialogs / banners intercept mid-flow actions** | High | High | Implement a background modal-watcher thread (or pre-action hook) that detects and dismisses known dialogs before each step executes |
| 4 | **DPI scaling differs between capture machine and execution machine** | Medium | High | Standardize Citrix session resolution and DPI in VDI policy; validate reference images on execution host before CI run; store DPI metadata alongside each image asset |
| 5 | **OCR failures on small-point Epic fonts** | Medium | High | Benchmark Tesseract PSM modes on representative Epic screens; apply 2× upscale + sharpening preprocessing; maintain a per-field OCR config map |
| 6 | **Citrix session loss during long-running regression suites** | Medium | High | Implement `CitrixSessionGuard` with auto-reconnect; wrap every test with a session health assertion in `conftest.py` fixture teardown |
| 7 | **Screen coordinate drift after Epic or Citrix upgrades** | Medium | Medium | Store anchor images in version-tagged subdirectories; add a validation step in CI that re-confirms all anchors against a reference screenshot before running tests |
| 8 | **License / SSO prompts appearing on cold-start or after session timeout** | Medium | Medium | Detect and handle known Epic license/SSO screens in the session setup fixture; log occurrences as warnings, not failures |
| 9 | **`StepDefinitions.qfl` coupling to UFT reporter API** | Low | Medium | Map each UFT reporter call to Allure step decorator equivalents during `step_definitions.py` migration; do not port the API shape, only the semantic intent |
| 10 | **PHI in test data files committed to version control** | Low | Critical | Gate repository with `git-secrets` or `detect-secrets` pre-commit hook; replace all real member data with synthetic data generated by a data-factory utility before first commit |

---

## 6. Open Questions

- **Q1 — Exact test case IDs:** What are the actual `TEST_188xxx` identifiers in scope for this migration pass? The business flow map and classification table use placeholders; the answers will determine test module naming and BDD step reuse.

- **Q2 — Screen inventory:** Which Epic Hyperdrive screens are exercised across the in-scope test cases? The POM file count and screen names determine the size of the `screens/` package and the image-capture effort.

- **Q3 — Citrix session provisioning:** Is a single shared Citrix session used across all tests, or is a fresh session provisioned per test run? This determines whether the `conftest.py` session fixture is `scope="session"` or `scope="function"`.

- **Q4 — Target execution host:** What OS, Python version, and Tesseract version are installed on the execution host? This constrains `requirements.txt` and OCR preprocessing parameters.

- **Q5 — Reporting consumer:** Where must test results be published — local Allure HTML only, or also a CI system (Jenkins, GitHub Actions) or a dashboard (Zephyr, Xray)? This determines the reporter integration depth.

- **Q6 — Data sensitivity policy:** Are existing `.xlsx` test data files safe to commit to the migration repository, or must a synthetic data generation step be built before any data file is versioned?

- **Q7 — `CommonFunctions.qfl` wait strategy:** Does `CommonFunctions.qfl` rely on UFT's built-in Smart Identification or Checkpoint objects in addition to explicit waits? If so, those must be individually re-mapped since no direct PyAutoGUI equivalent exists.

- **Q8 — Parallelism requirement:** Is there a requirement to run multiple test cases concurrently? If yes, multi-session VDI provisioning must be scoped and `pytest-xdist` safety evaluated before the runner design is finalized.
