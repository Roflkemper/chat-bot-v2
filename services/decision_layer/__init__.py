"""Decision Layer — rule-based translator from upstream signal state to operator events.

See decision_layer.py for full module docstring and DECISION_LAYER_v1 design source.
"""
from services.decision_layer.decision_layer import (
    DecisionInputs,
    DecisionLayer,
    DecisionLayerResult,
    Event,
    evaluate,
)

__all__ = [
    "DecisionInputs",
    "DecisionLayer",
    "DecisionLayerResult",
    "Event",
    "evaluate",
]
