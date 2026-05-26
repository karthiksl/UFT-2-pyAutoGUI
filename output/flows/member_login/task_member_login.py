"""Task stubs for member_login screen — generated from TEST_188001_MEMBER_LOGIN.qfl.

One function per UFT object. Wire up actions/OCR calls then import
into your flow as: from automation.tests.tasks.member_login import task_member_login
"""

from __future__ import annotations

from automation.common import Context
from automation.core import actions, ocr, waits


def username(ctx: Context) -> None:
    # TODO: implement — OR object "member_login.username" (type: input)
    actions.click("member_login.username")


def password(ctx: Context) -> None:
    # TODO: implement — OR object "member_login.password" (type: input)
    actions.click("member_login.password")


def sign_in(ctx: Context) -> None:
    # TODO: implement — OR object "member_login.sign_in" (type: button)
    actions.click("member_login.sign_in")

