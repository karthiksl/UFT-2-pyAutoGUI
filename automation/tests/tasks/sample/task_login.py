"""Login-screen atomic tasks for the SAMPLE_TEST_000001 dry-run flow."""

from __future__ import annotations

from automation.common import Context
from automation.common.poms import sample_home as home_pom
from automation.common.poms import sample_login as login_pom
from automation.core import actions


def enter_username(ctx: Context, username: str) -> None:
    actions.type_text(login_pom.USERNAME_FIELD, username)


def enter_password(ctx: Context, password: str) -> None:
    actions.type_text(login_pom.PASSWORD_FIELD, password)


def click_login(ctx: Context) -> None:
    actions.click(login_pom.LOGIN_BTN, expect_after=home_pom.BANNER_LABEL)
