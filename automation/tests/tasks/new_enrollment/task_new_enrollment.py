"""Task stubs for new_enrollment screen — generated from TEST_188004_NEW_ENROLLMENT.qfl.

One function per UFT object. Wire up actions/OCR calls then import
into your flow as: from automation.tests.tasks.new_enrollment import task_new_enrollment
"""

from __future__ import annotations

from automation.common import Context
from automation.core import actions, ocr, waits


def activity_menu(ctx: Context) -> None:
    # TODO: implement — OR object "new_enrollment.activity_menu" (type: button)
    actions.click("new_enrollment.activity_menu")


def enrollment_menu_item(ctx: Context) -> None:
    # TODO: implement — OR object "new_enrollment.enrollment_menu_item" (type: button)
    actions.click("new_enrollment.enrollment_menu_item")


def enrollment_type_dropdown(ctx: Context) -> None:
    # TODO: implement — OR object "new_enrollment.enrollment_type_dropdown" (type: input)
    actions.click("new_enrollment.enrollment_type_dropdown")


def plan_dropdown(ctx: Context) -> None:
    # TODO: implement — OR object "new_enrollment.plan_dropdown" (type: input)
    actions.click("new_enrollment.plan_dropdown")


def effective_date_input(ctx: Context) -> None:
    # TODO: implement — OR object "new_enrollment.effective_date_input" (type: input)
    actions.click("new_enrollment.effective_date_input")


def submit_enrollment(ctx: Context) -> None:
    # TODO: implement — OR object "new_enrollment.submit_enrollment" (type: button)
    actions.click("new_enrollment.submit_enrollment")

