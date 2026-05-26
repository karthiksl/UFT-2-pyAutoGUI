# Visual Object Repository — Schema Reference

**File:** `automation/or/app_or.yaml`  
**Loaded by:** `automation/core/or_loader.py → load_or()`  
**Version:** 1  

---

## 1. Design principles

| Principle | Rule |
|---|---|
| No raw coordinates in business code | Every pixel lookup goes through a named OR entry |
| Region-first searching | `finder.locate()` only looks inside `region`; never full-screen |
| Explicit confidence | Every entry carries its own threshold; never rely on global default silently |
| Placeholder discipline | Unverified entries are marked `status: placeholder`; CI refuses to run a test whose objects are all placeholder |
| OCR separation | Text validation lives in `ocr_targets`, not in `objects`; objects are image-only |

---

## 2. Top-level keys

| Key | Required | Description |
|---|---|---|
| `meta` | yes | Schema version and environment facts |
| `citrix` | yes when `meta.citrix: true` | Session-level anchors for `core/citrix.py` |
| `busy` | yes | Spinner / loading anchors for `core/waits.wait_while_busy()` |
| `screens` | yes | Logical screen groups with navigation anchors |
| `objects` | yes | Individual interactable UI elements |
| `ocr_targets` | yes | Text-validation regions for `core/ocr.py` |
| `data_bindings` | yes | Data column → logical field mappings |

---

## 3. `meta`

```yaml
meta:
  version: 1                      # increment on breaking schema changes
  application: Epic Hyperdrive    # human label only
  framework: app_automation_pyautogui
  dpi_profile: 100               # Windows Display Scale % at capture time
  resolution: 1920x1080          # monitor resolution at capture time
  citrix: true                   # enables citrix block validation
```

**Rule:** When `dpi_profile` or `resolution` changes, **all** images must be
re-captured. The framework logs a warning when the runtime display does not
match `meta.resolution`.

---

## 4. `citrix` block

Used exclusively by `core/citrix.assert_session_healthy()` and
`core/citrix.ensure_citrix_focused()`.

```yaml
citrix:
  session_frame:
    description: "Optional human note"
    image: citrix_system/session_frame_bar.png  # relative to assets/images/
    region: [0, 0, 1920, 38]   # [x, y, width, height] absolute pixels
    min_confidence: 0.82
    status: stable | placeholder | inferred
```

**Required sub-keys:** `disconnected`, `reconnecting`, `session_locked`,
`logon_in_progress` — each with `image`, `region`, `min_confidence`.

---

## 5. `busy` block

Used by `core/waits.wait_while_busy(busy_spec)`.

```yaml
busy:
  epic_spinner:
    image: busy/epic_activity_spinner.png
    region: [860, 490, 200, 100]
    min_confidence: 0.80
    status: placeholder
```

The key name (e.g. `epic_spinner`) is the logical name passed to
`waits.wait_while_busy()` after resolving through the busy index. Business code
calls `wait_while_busy("epic_spinner")`.

---

## 6. `screens` block

Each screen entry names a logical group and defines its identifying **anchor** —
the image that must be visible for the screen to be considered active.

```yaml
screens:
  coverage_change:
    description: "Coverage change transaction screen"
    anchor:
      image: anchors/coverage_change/coverage_change_header.png
      region: [210, 90, 650, 55]
      min_confidence: 0.87
      status: placeholder
    next_screens: [plan_selection, confirmation]   # optional navigation graph
```

`next_screens` is documentation-only today; a future prompt will use it to
validate navigation paths in the test runner.

**`core/screen.ScreenAnchor.assert_active()`** reads this entry to gate
navigation.

---

## 7. `objects` block

The primary lookup table for `core/actions.click()` and `core/waits.*`.

```yaml
objects:
  - name: enrollment.submit_enrollment_button   # <screen>.<object> — unique
    screen: enrollment                          # must match a screens key
    type: button                                # button|input|link|tab|checkbox|dropdown|label|table_cell
    image: objects/enrollment/submit_enrollment_button.png
    region: [1750, 940, 160, 45]               # [x, y, w, h]
    min_confidence: 0.87                        # override default with a comment when changed
    expect_after: confirmation.confirmation_number_label   # optional post-click anchor
    notes: "Submits the full enrollment transaction"
    status: placeholder                         # stable|placeholder|inferred
```

