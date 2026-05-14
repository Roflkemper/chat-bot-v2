"""Telegram alert dedup wrapper — state-change + cooldown + cluster-collapse.

Per Finding 1 (TZ-TELEGRAM-INVENTORY): cooldown ≠ dedup.
A cooldown alone allows the same RSI=27 to re-emit every 180 seconds even
though nothing materially changed. This wrapper adds two additional gates:

1. **State-change check**: emit only when the condition's value differs from
   the last emitted value by ≥ a per-emitter delta threshold.
2. **Cluster collapse**: within `cluster_window_sec`, multiple LEVEL_BREAK
   alerts with the same direction and prices within `cluster_price_delta_pct`
   collapse into ONE message with an aggregated levels list.

Per-emitter config controls all thresholds. Cooldown stays as a secondary
guard (final emit must satisfy cooldown AND state-change at the cooldown
expiry moment, not just at the original event).

Reasoning string: Russian only (per block 11 frozen params).

Usage:
    cfg = DedupConfig(cooldown_sec=180, value_delta_min=5)
    dedup = DedupLayer(cfg)
    decision = dedup.evaluate(emitter="auto_edge_alerts.rsi", value=27.5, key="BTCUSDT_15m")
    if decision.should_emit:
        send_telegram(text)
        dedup.record_emit(emitter="...", value=27.5, key="...", ts=now)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
_STATE_PATH = _ROOT / "data" / "telegram" / "dedup_state.json"


@dataclass
class DedupConfig:
    """Per-emitter dedup parameters.

    All times in seconds. value_delta_min is in the units of the emitter's
    primary metric (e.g. RSI points, price percentage).
    """
    cooldown_sec: int = 180
    value_delta_min: float = 5.0           # state-change threshold
    cluster_window_sec: int = 60           # for cluster collapse
    cluster_price_delta_pct: float = 0.5   # prices within this % cluster
    cluster_enabled: bool = False          # opt-in per emitter


@dataclass
class DedupDecision:
    """Output of evaluate(): whether to emit + reasoning in Russian."""
    should_emit: bool
    reason_ru: str
    cluster_levels: Optional[list[float]] = None  # if collapsing happened


@dataclass
class _EmitterState:
    last_emit_ts: float = 0.0
    last_emit_value: Optional[float] = None
    pending_cluster: list[tuple[float, float]] = field(default_factory=list)
    # pending_cluster: list of (ts, price) inside cluster_window_sec


class DedupLayer:
    """Stateful dedup wrapper. One instance per process; persists state to disk."""

    def __init__(self, cfg: DedupConfig, state_path: Path = _STATE_PATH) -> None:
        self.cfg = cfg
        self.state_path = state_path
        self._state: dict[str, _EmitterState] = {}
        self._load()

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for key, entry in raw.items():
            self._state[key] = _EmitterState(
                last_emit_ts=float(entry.get("last_emit_ts", 0)),
                last_emit_value=entry.get("last_emit_value"),
                pending_cluster=list(entry.get("pending_cluster", [])),
            )

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        out = {
            key: {
                "last_emit_ts": s.last_emit_ts,
                "last_emit_value": s.last_emit_value,
                "pending_cluster": s.pending_cluster,
            }
            for key, s in self._state.items()
        }
        self.state_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    def _state_key(self, emitter: str, key: str) -> str:
        return f"{emitter}::{key}"

    def evaluate(
        self,
        emitter: str,
        key: str,
        value: float,
        now_ts: Optional[float] = None,
    ) -> DedupDecision:
        """Decide whether to emit. Does NOT mutate state — call record_emit() if you do emit.

        emitter: namespaced source (e.g. "auto_edge_alerts.rsi")
        key:     within-emitter identity (e.g. "BTCUSDT_15m")
        value:   primary metric the alert is keyed on (RSI points, price)
        """
        now = now_ts if now_ts is not None else time.time()
        sk = self._state_key(emitter, key)
        st = self._state.get(sk)

        if st is None or st.last_emit_value is None:
            return DedupDecision(should_emit=True, reason_ru="первый сигнал — пропускаем")

        elapsed = now - st.last_emit_ts
        if elapsed < self.cfg.cooldown_sec:
            return DedupDecision(
                should_emit=False,
                reason_ru=f"cooldown активен (прошло {int(elapsed)}с из {self.cfg.cooldown_sec}с)",
            )

        delta = abs(float(value) - float(st.last_emit_value))
        if delta < self.cfg.value_delta_min:
            return DedupDecision(
                should_emit=False,
                reason_ru=(
                    f"значение не изменилось материально "
                    f"(дельта {delta:.2f} < порог {self.cfg.value_delta_min:.2f})"
                ),
            )

        return DedupDecision(
            should_emit=True,
            reason_ru=f"cooldown истёк и значение изменилось (дельта {delta:.2f})",
        )

    def evaluate_cluster(
        self,
        emitter: str,
        key: str,
        price: float,
        now_ts: Optional[float] = None,
    ) -> DedupDecision:
        """Cluster-collapse decision for LEVEL_BREAK-type alerts.

        Collects nearby prices within cluster_window_sec. If multiple prices
        within cluster_price_delta_pct, collapse into one emit with all levels.

        Returns:
            should_emit=True with cluster_levels populated when window closes
            should_emit=False (buffered) while still inside the window
        """
        if not self.cfg.cluster_enabled:
            # No clustering — fall back to plain evaluate using price as value
            return self.evaluate(emitter, key, price, now_ts=now_ts)

        now = now_ts if now_ts is not None else time.time()
        sk = self._state_key(emitter, key)
        st = self._state.setdefault(sk, _EmitterState())

        # Drop pending cluster entries older than window
        st.pending_cluster = [
            (ts, p) for (ts, p) in st.pending_cluster
            if now - ts <= self.cfg.cluster_window_sec
        ]

        # Add this price to pending cluster if it's within price-delta of an existing one
        if st.pending_cluster:
            anchor_price = st.pending_cluster[0][1]
            within = abs(price - anchor_price) / anchor_price * 100 < self.cfg.cluster_price_delta_pct
            if within:
                st.pending_cluster.append((now, price))
                return DedupDecision(
                    should_emit=False,
                    reason_ru=f"кластер: накапливаем (текущий размер {len(st.pending_cluster)})",
                )

        # No existing cluster within delta — start a new one and emit immediately
        # (single-level case stays a normal alert)
        st.pending_cluster = [(now, price)]
        return DedupDecision(
            should_emit=True,
            reason_ru="новый сигнал (кластер из 1 уровня)",
            cluster_levels=[price],
        )

    def flush_cluster(
        self,
        emitter: str,
        key: str,
        now_ts: Optional[float] = None,
    ) -> DedupDecision:
        """Force-flush pending cluster as one collapsed emit.

        Caller should call this when cluster_window_sec has elapsed since
        the cluster's first price.
        """
        sk = self._state_key(emitter, key)
        st = self._state.get(sk)
        if st is None or len(st.pending_cluster) <= 1:
            return DedupDecision(should_emit=False, reason_ru="нет накопленного кластера")
        levels = [p for (_, p) in st.pending_cluster]
        st.pending_cluster = []
        return DedupDecision(
            should_emit=True,
            reason_ru=f"кластер схлопнут: {len(levels)} уровней",
            cluster_levels=levels,
        )

    def record_emit(
        self,
        emitter: str,
        key: str,
        value: float,
        now_ts: Optional[float] = None,
    ) -> None:
        """Record an emit so the next evaluate() sees it. Call AFTER successful send."""
        now = now_ts if now_ts is not None else time.time()
        sk = self._state_key(emitter, key)
        st = self._state.setdefault(sk, _EmitterState())
        st.last_emit_ts = now
        st.last_emit_value = float(value)
        self._save()
