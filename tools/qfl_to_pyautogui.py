"""
tools/qfl_to_pyautogui.py — UFT QFL → PyAutoGUI Converter
==========================================================
Converts any UFT One VBScript (.qfl) file to Python PyAutoGUI automation code.

Every translated statement is assigned a confidence score (0–100) that reflects
how reliably the pattern was converted:

  100  EXACT    — perfect 1-to-1 translation, no manual review needed
   90  HIGH     — correct translation, minor wiring needed (e.g. add OR entry)
   75  GOOD     — translated with a guiding TODO; 1–2 minutes to resolve
   55  MEDIUM   — partial translation; dropdown / table logic needed manually
   30  LOW      — placeholder emitted; must be written manually
   10  FALLBACK — pattern unrecognised; raw VBScript kept as a comment

Handles
-------
  Structural
    - VBScript If / ElseIf / Else / End If  → Python if/elif/else
    - For i = 1 To n [Step s] / Next        → for i in range(...)
    - For Each item In collection / Next    → for item in collection
    - Do While / Do Until / Loop            → while / while not
    - Select Case / Case / Case Else / End Select → if/elif/else chain
    - With obj / End With                   → inline object prefix expansion
    - On Error Resume Next / On Error GoTo 0 → try/except block
    - Line continuation (_ at end of line)  → joined logical lines
    - Exit Function / Exit Sub              → return
    - End Function / End Sub               → end of generated function

  UFT Web objects
    - WebEdit("Name").Set val               → actions.type_text(...)
    - WebEdit("Name").SetSecure/Encrypted   → actions.type_text(...) with note
    - WebEdit("Name").GetROProperty("value")→ ocr.read_target(...)
    - WebEdit("Name").Click                 → actions.click(...)
    - WebButton("Name").Click               → actions.click(...)
    - WebElement("Name").Click              → actions.click(...)
    - WebElement("Name").FireEvent "event"  → actions.click(...) + TODO
    - WebElement("Name").SetAttribute       → actions.type_text(...) + TODO
    - WebElement("Name").GetROProperty(p)  → ocr.read_target(...)
    - WebLink("Name").Click                 → actions.click(...)
    - WebCheckBox("Name").Set "ON"/"OFF"    → actions.click(...) with guard
    - WebRadioGroup("Name").Select val      → actions.click(...) + TODO
    - WebList("Name").Select val            → actions.click + TODO
    - WebList("Name").GetROProperty("value")→ ocr.read_target(...)
    - WebFile("Name").Set path              → actions.type_text(...) + TODO
    - WebTable("Name").ChildItem(r,c,…).Click → TODO
    - Browser(…).Page(…).WebElement(…).Click → actions.click(...)
    - Browser(…).Page(…).WebEdit(…).Set    → actions.type_text(...)
    - Browser(…).Page(…).WebButton(…).Click→ actions.click(...)
    - Browser(…).Page(…).WebList(…).Select → actions.click + TODO
    - Browser(…).Page(…).WebCheckBox(…).Set→ actions.click(...)
    - Browser(…).Page(…).GetROProperty("title") → TODO
    - Browser(…).Sync                       → waits.wait_for_screen_stable(...)

  UFT Win / Java / Dialog objects
    - WinButton("Name").Click               → actions.click(...)
    - WinEdit("Name").Set val               → actions.type_text(...)
    - WinEdit("Name").GetROProperty("value")→ ocr.read_target(...)
    - WinList("Name").Select val            → actions.click + TODO
    - JavaButton("Name").Click              → actions.click(...)
    - JavaEdit("Name").SetText val          → actions.type_text(...)
    - JavaList("Name").Select val           → actions.click + TODO
    - Dialog("Name").WinButton("Name").Click→ actions.click(...)
    - Window("Name").Activate               → citrix / TODO
    - SwfButton("Name").Click               → actions.click(...)

  Page / element existence
    - Page("Name").Exist(n)                 → _screen_exists(or_repo, ..., timeout=n)
    - WebElement("Name").Exist(n)           → _screen_exists(or_repo, ..., timeout=n)

  Data
    - DataTable("Col") / DataTable("Col", dtLocalSheet) → row.require("Col")
    - Environment("Var")                    → os.environ.get("Var", "")

  Reporting
    - Reporter.ReportEvent micPass          → ctx.reporter.passed(...)
    - Reporter.ReportEvent micFail          → ctx.reporter.failed(...) + raise
    - Reporter.ReportEvent micWarning       → ctx.reporter.warning(...)
    - Reporter.ReportEvent micInfo          → ctx.reporter.info(...)

  VBScript expressions (auto-translated inside assignments and conditions)
    - & concatenation                       → str + join
    - InStr(a, b) > 0                       → b in a
    - Len(s), Left/Right/Mid(s,n)           → len(s), s[:n], s[-n:], s[i:i+n]
    - UCase/LCase/Trim/LTrim/RTrim(s)      → s.upper/lower/strip/lstrip/rstrip()
    - Replace(s, find, rep)                 → s.replace(find, rep)
    - CStr/CInt/CLng/CDbl/CSng/CBool(v)    → str/int/int/float/float/bool(v)
    - IsNull/IsEmpty/IsNumeric(v)           → v is None / v is None or v=="" / ...
    - Now() / Date() / Time()              → datetime.now() / .date() / .time()
    - <>, And, Or, Not                      → !=, and, or, not
    - Hungarian notation sVar/bFlag/iN      → var / flag / n  (snake_case)

  System calls
    - MsgBox "..."                          → ctx.logger.info(...)
    - Call FunctionName(args)              → snake_name(args)  # TODO import
    - SystemUtil.Run path                   → subprocess.run([path])  + TODO
    - Wait N                               → waits.wait_for_screen_stable(...)  TODO

Usage
-----
  python3 tools/qfl_to_pyautogui.py --qfl source/qfl/TEST_188001_MEMBER_LOGIN.qfl
  python3 tools/qfl_to_pyautogui.py --qfl source/qfl/TEST_188001_MEMBER_LOGIN.qfl --dry-run
  python3 tools/qfl_to_pyautogui.py --qfl source/qfl/TEST_188001_MEMBER_LOGIN.qfl \\
      --screen epic_login --out-dir output/flows/epic_login
  python3 tools/qfl_to_pyautogui.py --all                  # batch convert source/qfl/*.qfl
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

INDENT = "    "
SEP    = "─" * 68

# ── Confidence tier labels ────────────────────────────────────────────────────
_TIER: dict[str, tuple[int, str]] = {
    "EXACT":    (100, "perfect 1-to-1, no changes needed"),
    "HIGH":     (90,  "correct translation, add OR/YAML entry"),
    "GOOD":     (75,  "translated with TODO; 1-2 min to resolve"),
    "MEDIUM":   (55,  "partial — dropdown/table needs manual work"),
    "LOW":      (30,  "placeholder — write manually"),
    "FALLBACK": (10,  "unrecognised pattern — raw VBScript kept"),
}
CONF = {k: v[0] for k, v in _TIER.items()}


def _tier_label(score: int) -> str:
    if score >= 95: return "EXACT"
    if score >= 85: return "HIGH"
    if score >= 65: return "GOOD"
    if score >= 45: return "MEDIUM"
    if score >= 20: return "LOW"
    return "FALLBACK"


def _quality_label(avg: float) -> str:
    if avg >= 90: return "EXCELLENT"
    if avg >= 75: return "GOOD"
    if avg >= 60: return "FAIR"
    if avg >= 40: return "POOR"
    return "NEEDS REVIEW"


# Toggle for inline `# confidence: TIER (NN) - pattern` comments above each
# translated statement.  Set False via the --no-conf-comments CLI flag.
EMIT_CONF_COMMENTS: bool = True


def _conf_comment(confidence: int, pattern: str) -> str:
    """Render a one-line confidence comment for emit()."""
    return f"# confidence: {_tier_label(confidence)} ({confidence}) - {pattern}"


# ═══════════════════════════════════════════════════════════════════════════════
# Expression helpers
# ═══════════════════════════════════════════════════════════════════════════════

def snake(name: str) -> str:
    """PascalCase / camelCase / "Mixed Words" → snake_case.

    Handles internal separators (space, hyphen, dot, slash) as well as case
    boundaries so element names like ``"Sign In"`` or ``"plan-name"`` become
    ``sign_in`` / ``plan_name`` — important when these strings come from real
    UFT object-repository labels.
    """
    # Replace any non-alphanumeric run with a single underscore.
    s = re.sub(r"[^A-Za-z0-9]+", "_", name)
    # Split camelCase / PascalCase / acronym boundaries.
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower().strip("_")


def py_var(vb: str) -> str:
    """Strip Hungarian notation prefix and snake_case the result."""
    vb = vb.strip()
    m = re.match(r"^(str|arr|obj|lng|dbl|byt|cur|dat|int|bool|s|b|i|n|d|f|l)([A-Z])", vb)
    if m:
        vb = vb[len(m.group(1)):]
    return snake(vb)


def _split_vb_concat(expr: str) -> list[str]:
    """Split on ``&`` outside string literals AND outside parentheses.

    Concatenation in VBScript is the ``&`` operator; nested function calls and
    grouping must NOT be split. e.g. ``foo(a & b) & c`` → ``["foo(a & b)", "c"]``.
    """
    parts: list[str] = []
    current = ""
    in_str = False
    depth = 0
    for ch in expr:
        if ch == '"':
            in_str = not in_str
            current += ch
        elif ch == '(' and not in_str:
            depth += 1
            current += ch
        elif ch == ')' and not in_str:
            depth = max(0, depth - 1)
            current += ch
        elif ch == '&' and not in_str and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    return [p for p in parts if p]


def _translate_vbfunc(vb: str) -> str | None:
    """Translate a recognised VBScript built-in function call. Returns None if unknown."""
    # Len(s)
    m = re.match(r"^Len\s*\((.+)\)$", vb, re.I)
    if m: return f"len({py_var(m.group(1).strip())})"
    # UCase / LCase
    m = re.match(r"^UCase\s*\((.+)\)$", vb, re.I)
    if m: return f"{py_var(m.group(1).strip())}.upper()"
    m = re.match(r"^LCase\s*\((.+)\)$", vb, re.I)
    if m: return f"{py_var(m.group(1).strip())}.lower()"
    # Trim / LTrim / RTrim
    m = re.match(r"^Trim\s*\((.+)\)$", vb, re.I)
    if m: return f"{py_var(m.group(1).strip())}.strip()"
    m = re.match(r"^LTrim\s*\((.+)\)$", vb, re.I)
    if m: return f"{py_var(m.group(1).strip())}.lstrip()"
    m = re.match(r"^RTrim\s*\((.+)\)$", vb, re.I)
    if m: return f"{py_var(m.group(1).strip())}.rstrip()"
    # Left(s, n) / Right(s, n)
    m = re.match(r"^Left\s*\((.+),\s*(\d+)\)$", vb, re.I)
    if m: return f"{py_var(m.group(1).strip())}[:{m.group(2)}]"
    m = re.match(r"^Right\s*\((.+),\s*(\d+)\)$", vb, re.I)
    if m: return f"{py_var(m.group(1).strip())}[-{m.group(2)}:]"
    # Mid(s, start, len) — VBScript is 1-indexed
    m = re.match(r"^Mid\s*\((.+),\s*(\d+),\s*(\d+)\)$", vb, re.I)
    if m:
        start = int(m.group(2)) - 1
        end   = start + int(m.group(3))
        return f"{py_var(m.group(1).strip())}[{start}:{end}]"
    # Replace(s, find, rep)
    m = re.match(r'^Replace\s*\((.+),\s*(".*?"),\s*(".*?")\)$', vb, re.I)
    if m: return f"{py_var(m.group(1).strip())}.replace({m.group(2)}, {m.group(3)})"
    # Type conversions
    m = re.match(r"^C(Str|Int|Lng|Dbl|Sng|Bool)\s*\((.+)\)$", vb, re.I)
    if m:
        typ = {"Str": "str", "Int": "int", "Lng": "int",
               "Dbl": "float", "Sng": "float", "Bool": "bool"}[m.group(1).capitalize()]
        return f"{typ}({py_var(m.group(2).strip())})"
    # Now / Date / Time
    if re.match(r"^Now\s*\(\s*\)$", vb, re.I): return "datetime.now()"
    if re.match(r"^Date\s*\(\s*\)$", vb, re.I): return "datetime.now().date()"
    if re.match(r"^Time\s*\(\s*\)$", vb, re.I): return "datetime.now().time()"
    # Abs / Int / Round
    m = re.match(r"^Abs\s*\((.+)\)$", vb, re.I)
    if m: return f"abs({py_var(m.group(1).strip())})"
    m = re.match(r"^Round\s*\((.+),\s*(\d+)\)$", vb, re.I)
    if m: return f"round({py_var(m.group(1).strip())}, {m.group(2)})"
    # Environment("Var")
    m = re.match(r'^Environment\s*\(\s*"(\w+)"\s*\)$', vb, re.I)
    if m: return f'os.environ.get("{m.group(1)}", "")'
    # Split(s, delim) — keep first two args; ignore VBScript limit/compare flags.
    m = re.match(r"^Split\s*\((.+?),\s*((?:\"[^\"]*\")|(?:'[^']*'))(?:\s*,[^)]*)?\)$", vb, re.I)
    if m: return f"{py_var(m.group(1).strip())}.split({m.group(2).strip()})"
    # Join(arr, delim)
    m = re.match(r"^Join\s*\((.+?),\s*((?:\"[^\"]*\")|(?:'[^']*'))\)$", vb, re.I)
    if m: return f"{m.group(2).strip()}.join({py_var(m.group(1).strip())})"
    # Chr / Asc / Hex / Oct
    m = re.match(r"^Chr\s*\((.+)\)$", vb, re.I)
    if m: return f"chr({py_var(m.group(1).strip())})"
    m = re.match(r'^Asc\s*\((.+)\)$', vb, re.I)
    if m: return f"ord({m.group(1).strip()})"
    m = re.match(r"^Hex\s*\((.+)\)$", vb, re.I)
    if m: return f'format({py_var(m.group(1).strip())}, "X")'
    m = re.match(r"^Oct\s*\((.+)\)$", vb, re.I)
    if m: return f'format({py_var(m.group(1).strip())}, "o")'
    # UBound / LBound
    m = re.match(r"^UBound\s*\((.+)\)$", vb, re.I)
    if m: return f"len({py_var(m.group(1).strip())}) - 1"
    m = re.match(r"^LBound\s*\((.+)\)$", vb, re.I)
    if m: return "0"
    # Array(a, b, c) → [a, b, c]
    m = re.match(r"^Array\s*\((.*)\)$", vb, re.I)
    if m:
        inner = m.group(1).strip()
        if not inner: return "[]"
        return "[" + ", ".join(py_expr(p.strip()) for p in inner.split(",")) + "]"
    # String(n, "x") → "x" * n
    m = re.match(r'^String\s*\(\s*(\d+)\s*,\s*"([^"]+)"\s*\)$', vb, re.I)
    if m: return f'"{m.group(2)}" * {m.group(1)}'
    # Space(n) → " " * n
    m = re.match(r"^Space\s*\(\s*(\d+)\s*\)$", vb, re.I)
    if m: return f'" " * {m.group(1)}'
    # StrReverse(s)
    m = re.match(r"^StrReverse\s*\((.+)\)$", vb, re.I)
    if m: return f"{py_var(m.group(1).strip())}[::-1]"
    # InStr(hay, needle) used as expression (not condition)
    m = re.match(r"^InStr\s*\((.+?)\s*,\s*(.+)\)$", vb, re.I)
    if m: return f"({py_var(m.group(1).strip())}.find({py_expr(m.group(2).strip())}) + 1)"
    # Year/Month/Day/Hour/Minute/Second(date)
    m = re.match(r"^(Year|Month|Day|Hour|Minute|Second)\s*\((.+)\)$", vb, re.I)
    if m:
        attr = m.group(1).lower()
        return f"{py_var(m.group(2).strip())}.{attr}"
    # Int(x) — VBScript "Int" truncates toward -inf, mostly used like int() on positives.
    m = re.match(r"^Int\s*\((.+)\)$", vb, re.I)
    if m: return f"int({py_var(m.group(1).strip())})"
    # FormatNumber(x, n) → f"{x:.nf}"
    m = re.match(r"^FormatNumber\s*\(\s*(.+?)\s*,\s*(\d+)\s*\)$", vb, re.I)
    if m: return f'f"{{{py_var(m.group(1).strip())}:.{m.group(2)}f}}"'
    return None


def py_expr(vb: str) -> str:
    """Translate a VBScript value/expression to Python."""
    vb = vb.strip()
    if not vb:
        return '""'

    # DataTable("Col")
    m = re.match(r'^DataTable\s*\(\s*"(\w+)"[^)]*\)\s*$', vb, re.I)
    if m:
        return f'row.require("{m.group(1)}")'

    # String literal
    if vb.startswith('"') and vb.endswith('"') and vb.count('"') == 2:
        return vb

    # Boolean
    if vb.lower() == "true":  return "True"
    if vb.lower() == "false": return "False"

    # Nothing / Null / Empty
    if vb.lower() in ("nothing", "null", "empty"): return "None"

    # Numeric
    if re.match(r"^\d+(\.\d+)?$", vb):
        return vb

    # VBScript built-in function
    translated = _translate_vbfunc(vb)
    if translated:
        return translated

    # Pure variable name
    if re.match(r"^[a-zA-Z_]\w*$", vb):
        return py_var(vb)

    # VBScript & concatenation
    if "&" in vb:
        parts = _split_vb_concat(vb)
        py_parts: list[str] = []
        for p in parts:
            m2 = re.match(r'^DataTable\s*\(\s*"(\w+)"[^)]*\)\s*$', p, re.I)
            if m2:
                py_parts.append(f'row.require("{m2.group(1)}")')
            elif p.startswith('"') and p.endswith('"'):
                py_parts.append(p)
            elif re.match(r"^[a-zA-Z_]\w*$", p):
                py_parts.append(py_var(p))
            elif re.match(r"^\d+(\.\d+)?$", p):
                py_parts.append(p)
            else:
                func_t = _translate_vbfunc(p)
                if func_t:
                    py_parts.append(func_t)
                else:
                    py_parts.append(f"str({py_var(p)})")
        return " + ".join(py_parts)

    # Unrecognised — return a placeholder that is still valid Python so the
    # surrounding statement parses. The trailing comment carries the original
    # VBScript so a human reviewer can finish the translation. Previously this
    # returned a bare ``# TODO …`` which produced syntax errors when used on
    # the right-hand side of an assignment.
    safe_vb = vb.replace("\n", " ")
    return f'None  # TODO: translate expression — {safe_vb}'


# Module-level mutable; set by converter before translating each function.
_screen = "epic_screen"


def py_cond(vb: str) -> str:
    """Translate a VBScript Boolean condition to Python."""
    expr = vb.strip()
    expr = re.sub(r"\s+Then\s*$", "", expr, flags=re.I).strip()

    # InStr(hay, needle) > 0 / >= 1
    def sub_instr_pos(m: re.Match) -> str:
        hay  = py_var(m.group(1).strip())
        ndl  = py_expr(m.group(2).strip())
        op, n = m.group(3).strip(), m.group(4).strip()
        if (op == ">" and n == "0") or (op == ">=" and n == "1"):
            return f"{ndl} in {hay}"
        return f"({hay}.find({ndl}) {op} {n})"
    expr = re.sub(
        r"InStr\s*\(\s*(\w+)\s*,\s*([^)]+)\)\s*([><=!]+)\s*(\d+)",
        sub_instr_pos, expr, flags=re.I,
    )

    # IsNull / IsEmpty / IsNumeric
    def sub_isnull(m: re.Match) -> str:
        return f"{py_var(m.group(1).strip())} is None"
    expr = re.sub(r"IsNull\s*\(\s*(\w+)\s*\)", sub_isnull, expr, flags=re.I)

    def sub_isempty(m: re.Match) -> str:
        v = py_var(m.group(1).strip())
        return f"({v} is None or {v} == \"\")"
    expr = re.sub(r"IsEmpty\s*\(\s*(\w+)\s*\)", sub_isempty, expr, flags=re.I)

    def sub_isnumeric(m: re.Match) -> str:
        return f"str({py_var(m.group(1).strip())}).isnumeric()"
    expr = re.sub(r"IsNumeric\s*\(\s*(\w+)\s*\)", sub_isnumeric, expr, flags=re.I)

    # Page("X").Exist(n) → _screen_exists(...)
    def sub_page_exist(m: re.Match) -> str:
        page, tmout = m.group(1), m.group(2)
        anchor = f"{snake(page)}.header_label"
        return f'_screen_exists(or_repo, "{anchor}", timeout={tmout})'
    expr = re.sub(
        r'Page\s*\(\s*"(\w+)"\s*\)\s*\.Exist\s*\(\s*(\d+)\s*\)',
        sub_page_exist, expr, flags=re.I,
    )

    # WebElement("X").Exist(n) → _screen_exists(...)
    def sub_elem_exist(m: re.Match) -> str:
        elem, tmout = m.group(1), m.group(2)
        return f'_screen_exists(or_repo, "{_screen}.{snake(elem)}", timeout={tmout})'
    expr = re.sub(
        r'WebElement\s*\(\s*"(\w+)"\s*\)\s*\.Exist\s*\(\s*(\d+)\s*\)',
        sub_elem_exist, expr, flags=re.I,
    )

    # WebList("X").GetROProperty("value")
    def sub_list_prop(m: re.Match) -> str:
        elem = m.group(1)
        return f'ocr.read_target("{_screen}.{snake(elem)}_text").text'
    expr = re.sub(
        r'WebList\s*\(\s*"(\w+)"\s*\)\s*\.GetROProperty\s*\(\s*"value"\s*\)',
        sub_list_prop, expr, flags=re.I,
    )

    # VBScript operators (order matters — replace <> before turning bare = into ==).
    expr = expr.replace("<>", "!=")
    # Convert bare `=` to `==` for equality comparison, but skip operators that
    # already include `=` (==, <=, >=, !=) and skip `=` inside string literals.
    expr = _equate_bare_equals(expr)
    expr = re.sub(r"\bNot\b\s*", "not ", expr, flags=re.I)
    expr = re.sub(r"\bAnd\b",     "and",  expr, flags=re.I)
    expr = re.sub(r"\bOr\b",      "or",   expr, flags=re.I)

    # Err.Number / Err.Description map to a thread-local _err object the runtime
    # provides inside On Error Resume Next blocks. For now expose as `_err.*`.
    expr = re.sub(r"\bErr\s*\.\s*(Number|Description|Source)\b",
                  lambda m: f"_err.{m.group(1).lower()}", expr, flags=re.I)

    # Hungarian variable references
    def sub_vbvar(m: re.Match) -> str:
        return py_var(m.group(0))
    expr = re.sub(r"\b[sibdnflr][A-Z]\w*\b", sub_vbvar, expr)

    return expr.strip()


def _equate_bare_equals(expr: str) -> str:
    """Replace ``=`` with ``==`` only where it means equality, not assignment.

    Skips:
      - operators that already include ``=`` (``==``, ``!=``, ``<=``, ``>=``)
      - ``=`` inside string literals
      - keyword-arg style ``name=value`` (none of which VBScript conditions use,
        but the rule is conservative anyway).
    """
    out: list[str] = []
    in_str = False
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == '"':
            in_str = not in_str
            out.append(ch)
            i += 1
            continue
        if ch == '=' and not in_str:
            prev = expr[i - 1] if i > 0 else ""
            nxt  = expr[i + 1] if i + 1 < len(expr) else ""
            if prev in "!<>=:" or nxt == "=":
                out.append(ch)          # part of an existing multi-char op
            else:
                out.append("==")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ═══════════════════════════════════════════════════════════════════════════════
# Statement translator
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StmtResult:
    lines:      list[str]
    confidence: int  = 100        # 0–100 conversion confidence
    pattern:    str  = ""         # human label of matched UFT pattern
    is_data_load: bool = False
    data_col:   str  = ""
    data_var:   str  = ""
    obj_name:   str  = ""
    obj_type:   str  = ""
    ocr_name:   str  = ""


def _obj(screen: str, elem: str, obj_type: str = "button") -> tuple[str, str]:
    """Return (logical_name, obj_type) for an element."""
    return f"{screen}.{snake(elem)}", obj_type


def _normalise_descriptive_programming(stmt: str) -> str:
    """Collapse UFT descriptive programming into single-name form.

    UFT lets test authors identify a runtime object by property pairs, e.g.::

        WebButton("name:=Save", "html id:=btn-save", "type:=submit").Click

    For converter purposes we only need a stable logical name. We pick the
    ``name:=`` value (preferred), or fall back to the first quoted property
    value, and rewrite the call as ``WebButton("Save").Click``. This lets
    every downstream regex stay simple.

    The transform is a no-op for ordinary single-string identifiers.
    """
    pattern = re.compile(
        r'((?:Web|Win|Java|Sap|Swf|Mobile|Page|Browser|Dialog|Window|Frame|Image)\w*)\s*'
        r'\(((?:"[^"]*"\s*,?\s*)+)\)'
    )

    def _pick(quotes_blob: str) -> str:
        # Extract all quoted strings.
        parts = re.findall(r'"([^"]*)"', quotes_blob)
        # Prefer name:= over anything else.
        for p in parts:
            m = re.match(r"^\s*name\s*:=\s*(.+)$", p, re.I)
            if m:
                return m.group(1).strip()
        # Otherwise strip prop:= from the first part.
        if parts:
            m = re.match(r"^\s*[\w\s]+:=\s*(.+)$", parts[0])
            return (m.group(1) if m else parts[0]).strip()
        return ""

    def sub(m: re.Match) -> str:
        obj = m.group(1)
        chosen = _pick(m.group(2))
        return f'{obj}("{chosen}")'

    return pattern.sub(sub, stmt)


def translate_stmt(stripped: str, screen: str) -> StmtResult:  # noqa: C901 (complexity ok)
    """Translate one VBScript statement to Python. Returns a StmtResult."""
    global _screen
    _screen = screen
    # Collapse descriptive programming so the rest of this function deals only
    # with the simple single-string identifier form.
    stripped = _normalise_descriptive_programming(stripped)

    # ── Dim declarations ─────────────────────────────────────────────────────
    if re.match(r"^Dim\b", stripped, re.I):
        return StmtResult(lines=[], confidence=100, pattern="Dim (removed)")

    # ── Option Explicit / ReDim / Public/Private bare decls ───────────────────
    if re.match(r"^Option\s+Explicit\s*$", stripped, re.I):
        return StmtResult(lines=[], confidence=100, pattern="Option Explicit (removed)")
    m = re.match(r"^ReDim\s+(?:Preserve\s+)?(\w+)\s*\((.+)\)\s*$", stripped, re.I)
    if m:
        var, size = py_var(m.group(1)), py_expr(m.group(2).strip())
        return StmtResult(
            lines=[f"{var} = [None] * ({size} + 1)"],
            confidence=CONF["HIGH"], pattern="ReDim",
        )

    # ── Const NAME = value ────────────────────────────────────────────────────
    m = re.match(r"^Const\s+(\w+)\s*=\s*(.+)$", stripped, re.I)
    if m:
        name, val = m.group(1).upper(), py_expr(m.group(2).strip())
        return StmtResult(
            lines=[f"{name} = {val}"],
            confidence=100, pattern="Const",
        )

    # ── Wait N — translate to a synchronisation call ──────────────────────────
    # Accepts ``Wait 2`` and ``Wait(2)``; emits ``waits.wait_for_screen_stable(...)``
    # with timeout=N as the preferred sync. A TODO comment points the user to a
    # tighter region if they need one. Score: HIGH — generated code is callable.
    m = re.match(r"^Wait\s*\(?\s*(\d+(?:\.\d+)?)\s*\)?\s*$", stripped, re.I)
    if m:
        n = m.group(1)
        return StmtResult(
            lines=[
                f"# Wait {n}s — prefer waits.wait_for_screen_stable / wait_for_object_exists",
                f"# TODO: tighten region= to the area being waited on for faster sync",
                f"waits.wait_for_screen_stable(region=(0, 0, 1920, 1080), timeout={n})",
            ],
            confidence=CONF["HIGH"], pattern=f"Wait {n}",
        )

    # ── Exit Function / Exit Sub ──────────────────────────────────────────────
    if re.match(r"^Exit\s+(Function|Sub)\s*$", stripped, re.I):
        return StmtResult(lines=["return"], confidence=100, pattern="Exit Function")

    # ── Exit For / Exit Do — break out of the loop ────────────────────────────
    if re.match(r"^Exit\s+(For|Do)\s*$", stripped, re.I):
        return StmtResult(lines=["break"], confidence=100, pattern="Exit loop")

    # ── Err.Clear / Err.Raise ─────────────────────────────────────────────────
    if re.match(r"^Err\s*\.\s*Clear\s*$", stripped, re.I):
        return StmtResult(
            lines=["# Err.Clear — handled by leaving the surrounding try/except"],
            confidence=CONF["HIGH"], pattern="Err.Clear",
        )
    m = re.match(r"^Err\s*\.\s*Raise\s+(.+)$", stripped, re.I)
    if m:
        return StmtResult(
            lines=[f"raise RuntimeError(\"Err.Raise: \" + str({py_expr(m.group(1).strip())}))"],
            confidence=CONF["HIGH"], pattern="Err.Raise",
        )

    # ── DataTable read ────────────────────────────────────────────────────────
    m = re.match(r'^(\w+)\s*=\s*DataTable\s*\(\s*"(\w+)"[^)]*\)\s*$', stripped, re.I)
    if m:
        var, col = py_var(m.group(1)), m.group(2)
        return StmtResult(
            lines=[f'{var} = row.require("{col}")'],
            confidence=100, pattern="DataTable read",
            is_data_load=True, data_col=col, data_var=var,
        )

    # ── Environment("Var") read ───────────────────────────────────────────────
    m = re.match(r'^(\w+)\s*=\s*Environment\s*\(\s*"(\w+)"\s*\)\s*$', stripped, re.I)
    if m:
        var, key = py_var(m.group(1)), m.group(2)
        return StmtResult(
            lines=[
                "import os  # ensure os is imported at top of file",
                f'{var} = os.environ.get("{key}", "")',
            ],
            confidence=CONF["HIGH"], pattern="Environment variable",
        )

    # ── Reporter.ReportEvent micPass ─────────────────────────────────────────
    m = re.match(
        r'^Reporter\s*\.\s*ReportEvent\s+micPass\s*,\s*"([^"]+)"\s*,\s*(.+)$',
        stripped, re.I,
    )
    if m:
        label, msg = m.group(1), py_expr(m.group(2).strip())
        return StmtResult(
            lines=[f'ctx.reporter.passed("{label}", {msg})'],
            confidence=100, pattern="Reporter micPass",
        )

    # ── Reporter.ReportEvent micFail ─────────────────────────────────────────
    m = re.match(
        r'^Reporter\s*\.\s*ReportEvent\s+micFail\s*,\s*"([^"]+)"\s*,\s*(.+)$',
        stripped, re.I,
    )
    if m:
        label, msg = m.group(1), py_expr(m.group(2).strip())
        return StmtResult(
            lines=[
                f'ctx.reporter.failed("{label}", {msg})',
                f'raise AssertionError("{label} failed")',
            ],
            confidence=100, pattern="Reporter micFail",
        )

    # ── Reporter.ReportEvent micWarning ─────────────────────────────────────
    m = re.match(
        r'^Reporter\s*\.\s*ReportEvent\s+mic(Warning|Info)\s*,\s*"([^"]+)"\s*,\s*(.+)$',
        stripped, re.I,
    )
    if m:
        level = m.group(1).lower()
        label, msg = m.group(2), py_expr(m.group(3).strip())
        return StmtResult(
            lines=[f'ctx.reporter.{level}("{label}", {msg})'],
            confidence=100, pattern=f"Reporter mic{m.group(1)}",
        )

    # ══ Helpers shared with descriptive programming ═══════════════════════════
    # If the object name uses UFT's descriptive-programming form, e.g.
    # ``WebButton("name:=Save", "html id:=btn-save")``, extract the "name:=" or
    # the first quoted value. Element names captured by the regex below are
    # already the inner string between the outer quotes, so we just unwrap any
    # leading ``<prop>:=`` prefix here.
    def _strip_desc_prefix(raw: str) -> str:
        # ``name:=Save``  →  ``Save``   (any property:= prefix is dropped)
        m_strip = re.match(r"^\s*[\w\s]+:=\s*(.+)$", raw)
        return (m_strip.group(1) if m_strip else raw).strip()

    # ══ UFT Web object actions ════════════════════════════════════════════════

    # ── WebEdit.Set ───────────────────────────────────────────────────────────
    m = re.match(r'^WebEdit\s*\(\s*"(\w+)"\s*\)\s*\.Set\s+(.+)$', stripped, re.I)
    if m:
        elem, val = m.group(1), py_expr(m.group(2))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[f'actions.type_text("{logical}", {val})'],
            confidence=100, pattern="WebEdit.Set",
            obj_name=logical, obj_type=otype,
        )

    # ── WebEdit.SetSecure / SetEncrypted ─────────────────────────────────────
    m = re.match(r'^WebEdit\s*\(\s*"(\w+)"\s*\)\s*\.(SetSecure|SetEncrypted)\s+(.+)$', stripped, re.I)
    if m:
        elem, method, val = m.group(1), m.group(2), py_expr(m.group(3))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[
                f"# NOTE: {method} → using plain type_text (mask in logs if sensitive)",
                f'actions.type_text("{logical}", {val})',
            ],
            confidence=CONF["HIGH"], pattern=f"WebEdit.{method}",
            obj_name=logical, obj_type=otype,
        )

    # ── WebEdit.GetROProperty("value"/"innerText") ────────────────────────────
    m = re.match(
        r'^(\w+)\s*=\s*WebEdit\s*\(\s*"(\w+)"\s*\)\s*\.GetROProperty\s*\(\s*"(value|innerText|text)"\s*\)',
        stripped, re.I,
    )
    if m:
        var, elem = py_var(m.group(1)), m.group(2)
        ocr_name = f"{screen}.{snake(elem)}_text"
        return StmtResult(
            lines=[
                f'{var}_result = ocr.read_target("{ocr_name}")',
                f"{var} = {var}_result.text",
            ],
            confidence=CONF["HIGH"], pattern="WebEdit.GetROProperty",
            ocr_name=ocr_name,
        )

    # ── WebEdit.Click ─────────────────────────────────────────────────────────
    m = re.match(r'^WebEdit\s*\(\s*"(\w+)"\s*\)\s*\.Click\s*$', stripped, re.I)
    if m:
        logical, otype = _obj(screen, m.group(1), "input")
        return StmtResult(
            lines=[f'actions.click("{logical}")'],
            confidence=100, pattern="WebEdit.Click",
            obj_name=logical, obj_type=otype,
        )

    # ── WebButton.Click ───────────────────────────────────────────────────────
    m = re.match(r'^WebButton\s*\(\s*"(\w+)"\s*\)\s*\.Click\s*$', stripped, re.I)
    if m:
        logical, otype = _obj(screen, m.group(1), "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")'],
            confidence=100, pattern="WebButton.Click",
            obj_name=logical, obj_type=otype,
        )

    # ── WebLink.Click ─────────────────────────────────────────────────────────
    m = re.match(r'^WebLink\s*\(\s*"(\w+)"\s*\)\s*\.Click\s*$', stripped, re.I)
    if m:
        logical, otype = _obj(screen, m.group(1), "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")'],
            confidence=100, pattern="WebLink.Click",
            obj_name=logical, obj_type=otype,
        )

    # ── WebElement.Click ──────────────────────────────────────────────────────
    m = re.match(r'^WebElement\s*\(\s*"(\w+)"\s*\)\s*\.Click\s*$', stripped, re.I)
    if m:
        logical, otype = _obj(screen, m.group(1), "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")'],
            confidence=100, pattern="WebElement.Click",
            obj_name=logical, obj_type=otype,
        )

    # ── WebElement.FireEvent ──────────────────────────────────────────────────
    m = re.match(r'^WebElement\s*\(\s*"(\w+)"\s*\)\s*\.FireEvent\s+"([^"]+)"', stripped, re.I)
    if m:
        elem, event = m.group(1), m.group(2)
        logical, otype = _obj(screen, elem, "button")
        return StmtResult(
            lines=[
                f'# NOTE: FireEvent "{event}" → simulating as click',
                f'actions.click("{logical}")',
            ],
            confidence=CONF["GOOD"], pattern="WebElement.FireEvent",
            obj_name=logical, obj_type=otype,
        )

    # ── WebElement.SetAttribute ───────────────────────────────────────────────
    m = re.match(r'^WebElement\s*\(\s*"(\w+)"\s*\)\s*\.SetAttribute\s+"([^"]+)"\s*,\s*(.+)$', stripped, re.I)
    if m:
        elem, attr, val = m.group(1), m.group(2), py_expr(m.group(3))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[
                f'# TODO: SetAttribute "{attr}" → use type_text or JS injection',
                f'actions.type_text("{logical}", {val})',
            ],
            confidence=CONF["MEDIUM"], pattern="WebElement.SetAttribute",
            obj_name=logical, obj_type=otype,
        )

    # ── WebElement.GetROProperty ──────────────────────────────────────────────
    m = re.match(
        r'^(\w+)\s*=\s*WebElement\s*\(\s*"(\w+)"\s*\)\s*\.GetROProperty\s*\(\s*"([^"]+)"\s*\)',
        stripped, re.I,
    )
    if m:
        var, elem, prop = py_var(m.group(1)), m.group(2), m.group(3)
        if prop.lower() in ("innertext", "value", "text", "innerhtml"):
            ocr_name = f"{screen}.{snake(elem)}_text"
            return StmtResult(
                lines=[
                    f'{var}_result = ocr.read_target("{ocr_name}")',
                    f"{var} = {var}_result.text",
                ],
                confidence=CONF["HIGH"], pattern="WebElement.GetROProperty(text)",
                ocr_name=ocr_name,
            )
        return StmtResult(
            lines=[
                f'# TODO: GetROProperty("{prop}") — use OCR or waits to verify visual state',
                f'{var} = "TODO_{snake(elem)}_{snake(prop)}"',
            ],
            confidence=CONF["LOW"], pattern=f"WebElement.GetROProperty({prop})",
        )

    # ── WebCheckBox.Set ───────────────────────────────────────────────────────
    m = re.match(r'^WebCheckBox\s*\(\s*"(\w+)"\s*\)\s*\.Set\s+(.+)$', stripped, re.I)
    if m:
        elem, state = m.group(1), m.group(2).strip().strip('"').upper()
        logical, otype = _obj(screen, elem, "button")
        on_state = "ON" in state or state == "TRUE"
        return StmtResult(
            lines=[
                f'# Checkbox: click only if state needs to change → verify with OCR first',
                f'actions.click("{logical}")  # sets to {"checked" if on_state else "unchecked"}',
            ],
            confidence=CONF["HIGH"], pattern="WebCheckBox.Set",
            obj_name=logical, obj_type=otype,
        )

    # ── WebRadioGroup.Select ──────────────────────────────────────────────────
    m = re.match(r'^WebRadioGroup\s*\(\s*"(\w+)"\s*\)\s*\.Select\s+(.+)$', stripped, re.I)
    if m:
        elem, val = m.group(1), py_expr(m.group(2))
        logical, otype = _obj(screen, elem, "button")
        return StmtResult(
            lines=[
                f'# TODO: locate radio option by OCR and click',
                f'actions.click("{logical}")  # option: {val}',
            ],
            confidence=CONF["GOOD"], pattern="WebRadioGroup.Select",
            obj_name=logical, obj_type=otype,
        )

    # ── WebList.Select ────────────────────────────────────────────────────────
    m = re.match(r'^WebList\s*\(\s*"(\w+)"\s*\)\s*\.Select\s+(.+)$', stripped, re.I)
    if m:
        elem, val = m.group(1), py_expr(m.group(2))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[
                f"# TODO: dropdown select — click to open, then locate option by OCR",
                f'actions.click("{logical}")',
                f"actions.type_text(\"{logical}\", {val})  # or use arrow-key navigation",
            ],
            confidence=CONF["MEDIUM"], pattern="WebList.Select",
            obj_name=logical, obj_type=otype,
        )

    # ── WebList.GetROProperty ─────────────────────────────────────────────────
    m = re.match(
        r'^(\w+)\s*=\s*WebList\s*\(\s*"(\w+)"\s*\)\s*\.GetROProperty\s*\(\s*"value"\s*\)',
        stripped, re.I,
    )
    if m:
        var, elem = py_var(m.group(1)), m.group(2)
        ocr_name = f"{screen}.{snake(elem)}_text"
        return StmtResult(
            lines=[
                f'{var}_result = ocr.read_target("{ocr_name}")',
                f"{var} = {var}_result.text",
            ],
            confidence=CONF["HIGH"], pattern="WebList.GetROProperty",
            ocr_name=ocr_name,
        )

    # ── WebFile.Set ───────────────────────────────────────────────────────────
    m = re.match(r'^WebFile\s*\(\s*"(\w+)"\s*\)\s*\.Set\s+(.+)$', stripped, re.I)
    if m:
        elem, val = m.group(1), py_expr(m.group(2))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[
                f'# TODO: file upload — type the path and press Enter',
                f'actions.type_text("{logical}", {val})',
                f'actions.press("enter")',
            ],
            confidence=CONF["GOOD"], pattern="WebFile.Set",
            obj_name=logical, obj_type=otype,
        )

    # ── WebTable.ChildItem click ──────────────────────────────────────────────
    m = re.match(r'^WebTable\s*\(\s*"(\w+)"\s*\)\s*\.ChildItem\s*\((.+)\)\s*\.Click', stripped, re.I)
    if m:
        elem, coords = m.group(1), m.group(2)
        return StmtResult(
            lines=[
                f'# TODO: table cell click — locate row/col by OCR: WebTable("{elem}") ChildItem({coords})',
                f'# Use ocr.read_target to find the row, then actions.click on the cell',
            ],
            confidence=CONF["LOW"], pattern="WebTable.ChildItem.Click",
        )

    # ── DblClick / DoubleClick / RightClick — for any UFT object class ────────
    # We match the common forms by class; each falls back to actions.click().
    m = re.match(
        r'^(Web\w+|Win\w+|Java\w+|Image)\s*\(\s*"([^"]+)"\s*\)\s*\.(DblClick|DoubleClick|RightClick)\s*$',
        stripped, re.I,
    )
    if m:
        elem, method = m.group(2), m.group(3)
        logical, otype = _obj(screen, elem, "button")
        is_double = method.lower() in ("dblclick", "doubleclick")
        is_right  = method.lower() == "rightclick"
        kwargs = []
        if is_double: kwargs.append("double=True")
        if is_right:  kwargs.append('button="right"')
        call = f'actions.click("{logical}"' + (", " + ", ".join(kwargs) if kwargs else "") + ")"
        return StmtResult(
            lines=[call],
            confidence=CONF["HIGH"], pattern=f"{m.group(1)}.{method}",
            obj_name=logical, obj_type=otype,
        )

    # ── .Type / .SendKeys — type literal text into the focused element ────────
    m = re.match(
        r'^(Web\w+|Win\w+|Java\w+)\s*\(\s*"([^"]+)"\s*\)\s*\.(Type|SendKeys)\s+(.+)$',
        stripped, re.I,
    )
    if m:
        elem, val = m.group(2), py_expr(m.group(4))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[f'actions.type_text("{logical}", {val})'],
            confidence=CONF["HIGH"], pattern=f"{m.group(1)}.{m.group(3)}",
            obj_name=logical, obj_type=otype,
        )

    # ── .WaitProperty(prop, value, timeout) — element appearance with timeout ─
    m = re.match(
        r'^(Web\w+|Win\w+|Java\w+)\s*\(\s*"([^"]+)"\s*\)\s*\.WaitProperty\s+'
        r'"([^"]+)"\s*,\s*([^,]+)\s*,\s*(\d+)\s*$',
        stripped, re.I,
    )
    if m:
        cls, elem, prop, target, tmout = m.groups()
        logical, otype = _obj(screen, elem, "button")
        return StmtResult(
            lines=[
                f'# WaitProperty("{prop}", {target}) — implemented as wait_for_object_exists',
                f'waits.wait_for_object_exists(or_repo.get("{logical}"), timeout={tmout})',
            ],
            confidence=CONF["HIGH"], pattern=f"{cls}.WaitProperty",
            obj_name=logical, obj_type=otype,
        )

    # ── Image("X").Click / WebImage("X").Click ────────────────────────────────
    m = re.match(r'^(Web)?Image\s*\(\s*"([^"]+)"\s*\)\s*\.Click\s*$', stripped, re.I)
    if m:
        elem = m.group(2)
        logical, otype = _obj(screen, elem, "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")'],
            confidence=100, pattern=f"{m.group(1) or ''}Image.Click",
            obj_name=logical, obj_type=otype,
        )

    # ── WinComboBox.Select / WinComboBox.Select#N ─────────────────────────────
    m = re.match(r'^WinComboBox\s*\(\s*"([^"]+)"\s*\)\s*\.Select\s+(.+)$', stripped, re.I)
    if m:
        elem, val = m.group(1), py_expr(m.group(2))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[
                f"# TODO: WinComboBox dropdown — click and arrow-key navigate",
                f'actions.click("{logical}")',
                f'actions.type_text("{logical}", {val})',
            ],
            confidence=CONF["MEDIUM"], pattern="WinComboBox.Select",
            obj_name=logical, obj_type=otype,
        )

    # ── WinCheckBox.Set / WinRadioButton.Set ──────────────────────────────────
    m = re.match(r'^(WinCheckBox|WinRadioButton)\s*\(\s*"([^"]+)"\s*\)\s*\.Set\s+(.+)$',
                 stripped, re.I)
    if m:
        cls, elem, _state = m.group(1), m.group(2), m.group(3)
        logical, otype = _obj(screen, elem, "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")  # {cls}.Set — verify state first if toggle is critical'],
            confidence=CONF["HIGH"], pattern=f"{cls}.Set",
            obj_name=logical, obj_type=otype,
        )

    # ── Browser(…).Page(…).Frame(…).WebX(…).METHOD — handled by stripping the
    #    Frame() segment so the existing Browser.Page handlers below match. ──
    if re.search(r'Frame\s*\([^)]+\)\s*\.', stripped, re.I):
        stripped = re.sub(r'\.\s*Frame\s*\([^)]+\)\s*\.', '.', stripped)

    # ── Browser(…).Page(…).WebButton(…).Click ────────────────────────────────
    m = re.match(
        r'^Browser\([^)]+\)\s*\.\s*Page\([^)]+\)\s*\.\s*WebButton\s*\(\s*"([^"]+)"\s*\)\s*\.Click',
        stripped, re.I,
    )
    if m:
        logical, otype = _obj(screen, m.group(1), "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")'],
            confidence=100, pattern="Browser.Page.WebButton.Click",
            obj_name=logical, obj_type=otype,
        )

    # ── Browser(…).Page(…).WebEdit(…).Set ────────────────────────────────────
    m = re.match(
        r'^Browser\([^)]+\)\s*\.\s*Page\([^)]+\)\s*\.\s*WebEdit\s*\(\s*"(\w+)"\s*\)\s*\.Set\s+(.+)$',
        stripped, re.I,
    )
    if m:
        elem, val = m.group(1), py_expr(m.group(2))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[f'actions.type_text("{logical}", {val})'],
            confidence=100, pattern="Browser.Page.WebEdit.Set",
            obj_name=logical, obj_type=otype,
        )

    # ── Browser(…).Page(…).WebElement(…).Click ───────────────────────────────
    m = re.match(
        r'^Browser\([^)]+\)\s*\.\s*Page\([^)]+\)\s*\.\s*WebElement\s*\(\s*"(\w+)"\s*\)\s*\.Click',
        stripped, re.I,
    )
    if m:
        logical, otype = _obj(screen, m.group(1), "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")'],
            confidence=100, pattern="Browser.Page.WebElement.Click",
            obj_name=logical, obj_type=otype,
        )

    # ── Browser(…).Page(…).WebElement(…).GetROProperty ───────────────────────
    m = re.match(
        r'^(\w+)\s*=\s*Browser\([^)]+\)\s*\.\s*Page\([^)]+\)\s*\.'
        r'WebElement\s*\(\s*"(\w+)"\s*\)\s*\.'
        r'GetROProperty\s*\(\s*"(innerText|value|innerHTML|text)"\s*\)',
        stripped, re.I,
    )
    if m:
        var, elem = py_var(m.group(1)), m.group(2)
        ocr_name = f"{screen}.{snake(elem)}_text"
        return StmtResult(
            lines=[
                f'{var}_result = ocr.read_target("{ocr_name}")',
                f"{var} = {var}_result.text",
            ],
            confidence=CONF["HIGH"], pattern="Browser.Page.WebElement.GetROProperty",
            ocr_name=ocr_name,
        )

    # ── Browser(…).Page(…).WebList(…).Select ─────────────────────────────────
    m = re.match(
        r'^Browser\([^)]+\)\s*\.\s*Page\([^)]+\)\s*\.\s*WebList\s*\(\s*"(\w+)"\s*\)\s*\.Select\s+(.+)$',
        stripped, re.I,
    )
    if m:
        elem, val = m.group(1), py_expr(m.group(2))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[
                f"# TODO: dropdown select — click to open, then locate option by OCR",
                f'actions.click("{logical}")',
                f"actions.type_text(\"{logical}\", {val})",
            ],
            confidence=CONF["MEDIUM"], pattern="Browser.Page.WebList.Select",
            obj_name=logical, obj_type=otype,
        )

    # ── Browser(…).Page(…).WebCheckBox(…).Set ────────────────────────────────
    m = re.match(
        r'^Browser\([^)]+\)\s*\.\s*Page\([^)]+\)\s*\.\s*WebCheckBox\s*\(\s*"(\w+)"\s*\)\s*\.Set\s+(.+)$',
        stripped, re.I,
    )
    if m:
        elem, state_raw = m.group(1), m.group(2).strip().strip('"').upper()
        logical, otype = _obj(screen, elem, "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")  # sets checkbox to {"checked" if "ON" in state_raw or state_raw == "TRUE" else "unchecked"}'],
            confidence=CONF["HIGH"], pattern="Browser.Page.WebCheckBox.Set",
            obj_name=logical, obj_type=otype,
        )

    # ── Browser(…).Page(…).GetROProperty("title") ────────────────────────────
    m = re.match(
        r'^(\w+)\s*=\s*Browser\([^)]+\)\s*\.\s*Page\([^)]+\)\s*\.'
        r'GetROProperty\s*\(\s*"title"\s*\)',
        stripped, re.I,
    )
    if m:
        var = py_var(m.group(1))
        return StmtResult(
            lines=[
                f"# TODO: get page/window title — use pygetwindow or OCR on title bar",
                f'# import pygetwindow as gw; {var} = gw.getActiveWindow().title',
                f'{var} = "TODO_window_title"',
            ],
            confidence=CONF["LOW"], pattern="Browser.Page.GetROProperty(title)",
        )

    # ── Browser(…).Sync ───────────────────────────────────────────────────────
    m = re.match(r'^Browser\([^)]+\)\s*\.\s*Sync\s*$', stripped, re.I)
    if m:
        return StmtResult(
            lines=["waits.wait_for_screen_stable(region=(0, 0, 1280, 800))"],
            confidence=CONF["HIGH"], pattern="Browser.Sync",
        )

    # ── Page("Name").Exist(n) standalone ─────────────────────────────────────
    m = re.match(r'^Page\s*\(\s*"(\w+)"\s*\)\s*\.Exist\s*\(\s*(\d+)\s*\)\s*$', stripped, re.I)
    if m:
        page, tmout = m.group(1), m.group(2)
        anchor = f"{snake(page)}.header_label"
        return StmtResult(
            lines=[
                f"# Wait for '{page}' screen to appear",
                f'waits.wait_for_object_exists(or_repo.get("{anchor}"), timeout={tmout})',
            ],
            confidence=CONF["HIGH"], pattern="Page.Exist (standalone)",
        )

    # ══ Win / Java / Dialog objects ═══════════════════════════════════════════

    # ── WinButton.Click ───────────────────────────────────────────────────────
    m = re.match(r'^WinButton\s*\(\s*"(\w+)"\s*\)\s*\.Click\s*$', stripped, re.I)
    if m:
        logical, otype = _obj(screen, m.group(1), "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")'],
            confidence=CONF["HIGH"], pattern="WinButton.Click",
            obj_name=logical, obj_type=otype,
        )

    # ── WinEdit.Set ───────────────────────────────────────────────────────────
    m = re.match(r'^WinEdit\s*\(\s*"(\w+)"\s*\)\s*\.Set\s+(.+)$', stripped, re.I)
    if m:
        elem, val = m.group(1), py_expr(m.group(2))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[f'actions.type_text("{logical}", {val})'],
            confidence=CONF["HIGH"], pattern="WinEdit.Set",
            obj_name=logical, obj_type=otype,
        )

    # ── WinEdit.GetROProperty ─────────────────────────────────────────────────
    m = re.match(
        r'^(\w+)\s*=\s*WinEdit\s*\(\s*"(\w+)"\s*\)\s*\.GetROProperty\s*\(\s*"(value|text)"\s*\)',
        stripped, re.I,
    )
    if m:
        var, elem = py_var(m.group(1)), m.group(2)
        ocr_name = f"{screen}.{snake(elem)}_text"
        return StmtResult(
            lines=[
                f'{var}_result = ocr.read_target("{ocr_name}")',
                f"{var} = {var}_result.text",
            ],
            confidence=CONF["HIGH"], pattern="WinEdit.GetROProperty",
            ocr_name=ocr_name,
        )

    # ── WinList.Select ────────────────────────────────────────────────────────
    m = re.match(r'^WinList\s*\(\s*"(\w+)"\s*\)\s*\.Select\s+(.+)$', stripped, re.I)
    if m:
        elem, val = m.group(1), py_expr(m.group(2))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[
                f"# TODO: WinList dropdown — click, navigate by arrow keys",
                f'actions.click("{logical}")',
                f"actions.type_text(\"{logical}\", {val})",
            ],
            confidence=CONF["MEDIUM"], pattern="WinList.Select",
            obj_name=logical, obj_type=otype,
        )

    # ── JavaButton.Click ──────────────────────────────────────────────────────
    m = re.match(r'^JavaButton\s*\(\s*"(\w+)"\s*\)\s*\.Click\s*$', stripped, re.I)
    if m:
        logical, otype = _obj(screen, m.group(1), "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")'],
            confidence=CONF["HIGH"], pattern="JavaButton.Click",
            obj_name=logical, obj_type=otype,
        )

    # ── JavaEdit.SetText ──────────────────────────────────────────────────────
    m = re.match(r'^JavaEdit\s*\(\s*"(\w+)"\s*\)\s*\.SetText\s+(.+)$', stripped, re.I)
    if m:
        elem, val = m.group(1), py_expr(m.group(2))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[f'actions.type_text("{logical}", {val})'],
            confidence=CONF["HIGH"], pattern="JavaEdit.SetText",
            obj_name=logical, obj_type=otype,
        )

    # ── JavaList.Select ───────────────────────────────────────────────────────
    m = re.match(r'^JavaList\s*\(\s*"(\w+)"\s*\)\s*\.Select\s+(.+)$', stripped, re.I)
    if m:
        elem, val = m.group(1), py_expr(m.group(2))
        logical, otype = _obj(screen, elem, "input")
        return StmtResult(
            lines=[
                f"# TODO: JavaList — click to open, navigate by arrow keys",
                f'actions.click("{logical}")',
                f"actions.type_text(\"{logical}\", {val})",
            ],
            confidence=CONF["MEDIUM"], pattern="JavaList.Select",
            obj_name=logical, obj_type=otype,
        )

    # ── Dialog("Name").WinButton("Name").Click ────────────────────────────────
    m = re.match(
        r'^Dialog\s*\([^)]+\)\s*\.\s*WinButton\s*\(\s*"(\w+)"\s*\)\s*\.Click',
        stripped, re.I,
    )
    if m:
        logical, otype = _obj(screen, m.group(1), "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")'],
            confidence=CONF["HIGH"], pattern="Dialog.WinButton.Click",
            obj_name=logical, obj_type=otype,
        )

    # ── SwfButton.Click (Silverlight/Flash) ───────────────────────────────────
    m = re.match(r'^SwfButton\s*\(\s*"(\w+)"\s*\)\s*\.Click\s*$', stripped, re.I)
    if m:
        logical, otype = _obj(screen, m.group(1), "button")
        return StmtResult(
            lines=[f'actions.click("{logical}")  # Silverlight/Flash button'],
            confidence=CONF["HIGH"], pattern="SwfButton.Click",
            obj_name=logical, obj_type=otype,
        )

    # ── Window("Name").Activate ───────────────────────────────────────────────
    m = re.match(r'^Window\s*\(\s*"([^"]+)"\s*\)\s*\.Activate\s*$', stripped, re.I)
    if m:
        title = m.group(1)
        return StmtResult(
            lines=[
                f'# TODO: bring window "{title}" to foreground',
                f'# import pygetwindow as gw',
                f'# wins = gw.getWindowsWithTitle("{title}"); wins[0].activate() if wins else None',
            ],
            confidence=CONF["LOW"], pattern="Window.Activate",
        )

    # ── SystemUtil.Run ────────────────────────────────────────────────────────
    m = re.match(r'^SystemUtil\s*\.\s*Run\s+(.+)$', stripped, re.I)
    if m:
        path = py_expr(m.group(1).strip())
        return StmtResult(
            lines=[
                f"# TODO: launch external process",
                f"import subprocess",
                f"subprocess.Popen([{path}])  # adjust args as needed",
            ],
            confidence=CONF["MEDIUM"], pattern="SystemUtil.Run",
        )

    # ── SystemUtil.CloseProcessByName ─────────────────────────────────────────
    m = re.match(r'^SystemUtil\s*\.\s*CloseProcessByName\s+"([^"]+)"', stripped, re.I)
    if m:
        proc = m.group(1)
        return StmtResult(
            lines=[
                f"# TODO: kill process '{proc}'",
                f"import subprocess",
                f'subprocess.run(["taskkill", "/f", "/im", "{proc}"], check=False)',
            ],
            confidence=CONF["MEDIUM"], pattern="SystemUtil.CloseProcessByName",
        )

    # ── MsgBox ────────────────────────────────────────────────────────────────
    m = re.match(r'^MsgBox\s+(.+)$', stripped, re.I)
    if m:
        msg = py_expr(m.group(1).strip())
        return StmtResult(
            lines=[f'ctx.logger.info("MsgBox: " + str({msg}))'],
            confidence=CONF["HIGH"], pattern="MsgBox",
        )

    # ── Call FunctionName(args) ───────────────────────────────────────────────
    m = re.match(r'^Call\s+(\w+)\s*\(([^)]*)\)$', stripped, re.I)
    if m:
        fn, args_raw = m.group(1), m.group(2).strip()
        args_py = ", ".join(py_expr(a.strip()) for a in args_raw.split(",")) if args_raw else ""
        return StmtResult(
            lines=[f"{snake(fn)}({args_py})  # TODO: ensure function is imported"],
            confidence=CONF["GOOD"], pattern="Call function",
        )

    # ── Set obj = Nothing ────────────────────────────────────────────────────
    m = re.match(r'^Set\s+(\w+)\s*=\s*Nothing\s*$', stripped, re.I)
    if m:
        var = py_var(m.group(1))
        return StmtResult(lines=[f"{var} = None"], confidence=100, pattern="Set Nothing")

    # ── Simple assignment: sVar = expression ─────────────────────────────────
    m = re.match(r'^(\w+)\s*=\s*(.+)$', stripped)
    if m:
        var  = py_var(m.group(1))
        expr = py_expr(m.group(2).strip())
        conf = CONF["GOOD"] if "# TODO" in expr else 100
        return StmtResult(
            lines=[f"{var} = {expr}"],
            confidence=conf, pattern="Variable assignment",
        )

    # ── Fallback ─────────────────────────────────────────────────────────────
    return StmtResult(
        lines=[f"# TODO: translate → {stripped}"],
        confidence=CONF["FALLBACK"], pattern="Unrecognised",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# QFL function-body translator
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FunctionResult:
    fn_name:      str
    screen:       str
    data_columns: list[tuple[str, str]]           = field(default_factory=list)
    objects:      dict[str, str]                  = field(default_factory=dict)
    ocr_targets:  list[str]                       = field(default_factory=list)
    body_lines:   list[str]                       = field(default_factory=list)
    stmt_report:  list[tuple[int, str, str]]      = field(default_factory=list)
    # (confidence, pattern_label, original_vbscript)


def _join_continuations(raw_lines: list[str]) -> list[str]:
    """Join VBScript line continuations (physical line ending with _)."""
    logical: list[str] = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].rstrip()
        while re.search(r"\s_$", line):
            line = line.rstrip()[:-1].rstrip()
            i += 1
            if i < len(raw_lines):
                line += " " + raw_lines[i].strip()
        logical.append(line)
        i += 1
    return logical


def _strip_inline_comment(line: str) -> tuple[str, str]:
    """Return (code_part, comment_part) splitting on the first ' outside strings."""
    in_str = False
    for idx, ch in enumerate(line):
        if ch == '"':
            in_str = not in_str
        elif ch == "'" and not in_str:
            return line[:idx].rstrip(), "  # " + line[idx + 1:].strip()
    return line, ""


