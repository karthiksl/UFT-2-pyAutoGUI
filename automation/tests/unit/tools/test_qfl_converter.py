"""Unit tests for tools/qfl_to_pyautogui.py — the QFL → PyAutoGUI converter.

These tests pin the public converter API and assert behaviour for every
recognised UFT VBScript pattern. They serve two purposes:

  1. Regression guard — every currently-supported pattern stays supported.
  2. Specification — adding a new pattern requires adding a test here first.

The tests intentionally avoid the file-system code paths (``_convert_one``
writing files) and instead exercise the parser helpers and statement
translator directly. End-to-end conversion of the 5 sample QFLs is asserted
in ``test_qfl_converter_e2e.py``.
"""

from __future__ import annotations

import ast
import re
import textwrap

import pytest

from tools.qfl_to_pyautogui import (
    CONF,
    StmtResult,
    _build_confidence_report,
    _join_continuations,
    _split_vb_concat,
    _strip_inline_comment,
    infer_screen,
    parse_qfl,
    py_cond,
    py_expr,
    py_var,
    snake,
    translate_function,
    translate_stmt,
)

# ───────────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────────

def _t(stmt: str, screen: str = "login") -> StmtResult:
    """Shortcut: translate a single statement against a given screen."""
    return translate_stmt(stmt, screen)


def _assert_valid_python(code: str, *, allow_partial: bool = False) -> None:
    """Assert that *code* parses as a Python expression or module."""
    if allow_partial:
        # Wrap in dummy assignment so bare expressions still parse.
        try:
            ast.parse(f"_x = {code}\n")
            return
        except SyntaxError:
            pass
    ast.parse(code)


# ═══════════════════════════════════════════════════════════════════════════════
# Naming helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestSnake:
    @pytest.mark.parametrize("vb,expected", [
        ("MemberLogin",        "member_login"),
        ("WebButton",          "web_button"),
        ("HTTPResponse",       "http_response"),
        ("XMLHttpRequest",     "xml_http_request"),
        ("simpleCase",         "simple_case"),
        ("ALL_CAPS",           "all_caps"),
        ("already_snake",      "already_snake"),
        ("withNumber123Inner", "with_number123_inner"),
    ])
    def test_pascal_camel_to_snake(self, vb: str, expected: str) -> None:
        assert snake(vb) == expected


class TestPyVar:
    @pytest.mark.parametrize("vb,expected", [
        # Hungarian prefixes are stripped.
        ("sUser",        "user"),
        ("iCount",       "count"),
        ("bFlag",        "flag"),
        ("strName",      "name"),
        ("objConn",      "conn"),
        ("arrItems",     "items"),
        # No Hungarian prefix → standard snake.
        ("UserName",     "user_name"),
        ("counter",      "counter"),
    ])
    def test_hungarian_stripped(self, vb: str, expected: str) -> None:
        assert py_var(vb) == expected


class TestInferScreen:
    @pytest.mark.parametrize("fn,expected", [
        ("TEST_188001_MemberLogin",    "member_login"),
        ("RUN_CoverageVerify",         "coverage_verify"),
        ("UFT_TEST_EpicHome",          "epic_home"),
        ("MyCustomFlow",               "my_custom_flow"),
    ])
    def test_infer_strips_prefix_noise(self, fn: str, expected: str) -> None:
        assert infer_screen(fn) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Concatenation splitter (handles &, nested parens, string literals)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSplitVbConcat:
    def test_simple_concat(self) -> None:
        assert _split_vb_concat('"a" & "b"') == ['"a"', '"b"']

    def test_three_parts(self) -> None:
        assert _split_vb_concat('a & b & c') == ['a', 'b', 'c']

    def test_amp_inside_string_is_not_split(self) -> None:
        assert _split_vb_concat('"a&b" & c') == ['"a&b"', 'c']

    def test_amp_inside_parentheses_is_not_split(self) -> None:
        # foo(a & b) is one part; only the outer & splits.
        assert _split_vb_concat('foo(a & b) & c') == ['foo(a & b)', 'c']

    def test_nested_parens(self) -> None:
        assert _split_vb_concat('foo(bar(a & b)) & c') == ['foo(bar(a & b))', 'c']

    def test_leading_trailing_whitespace_trimmed(self) -> None:
        assert _split_vb_concat('  a  &  b  ') == ['a', 'b']


