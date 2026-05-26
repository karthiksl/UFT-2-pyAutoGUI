# ADR-001: OCR Retry Strategy, Dropdown Select Strategy, and CI Pipeline Design

**Status:** Proposed  
**Date:** 2026-05-25  
**Deciders:** Karthikeyan (sole maintainer)  
**Context project:** UFT One → PyAutoGUI migration framework for Epic Hyperdrive on Citrix

---

## Background

Three open design questions were identified during the initial build of the framework.
Each is evaluated here against the hard constraints: Python 3.9+, no DOM/accessibility APIs,
all element finding is visual (screenshot + OpenCV/OCR), target is Epic in a Citrix session,
team of 1–2 with no dedicated DevOps, macOS dev / Windows Citrix VDI production split.

---

## Decision 1 — OCR Retry Layer

### Context

`core/ocr.py` already ships a working retry loop inside `assert_text` and a separate
`core/retries.py` decorator. Reading the two together reveals three gaps:

1. **Debug images are written on every `read_text` call**, not just failures. A single
   flow test with 30 OCR calls generates 30+ debug PNGs regardless of outcome. On a
   long-running CI machine `assets/ocr_debug/` will fill disk within days.

2. **Backoff is inconsistent.** `assert_text` uses *linear* backoff (`backoff * attempt`,
   so 0.75 s, 1.50 s, 2.25 s at defaults). `retries.retry` uses *exponential* backoff
   (`delay *= backoff`, so 1.0 s, 1.5 s, 2.25 s). The two mechanisms overlap and callers
   can accidentally nest them (wrapping `assert_text` inside `retry`).

3. **`OcrLowConfidenceError` and `OcrTextMismatchError` are treated identically by the
   retry loop**, but they have very different recovery prospects. Low confidence usually
   means the screen hasn't rendered yet — waiting helps. Text mismatch usually means the
   screen rendered with wrong content — waiting rarely helps.

### Options considered

| # | Retry count | Backoff | Debug image policy | Low conf vs mismatch |
|---|---|---|---|---|
| A | 3 (hardcoded) | Linear 0.75× | Every read | Retry both identically |
| B | Config-driven (default 3) | Exponential 1.5× | Failures only + on demand | Retry low-conf; raise mismatch immediately |
| C | Config-driven (default 5) | Adaptive (Citrix round-trip aware) | Failures only | Retry both, longer timeout for low-conf |

**Option A** is the status quo. Disk waste and inconsistency are accepted as-is.

**Option B** is a targeted fix with minimal scope change. It separates the two failure modes,
aligns backoff with `retries.py`, and guards disk. It requires touching only `ocr.assert_text`
and adding a one-line debug-image policy flag.

**Option C** adds complexity (adaptive backoff requires measuring Citrix round-trip time) for
marginal gain. Not appropriate at team size 1–2 without evidence that 3 retries is
insufficient.

### Decision: Option B

Apply these specific changes to `core/ocr.py`:

```python
# assert_text signature change
def assert_text(
    target_or_region: str | tuple[int, int, int, int],
    expected: str,
    *,
    mode: Literal["contains", "equals", "regex"] = "contains",
    min_confidence: float | None = None,
    case_sensitive: bool = False,
    retries: int | None = None,      # None → read from config key "max_retry_attempts"
    backoff: float = 1.5,            # was 0.75; now exponential to match retries.py
    save_debug_on: Literal["always", "failure"] = "failure",  # NEW
) -> OcrResult:
```

Inside the retry loop:
- `OcrLowConfidenceError` → retry up to `retries` times (screen may still be rendering).
- `OcrTextMismatchError` → **do not retry**; raise immediately. If the screen rendered
  correctly but shows wrong text, retrying wastes time and masks a real data problem.
- Only call `_save_debug_image` when `save_debug_on == "always"` OR the attempt failed.

Backoff formula: `sleep_s = backoff ** (attempt - 1)` (0.0 s, 1.5 s, 2.25 s for 3 attempts).
This matches `retries.py` and avoids accidental double-backoff when nesting.

