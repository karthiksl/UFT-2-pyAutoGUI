# UFT → PyAutoGUI Migration Framework

Reusable PyAutoGUI + pytesseract automation framework for Epic Hyperdrive
running inside a Citrix / VDI session.

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.11+ |
| Tesseract OCR | 5.x (must be on `PATH`) |
| Citrix Workspace | any (Windows only for focus control) |
| OS | Windows (execution), macOS/Linux (dev/test) |

---

## Install

```bash
# From repo root
pip install -e ".[test]"          # core + test deps
pip install -e ".[test,windows]"  # add pywinauto on Windows
```

---

## Configuration

Framework settings are loaded in priority order:

1. Built-in defaults (see `core/config.py → _DEFAULTS`)
2. YAML file passed via `--config` or `AUTOMATION_CONFIG_PATH` env var
3. Environment variables prefixed `AUTOMATION_` (e.g. `AUTOMATION_LOG_LEVEL=DEBUG`)

Key settings:

| Key | Default | Description |
|---|---|---|
| `or_path` | `or/epic_or.yaml` | Visual Object Repository YAML |
| `assets_dir` | `assets/images` | Reference PNG directory |
| `screenshots_dir` | `assets/screenshots` | Failure screenshot output |
| `citrix_window_title` | `Citrix Viewer` | Window title to focus |
| `default_confidence` | `0.85` | Image-match threshold |
| `default_timeout` | `30.0` | Wait timeout in seconds |
| `ocr_min_confidence` | `0.65` | Minimum acceptable OCR confidence |

---

## Run tests

```bash
# All tests
pytest

# Smoke tests only
python -m automation.run --suite smoke

# Single test case
python -m automation.run --test-id TEST_188001

# Debug mode with Allure report
python -m automation.run --suite regression \
    --report-dir allure-results \
    --log-level DEBUG

# View Allure report (requires allure CLI)
allure serve allure-results
```

---

## Project layout

```
automation/
├── core/          Framework internals — never import business logic here
│   ├── config.py           YAML + env config loader
│   ├── or_loader.py        Visual OR YAML → VisualOR / ObjectSpec
│   ├── finder.py           Bounded image-anchor locate (pixels stay here)
│   ├── actions.py          Two-phase click, type_text, hotkey
│   ├── waits.py            Explicit wait predicates
│   ├── retries.py          Retry decorator + screenshot-on-failure
│   ├── citrix.py           Window focus + session health
│   ├── ocr.py              pytesseract wrapper (TODO: prompt-04)
│   ├── screen.py           Screen anchor helpers
│   ├── exceptions.py       FailureCode enum + exception hierarchy
│   ├── logging_setup.py    loguru configuration
│   └── reporting.py        Allure integration (TODO: prompt-10)
├── or/
│   └── epic_or.yaml        Visual Object Repository (TODO: prompt-03)
├── common/        Migrated FunctionLibrary helpers (TODO: prompt-05)
├── tests/
│   ├── conftest.py         Session OR fixture, Citrix guard, failure hook
│   ├── tasks/              Atomic UI task modules
│   └── flows/              Business flow test modules
├── assets/
│   └── images/             Reference PNG crops (captured in Citrix session)
└── data/                   CSV / XLSX test data
```

---

## Adding a new screen

1. Capture reference PNG crops inside the Citrix session at production DPI.
2. Add entries to `or/epic_or.yaml` with measured region coordinates.
3. Create `tests/tasks/<screen_name>.py` with atomic task functions.

## Adding a new test case

1. Create `tests/flows/test_<TEST_ID>.py`.
2. Use only functions from `core/actions`, `core/waits`, `core/ocr`, and `tests/tasks/`.
3. Mark with `@pytest.mark.smoke` or `@pytest.mark.regression`.
4. Add test data rows to the appropriate `data/` directory.