def translate_function(fn_lines: list[str], fn_name: str, screen: str) -> FunctionResult:  # noqa: C901
    """Translate the body of one VBScript function to Python body lines."""
    result = FunctionResult(fn_name=fn_name, screen=screen)

    logical = _join_continuations(fn_lines)
    seen_data_cols: set[str] = set()
    depth = 1
    body:  list[str] = []

    # For Select Case tracking
    _select_var: list[str] = []   # stack of select variable names
    _case_depth: list[int] = []   # depth when Select Case was opened

    # For With tracking
    _with_obj: list[str] = []     # stack of With object names

    def emit(*lines: str, d: int | None = None) -> None:
        lvl = d if d is not None else depth
        for ln in lines:
            if ln == "":
                body.append("")
            else:
                body.append(INDENT * lvl + ln)

    i = 0
    while i < len(logical):
        raw = logical[i]
        stripped, inline_cmt = _strip_inline_comment(raw.strip())
        stripped = stripped.strip()
        i += 1

        if not stripped:
            body.append("")
            continue

        if stripped.startswith("'"):
            emit("# " + stripped[1:].strip())
            continue

        # ── End If ───────────────────────────────────────────────────────────
        if re.match(r"^End\s+If\s*$", stripped, re.I):
            depth = max(1, depth - 1)
            continue

        # ── Else ─────────────────────────────────────────────────────────────
        if re.match(r"^Else\s*$", stripped, re.I):
            depth = max(1, depth - 1)
            if EMIT_CONF_COMMENTS:
                emit(_conf_comment(CONF["EXACT"], "Else branch"))
            emit("else:")
            result.stmt_report.append((CONF["EXACT"], "Else branch", stripped))
            depth += 1
            continue

        # ── ElseIf ───────────────────────────────────────────────────────────
        m = re.match(r"^ElseIf\s+(.+)\s+Then\s*$", stripped, re.I)
        if m:
            depth = max(1, depth - 1)
            if EMIT_CONF_COMMENTS:
                emit(_conf_comment(CONF["EXACT"], "ElseIf branch"))
            emit(f"elif {py_cond(m.group(1))}:")
            result.stmt_report.append((CONF["EXACT"], "ElseIf branch", stripped))
            depth += 1
            continue

        # ── If … Then (block form) ────────────────────────────────────────────
        if re.match(r"^If\s+.+\s+Then\s*$", stripped, re.I):
            inner = re.sub(r"^If\s+", "", stripped, flags=re.I)
            inner = re.sub(r"\s+Then\s*$", "", inner, flags=re.I)
            if EMIT_CONF_COMMENTS:
                emit(_conf_comment(CONF["EXACT"], "If...Then block"))
            emit(f"if {py_cond(inner)}:" + inline_cmt)
            result.stmt_report.append((CONF["EXACT"], "If...Then block", stripped))
            depth += 1
            continue

        # ── If … Then stmt (single-line) ──────────────────────────────────────
        m = re.match(r"^If\s+(.+?)\s+Then\s+(.+)$", stripped, re.I)
        if m:
            cond = py_cond(m.group(1))
            sr   = translate_stmt(m.group(2).strip(), screen)
            _register(sr, result, seen_data_cols)
            if EMIT_CONF_COMMENTS:
                emit(_conf_comment(CONF["EXACT"], "If...Then (single-line)"))
            emit(f"if {cond}:" + inline_cmt)
            result.stmt_report.append((CONF["EXACT"], "If...Then (single-line)", stripped))
            depth += 1
            if EMIT_CONF_COMMENTS and sr.pattern:
                emit(_conf_comment(sr.confidence, sr.pattern))
            for ln in sr.lines:
                emit(ln)
            depth -= 1
            continue

        # ── For i = start To end [Step n] ────────────────────────────────────
        m = re.match(r"^For\s+(\w+)\s*=\s*(.+?)\s+To\s+(.+?)(?:\s+Step\s+(.+))?\s*$", stripped, re.I)
        if m:
            var   = py_var(m.group(1))
            start = py_expr(m.group(2).strip())
            stop  = py_expr(m.group(3).strip())
            step  = py_expr(m.group(4).strip()) if m.group(4) else None
            rng   = f"range({start}, {stop} + 1{f', {step}' if step else ''})"
            if EMIT_CONF_COMMENTS:
                emit(_conf_comment(CONF["HIGH"], "For...Next loop"))
            emit(f"for {var} in {rng}:" + inline_cmt)
            result.stmt_report.append((CONF["HIGH"], "For...Next loop", stripped))
            depth += 1
            continue

        # ── For Each item In collection ───────────────────────────────────────
        m = re.match(r"^For\s+Each\s+(\w+)\s+In\s+(.+)$", stripped, re.I)
        if m:
            var  = py_var(m.group(1))
            coll = py_expr(m.group(2).strip())
            if EMIT_CONF_COMMENTS:
                emit(_conf_comment(CONF["HIGH"], "For Each...Next loop"))
            emit(f"for {var} in {coll}:" + inline_cmt)
            result.stmt_report.append((CONF["HIGH"], "For Each...Next loop", stripped))
            depth += 1
            continue

        # ── Next [var] ────────────────────────────────────────────────────────
        if re.match(r"^Next(\s+\w+)?\s*$", stripped, re.I):
            depth = max(1, depth - 1)
            continue

        # ── Do While / Do Until ───────────────────────────────────────────────
        m = re.match(r"^Do\s+(While|Until)\s+(.+)$", stripped, re.I)
        if m:
            kw, cond = m.group(1).lower(), py_cond(m.group(2))
            label = f"Do {m.group(1)}"
            if EMIT_CONF_COMMENTS:
                emit(_conf_comment(CONF["HIGH"], label))
            if kw == "while":
                emit(f"while {cond}:" + inline_cmt)
            else:
                emit(f"while not ({cond}):" + inline_cmt)
            result.stmt_report.append((CONF["HIGH"], label, stripped))
            depth += 1
            continue

        # ── Do (loop at bottom) ───────────────────────────────────────────────
        if re.match(r"^Do\s*$", stripped, re.I):
            if EMIT_CONF_COMMENTS:
                emit(_conf_comment(CONF["HIGH"], "Do...Loop"))
            emit("while True:" + inline_cmt)
            result.stmt_report.append((CONF["HIGH"], "Do...Loop", stripped))
            depth += 1
            continue

        # ── Loop [While/Until condition] ──────────────────────────────────────
        m = re.match(r"^Loop\s*(While|Until)?\s*(.*)?$", stripped, re.I)
        if m:
            depth = max(1, depth - 1)
            if m.group(1):
                kw, cond = m.group(1).lower(), py_cond(m.group(2).strip())
                if EMIT_CONF_COMMENTS:
                    emit(_conf_comment(CONF["HIGH"], f"Loop {m.group(1)}"))
                if kw == "while":
                    emit(f"if not ({cond}): break")
                else:
                    emit(f"if {cond}: break")
            continue

        # ── Select Case var ───────────────────────────────────────────────────
        m = re.match(r"^Select\s+Case\s+(.+)$", stripped, re.I)
        if m:
            var = py_var(m.group(1).strip())
            _select_var.append(var)
            _case_depth.append(depth)
            if EMIT_CONF_COMMENTS:
                emit(_conf_comment(CONF["HIGH"], f"Select Case ({var})"))
            result.stmt_report.append((CONF["HIGH"], "Select Case", stripped))
            # First Case will open the if
            continue

        # ── Case val[, val2, ...] ─────────────────────────────────────────────
        m = re.match(r"^Case\s+(.+)$", stripped, re.I)
        if m and _select_var:
            vals_raw = m.group(1).strip()
            var      = _select_var[-1]
            base_d   = _case_depth[-1]

            if re.match(r"^Else\s*$", vals_raw, re.I):
                if EMIT_CONF_COMMENTS:
                    emit(_conf_comment(CONF["EXACT"], "Case Else"), d=base_d)
                emit("else:", d=base_d)
                depth = base_d + 1
            else:
                vals = [py_expr(v.strip()) for v in vals_raw.split(",")]
                cond = f"{var} in ({', '.join(vals)})" if len(vals) > 1 else f"{var} == {vals[0]}"
                kw   = "if" if depth <= base_d + 1 else "elif"
                if EMIT_CONF_COMMENTS:
                    emit(_conf_comment(CONF["EXACT"], f"Case ({kw})"), d=base_d)
                emit(f"{kw} {cond}:", d=base_d)
                depth = base_d + 1
            continue

        # ── End Select ────────────────────────────────────────────────────────
        if re.match(r"^End\s+Select\s*$", stripped, re.I):
            if _select_var:
                depth = _case_depth.pop()
                _select_var.pop()
            continue

        # ── With obj ─────────────────────────────────────────────────────────
        m = re.match(r"^With\s+(.+)$", stripped, re.I)
        if m:
            _with_obj.append(m.group(1).strip())
            result.stmt_report.append((CONF["HIGH"], "With block", stripped))
            continue

        # ── .Property (inside With) ───────────────────────────────────────────
        if stripped.startswith(".") and _with_obj:
            expanded = _with_obj[-1] + stripped
            sr = translate_stmt(expanded, screen)
            _register(sr, result, seen_data_cols)
            if not sr.is_data_load:
                _maybe_emit(sr, body, emit, inline_cmt, depth)
            continue

        # ── End With ─────────────────────────────────────────────────────────
        if re.match(r"^End\s+With\s*$", stripped, re.I):
            if _with_obj:
                _with_obj.pop()
            continue

        # ── On Error Resume Next ──────────────────────────────────────────────
        if re.match(r"^On\s+Error\s+Resume\s+Next\s*$", stripped, re.I):
            if EMIT_CONF_COMMENTS:
                emit(_conf_comment(CONF["GOOD"], "On Error Resume Next"))
            emit("try:  # On Error Resume Next")
            result.stmt_report.append((CONF["GOOD"], "On Error Resume Next", stripped))
            depth += 1
            continue

        # ── On Error GoTo 0 ───────────────────────────────────────────────────
        if re.match(r"^On\s+Error\s+GoTo\s+0\s*$", stripped, re.I):
            depth = max(1, depth - 1)
            if EMIT_CONF_COMMENTS:
                emit(_conf_comment(CONF["GOOD"], "On Error GoTo 0"))
            emit("except Exception:")
            depth += 1
            emit("pass  # On Error GoTo 0 — suppress all errors from the try block above")
            depth -= 1
            continue

        # ── Regular statement ─────────────────────────────────────────────────
        sr = translate_stmt(stripped, screen)
        _register(sr, result, seen_data_cols)
        result.stmt_report.append((sr.confidence, sr.pattern, stripped))

        if sr.is_data_load:
            continue

        # Suppress `return` immediately after `raise` (dead code)
        if sr.lines == ["return"]:
            last_code = next(
                (ln.strip() for ln in reversed(body) if ln.strip()), ""
            )
            if last_code.startswith("raise"):
                continue

        _maybe_emit(sr, body, emit, inline_cmt, depth)

    # Collapse consecutive blank lines
    condensed: list[str] = []
    prev_blank = False
    for line in body:
        if line == "":
            if not prev_blank:
                condensed.append(line)
            prev_blank = True
        else:
            condensed.append(line)
            prev_blank = False

    result.body_lines = condensed
    return result