Add to `config.py` defaults:
```python
"max_retry_attempts": 3,       # already present
"ocr_debug_on_failure_only": True,  # NEW — set False to restore "always" behaviour
```

### Trade-offs

| Dimension | Assessment |
|---|---|
| Complexity delta | Low — 15–20 line change in one function |
| Disk usage | Reduced ~90% in passing runs |
| Debuggability | Unchanged for failing runs (debug image still saved) |
| Breaking change | `backoff` default changes 0.75 → 1.5; `retries` now nullable |
| Unit test impact | Update 3–4 existing tests that assert on the exact sleep timing |

### Consequences

- Easier: triage of flaky tests (debug image always present on failure, nowhere else to look).
- Harder: reproducing intermittent issues that passed on retry (the passing attempt leaves no image). Mitigate by setting `AUTOMATION_OCR_DEBUG_ON_FAILURE_ONLY=false` locally.
- Revisit: if Citrix JPEG compression degrades further (e.g. after an infrastructure upgrade), consider adding `"denoise"` to `_DEFAULT_PIPELINE` before `"upscale_2x"`.

### Action items

- [ ] Update `assert_text` in `core/ocr.py` per the signature above.
- [ ] Add `ocr_debug_on_failure_only` key to `config.py` defaults.
- [ ] Update unit tests that hard-code `backoff * attempt` sleep expectations.
- [ ] Add a unit test: `OcrTextMismatchError` on attempt 1 propagates without retry.
- [ ] Document `save_debug_on` and `ocr_debug_on_failure_only` in `docs/DEVELOPER_GUIDE.md`.

---

## Decision 2 — Dropdown Select Strategy

### Context

`core/actions.py` currently provides `click`, `type_text`, `hotkey`, and `press`.
There is no `select_dropdown` action. The converter maps `WebList.Select` to a
`# TODO` comment at confidence MEDIUM (score 55), meaning every dropdown in any
generated flow file requires manual implementation. Epic Hyperdrive dropdowns seen so
far fall into three visual types:

- **Type-to-filter dropdowns** — clicking the field opens a search box; typing filters
  the list and pressing Enter or clicking the match selects it. Most Epic lookup fields
  work this way (provider, plan, diagnosis code).
- **Short static lists** — 3–10 items, arrow-key navigable, often no text input.
  Examples: Yes/No/Unknown, plan type, gender.
- **Long scroll lists** — 20–100+ items, sometimes have a scroll bar but no text filter.
  Rare in Hyperdrive but present in legacy workflow screens.

No accessibility APIs are available. The implementation must be purely visual.

### Options considered

**Option A — Arrow-key only**  
Click the dropdown anchor, press `Down` N times (N derived from position in a
predefined list in `app_or.yaml`), press `Enter`. Simple, zero OCR. Brittle if list
order changes with data or Epic version.

**Option B — OCR scan of open list**  
Click to open, screenshot the open list region, run OCR to find the target item's
bounding box, click it. Handles any list size, any order. Fails if Citrix JPEG
compression makes text illegible in the open dropdown (which is a narrow rendering area
with small font).

**Option C — Tiered: type-to-filter → arrow-key fallback**  
Click to open, type the target value, wait for a suggestion list to appear (OCR or
image anchor). If suggestion appears, click or press `Enter`. If no suggestion after
1 second, fall back to arrow-key navigation using a `max_arrows` cap. Covers the vast
majority of Epic fields efficiently with a safety net for short lists.

### Decision: Option C

Implement `actions.select_dropdown` in `core/actions.py`:

```python
def select_dropdown(
    logical_name: str,
    value: str,
    *,
    strategy: Literal["type_filter", "arrow_key", "auto"] = "auto",
    max_arrows: int = 15,
    confirm_key: str = "enter",
    expect_after: str | None = None,
) -> None:
    """Select *value* from a dropdown identified by *logical_name*.

    strategy="auto"        → try type-to-filter; fall back to arrow-key.
    strategy="type_filter" → type-to-filter only; raise if suggestion absent.
    strategy="arrow_key"   → arrow-key only; *value* must match OR list entry.
    """
```