### Field reference

| Field | Required | Type | Notes |
|---|---|---|---|
| `name` | yes | `screen.object` | Globally unique; lowercase, underscores |
| `screen` | yes | string | Must match a key in `screens` |
| `type` | yes | enum | One of the 8 type values listed above |
| `image` | yes | path | Relative to `automation/assets/images/` |
| `region` | yes | `[x, y, w, h]` | Absolute screen pixels at `meta.resolution` |
| `min_confidence` | yes | float (0,1] | Default 0.80 for objects; annotate overrides |
| `expect_after` | no | `screen.object` | Anchor that must appear after this action |
| `notes` | no | string | Human notes for contributors |
| `status` | yes | enum | `stable` / `placeholder` / `inferred` |

### Status meanings

| Status | Meaning | CI behaviour |
|---|---|---|
| `stable` | PNG captured at production DPI, confidence tuned | Runs normally |
| `placeholder` | Filename reserved; PNG not yet captured | Test skipped with `pytest.mark.skip` |
| `inferred` | Object assumed from workflow; screen/region TBD | Test skipped + warning logged |

---

## 8. `ocr_targets` block

Defines text-validation regions consumed by `core/ocr.assert_text()`.
**No object image is needed here** — only the screen region and expected pattern.

```yaml
ocr_targets:
  - name: confirmation.confirmation_number_value   # <screen>.<field>
    screen: confirmation
    region: [210, 195, 600, 50]
    expected_pattern: "Confirmation\\s*#?\\s*:\\s*\\d{8,14}"
    lang: eng                                       # tesseract lang code
    preprocess: [grayscale, upscale_2x, otsu_threshold]
    min_confidence: 0.70                            # OCR confidence, not image confidence
    notes: "Human note"
    status: placeholder
```

### `preprocess` pipeline options (ordered; applied left-to-right)

| Step | Effect |
|---|---|
| `grayscale` | Convert to single-channel |
| `upscale_2x` | 2× bicubic resize (improves Tesseract on small fonts) |
| `gaussian_denoise` | Gaussian blur σ=1 to reduce Citrix JPEG artifacts |
| `otsu_threshold` | Binarise using Otsu's method |
| `sharpen` | Unsharp mask to recover edge definition after denoise |

### Calling from business code

```python
# Read and validate in one call:
ocr.assert_text(
    "confirmation.confirmation_number_value",
    actual=expected_conf_number,
    mode="contains",          # "contains" | "equals" | "regex"
    min_confidence=0.70,
)

# Or read raw text and inspect yourself:
result = ocr.read_text_by_name("confirmation.status_value")
assert result.text.strip() == "Accepted"
```

---

## 9. `data_bindings` block

Maps logical field names to source file columns. The `source` key matches the
subdirectory name under `automation/data/`.

```yaml
data_bindings:
  coverage_effective_date:
    source: coverage_data          # → automation/data/coverage_data/
    column: EffectiveDate
    format: "%m/%d/%Y"            # optional strftime format for date coercion
    sensitive: false              # true = mask in logs (default false)
    notes: "Human note"
```

Business code accesses bindings through `common/data_reader.py`:

```python
from automation.common.data_reader import load_cases, get_field

cases = load_cases("coverage_data", sheet="Sheet1")
for row in cases:
    date_str = get_field(row, "coverage_effective_date")  # resolves binding + format
```

---

## 10. Adding a new screen (checklist)

1. Capture reference PNGs inside the Citrix session at `meta.dpi_profile` / `meta.resolution`.
2. Add screen entry under `screens:` with anchor image and region.
3. Add all objects under `objects:` — set `status: placeholder`.
4. Add any OCR-validated fields under `ocr_targets:`.
5. Run `python -c "from automation.core.or_loader import load_or; load_or('automation/or/app_or.yaml')"` — must print without error.
6. Capture PNGs, update paths, flip `status` to `stable`.
7. Run the specific test with `pytest -k <test_id> -v` and verify image match.

