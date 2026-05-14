from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RuntimeFlags:
    use_new_context_pipeline: bool = True
    use_new_strategy_registry: bool = True
    use_new_final_arbiter: bool = True
    use_new_execution_layer: bool = True
    use_new_presentation_layer: bool = True
    allow_legacy_fallback: bool = True
