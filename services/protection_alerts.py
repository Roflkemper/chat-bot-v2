"""Protection alerts — 3 проверки каждые 30с + relay LIQ_CASCADE из SignalAlertWorker.

Алерты:
  1. BTC_FAST_MOVE  — резкое движение цены по 1h OHLCV
  2. POSITION_STRESS — unrealized PnL бота в просадке
  3. LIQ_DANGER    — близко к ликвидации
  4. LIQ_CASCADE   — уже обрабатывается SignalAlertWorker; здесь не дублируем

Dry-run режим: алерты пишутся в лог, не в Telegram.
Конфиг: config/protection_alerts.yaml
"""
from __future__ import annotations

import csv
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CFG = _ROOT / "config" / "protection_alerts.yaml"


def _now_mono() -> float:
    return time.monotonic()


class ProtectionAlerts:
    _instance: "ProtectionAlerts | None" = None
    _lock = threading.Lock()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self, cfg_path: Path = _DEFAULT_CFG) -> None:
        raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        self._enabled: bool = bool(raw.get("enabled", True))
        self._dry_run: bool = bool(raw.get("dry_run", True))

        bfm = raw.get("btc_fast_move", {})
        self._bfm_warn = float(bfm.get("warning_pct", 1.5))
        self._bfm_crit = float(bfm.get("critical_pct", 2.5))
        self._bfm_extr = float(bfm.get("extreme_pct", 4.0))
        self._bfm_db   = int(bfm.get("debounce_min", 30))

        ps = raw.get("position_stress", {})
        self._ps_warn = float(ps.get("warning_usd", -150))
        self._ps_crit = float(ps.get("critical_usd", -300))
        self._ps_extr = float(ps.get("extreme_usd", -500))
        self._ps_minpos = float(ps.get("min_position_usd", 2000))
        self._ps_db    = int(ps.get("debounce_min", 15))

        ld = raw.get("liq_danger", {})
        self._ld_crit = float(ld.get("critical_pct", 15))
        self._ld_emer = float(ld.get("emergency_pct", 10))
        self._ld_db   = int(ld.get("debounce_min", 5))

        data = raw.get("data", {})
        self._ohlcv_1h   = _ROOT / data.get("ohlcv_1h_csv",   "market_live/market_1h.csv")
        self._ohlcv_1m   = _ROOT / data.get("ohlcv_1m_csv",   "market_live/market_1m.csv")
        self._snaps_dir  = _ROOT / data.get("snapshots_dir",  "ginarea_tracker/ginarea_live")
        self._signals_csv = _ROOT / data.get("signals_csv",   "market_live/signals.csv")

        self._debounce: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def instance(cls, cfg_path: Path = _DEFAULT_CFG) -> "ProtectionAlerts":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(cfg_path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    # ------------------------------------------------------------------
    # Public controls
    # ------------------------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        logger.info("protection_alerts.set_enabled enabled=%s", enabled)

    def set_threshold(self, alert: str, level: str, value: float) -> bool:
        """Update a threshold at runtime. Returns True on success."""
        mapping = {
            ("position_stress", "warning"):  "_ps_warn",
            ("position_stress", "critical"): "_ps_crit",
            ("position_stress", "extreme"):  "_ps_extr",
            ("btc_fast_move",   "warning"):  "_bfm_warn",
            ("btc_fast_move",   "critical"): "_bfm_crit",
            ("btc_fast_move",   "extreme"):  "_bfm_extr",
            ("liq_danger",      "critical"): "_ld_crit",
            ("liq_danger",      "emergency"):"_ld_emer",
        }
        attr = mapping.get((alert, level))
        if attr is None:
            return False
        setattr(self, attr, float(value))
        logger.info("protection_alerts.threshold_updated alert=%s level=%s value=%s", alert, level, value)
        return True

    def status_text(self) -> str:
        mode = "DRY-RUN (лог)" if self._dry_run else "LIVE (Telegram)"
        state = "✅ ON" if self._enabled else "⏸ OFF"
        lines = [
            f"🛡 Защита: {state} | {mode}",
            "",
            f"BTC_FAST_MOVE  warn≥{self._bfm_warn}%  crit≥{self._bfm_crit}%  extr≥{self._bfm_extr}%  db={self._bfm_db}мин",
            f"POSITION_STRESS  warn<{self._ps_warn}$  crit<{self._ps_crit}$  extr<{self._ps_extr}$  db={self._ps_db}мин",
            f"LIQ_DANGER  crit<{self._ld_crit}%  emer<{self._ld_emer}%  db={self._ld_db}мин",
            f"LIQ_CASCADE  активен (SignalAlertWorker)",
        ]
        if self._debounce:
            lines.append("")
            lines.append("Последние алерты:")
            now = _now_mono()
            for k, ts in sorted(self._debounce.items(), key=lambda x: -x[1])[:6]:
                ago = int((now - ts) // 60)
                lines.append(f"  {k}: {ago}мин назад")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Main tick — вызывается каждые 30с из app_runner
    # ------------------------------------------------------------------

    async def tick(self) -> None:
        if not self._enabled:
            return
        for check in (
            self._check_btc_fast_move,
            self._check_position_stress,
            self._check_liq_danger,
        ):
            try:
                await check()
            except Exception:
                logger.exception("protection_alerts.check_failed fn=%s", check.__name__)

    # ------------------------------------------------------------------
    # Debounce
    # ------------------------------------------------------------------

    def _should_send(self, key: str, debounce_min: int) -> bool:
        if _now_mono() - self._debounce.get(key, 0.0) < debounce_min * 60:
            return False
        self._debounce[key] = _now_mono()
        return True

    # ------------------------------------------------------------------
    # Internal send
    # ------------------------------------------------------------------

    async def _emit(self, text: str) -> None:
        if self._dry_run:
            logger.info("[PROTECTION DRY-RUN]\n%s", text)
            return
        from services.telegram_alert_service import send_telegram_alert
        await send_telegram_alert(text)

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _ohlcv_closes(self, path: Path, n: int) -> list[float]:
        if not path.exists():
            return []
        rows: list[float] = []
        try:
            with path.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    try:
                        rows.append(float(row["close"]))
                    except (KeyError, ValueError):
                        pass
        except Exception:
            logger.exception("protection_alerts.ohlcv_read_failed path=%s", path)
        return rows[-n:] if rows else []

    def _current_price(self) -> float | None:
        closes = self._ohlcv_closes(self._ohlcv_1m, 1)
        return closes[0] if closes else None

    def _bot_snapshots(self) -> dict[str, dict[str, Any]]:
        if not self._snaps_dir.exists():
            return {}
        candidates = sorted(
            self._snaps_dir.glob("snapshots*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return {}
        latest: dict[str, dict[str, Any]] = {}
        try:
            with candidates[0].open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    alias = (row.get("alias") or "").strip()
                    if alias:
                        latest[alias] = dict(row)
        except Exception:
            logger.exception("protection_alerts.snaps_read_failed path=%s", candidates[0])
        return latest

    # ------------------------------------------------------------------
    # Alert 1 — BTC_FAST_MOVE
    # ------------------------------------------------------------------

    def _1h_change(self) -> tuple[float, float, float] | None:
        """Returns (pct, price_from, price_to) or None."""
        closes = self._ohlcv_closes(self._ohlcv_1h, 2)
        if len(closes) < 2 or closes[-2] == 0:
            return None
        p0, p1 = closes[-2], closes[-1]
        return (p1 - p0) / p0 * 100, p0, p1

    async def _check_btc_fast_move(self) -> None:
        result = self._1h_change()
        if result is None:
            return
        pct, p0, p1 = result
        abs_pct = abs(pct)

        if abs_pct >= self._bfm_extr:
            level, icon = "EXTREME", "🔥"
        elif abs_pct >= self._bfm_crit:
            level, icon = "CRITICAL", "🚨"
        elif abs_pct >= self._bfm_warn:
            level, icon = "WARNING", "⚠️"
        else:
            return

        if not self._should_send(f"BTC_FAST_MOVE_{level}", self._bfm_db):
            return

        sign = "+" if pct > 0 else ""
        text = (
            f"{icon} BTC FAST MOVE [{level}]\n"
            f"Δ1ч: {sign}{pct:.2f}% | ${p0:,.0f} → ${p1:,.0f}\n"
            f"\nДействие: наблюдение."
        )
        if abs_pct >= self._bfm_crit:
            text += "\nЕсли рост продолжится >3% — рассмотри raise_top на шортах."
        await self._emit(text)

    # ------------------------------------------------------------------
    # Alert 2 — POSITION_STRESS
    # ------------------------------------------------------------------

    async def _check_position_stress(self) -> None:
        price = self._current_price()
        if not price:
            return
        for alias, snap in self._bot_snapshots().items():
            try:
                profit_btc = float(snap.get("current_profit") or 0)
                position   = float(snap.get("position") or 0)
                avg_entry  = float(snap.get("average_price") or 0)
                liq_price  = float(snap.get("liquidation_price") or 0)
            except (ValueError, TypeError):
                continue

            # Inverse contract: current_profit is in BTC → convert to USD
            upnl_usd = profit_btc * price

            if upnl_usd <= self._ps_extr:
                level, icon = "EXTREME", "🔥"
            elif upnl_usd <= self._ps_crit:
                level, icon = "CRITICAL", "🚨"
            elif upnl_usd <= self._ps_warn and abs(position) >= self._ps_minpos:
                level, icon = "WARNING", "⚠️"
            else:
                continue

            if not self._should_send(f"POSITION_STRESS_{alias}_{level}", self._ps_db):
                continue

            dist = abs(liq_price - price) / price * 100 if liq_price else 0
            lines = [
                f"{icon} POSITION STRESS — {alias} [{level}]",
                f"unrealized: {upnl_usd:+.0f}$",
                f"position: {position:+,.0f}$",
            ]
            if dist:
                lines.append(f"distance to liq: {dist:.1f}%")
            if avg_entry:
                lines.append(f"avg entry: {avg_entry:,.0f} | current: {price:,.0f}")
            lines.append("\nДействие: рассмотри RAISE_TOP или сокращение позиции.")
            if dist > 15:
                lines.append("Не закрывай вручную в минус если distance>15% — сетка вытянет.")
            await self._emit("\n".join(lines))

    # ------------------------------------------------------------------
    # Alert 3 — LIQ_DANGER
    # ------------------------------------------------------------------

    async def _check_liq_danger(self) -> None:
        price = self._current_price()
        if not price:
            return
        for alias, snap in self._bot_snapshots().items():
            try:
                liq_price = float(snap.get("liquidation_price") or 0)
                position  = float(snap.get("position") or 0)
            except (ValueError, TypeError):
                continue

            if not liq_price:
                continue

            dist = abs(liq_price - price) / price * 100

            if dist <= self._ld_emer:
                level, icon = "EMERGENCY", "🔥"
            elif dist <= self._ld_crit:
                level, icon = "CRITICAL", "🚨"
            else:
                continue

            if not self._should_send(f"LIQ_DANGER_{alias}_{level}", self._ld_db):
                continue

            text = (
                f"{icon} LIQ DANGER — {alias} [{level}]\n"
                f"distance to liq: {dist:.1f}%\n"
                f"position: {position:+,.0f}$\n"
                f"current: {price:,.0f} | liq: {liq_price:,.0f}\n"
                f"\nДЕЙСТВИЕ ТРЕБУЕТСЯ:\n"
                f"1. Урезать позицию на 30-50%\n"
                f"2. Или открыть hedge\n"
                f"3. Не ждать — distance падает быстро"
            )
            await self._emit(text)