---

## 11. Region coordinate guide

All regions are `[x, y, width, height]` in **absolute screen pixels** measured
from the **top-left corner of the physical display** (not the Citrix window).

```
(0,0) ┌─────────────────────────────────────────────────────────────┐
      │  Citrix toolbar strip       [0, 0, 1920, 38]                │
      ├──────────┬──────────────────────────────────────────────────┤
      │  Epic    │  Epic content area (navigation + forms)          │
      │  sidebar │  x starts at 210 for most elements               │
      │  ~210px  │                                                  │
      │          │                                                  │
      │          │                                                  │
      │          │  Action bar / save buttons near y=940            │
      ├──────────┴──────────────────────────────────────────────────┤
      │  Epic status bar                  y ≈ 980–1080              │
(1920,1080) └─────────────────────────────────────────────────────┘
```

When in doubt: use screenshot + pixel ruler to measure, then add 10 px padding
on each edge and widen the region — a wider region costs milliseconds but
prevents `UiNotFoundError` from minor pixel drift.

---

## Coverage Report

### TEST_CASE_ID_001 — Member Enrollment (New Member Add)

**Screens touched:** `epic_home` → `member_search` → `member_chart` →
`enrollment` → `plan_selection` → `dependent_management` → `confirmation`

| Object / OCR target | Purpose |
|---|---|
| `epic_home.new_enrollment_tile` | Entry point — launch enrollment transaction |
| `enrollment.effective_date_field` | Enter coverage effective date from `coverage_effective_date` binding |
| `enrollment.coverage_type_dropdown` | Select Medical / Dental / Vision |
| `enrollment.select_plan_button` | Open plan selection modal |
| `plan_selection.plan_row_radio_first` | Select target plan row |
| `plan_selection.select_plan_ok_button` | Confirm plan selection |
| `enrollment.add_dependent_link` | Navigate to dependent management |
| `dependent_management.dep_first_name_field` | Enter dependent first name |
| `dependent_management.dep_relationship_dropdown` | Set relationship type |
| `enrollment.submit_enrollment_button` | Submit full enrollment |
| `confirmation.confirmation_number_label` | Assert confirmation screen loaded |
| OCR: `confirmation.confirmation_number_value` | Extract and log confirmation number |
| OCR: `confirmation.status_value` | Assert status = "Accepted" |
| Data bindings used | `member_id`, `coverage_effective_date`, `coverage_type`, `plan_name`, `dep_first_name`, `dep_relationship`, `expected_confirmation_status` |

---

### TEST_CASE_ID_002 — Coverage Change (Plan Modification)

**Screens touched:** `epic_home` → `member_search` → `member_chart` →
`coverage_change` → `plan_selection` → `confirmation`

| Object / OCR target | Purpose |
|---|---|
| `member_search.search_mrn_field` | Look up existing member by MRN |
| `member_search.search_submit_button` | Execute search |
| `member_search.results_table_first_row` | Open first match |
| `member_chart.coverage_tab` | Navigate to coverage screen |
| OCR: `coverage_change.current_plan_name_value` | Verify pre-change plan name matches test data |
| `coverage_change.change_effective_date_field` | Enter change effective date |
| `coverage_change.change_reason_dropdown` | Select change reason code |
| `coverage_change.new_plan_select_button` | Open plan selection |
| `plan_selection.plan_row_radio_first` | Select new plan |
| `plan_selection.select_plan_ok_button` | Confirm new plan |
| `coverage_change.submit_change_button` | Submit change transaction |
| `confirmation.confirmation_status_label` | Assert confirmation screen anchor |
| OCR: `confirmation.status_value` | Assert status = "Accepted" or "Pending" |
| `confirmation.return_to_chart_button` | Navigate back to member chart |
| Data bindings used | `member_id`, `plan_name`, `coverage_effective_date`, `change_reason`, `expected_confirmation_status` |