def _maybe_emit(sr: StmtResult, body: list, emit, inline_cmt: str, depth: int) -> None:
    """Emit statement lines into body, prefixed by a confidence comment.

    The leading `# confidence: …` line is suppressed when EMIT_CONF_COMMENTS is
    False (set by the --no-conf-comments CLI flag) or when the statement
    produced no code (e.g. Dim, Exit Function followed by raise).
    """
    if not sr.lines:
        return
    if EMIT_CONF_COMMENTS and sr.pattern:
        emit(_conf_comment(sr.confidence, sr.pattern))
    for j, ln in enumerate(sr.lines):
        emit(ln + (inline_cmt if j == len(sr.lines) - 1 else ""))


def _register(sr: StmtResult, result: FunctionResult, seen: set[str]) -> None:
    if sr.is_data_load and sr.data_col not in seen:
        seen.add(sr.data_col)
        result.data_columns.append((sr.data_col, sr.data_var))
    if sr.obj_name and sr.obj_name not in result.objects:
        result.objects[sr.obj_name] = sr.obj_type
    if sr.ocr_name and sr.ocr_name not in result.ocr_targets:
        result.ocr_targets.append(sr.ocr_name)


# ═══════════════════════════════════════════════════════════════════════════════
# Confidence report builder
# ═══════════════════════════════════════════════════════════════════════════════

