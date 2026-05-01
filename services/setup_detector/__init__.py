from __future__ import annotations

from .combo_filter import COMBO_FILTER, filter_setups, is_combo_allowed
from .loop import setup_detector_loop
from .models import Setup, SetupBasis, SetupStatus, SetupType, make_setup, setup_side
from .outcomes import OutcomesWriter, ProgressResult, SetupOutcome, check_setup_progress
from .setup_types import DETECTOR_REGISTRY, DetectionContext, PortfolioSnapshot
from .stats_aggregator import SetupStats, compute_setup_stats, format_stats_card
from .storage import SetupStorage
from .tracker import setup_tracker_loop

__all__ = [
    "COMBO_FILTER",
    "filter_setups",
    "is_combo_allowed",
    "Setup",
    "SetupBasis",
    "SetupStatus",
    "SetupType",
    "make_setup",
    "setup_side",
    "DetectionContext",
    "PortfolioSnapshot",
    "DETECTOR_REGISTRY",
    "SetupStorage",
    "setup_detector_loop",
    "setup_tracker_loop",
    "ProgressResult",
    "SetupOutcome",
    "OutcomesWriter",
    "check_setup_progress",
    "SetupStats",
    "compute_setup_stats",
    "format_stats_card",
]
