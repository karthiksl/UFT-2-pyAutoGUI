"""Unit tests for automation.common.reporting_legacy."""

from __future__ import annotations

from automation.common.reporting_legacy import MicStatus, ReporterAdapter


class TestMicStatus:
    def test_pass_value_is_zero(self) -> None:
        assert MicStatus.PASS == 0

    def test_fail_value_is_one(self) -> None:
        assert MicStatus.FAIL == 1

    def test_warning_value_is_two(self) -> None:
        assert MicStatus.WARNING == 2

    def test_info_value_is_three(self) -> None:
        assert MicStatus.INFO == 3


class TestReporterAdapter:
    def test_passed_records_event(self) -> None:
        r = ReporterAdapter("TC001")
        r.passed("Step 1", "details")
        assert len(r.events) == 1
        assert r.events[0]["status"] == "PASS"

    def test_failed_records_event(self) -> None:
        r = ReporterAdapter()
        r.failed("Bad step", "something broke")
        assert r.has_failures() is True

    def test_no_failures_initially(self) -> None:
        r = ReporterAdapter()
        assert r.has_failures() is False

    def test_reset_clears_events(self) -> None:
        r = ReporterAdapter()
        r.passed("step")
        r.reset()
        assert r.events == []

    def test_report_event_with_mic_status_int(self) -> None:
        r = ReporterAdapter()
        r.report_event(MicStatus.WARNING, "warn step", "detail")
        assert r.events[0]["status"] == "WARNING"

    def test_info_event(self) -> None:
        r = ReporterAdapter()
        r.info("Info step")
        assert r.events[0]["status"] == "INFO"

    def test_warning_convenience(self) -> None:
        r = ReporterAdapter()
        r.warning("warn step")
        assert r.events[0]["status"] == "WARNING"

    def test_events_returns_copy(self) -> None:
        r = ReporterAdapter()
        r.passed("s")
        events = r.events
        events.clear()
        assert len(r.events) == 1