def _build_confidence_report(frs: list[FunctionResult]) -> dict:
    """Compute confidence statistics across all converted functions."""
    all_stmts: list[tuple[int, str, str]] = []
    for fr in frs:
        all_stmts.extend(fr.stmt_report)

    if not all_stmts:
        return {"total": 0, "avg": 100, "quality": "EXCELLENT", "by_tier": {}, "todos": []}

    total = len(all_stmts)
    avg   = sum(c for c, _, _ in all_stmts) / total

    by_tier: dict[str, int] = {}
    todos: list[tuple[str, str]] = []
    for conf, pattern, original in all_stmts:
        label = _tier_label(conf)
        by_tier[label] = by_tier.get(label, 0) + 1
        if conf < 90:
            todos.append((pattern, original[:60]))

    return {
        "total":    total,
        "avg":      avg,
        "quality":  _quality_label(avg),
        "by_tier":  by_tier,
        "todos":    todos,
    }


def _format_report_text(report: dict, prefix: str = "  ") -> str:
    """Format the confidence report as a multi-line string."""
    lines: list[str] = []
    total = report["total"]
    if total == 0:
        return f"{prefix}No statements found.\n"

    avg   = report["avg"]
    qual  = report["quality"]
    lines.append(f"{prefix}Statements translated : {total}")
    lines.append(f"{prefix}Average confidence    : {avg:.0f}%  → {qual}")
    lines.append(f"{prefix}")
    tier_order = ["EXACT", "HIGH", "GOOD", "MEDIUM", "LOW", "FALLBACK"]
    for tier in tier_order:
        count = report["by_tier"].get(tier, 0)
        if count:
            pct   = count / total * 100
            score = CONF[tier]
            desc  = _TIER[tier][1]
            lines.append(f"{prefix}  {tier:<8} ({score:>3}%) : {count:>3}  ({pct:4.0f}%)  — {desc}")
    if report["todos"]:
        lines.append(f"{prefix}")
        lines.append(f"{prefix}Items needing attention:")
        for pattern, original in report["todos"][:15]:
            lines.append(f"{prefix}  [{pattern}]  {original}")
        if len(report["todos"]) > 15:
            lines.append(f"{prefix}  … and {len(report['todos']) - 15} more")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# QFL file parser