# ═══════════════════════════════════════════════════════════════════════════════
# Inline comment stripper
# ═══════════════════════════════════════════════════════════════════════════════

class TestStripInlineComment:
    def test_no_comment(self) -> None:
        code, cmt = _strip_inline_comment('WebButton("Save").Click')
        assert code == 'WebButton("Save").Click'
        assert cmt == ''

    def test_trailing_comment(self) -> None:
        code, cmt = _strip_inline_comment('x = 1   \' this is a note')
        assert code == 'x = 1'
        assert 'this is a note' in cmt

    def test_apostrophe_inside_string_is_not_a_comment(self) -> None:
        code, cmt = _strip_inline_comment('s = "don\'t split"')
        assert code == 's = "don\'t split"'
        assert cmt == ''


# ═══════════════════════════════════════════════════════════════════════════════
# Line continuation joiner
# ═══════════════════════════════════════════════════════════════════════════════

class TestJoinContinuations:
    def test_single_continuation(self) -> None:
        raw = ['Reporter.ReportEvent micFail, "Step", _',
               '    "Long message"']
        joined = _join_continuations(raw)
        assert len(joined) == 1
        assert 'Long message' in joined[0]

    def test_multiple_continuations(self) -> None:
        raw = ['a = "one" & _', '    "two" & _', '    "three"']
        joined = _join_continuations(raw)
        assert joined == ['a = "one" & "two" & "three"']

    def test_no_continuation_passthrough(self) -> None:
        raw = ['line one', 'line two']
        assert _join_continuations(raw) == raw


# ═══════════════════════════════════════════════════════════════════════════════
# py_expr — VBScript expression → Python
# ═══════════════════════════════════════════════════════════════════════════════

