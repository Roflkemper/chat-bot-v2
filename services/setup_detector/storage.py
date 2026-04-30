from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    Setup,
    SetupBasis,
    SetupStatus,
    SetupType,
    make_setup,
)

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_JSONL = _ROOT / "state" / "setups.jsonl"
_DEFAULT_ACTIVE = _ROOT / "state" / "setups_active.json"


def _setup_to_dict(setup: Setup) -> dict[str, Any]:
    return {
        "setup_id": setup.setup_id,
        "setup_type": setup.setup_type.value,
        "detected_at": setup.detected_at.isoformat(),
        "pair": setup.pair,
        "current_price": setup.current_price,
        "regime_label": setup.regime_label,
        "session_label": setup.session_label,
        "entry_price": setup.entry_price,
        "stop_price": setup.stop_price,
        "tp1_price": setup.tp1_price,
        "tp2_price": setup.tp2_price,
        "risk_reward": setup.risk_reward,
        "grid_action": setup.grid_action,
        "grid_target_bots": list(setup.grid_target_bots),
        "grid_param_change": setup.grid_param_change,
        "strength": setup.strength,
        "confidence_pct": setup.confidence_pct,
        "basis": [{"label": b.label, "value": b.value, "weight": b.weight} for b in setup.basis],
        "cancel_conditions": list(setup.cancel_conditions),
        "window_minutes": setup.window_minutes,
        "expires_at": setup.expires_at.isoformat(),
        "status": setup.status.value,
        "portfolio_impact_note": setup.portfolio_impact_note,
        "recommended_size_btc": setup.recommended_size_btc,
    }


def _setup_from_dict(d: dict[str, Any]) -> Setup:
    basis = tuple(
        SetupBasis(label=b["label"], value=b["value"], weight=float(b["weight"]))
        for b in d.get("basis", [])
    )
    detected_at = datetime.fromisoformat(d["detected_at"])
    if detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=timezone.utc)
    # Use make_setup with explicit detected_at to preserve IDs and timestamps
    setup = make_setup(
        setup_type=SetupType(d["setup_type"]),
        pair=d["pair"],
        current_price=float(d["current_price"]),
        regime_label=d["regime_label"],
        session_label=d["session_label"],
        entry_price=d.get("entry_price"),
        stop_price=d.get("stop_price"),
        tp1_price=d.get("tp1_price"),
        tp2_price=d.get("tp2_price"),
        risk_reward=d.get("risk_reward"),
        grid_action=d.get("grid_action"),
        grid_target_bots=tuple(d.get("grid_target_bots", [])),
        grid_param_change=d.get("grid_param_change"),
        strength=int(d["strength"]),
        confidence_pct=float(d["confidence_pct"]),
        basis=basis,
        cancel_conditions=tuple(d.get("cancel_conditions", [])),
        window_minutes=int(d.get("window_minutes", 120)),
        portfolio_impact_note=d.get("portfolio_impact_note", ""),
        recommended_size_btc=float(d.get("recommended_size_btc", 0.05)),
        detected_at=detected_at,
    )
    # Override status (make_setup always sets DETECTED)
    actual_status = SetupStatus(d.get("status", "detected"))
    if actual_status != SetupStatus.DETECTED:
        object.__setattr__(setup, "setup_id", d["setup_id"])
        object.__setattr__(setup, "status", actual_status)
    else:
        object.__setattr__(setup, "setup_id", d["setup_id"])
    return setup


_ACTIVE_STATUSES = {SetupStatus.DETECTED, SetupStatus.ENTRY_HIT}


class SetupStorage:
    def __init__(
        self,
        jsonl_path: Path | None = None,
        active_path: Path | None = None,
    ) -> None:
        self._jsonl = jsonl_path or _DEFAULT_JSONL
        self._active = active_path or _DEFAULT_ACTIVE
        self._jsonl.parent.mkdir(parents=True, exist_ok=True)

    def write(self, setup: Setup) -> None:
        d = _setup_to_dict(setup)
        with self._jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        self._update_active(setup)
        logger.info(
            "setup_storage.write id=%s type=%s strength=%d",
            setup.setup_id,
            setup.setup_type.value,
            setup.strength,
        )

    def list_active(self) -> list[Setup]:
        if not self._active.exists():
            return []
        try:
            data: list[dict[str, Any]] = json.loads(self._active.read_text(encoding="utf-8"))
            return [_setup_from_dict(d) for d in data]
        except Exception:
            logger.exception("setup_storage.list_active_failed")
            return []

    def list_recent(self, hours: int = 24) -> list[Setup]:
        if not self._jsonl.exists():
            return []
        cutoff_ts = datetime.now(timezone.utc).timestamp() - hours * 3600
        result: list[Setup] = []
        try:
            for line in self._jsonl.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    detected = datetime.fromisoformat(d.get("detected_at", ""))
                    if detected.tzinfo is None:
                        detected = detected.replace(tzinfo=timezone.utc)
                    if detected.timestamp() >= cutoff_ts:
                        result.append(_setup_from_dict(d))
                except Exception:
                    continue
        except Exception:
            logger.exception("setup_storage.list_recent_failed")
        return result

    def update_status(self, setup_id: str, new_status: SetupStatus) -> None:
        """Update status in active JSON. Removes if terminal status."""
        if not self._active.exists():
            return
        try:
            data: list[dict[str, Any]] = json.loads(self._active.read_text(encoding="utf-8"))
            updated: list[dict[str, Any]] = []
            for d in data:
                if d.get("setup_id") == setup_id:
                    d = dict(d)
                    d["status"] = new_status.value
                    if new_status in _ACTIVE_STATUSES:
                        updated.append(d)
                    # else: terminal status — remove from active
                else:
                    updated.append(d)
            self._active.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("setup_storage.update_status_failed id=%s", setup_id)

    def _update_active(self, setup: Setup) -> None:
        existing: list[dict[str, Any]] = []
        if self._active.exists():
            try:
                existing = json.loads(self._active.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        # Remove if same setup_id already present (idempotent)
        existing = [d for d in existing if d.get("setup_id") != setup.setup_id]
        if setup.status in _ACTIVE_STATUSES:
            existing.append(_setup_to_dict(setup))
        self._active.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