# ═══════════════════════════════════════════════════════════════════════════════

def parse_qfl(path: Path) -> list[tuple[str, list[str]]]:
    """Extract (fn_name, body_lines) for every Function/Sub in the QFL.

    If the file contains no Function/Sub wrapper (a top-level VBScript), the
    whole file is returned as a single pseudo-function named after the file
    stem so the rest of the pipeline can still process it.
    """
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    functions: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(raw):
        m = re.match(r"^\s*(?:Public\s+|Private\s+)?(?:Function|Sub)\s+(\w+)", raw[i], re.I)
        if m:
            fn_name = m.group(1)
            body: list[str] = []
            i += 1
            while i < len(raw):
                if re.match(r"^\s*End\s+(?:Function|Sub)\s*$", raw[i], re.I):
                    break
                body.append(raw[i])
                i += 1
            functions.append((fn_name, body))
        i += 1

    # Top-level script fallback — treat the entire file as one function.
    if not functions:
        # Strip leading/trailing blank lines but keep the body verbatim.
        body = [ln for ln in raw]
        pseudo = snake(path.stem)
        if not pseudo or pseudo[0].isdigit():
            pseudo = f"qfl_{pseudo}"
        functions.append((pseudo, body))
    return functions


# ═══════════════════════════════════════════════════════════════════════════════
# Screen-name inference
# ═══════════════════════════════════════════════════════════════════════════════