The `app_or.yaml` entry for a dropdown gains two optional keys:

```yaml
objects:
  - name: member_search.plan_type_dropdown
    screen: member_search
    image: member_search/plan_type_dropdown.png
    region: [120, 340, 200, 28]
    dropdown:
      strategy: auto      # auto | type_filter | arrow_key
      max_arrows: 10      # cap for arrow-key fallback; ignored for type_filter
      choices:            # optional; enables arrow-key without OCR
        - "Commercial"
        - "Medicaid"
        - "Medicare"
```

When `choices` is populated and `strategy` is `arrow_key` or falls back to it,
the implementation computes the required arrow count from the list rather than
doing OCR, making it deterministic.

**Why not Option B?** OCR on the open dropdown list is the least reliable path: the
open list is rendered in a narrow floating element, often with small font (9–11px
equivalent after Citrix JPEG compression), and the hit rate on Citrix will be
materially lower than on a clean screenshot. Option B should be reserved as a last
resort, not the default.

### Trade-offs

| Dimension | Assessment |
|---|---|
| Complexity | Medium — new function, new OR keys, new unit tests |
| Reliability | High for type-to-filter fields; medium for arrow-key fallback |
| OR maintenance | One extra `dropdown:` block per dropdown element |
| Converter impact | Upgrade `WebList.Select` pattern from score 55 → 75 |

### Consequences

- Easier: converting QFL files with `WebList.Select` — the generated line becomes
  `actions.select_dropdown("screen.field", value)` at confidence GOOD rather than a
  manual TODO at MEDIUM.
- Harder: dropdowns with dynamically ordered lists (sorted by recent use) will require
  `strategy: type_filter` set explicitly in the OR and a known filter prefix for each value.
- Revisit: if a dropdown type outside these three is discovered (e.g. a custom Epic
  Hyperdrive component that ignores keyboard input), add an `ocr_scan` strategy at that point.

### Action items

- [ ] Implement `select_dropdown` in `core/actions.py`.
- [ ] Add `dropdown:` sub-key support to `or_loader.py` (`ObjectSpec` dataclass).
- [ ] Write unit tests: `type_filter` happy path, `arrow_key` with `choices`, `auto` fallback.
- [ ] Update converter: map `WebList.Select` to `actions.select_dropdown(…)` at confidence 75.
- [ ] Add `select_dropdown` reference to `docs/HOW_TO_CONVERT.md` pattern table.
- [ ] Capture dropdown reference PNGs for all 5 sample QFL screens that have `WebList.Select`.

---

## Decision 3 — CI Pipeline Design

### Context

There is no CI configuration today (no `.github/` directory). The split is:

- **macOS (dev machine):** runs the converter, unit tests, and code quality checks.
  No Epic/Citrix access. `pyautogui.screenshot` and `ImageGrab.grab` work on macOS
  with a display; they fail in a headless GitHub-hosted runner without `$DISPLAY`.
- **Windows Citrix VDI (production):** runs flow tests against the real Epic screen.
  No automated trigger mechanism exists yet.

The 218 unit tests are already fully stubbed (no Tesseract binary required, no screen
required) and pass on any machine. Flow tests require a live Epic session and cannot
be headlessly stubbed without essentially re-implementing the UI.

### Options considered

**Option A — Single pipeline, skip flow tests on Mac**  
One GitHub Actions workflow. Unit tests run on `ubuntu-latest` (headless). Flow tests
are marked `@pytest.mark.flow` and excluded via `-m "not flow"` on CI. Flow tests run
manually from Windows VDI only.

**Option B — Two-job pipeline: unit (headless) + flow (self-hosted Windows runner)**  
Job 1 runs unit tests + linting on `ubuntu-latest` (every PR). Job 2 is triggered
manually or on a schedule, runs on a self-hosted Windows runner registered on the
Citrix VDI, requires an active Epic session.

