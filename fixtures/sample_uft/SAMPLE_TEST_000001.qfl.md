# SAMPLE_TEST_000001 — Mock Coverage Verification Flow

**UFT Test ID:** SAMPLE_TEST_000001  
**JIRA:** SAMPLE-1  
**Author:** Migration Team  
**Date Authored:** 2024-01-15  
**Status:** Active (synthetic fixture — does not connect to real Epic)

---

## Overview

This test logs into the Mock Epic application, verifies the patient banner
contains the expected MRN, navigates to the Coverage tab, and asserts that
the coverage effective date matches the value in the test data sheet.

It is the canonical "hello world" for the Epic Hyperdrive automation
framework. Every layer is exercised: login, navigation, image-based object
location, OCR text validation, and pass/fail reporting.

---

## Data Sheet: SAMPLE_TEST_000001.csv

| TestCaseID | MemberID | LastName | FirstName | DateOfBirth | CoverageEffectiveDate | ExpectedStatus |
|---|---|---|---|---|---|---|
| SAMPLE-1 | 1234567 | Rivera | Maria | 03/15/1982 | 01/01/2026 | Active |
| SAMPLE-2 | 9876543 | Thompson | James | 07/22/1975 | 04/01/2026 | Active |

---

## Test Steps (UFT engineer narrative)

### Setup

Before the test starts, the UFT suite loads the data sheet
`SAMPLE_TEST_000001.csv` and reads the current row into `DataTable`.  
The Citrix window title "Mock Epic — Citrix Viewer" is confirmed to be in
focus. A screenshot is saved as a baseline artifact.

---

### Step 1 — Navigate to the Login Screen

The test confirms the login screen is visible by checking for the
"Mock Epic" header banner image (`login_header_banner.png`).  
If the image is not found within 10 seconds, the test fails with
`LOGIN_SCREEN_NOT_FOUND`.

**UFT equivalent:**  
> `If Not Page("Login").Exist(10) Then Reporter.ReportEvent micFail, "Step 1", "Login screen not found"`

---

### Step 2 — Enter Username

The Username text field is located by its label image
(`login_username_input.png`).  
The string `"testuser"` is typed into it using `SetSecure` (in the real
script) or plain `Set` for the synthetic fixture.  
A 100 ms pause follows to allow UI rendering.

**UFT equivalent:**  
> `WebEdit("Username").Set "testuser"`

---

### Step 3 — Enter Password

The Password text field (`login_password_input.png`) receives the string
`"testpass"` via `Set`.

**UFT equivalent:**  
> `WebEdit("Password").Set "testpass"`

---

### Step 4 — Click Login

The Login button (`login_button.png`) is clicked.  
The test waits up to 15 seconds for the Home screen header
(`home_banner_label.png`) to appear. If the wait times out, the test
fails with `HOME_SCREEN_NOT_REACHED`.

**UFT equivalent:**  
> `WebButton("Login").Click`  
> `Wait 2`  
> `If Not Page("Home").Exist(15) Then Reporter.ReportEvent micFail, "Step 4", "Home not loaded"`

---

### Step 5 — Verify Patient Banner (MRN OCR)

On the Home screen, the patient banner region is OCR-read.  
The extracted text is asserted to match the pattern `MRN:\s*\d{7}`.  
The actual MRN digits are compared against `DataTable("MemberID")`.

**UFT equivalent:**  
> `sBannerText = Browser("Home").Page("Home").WebElement("PatientBanner").GetROProperty("innerText")`  
> `If Not (InStr(sBannerText, DataTable("MemberID")) > 0) Then`  
> `    Reporter.ReportEvent micFail, "Step 5", "MRN mismatch: " & sBannerText`

---

### Step 6 — Click Coverage Tab

The Coverage tab image (`home_coverage_tab.png`) is located on the Home
screen and clicked.  
The test waits for the Coverage screen header (`coverage_header.png`) to
appear within 10 seconds.

**UFT equivalent:**  
> `Browser("Home").Page("Home").WebElement("CoverageTab").Click`

---

### Step 7 — Assert Coverage Effective Date (OCR)

The coverage effective date region is OCR-read.  
The extracted date string is normalized to `MM/DD/YYYY` format and
compared against `DataTable("CoverageEffectiveDate")`.

Expected value: `01/01/2026` (row SAMPLE-1) or `04/01/2026` (row SAMPLE-2).

**UFT equivalent:**  
> `sDate = Browser("Coverage").Page("Coverage").WebElement("EffectiveDate").GetROProperty("innerText")`  
> `If sDate <> DataTable("CoverageEffectiveDate") Then`  
> `    Reporter.ReportEvent micFail, "Step 7", "Date mismatch: expected " & DataTable("CoverageEffectiveDate") & " got " & sDate`

---

### Step 8 — Log Pass and Close

`Reporter.ReportEvent micPass, "SAMPLE_TEST_000001", "Coverage verification passed for MRN " & DataTable("MemberID")`

The screen is left on the Coverage view; the driver resets to Login before
the next data row.

---

## Migration Notes

| UFT concept | Python equivalent |
|---|---|
| `DataTable("Col")` | `ctx.row.require("Col")` |
| `Reporter.ReportEvent micPass/micFail` | `ctx.reporter.passed(...)` / `ctx.reporter.failed(...)` |
| `Browser(...).Page(...).WebElement(...).Click` | `actions.click("sample_home.coverage_tab")` |
| `Browser(...).GetROProperty("innerText")` | `ocr.read_target("sample_home.mrn_text")` |
| `Page(...).Exist(timeout)` | `waits.wait_for_object_exists(spec, timeout=10)` |
| `Wait N` | `waits.wait_for_screen_stable(...)` (never bare `time.sleep`) |

---

## Object Repository Entries (sample_or.yaml)

All objects are defined in `automation/or/sample_or.yaml`.  
Reference images live under `automation/assets/images/sample/`.

| Logical Name | Type | Purpose |
|---|---|---|
| `sample_login.username_field` | input | Username text box |
| `sample_login.password_field` | input | Password text box |
| `sample_login.login_button` | button | Submit credentials |
| `sample_home.banner_label` | label | Patient banner (anchor + OCR region) |
| `sample_home.coverage_tab` | tab | Navigate to coverage screen |
| `sample_coverage.header_label` | label | Coverage screen anchor |
| `sample_coverage.effective_date_field` | label | Date value label (OCR-read) |

| OCR Target | Pattern | Purpose |
|---|---|---|
| `sample_home.mrn_text` | `MRN:\s*\d{7}` | Validate patient MRN in banner |
| `sample_coverage.effective_date_value` | `\d{2}/\d{2}/\d{4}` | Validate date field |