def infer_screen(fn_name: str) -> str:
    """Derive a snake_case screen name from a function name."""
    parts = fn_name.split("_")
    words = [
        p for p in parts
        if not re.match(r"^\d+$", p) and p.upper() not in {"TEST", "UFT", "RUN"}
    ]
    joined = "_".join(words) if words else fn_name
    return snake(joined)


# ═══════════════════════════════════════════════════════════════════════════════
# Code generators
# ═══════════════════════════════════════════════════════════════════════════════

def build_flow_py(frs: list[FunctionResult], qfl_stem: str, report: dict) -> str:
    """Render the complete flow Python file."""
    all_data:    list[tuple[str, str]] = []
    seen_cols:   set[str] = set()
    all_objects: dict[str, str] = {}
    all_ocr:     list[str] = []
    for fr in frs:
        for col, var in fr.data_columns:
            if col not in seen_cols:
                seen_cols.add(col)
                all_data.append((col, var))
        all_objects.update(fr.objects)
        for ot in fr.ocr_targets:
            if ot not in all_ocr:
                all_ocr.append(ot)

    avg   = report["avg"]
    qual  = report["quality"]
    total = report["total"]
    todo_count = sum(1 for c, _, _ in
                     [s for fr in frs for s in fr.stmt_report] if c < 90)

    L: list[str] = [
        '"""',
        f"Flow    : {', '.join(fr.fn_name for fr in frs)}",
        f"Source  : {qfl_stem}.qfl",
        "",
        "AUTO-GENERATED by tools/qfl_to_pyautogui.py",
        "Search for  # TODO  and resolve every item before running in CI.",
        "",
        "Conversion Report",
        f"  Statements   : {total}",
        f"  Score        : {avg:.0f}%  → {qual}",
    ]
    tier_order = ["EXACT", "HIGH", "GOOD", "MEDIUM", "LOW", "FALLBACK"]
    for tier in tier_order:
        count = report["by_tier"].get(tier, 0)
        if count:
            pct = count / total * 100 if total else 0
            L.append(f"  {tier:<8}     : {count:>3}  ({pct:.0f}%)")
    if todo_count:
        L.append(f"  TODOs to fix : {todo_count}  (search '# TODO' below)")
    L += ['"""', ""]

    L += [
        "from __future__ import annotations",
        "",
        "from automation.common import Context",
        "from automation.common.data import DataRow",
        "from automation.core import actions, ocr, waits",
        "",
        "",
        "def _screen_exists(or_repo, anchor: str, *, timeout: float) -> bool:",
        '    """Return True if the anchor element appears within timeout, False otherwise."""',
        "    try:",
        "        waits.wait_for_object_exists(or_repo.get(anchor), timeout=timeout)",
        "        return True",
        "    except Exception:",
        "        return False",
        "",
        "",
    ]

    for fr in frs:
        test_id = snake(fr.fn_name)
        L += [
            f"def flow_{test_id}(ctx: Context, row: DataRow) -> None:",
            f'    """Execute {fr.fn_name}."""',
            "    or_repo = ctx.or_repo",
            "",
        ]
        if fr.data_columns:
            L.append("    # ── Load data from CSV row ───────────────────────────────────")
            for col, var in fr.data_columns:
                L.append(f'    {var} = row.require("{col}")')
            L.append("")
        L.extend(fr.body_lines)
        L += ["", ""]

    return "\n".join(L)


