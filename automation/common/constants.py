"""Application-wide constants for Epic Hyperdrive automation.

# Migration notes
# UFT counterpart: FunctionLibrary/Constants.qfl or Environment variables
#   loaded via Environment.Value("CONST_NAME")
# Inferred functions / values:
#   AppConstants.DEFAULT_TIMEOUT      ← Environment("DefaultTimeout")
#   AppConstants.EPIC_DATE_FORMAT     ← hard-coded "MM/DD/YYYY" in multiple qfl
#   AppConstants.COVERAGE_TYPES       ← repeated literals in EnrollmentLib.qfl
#   AppConstants.PLAN_TIERS           ← repeated literals in PlanSelectionLib.qfl
#   AppConstants.CHANGE_REASONS       ← hard-coded dropdown values in CoverageLib.qfl
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class _AppConstants:
    """Frozen bag of application-level constants."""

    # Timing
    DEFAULT_TIMEOUT: float = 30.0
    NAVIGATION_TIMEOUT: float = 60.0
    MODAL_TIMEOUT: float = 20.0
    BUSY_POLL_INTERVAL: float = 0.5

    # Date / time formats
    EPIC_DATE_FORMAT: str = "%m/%d/%Y"

    # Citrix session window title (must match get_config()["citrix_window_title"])
    CITRIX_WINDOW_TITLE: str = "Citrix Viewer"

    # Epic domain values — must match application drop-down text exactly
    COVERAGE_TYPES: tuple[str, ...] = field(
        default_factory=lambda: ("Medical", "Dental", "Vision", "Life", "Disability")
    )

    PLAN_TIERS: tuple[str, ...] = field(
        default_factory=lambda: ("HMO", "PPO", "HDHP", "EPO")
    )

    CHANGE_REASONS: tuple[str, ...] = field(
        default_factory=lambda: (
            "Annual Open Enrollment",
            "Qualifying Life Event",
            "New Hire",
            "Termination",
            "COBRA",
            "Employer Change",
        )
    )

    CONFIRMATION_STATUSES: tuple[str, ...] = field(
        default_factory=lambda: ("Accepted", "Pending", "Rejected")
    )

    DEPENDENT_RELATIONSHIPS: tuple[str, ...] = field(
        default_factory=lambda: (
            "Spouse",
            "Child",
            "Domestic Partner",
            "Legal Guardian",
            "Disabled Dependent",
        )
    )

    # MRN / member ID constraints
    MRN_MIN_DIGITS: int = 6
    MRN_MAX_DIGITS: int = 10

    # OCR defaults
    OCR_MIN_CONFIDENCE: float = 0.65
    OCR_DEFAULT_LANG: str = "eng"

    # Retry defaults for business-layer operations
    BUSINESS_MAX_ATTEMPTS: int = 3
    BUSINESS_BACKOFF_S: float = 1.0


AppConstants = _AppConstants()
