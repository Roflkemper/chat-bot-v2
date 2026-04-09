from __future__ import annotations

from dataclasses import dataclass, field
from domain.contracts.directional_execution import DirectionalExecution
from domain.contracts.grid_execution import GridExecution


@dataclass(slots=True)
class ExecutionPlan:
    symbol: str
    timeframe: str
    timestamp: str
    primary_action: str
    primary_mode: str
    directional_execution: DirectionalExecution
    grid_execution: GridExecution
    operator_message: str
    warnings: list[str] = field(default_factory=list)
