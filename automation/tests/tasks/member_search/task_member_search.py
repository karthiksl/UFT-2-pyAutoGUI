"""Task stubs for member_search screen — generated from TEST_188002_MEMBER_SEARCH.qfl.

One function per UFT object. Wire up actions/OCR calls then import
into your flow as: from automation.tests.tasks.member_search import task_member_search
"""

from __future__ import annotations

from automation.common import Context
from automation.core import actions, ocr, waits


def patient_search_bar(ctx: Context) -> None:
    # TODO: implement — OR object "member_search.patient_search_bar" (type: button)
    actions.click("member_search.patient_search_bar")


def mrn_search_input(ctx: Context) -> None:
    # TODO: implement — OR object "member_search.mrn_search_input" (type: input)
    actions.click("member_search.mrn_search_input")


def search_button(ctx: Context) -> None:
    # TODO: implement — OR object "member_search.search_button" (type: button)
    actions.click("member_search.search_button")


def first_result_row(ctx: Context) -> None:
    # TODO: implement — OR object "member_search.first_result_row" (type: button)
    actions.click("member_search.first_result_row")