**Option C — Two-job pipeline with virtual framebuffer on Linux for unit tests**  
Same as B but uses `xvfb-run` on the Linux job so that `pyautogui.screenshot` doesn't
error even if accidentally called from unit tests. Adds complexity without clear benefit
since unit tests already monkeypatch all screen access.

### Decision: Option B

A two-job GitHub Actions pipeline is the right fit for a 1–2 person team with no
dedicated DevOps. Option C's `xvfb` complexity is unnecessary because the existing
unit-test conftest already monkeypatches every screen-touching function.

**Job 1 — `unit-tests` (runs on every push/PR, ubuntu-latest)**

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.9" }
      - name: Install deps
        run: pip install -e ".[test]" --break-system-packages
        working-directory: automation
      - name: Lint
        run: ruff check tools/ automation/
      - name: Unit tests
        run: pytest automation/tests/unit/ -v --tb=short
```

`tesseract-ocr` is **not** installed on the runner. The 4 Tesseract-binary tests will
be skipped via the existing `@requires_tesseract` marker — this is expected and
documented.

**Job 2 — `flow-tests` (manual trigger, self-hosted Windows runner)**

```yaml
  flow-tests:
    runs-on: [self-hosted, windows, citrix]
    if: github.event_name == 'workflow_dispatch'
    needs: unit-tests
    steps:
      - uses: actions/checkout@v4
      - name: Activate venv
        run: automation\.venv\Scripts\activate
        shell: cmd
      - name: Run regression flows
        run: pytest automation/tests/flows/ -m regression -v --tb=long
        env:
          AUTOMATION_LOG_LEVEL: DEBUG
```

The self-hosted runner must be registered on the Windows Citrix VDI machine that has
an active Epic session open. Runner registration is a one-time manual step
(`./config.cmd --url ... --token ...` from the GitHub Actions runner package).

**On the macOS dev machine the existing workflow is unchanged:**

```bash
source automation/.venv/bin/activate
pytest automation/tests/unit/ -v                        # fast, always
pytest automation/tests/flows/member_login/ -v          # manual, needs screen
```

### Trade-offs

| Dimension | Assessment |
|---|---|
| Setup effort | Low — GitHub Actions free tier covers job 1; runner registration is one session |
| Ongoing maintenance | Very low — YAML is ~40 lines, no custom Docker image |
| Flow test gate | Manual only; no automated gate on PRs (acceptable at team size 1–2) |
| Windows runner uptime | Self-hosted runner must be online; no fallback if VDI is down |

### Consequences

- Easier: every PR automatically validates unit tests and linting before merge; regressions
  in the converter or core framework are caught without touching the VDI.
- Harder: flow test results are not visible in PR checks; discipline is required to run
  them before merging changes that touch `core/` or `common/`.
- Revisit: if the team grows, replace the manual flow-test trigger with a scheduled
  nightly run (`cron: '0 22 * * 1-5'`) so results appear in Slack/email each morning.

### Action items

- [ ] Create `.github/workflows/ci.yml` with the two-job definition above.
- [ ] Install GitHub Actions self-hosted runner on the Windows Citrix VDI machine.
- [ ] Add `[self-hosted, windows, citrix]` label to the runner during registration.
- [ ] Add `flow` marker to `pyproject.toml` markers list.
- [ ] Tag existing flow test files with `@pytest.mark.flow`.
- [ ] Verify `pip install -e .[test]` works on `ubuntu-latest` (pyautogui headless install).
- [ ] Document the runner setup steps in `docs/HOW_TO_CONVERT.md` under "Running in CI".

---

## Summary

| Decision | Chosen option | Complexity | Priority |
|---|---|---|---|
| OCR retry strategy | Exp. backoff, fail-only debug images, don't retry mismatch | Low | Ship next |
| Dropdown select | Tiered type-filter → arrow-key, config in OR YAML | Medium | Before first dropdown QFL |
| CI pipeline | Two-job GitHub Actions (unit headless + flow manual) | Low | Set up this week |

All three decisions are independent and can be implemented in any order. The OCR fix
is the highest priority because it prevents disk exhaustion on any machine running
repeated test cycles.
