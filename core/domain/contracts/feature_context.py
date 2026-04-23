from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FeatureContext:
    range_feature: dict[str, Any] = field(default_factory=dict)
    liquidity_blocks_feature: dict[str, Any] = field(default_factory=dict)
    liquidation_reaction_feature: dict[str, Any] = field(default_factory=dict)
    impulse_feature: dict[str, Any] = field(default_factory=dict)
    fake_move_feature: dict[str, Any] = field(default_factory=dict)
    volume_feature: dict[str, Any] = field(default_factory=dict)
    orderflow_feature: dict[str, Any] = field(default_factory=dict)
    reversal_feature: dict[str, Any] = field(default_factory=dict)
    pinbar_feature: dict[str, Any] = field(default_factory=dict)
    multi_tf_feature: dict[str, Any] = field(default_factory=dict)
    pattern_memory_feature: dict[str, Any] = field(default_factory=dict)
    grid_preactivation_feature: dict[str, Any] = field(default_factory=dict)