def build_task_py(frs: list[FunctionResult], qfl_stem: str) -> str:
    """Render a task stub module."""
    all_objects: dict[str, str] = {}
    screen = frs[0].screen if frs else "epic_screen"
    for fr in frs:
        all_objects.update(fr.objects)
        if fr.screen:
            screen = fr.screen

    L: list[str] = [
        f'"""Task stubs for {screen} screen — generated from {qfl_stem}.qfl.',
        "",
        "One function per UFT object. Wire up actions/OCR calls then import",
        f'into your flow as: from automation.tests.tasks.{screen} import task_{screen}',
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from automation.common import Context",
        "from automation.core import actions, ocr, waits",
        "",
        "",
    ]
    for logical, obj_type in all_objects.items():
        fn_name = logical.split(".")[-1] if "." in logical else snake(logical)
        L += [
            f"def {fn_name}(ctx: Context) -> None:",
            f'    # TODO: implement — OR object "{logical}" (type: {obj_type})',
            f'    actions.click("{logical}")',
            "",
            "",
        ]
    return "\n".join(L)


def build_or_yaml(frs: list[FunctionResult]) -> str:
    """Render YAML object-repository entries for all discovered elements."""
    all_objects: dict[str, str] = {}
    all_ocr: list[str] = []
    for fr in frs:
        all_objects.update(fr.objects)
        for ot in fr.ocr_targets:
            if ot not in all_ocr:
                all_ocr.append(ot)

    L: list[str] = [
        "# ── Paste into automation/or/app_or.yaml ───────────────────────────",
        "# Fill in real region coordinates and capture reference PNG crops.",
        "",
        "objects:",
    ]
    for logical, obj_type in all_objects.items():
        screen_part, _, elem_part = logical.partition(".")
        L += [
            "",
            f"  - name: {logical}",
            f"    screen: {screen_part}",
            f"    type: {obj_type}",
            f"    image: {screen_part}/{elem_part}.png  # TODO: capture reference PNG",
            f"    region: [0, 0, 1280, 800]            # TODO: tighten to element bounds",
            f"    min_confidence: 0.82",
            f"    status: todo",
        ]
    if all_ocr:
        L += ["", "ocr_targets:"]
        for ocr_name in all_ocr:
            sp = ocr_name.split(".")[0]
            L += [
                "",
                f"  - name: {ocr_name}",
                f"    screen: {sp}",
                f"    region: [0, 0, 1280, 800]  # TODO: tighten to text region",
                f'    expected_pattern: ".*"      # TODO: set regex pattern',
                f"    lang: eng",
                f"    preprocess: [grayscale, upscale_2x, otsu_threshold]",
                f"    min_confidence: 0.60",
                f"    status: todo",
            ]
    return "\n".join(L) + "\n"


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a UFT QFL file to PyAutoGUI Python automation code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--qfl",     metavar="PATH",
                     help="Path to a single source .qfl file")
    src.add_argument("--all",     metavar="DIR", nargs="?", const="source/qfl",
                     help="Convert every *.qfl file under DIR (default: source/qfl)")
    parser.add_argument("--screen",   default="",    metavar="NAME",
                        help="Override inferred screen name (single-file mode only)")
    parser.add_argument("--out-dir",  default=None,  metavar="DIR",
                        help="Output directory for flow .py files (single-file mode only)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Print to stdout only — do NOT write to disk")
    parser.add_argument("--no-conf-comments", action="store_true",
                        help="Disable inline `# confidence: …` comments in generated code")
    args = parser.parse_args()

    global EMIT_CONF_COMMENTS
    if args.no_conf_comments:
        EMIT_CONF_COMMENTS = False

    # ── Batch mode: convert every .qfl in the directory ───────────────────
    if args.all:
        batch_dir = Path(args.all)
        if not batch_dir.is_dir():
            print(f"ERROR: --all directory does not exist: {batch_dir}", file=sys.stderr)
            sys.exit(1)
        qfls = sorted(batch_dir.glob("*.qfl"))
        if not qfls:
            print(f"ERROR: no .qfl files found in {batch_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"\nBatch mode: {len(qfls)} file(s) under {batch_dir}\n")
        results: list[tuple[str, float, int, str]] = []
        for q in qfls:
            try:
                _, avg, total, qual = _convert_one(q, screen="", out_dir=None,
                                                   dry_run=args.dry_run)
                results.append((q.name, avg, total, qual))
            except Exception as exc:                                # noqa: BLE001
                print(f"\nERROR converting {q.name}: {exc}\n", file=sys.stderr)
                results.append((q.name, 0.0, 0, "FAILED"))
        print(f"\n{'═' * 68}\n  BATCH SUMMARY\n{'═' * 68}")
        for name, avg, total, qual in results:
            print(f"  {name:<48} {total:>4} stmts  {avg:>5.1f}%  {qual}")
        print(f"{'═' * 68}\n")
        return

    qfl_path = Path(args.qfl)
    if not qfl_path.exists():
        print(f"ERROR: QFL file not found: {qfl_path}", file=sys.stderr)
        sys.exit(1)
    _convert_one(qfl_path, screen=args.screen, out_dir=args.out_dir,
                 dry_run=args.dry_run)


def _convert_one(qfl_path: Path, *, screen: str, out_dir: str | None,
                 dry_run: bool) -> tuple[Path | None, float, int, str]:
    """Convert one .qfl file. Returns (flow_path, avg_conf, total_stmts, quality)."""
    print(f"\n[1/4] Parsing: {qfl_path.name}")
    raw_functions = parse_qfl(qfl_path)
    print(f"       Found {len(raw_functions)} function(s): {[n for n, _ in raw_functions]}")

    frs: list[FunctionResult] = []
    override_screen = (screen or "").strip()
    for fn_name, body_lines in raw_functions:
        used_screen = override_screen or infer_screen(fn_name)
        print(f"       Translating  {fn_name!r}  →  screen={used_screen!r}")
        fr = translate_function(body_lines, fn_name, used_screen)
        frs.append(fr)
        print(f"         DataTable cols : {[c for c, _ in fr.data_columns]}")
        print(f"         Objects found  : {list(fr.objects.keys())}")
        print(f"         OCR targets    : {fr.ocr_targets}")

    # ── Confidence report ─────────────────────────────────────────────────────
    report = _build_confidence_report(frs)
    avg    = report["avg"]
    qual   = report["quality"]
    total  = report["total"]

    print(f"\n{'─'*68}")
    print(f"  CONVERSION CONFIDENCE REPORT — {qfl_path.name}")
    print(f"{'─'*68}")
    print(f"  Statements translated : {total}")
    print(f"  Overall score         : {avg:.1f}%  →  {qual}")
    print()
    tier_order = ["EXACT", "HIGH", "GOOD", "MEDIUM", "LOW", "FALLBACK"]
    for tier in tier_order:
        count = report["by_tier"].get(tier, 0)
        if count:
            pct   = count / total * 100 if total else 0
            score = CONF[tier]
            bar   = "█" * int(pct / 5)
            print(f"  {tier:<8} ({score:>3}%) : {count:>3}  ({pct:4.0f}%)  {bar}")
    if report["todos"]:
        print(f"\n  Items needing attention ({len(report['todos'])} total):")
        for pattern, original in report["todos"][:12]:
            print(f"    [{pattern:<30}]  {original}")
        if len(report["todos"]) > 12:
            print(f"    … and {len(report['todos']) - 12} more (search # TODO in generated file)")
    print(f"{'─'*68}\n")

    # ── Generate content ──────────────────────────────────────────────────────
    flow_py = build_flow_py(frs, qfl_path.stem, report)
    task_py = build_task_py(frs, qfl_path.stem)
    or_yaml = build_or_yaml(frs)

    if dry_run:
        print(f"\n[2/4] Generated flow file (preview):\n\n{SEP}\n{flow_py}\n{SEP}")
        print(f"\n[3/4] Generated task stub (preview):\n\n{SEP}\n{task_py}\n{SEP}")
        print(f"\n[4/4] YAML OR entries (preview):\n\n{SEP}\n{or_yaml}{SEP}")
        print("\nDRY RUN — no files written.  Remove --dry-run to save.")
        return None, avg, total, qual

    # ── Write to disk ─────────────────────────────────────────────────────────
    project_root   = Path(__file__).resolve().parent.parent
    automation     = project_root / "automation"
    primary_screen = override_screen or frs[0].screen
    test_id        = snake(frs[0].fn_name)

    flow_dir = Path(out_dir) if out_dir else (
        project_root / "output" / "flows" / primary_screen
    )
    # task stub lives alongside the flow file in output/flows/<screen>/
    task_dir = flow_dir
    flow_dir.mkdir(parents=True, exist_ok=True)

    flow_path = flow_dir / f"flow_{test_id}.py"
    writes = [
        (flow_path,                                flow_py),
        (flow_dir / "__init__.py",                ""),
        (task_dir / f"task_{primary_screen}.py",  task_py),
    ]
    for fpath, content in writes:
        # Don't clobber non-empty __init__.py files that already exist.
        if fpath.name == "__init__.py" and fpath.exists() and fpath.read_text().strip():
            print(f"  kept   {fpath.relative_to(project_root)}  (already populated)")
            continue
        fpath.write_text(content, encoding="utf-8")
        print(f"  wrote  {fpath.relative_to(project_root)}")

    todo_count = sum(1 for c, _, _ in
                     [s for fr in frs for s in fr.stmt_report] if c < 90)
    print(f"""
DONE.  Next steps
  1. Open   {flow_path.relative_to(project_root)}
     Resolve every  # TODO  comment.  ({todo_count} items)

  2. Paste the YAML block into automation/or/app_or.yaml
     Set real [x, y, w, h] regions and capture reference PNG crops.

  3. Copy to automation and run the test:
     cp output/flows/{primary_screen}/flow_{test_id}.py automation/tests/flows/{primary_screen}/
     cp output/flows/{primary_screen}/task_{primary_screen}.py automation/tests/tasks/{primary_screen}/
     cd automation && pytest tests/flows/{primary_screen}/flow_{test_id}.py -v
""")
    return flow_path, avg, total, qual


if __name__ == "__main__":
    main()
