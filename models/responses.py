from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from models.snapshots import AnalysisSnapshot, JournalSnapshot, PositionSnapshot


@dataclass
class BotResponsePayload:
    text: str
    command: Optional[str] = None
    timeframe: Optional[str] = None
    analysis_snapshot: Optional[AnalysisSnapshot] = None
    journal_snapshot: Optional[JournalSnapshot] = None
    position_snapshot: Optional[PositionSnapshot] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    file_path: Optional[str] = None
    file_caption: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "command": self.command,
            "timeframe": self.timeframe,
            "analysis_snapshot": self.analysis_snapshot.to_dict() if self.analysis_snapshot else None,
            "journal_snapshot": self.journal_snapshot.to_dict() if self.journal_snapshot else None,
            "position_snapshot": self.position_snapshot.to_dict() if self.position_snapshot else None,
            "metadata": dict(self.metadata),
            "file_path": self.file_path,
            "file_caption": self.file_caption,
        }
