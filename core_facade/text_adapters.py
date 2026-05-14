from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from models.snapshots import AnalysisSnapshot, JournalSnapshot, PositionSnapshot


LegacyBuilder = Callable[..., str]


def _analysis_dict(snapshot: AnalysisSnapshot) -> Dict[str, Any]:
    return snapshot.to_dict()


def _journal_dict(snapshot: Optional[JournalSnapshot]) -> Optional[Dict[str, Any]]:
    return snapshot.to_dict() if snapshot is not None else None


def _position_dict(snapshot: Optional[PositionSnapshot]) -> Optional[Dict[str, Any]]:
    return snapshot.to_dict() if snapshot is not None else None


def build_legacy_text(builder: LegacyBuilder, analysis_snapshot: AnalysisSnapshot, **kwargs: Any) -> str:
    return builder(_analysis_dict(analysis_snapshot), **kwargs)


def build_legacy_text_with_journal(
    builder: LegacyBuilder,
    analysis_snapshot: AnalysisSnapshot,
    journal_snapshot: Optional[JournalSnapshot] = None,
    **kwargs: Any,
) -> str:
    if journal_snapshot is None:
        return builder(_analysis_dict(analysis_snapshot), **kwargs)
    return builder(_analysis_dict(analysis_snapshot), journal=_journal_dict(journal_snapshot), **kwargs)


def build_legacy_text_with_position_and_journal(
    builder: LegacyBuilder,
    analysis_snapshot: AnalysisSnapshot,
    position_snapshot: Optional[PositionSnapshot] = None,
    journal_snapshot: Optional[JournalSnapshot] = None,
    **kwargs: Any,
) -> str:
    if position_snapshot is not None:
        kwargs["position"] = _position_dict(position_snapshot)
    if journal_snapshot is not None:
        kwargs["journal"] = _journal_dict(journal_snapshot)
    return builder(_analysis_dict(analysis_snapshot), **kwargs)
