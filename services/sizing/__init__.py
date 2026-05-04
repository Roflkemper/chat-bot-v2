"""Position sizing engine (rule-based v0.1).

See docs/DESIGN/SIZING_MULTIPLIER_v0_1.md for the spec.
"""
from .multiplier import SizingDecision, compute_sizing
from .integration import attach_sizing

__all__ = ["SizingDecision", "compute_sizing", "attach_sizing"]