class TestPyExpr:
    def test_string_literal_preserved(self) -> None:
        assert py_expr('"hello"') == '"hello"'

    def test_boolean(self) -> None:
        assert py_expr('True') == 'True'
        assert py_expr('false') == 'False'

    def test_null_nothing_empty(self) -> None:
        assert py_expr('Nothing') == 'None'
        assert py_expr('Null') == 'None'
        assert py_expr('Empty') == 'None'

    def test_numeric(self) -> None:
        assert py_expr('42') == '42'
        assert py_expr('3.14') == '3.14'

    def test_datatable_lookup(self) -> None:
        assert py_expr('DataTable("Username", dtLocalSheet)') == 'row.require("Username")'

    def test_environment_var(self) -> None:
        assert py_expr('Environment("USER")') == 'os.environ.get("USER", "")'

    def test_simple_concat(self) -> None:
        result = py_expr('"prefix-" & sUser')
        assert '"prefix-" + user' == result

    def test_concat_with_datatable(self) -> None:
        result = py_expr('"Hello " & DataTable("Name") & "!"')
        assert 'row.require("Name")' in result
        assert '+' in result

    def test_len_func(self) -> None:
        assert py_expr('Len(sName)') == 'len(name)'

    def test_left_right_mid(self) -> None:
        assert py_expr('Left(sName, 3)') == 'name[:3]'
        assert py_expr('Right(sName, 4)') == 'name[-4:]'
        # Mid is 1-indexed in VBScript; Mid(s, 2, 3) → s[1:4]
        assert py_expr('Mid(sName, 2, 3)') == 'name[1:4]'

    def test_case_helpers(self) -> None:
        assert py_expr('UCase(sName)') == 'name.upper()'
        assert py_expr('LCase(sName)') == 'name.lower()'
        assert py_expr('Trim(sName)') == 'name.strip()'

    def test_replace(self) -> None:
        assert py_expr('Replace(sName, "a", "b")') == 'name.replace("a", "b")'

    def test_type_conversions(self) -> None:
        assert py_expr('CStr(iX)')  == 'str(x)'
        assert py_expr('CInt(sN)')  == 'int(n)'
        assert py_expr('CDbl(sN)')  == 'float(n)'
        assert py_expr('CBool(iX)') == 'bool(x)'

    def test_now_date_time(self) -> None:
        assert py_expr('Now()')  == 'datetime.now()'
        assert py_expr('Date()') == 'datetime.now().date()'
        assert py_expr('Time()') == 'datetime.now().time()'

    def test_unrecognised_expression_yields_valid_python(self) -> None:
        """Regression: previously emitted a bare '# TODO ...' that broke syntax."""
        result = py_expr('SomeWeirdFunction(a, b, c)')
        # Result must be a parseable Python expression.
        _assert_valid_python(f"x = {result}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# py_cond — VBScript boolean → Python
# ═══════════════════════════════════════════════════════════════════════════════

class TestPyCond:
    def test_not_equal_operator(self) -> None:
        assert py_cond('sX <> sY') == 'x != y'

    def test_and_or_not(self) -> None:
        assert py_cond('a And b')  == 'a and b'
        assert py_cond('a Or b')   == 'a or b'
        assert py_cond('Not a')    == 'not a'

    def test_instr_substring(self) -> None:
        # InStr(hay, needle) > 0 → needle in hay
        assert py_cond('InStr(sActual, "expected") > 0') == '"expected" in actual'

    def test_isnull_isempty_isnumeric(self) -> None:
        assert py_cond('IsNull(sX)')    == 'x is None'
        assert py_cond('IsEmpty(sX)')   == '(x is None or x == "")'
        assert py_cond('IsNumeric(sX)') == 'str(x).isnumeric()'

    def test_strips_trailing_then(self) -> None:
        assert py_cond('a = b Then') == 'a = b'

    def test_page_exist_to_screen_exists(self) -> None:
        result = py_cond('Page("Home").Exist(10) Then')
        assert '_screen_exists(or_repo, "home.header_label", timeout=10)' in result


# ═══════════════════════════════════════════════════════════════════════════════
# UFT Web object actions
# ═══════════════════════════════════════════════════════════════════════════════

class TestWebActions:
    def test_webedit_set(self) -> None:
        r = _t('WebEdit("Username").Set sUser')
        assert r.lines == ['actions.type_text("login.username", user)']
        assert r.confidence == 100
        assert r.obj_name == 'login.username'

    def test_webedit_setsecure(self) -> None:
        r = _t('WebEdit("Password").SetSecure "abcdef"')
        assert any('type_text' in ln for ln in r.lines)
        assert r.confidence == CONF['HIGH']

    def test_webedit_getroproperty(self) -> None:
        r = _t('sActual = WebEdit("Field").GetROProperty("value")')
        assert any('ocr.read_target' in ln for ln in r.lines)
        assert r.ocr_name == 'login.field_text'

    def test_webedit_click(self) -> None:
        r = _t('WebEdit("Field").Click')
        assert r.lines == ['actions.click("login.field")']

    def test_webbutton_click(self) -> None:
        r = _t('WebButton("Sign In").Click')
        assert r.obj_name == 'login.sign_in'

    def test_weblink_click(self) -> None:
        r = _t('WebLink("More").Click')
        assert r.lines == ['actions.click("login.more")']

    def test_webelement_click(self) -> None:
        r = _t('WebElement("Tab").Click')
        assert r.lines == ['actions.click("login.tab")']

    def test_webelement_fireevent(self) -> None:
        r = _t('WebElement("Btn").FireEvent "onclick"')
        assert any('click' in ln for ln in r.lines)

    def test_webcheckbox_set_on(self) -> None:
        r = _t('WebCheckBox("AgreeToS").Set "ON"')
        assert r.obj_name == 'login.agree_to_s'

    def test_webradiogroup_select(self) -> None:
        r = _t('WebRadioGroup("Gender").Select "Female"')
        assert r.obj_name == 'login.gender'

    def test_weblist_select(self) -> None:
        r = _t('WebList("State").Select "TX"')
        assert r.confidence == CONF['MEDIUM']

    def test_weblist_getroproperty(self) -> None:
        r = _t('sValue = WebList("State").GetROProperty("value")')
        assert any('ocr.read_target' in ln for ln in r.lines)

    def test_webfile_set(self) -> None:
        r = _t('WebFile("Upload").Set "C:\\\\tmp\\\\file.pdf"')
        assert any('type_text' in ln for ln in r.lines)

    def test_browser_page_webbutton(self) -> None:
        r = _t('Browser("App").Page("Home").WebButton("Save").Click')
        assert r.lines == ['actions.click("login.save")']

    def test_browser_page_webedit_set(self) -> None:
        r = _t('Browser("App").Page("Home").WebEdit("User").Set "alice"')
        assert any('type_text' in ln for ln in r.lines)

    def test_browser_sync(self) -> None:
        r = _t('Browser("App").Sync')
        assert any('wait_for_screen_stable' in ln for ln in r.lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Win / Java / Dialog
# ═══════════════════════════════════════════════════════════════════════════════

class TestDesktopActions:
    def test_winbutton_click(self) -> None:
        r = _t('WinButton("OK").Click')
        assert r.lines == ['actions.click("login.ok")']

    def test_winedit_set(self) -> None:
        r = _t('WinEdit("Field").Set "x"')
        assert any('type_text' in ln for ln in r.lines)

    def test_javabutton_click(self) -> None:
        r = _t('JavaButton("Submit").Click')
        assert r.lines == ['actions.click("login.submit")']

    def test_javaedit_settext(self) -> None:
        r = _t('JavaEdit("Field").SetText "abc"')
        assert any('type_text' in ln for ln in r.lines)

    def test_dialog_winbutton(self) -> None:
        r = _t('Dialog("Confirm").WinButton("Yes").Click')
        assert r.lines == ['actions.click("login.yes")']

    def test_swfbutton_click(self) -> None:
        r = _t('SwfButton("Go").Click')
        assert any('click' in ln for ln in r.lines)

    def test_window_activate(self) -> None:
        r = _t('Window("Notepad").Activate')
        assert any('Notepad' in ln for ln in r.lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Reporter
# ═══════════════════════════════════════════════════════════════════════════════

class TestReporter:
    def test_micpass(self) -> None:
        r = _t('Reporter.ReportEvent micPass, "Step", "ok"')
        assert r.lines == ['ctx.reporter.passed("Step", "ok")']

    def test_micfail_emits_raise(self) -> None:
        r = _t('Reporter.ReportEvent micFail, "Step", "bad"')
        assert any('failed' in ln for ln in r.lines)
        assert any('raise' in ln for ln in r.lines)

    def test_micwarning(self) -> None:
        r = _t('Reporter.ReportEvent micWarning, "Step", "warn"')
        assert any('warning' in ln for ln in r.lines)

    def test_micinfo(self) -> None:
        r = _t('Reporter.ReportEvent micInfo, "Step", "info"')
        assert any('info' in ln for ln in r.lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Data
# ═══════════════════════════════════════════════════════════════════════════════

class TestData:
    def test_datatable_assignment(self) -> None:
        r = _t('sUser = DataTable("Username", dtLocalSheet)')
        assert r.lines == ['user = row.require("Username")']
        assert r.is_data_load is True

    def test_environment_assignment(self) -> None:
        r = _t('sHost = Environment("HOST")')
        assert any('os.environ.get("HOST"' in ln for ln in r.lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Function-body translation: blocks
# ═══════════════════════════════════════════════════════════════════════════════

def _flatten(fr) -> str:
    return "\n".join(fr.body_lines)


class TestBlocks:
    def test_if_else_endif(self) -> None:
        src = textwrap.dedent("""
            If sUser = "admin" Then
                Reporter.ReportEvent micPass, "P", "ok"
            Else
                Reporter.ReportEvent micFail, "F", "bad"
            End If
        """).strip().splitlines()
        fr = translate_function(src, "TestFn", "login")
        out = _flatten(fr)
        assert 'if user == "admin":' in out
        assert 'else:' in out

    def test_elseif_chain(self) -> None:
        src = textwrap.dedent("""
            If sX = 1 Then
                Reporter.ReportEvent micPass, "A", "1"
            ElseIf sX = 2 Then
                Reporter.ReportEvent micPass, "B", "2"
            Else
                Reporter.ReportEvent micPass, "C", "3"
            End If
        """).strip().splitlines()
        fr = translate_function(src, "TestFn", "login")
        out = _flatten(fr)
        assert 'if x == 1:' in out
        assert 'elif x == 2:' in out
        assert 'else:' in out

    def test_for_next(self) -> None:
        src = ['For i = 1 To 5', '    Reporter.ReportEvent micInfo, "loop", i', 'Next']
        fr = translate_function(src, "TestFn", "login")
        out = _flatten(fr)
        assert 'for i in range(1, 5 + 1):' in out

    def test_for_each(self) -> None:
        src = ['For Each item In arr', '    Reporter.ReportEvent micInfo, "i", item', 'Next']
        fr = translate_function(src, "TestFn", "login")
        out = _flatten(fr)
        assert 'for item in arr:' in out

    def test_do_while(self) -> None:
        src = ['Do While iN < 10', '    iN = iN + 1', 'Loop']
        fr = translate_function(src, "TestFn", "login")
        out = _flatten(fr)
        assert 'while n < 10:' in out

    def test_do_until(self) -> None:
        src = ['Do Until iN > 10', '    iN = iN + 1', 'Loop']
        fr = translate_function(src, "TestFn", "login")
        out = _flatten(fr)
        assert 'while not (n > 10):' in out

    def test_select_case(self) -> None:
        src = textwrap.dedent("""
            Select Case sX
                Case "a"
                    Reporter.ReportEvent micInfo, "A", "a"
                Case "b", "c"
                    Reporter.ReportEvent micInfo, "BC", "bc"
                Case Else
                    Reporter.ReportEvent micInfo, "E", "other"
            End Select
        """).strip().splitlines()
        fr = translate_function(src, "TestFn", "login")
        out = _flatten(fr)
        assert 'if x == "a":' in out
        assert 'elif x in ("b", "c"):' in out
        assert 'else:' in out

    def test_with_block_expands_object(self) -> None:
        src = textwrap.dedent("""
            With Browser("App").Page("Home")
                .WebEdit("User").Set "alice"
                .WebButton("Submit").Click
            End With
        """).strip().splitlines()
        fr = translate_function(src, "TestFn", "login")
        out = _flatten(fr)
        assert 'type_text("login.user"' in out
        assert 'click("login.submit")' in out

    def test_on_error_resume_next(self) -> None:
        src = textwrap.dedent("""
            On Error Resume Next
                WebButton("Maybe").Click
            On Error GoTo 0
        """).strip().splitlines()
        fr = translate_function(src, "TestFn", "login")
        out = _flatten(fr)
        assert 'try:' in out
        assert 'except Exception:' in out

    def test_exit_function_after_raise_is_suppressed(self) -> None:
        src = textwrap.dedent("""
            If Not WebElement("X").Exist(5) Then
                Reporter.ReportEvent micFail, "S", "bad"
                Exit Function
            End If
        """).strip().splitlines()
        fr = translate_function(src, "TestFn", "login")
        out = _flatten(fr)
        # raise then return is dead code; converter should drop the return.
        idx_raise = out.find('raise AssertionError')
        idx_return = out.find('return')
        assert idx_raise != -1
        # If 'return' appears at all, it must NOT be the line right after raise.
        if idx_return != -1:
            lines = out.splitlines()
            for i, ln in enumerate(lines):
                if 'raise' in ln and i + 1 < len(lines):
                    assert lines[i + 1].strip() != 'return'


# ═══════════════════════════════════════════════════════════════════════════════
# Generated code validity
# ═══════════════════════════════════════════════════════════════════════════════

class TestGeneratedCodeIsValidPython:
    """Every translated function body must parse as valid Python (after dedent)."""

    @pytest.mark.parametrize("vb_src", [
        # Each tuple is a tiny self-contained UFT fragment.
        'WebButton("Save").Click',
        'sUser = DataTable("User")',
        'Reporter.ReportEvent micPass, "S", "ok"',
        'Reporter.ReportEvent micFail, "S", "bad"',
        'If sX = "y" Then\n    WebButton("Save").Click\nEnd If',
        'For i = 1 To 5\n    WebButton("Save").Click\nNext',
        # Previously buggy: SomeUnknownFunc returned a bare TODO comment.
        'sActual = SomeUnknownFunc()',
    ])
    def test_translated_function_parses(self, vb_src: str) -> None:
        fr = translate_function(vb_src.splitlines(), "TestFn", "login")
        # Indent body 4 spaces to simulate a `def` wrapper.
        body = "\n".join("    " + ln if ln else "" for ln in fr.body_lines)
        if not body.strip():
            body = "    pass"
        prog = f"def f():\n{body}\n"
        try:
            ast.parse(prog)
        except SyntaxError as exc:
            pytest.fail(f"Generated code is not valid Python: {exc}\n\n{prog}")


# ═══════════════════════════════════════════════════════════════════════════════
# parse_qfl — function extractor
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseQfl:
    def test_extracts_named_function(self, tmp_path) -> None:
        qfl = tmp_path / "T.qfl"
        qfl.write_text(textwrap.dedent("""
            Public Function MyTest()
                WebButton("Save").Click
            End Function
        """).strip())
        fns = parse_qfl(qfl)
        assert len(fns) == 1
        assert fns[0][0] == "MyTest"
        assert any('Save' in ln for ln in fns[0][1])

    def test_extracts_sub(self, tmp_path) -> None:
        qfl = tmp_path / "T.qfl"
        qfl.write_text("Sub Foo\n    WebButton(\"x\").Click\nEnd Sub")
        fns = parse_qfl(qfl)
        assert fns[0][0] == "Foo"

    def test_top_level_script_wrapped_in_pseudo_function(self, tmp_path) -> None:
        qfl = tmp_path / "topscript.qfl"
        qfl.write_text('WebButton("Save").Click')
        fns = parse_qfl(qfl)
        assert len(fns) == 1
        # Name should be derived from the file stem.
        assert "topscript" in fns[0][0]

    def test_extracts_multiple_functions(self, tmp_path) -> None:
        qfl = tmp_path / "T.qfl"
        qfl.write_text(textwrap.dedent("""
            Public Function A()
                WebButton("a").Click
            End Function

            Public Function B()
                WebButton("b").Click
            End Function
        """).strip())
        fns = parse_qfl(qfl)
        assert [n for n, _ in fns] == ["A", "B"]


# ═══════════════════════════════════════════════════════════════════════════════
# Confidence report
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfidenceReport:
    def test_empty_report(self) -> None:
        report = _build_confidence_report([])
        assert report["total"] == 0
        assert report["avg"] == 100

    def test_excellent_quality_for_perfect_pattern(self) -> None:
        src = ['WebButton("Save").Click', 'Reporter.ReportEvent micPass, "S", "ok"']
        fr = translate_function(src, "TestFn", "login")
        report = _build_confidence_report([fr])
        assert report["quality"] == "EXCELLENT"


# ═══════════════════════════════════════════════════════════════════════════════
# NEW PATTERNS — extend coverage
# ═══════════════════════════════════════════════════════════════════════════════

class TestNewPatterns:
    """Patterns added during the Phase 2-5 audit. Each is a real UFT idiom."""

    # ── Exit For / Exit Do ──────────────────────────────────────────────────────
    def test_exit_for(self) -> None:
        r = _t('Exit For')
        assert r.lines == ['break']
        assert r.confidence == 100

    def test_exit_do(self) -> None:
        r = _t('Exit Do')
        assert r.lines == ['break']
        assert r.confidence == 100

    # ── Const declaration ───────────────────────────────────────────────────────
    def test_const_declaration(self) -> None:
        r = _t('Const MAX_RETRIES = 3')
        assert r.lines == ['MAX_RETRIES = 3']
        assert r.confidence == 100

    # ── Err.Number / Err.Description / Err.Clear ────────────────────────────────
    def test_err_clear(self) -> None:
        r = _t('Err.Clear')
        assert any('# Err.Clear' in ln or 'pass' in ln for ln in r.lines)

    def test_err_number_check_in_condition(self) -> None:
        # Err.Number <> 0 is a common UFT post-action check.
        result = py_cond('Err.Number <> 0')
        assert 'err.number' in result.lower() or '_err.number' in result.lower()

    # ── DblClick / DoubleClick / RightClick ─────────────────────────────────────
    def test_webelement_dblclick(self) -> None:
        r = _t('WebElement("Row").DblClick')
        assert any('double=True' in ln or 'doubleClick' in ln or 'dblclick' in ln.lower()
                   for ln in r.lines)

    def test_webelement_rightclick(self) -> None:
        r = _t('WebElement("Row").RightClick')
        assert any('right' in ln.lower() for ln in r.lines)

    # ── Send keys via .Type ─────────────────────────────────────────────────────
    def test_winedit_type(self) -> None:
        r = _t('WinEdit("Field").Type "hello"')
        assert any('type_text' in ln for ln in r.lines)

    # ── WaitProperty ────────────────────────────────────────────────────────────
    def test_waitproperty(self) -> None:
        r = _t('WebElement("X").WaitProperty "enabled", True, 10')
        assert any('wait_for_object_exists' in ln for ln in r.lines)

    # ── Frame in browser locator chain ──────────────────────────────────────────
    def test_browser_page_frame_webbutton(self) -> None:
        r = _t('Browser("App").Page("Home").Frame("inner").WebButton("Save").Click')
        assert r.lines == ['actions.click("login.save")']

    # ── Descriptive programming ─────────────────────────────────────────────────
    def test_descriptive_programming_extracts_name(self) -> None:
        r = _t('WebButton("name:=Submit", "html id:=btn-submit").Click')
        # Should match WebButton.Click and use 'Submit' (the "name:=" value) as elem.
        assert r.obj_name == 'login.submit'

    # ── Image / WebImage ────────────────────────────────────────────────────────
    def test_image_click(self) -> None:
        r = _t('Image("Logo").Click')
        assert r.lines == ['actions.click("login.logo")']

    def test_webimage_click(self) -> None:
        r = _t('WebImage("Logo").Click')
        assert r.lines == ['actions.click("login.logo")']

    # ── DataTable.SetCurrentRow / Value / GetRowCount ───────────────────────────
    def test_datatable_value_assign(self) -> None:
        r = _t('DataTable("Foo", dtLocalSheet) = "bar"')
        assert any('# TODO' in ln for ln in r.lines) or any('DataTable' in ln for ln in r.lines)

    # ── VBScript built-ins: Split, Join, Chr, Asc, Array ────────────────────────
    def test_split_function(self) -> None:
        result = py_expr('Split(sCsv, ",")')
        assert result == 'csv.split(",")'

    def test_join_function(self) -> None:
        result = py_expr('Join(arr, "-")')
        assert result == '"-".join(items)' or result == '"-".join(arr)'

    def test_chr_function(self) -> None:
        result = py_expr('Chr(65)')
        assert result == 'chr(65)'

    def test_asc_function(self) -> None:
        result = py_expr('Asc("A")')
        assert result == 'ord("A")'

    def test_ubound(self) -> None:
        result = py_expr('UBound(arr)')
        assert 'len(items) - 1' == result or 'len(arr) - 1' == result

    # ── Wait N translates to a proper wait helper ───────────────────────────────
    def test_wait_n_emits_callable_python(self) -> None:
        r = _t('Wait 2')
        # Must be runnable Python — not just a TODO comment.
        code = "\n".join(r.lines)
        # Either time.sleep or waits.wait_for_screen_stable, not bare TODO only.
        has_callable = (
            re.search(r'\bwaits\.\w+', code) is not None
            or re.search(r'\btime\.sleep', code) is not None
        )
        assert has_callable, f"Wait N must emit a callable wait; got: {r.lines}"

    # ── Case ranges and Case Is ────────────────────────────────────────────────
    def test_case_range(self) -> None:
        src = textwrap.dedent("""
            Select Case iX
                Case 1 To 5
                    Reporter.ReportEvent micInfo, "low", iX
                Case Is > 10
                    Reporter.ReportEvent micInfo, "high", iX
            End Select
        """).strip().splitlines()
        fr = translate_function(src, "TestFn", "login")
        out = _flatten(fr)
        assert '1 <= x <= 5' in out or '(x >= 1 and x <= 5)' in out
        assert 'x > 10' in out
