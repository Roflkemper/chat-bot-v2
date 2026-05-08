"""Counter-LONG dry-run cascade detector (DRY-RUN ONLY).

На каскаде long-ликвидаций >= threshold BTC за window_sec:
  - Проверяет portfolio guard (суммарный SHORT >= min_short_position_btc)
  - Запускает post-hoc симуляцию на market_1m.csv
  - Логирует в JSONL и отправляет в Telegram
  - Никаких реальных позиций не открывает

Live mode — отдельный апдейт после N>=5 dry-run сигналов, win-rate>=60%.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CFG = _ROOT / "config" / "counter_long.yaml"


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def simulate_posthoc(
    event_ts: str,
    entry_price: float,
    market_1m_csv: Path,
    *,
    target_pct: float = 0.30,
    stoploss_pct: float = 0.80,
    timeout_min: int = 60,
) -> dict[str, Any]:
    """Walk 1m bars after event_ts, determine counter-LONG outcome.

    Returns dict: outcome, pnl_pct, duration_min, bars_walked.
    outcome: 'target' | 'stop' | 'timeout' | 'insufficient_data' | 'error'
    """
    target_price = entry_price * (1 + target_pct / 100)
    stop_price = entry_price * (1 - stoploss_pct / 100)
    event_dt = _parse_ts(event_ts)
    bars_walked = 0
    last_close = entry_price

    try:
        with market_1m_csv.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                raw_ts = row.get("ts_utc") or row.get("Date") or ""
                if not raw_ts:
                    continue
                try:
                    bar_dt = _parse_ts(raw_ts)
                except ValueError:
                    continue
                if bar_dt <= event_dt:
                    continue

                bars_walked += 1
                elapsed_min = (bar_dt - event_dt).total_seconds() / 60
                high = float(row.get("high", 0) or 0)
                low = float(row.get("low", 0) or 0)
                close = float(row.get("close", 0) or 0)
                last_close = close

                if high >= target_price:
                    return {
                        "outcome": "target",
                        "pnl_pct": round(target_pct, 4),
                        "duration_min": round(elapsed_min, 1),
                        "bars_walked": bars_walked,
                    }
                if low <= stop_price:
                    return {
                        "outcome": "stop",
                        "pnl_pct": round(-stoploss_pct, 4),
                        "duration_min": round(elapsed_min, 1),
                        "bars_walked": bars_walked,
                    }
                if elapsed_min >= timeout_min:
                    pnl = (close - entry_price) / entry_price * 100
                    return {
                        "outcome": "timeout",
                        "pnl_pct": round(pnl, 4),
                        "duration_min": round(elapsed_min, 1),
                        "bars_walked": bars_walked,
                    }
    except Exception:
        logger.exception("counter_long.posthoc_failed entry=%.2f", entry_price)
        return {"outcome": "error", "pnl_pct": 0.0, "duration_min": 0.0, "bars_walked": 0}

    if bars_walked == 0:
        return {
            "outcome": "insufficient_data",
            "pnl_pct": 0.0,
            "duration_min": 0.0,
            "bars_walked": 0,
        }

    pnl = (last_close - entry_price) / entry_price * 100
    return {
        "outcome": "timeout",
        "pnl_pct": round(pnl, 4),
        "duration_min": float(bars_walked),
        "bars_walked": bars_walked,
    }


class CounterLongManager:
    """DRY-RUN counter-LONG cascade manager.

    Вызывать из asyncio-таска: `await manager.tick()` каждые 30с.
    """

    def __init__(self, cfg_path: Path = _DEFAULT_CFG) -> None:
        raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        self._enabled: bool = bool(raw.get("enabled", True))

        mode = raw.get("mode", "dry_run")
        if mode == "live":
            raise NotImplementedError("live mode не реализован — см. TZ-COUNTER-LONG-LIVE")

        trig = raw.get("trigger", {})
        self._trigger_side: str = str(trig.get("side", "long")).lower()
        self._min_qty_btc: float = float(trig.get("min_qty_btc", 15))
        _max = trig.get("max_qty_btc")
        self._max_qty_btc: float | None = float(_max) if _max is not None else None
        self._window_sec: int = int(trig.get("window_sec", 60))

        guard = raw.get("guard", {})
        self._min_short_btc: float = float(guard.get("min_short_position_btc", 0.5))

        sim = raw.get("sim_params", {})
        self._size_btc: float = float(sim.get("size_btc", 0.005))
        self._target_pct: float = float(sim.get("target_pct", 0.30))
        self._stoploss_pct: float = float(sim.get("stoploss_pct", 0.80))
        self._timeout_min: int = int(sim.get("timeout_min", 60))

        notify = raw.get("notify", {})
        self._dual_alert: bool = bool(notify.get("dual_alert", True))

        log_file: str = raw.get("log_file", "logs/counter_long_events.jsonl")
        log_path = Path(log_file)
        self._log_path: Path = log_path if log_path.is_absolute() else _ROOT / log_file

        self._liq_csv: Path = _ROOT / "market_live" / "liquidations.csv"
        self._market_1m_csv: Path = _ROOT / "market_live" / "market_1m.csv"
        self._snaps_dir: Path = _ROOT / "ginarea_tracker" / "ginarea_live"

        self._last_fired: float = 0.0
        self._dedup_sec: int = 900  # 15 min global cooldown
        # Fingerprint dedup: cascade_key -> epoch when last fired
        # key = "{qty_rounded_1}@{oldest_liq_ts_minute}"
        self._fired_keys: dict[str, float] = {}
        self._key_dedup_sec: int = 900  # 15 min per unique cascade key
        self._pending: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ public

    async def tick(self) -> None:
        if not self._enabled:
            return
        try:
            await self._check_new_cascade()
            await self._resolve_pending()
        except Exception:
            logger.exception("counter_long.tick_failed")

    # ------------------------------------------------------------------ detection

    def _sum_long_liq(self) -> tuple[float, float, str]:
        """Return (long_qty_btc, last_price, cascade_key).

        cascade_key = "{qty_rounded_0.1}@{oldest_contributing_ts_minute}"
        Used for fingerprint-based deduplication.
        """
        if not self._liq_csv.exists():
            return 0.0, 0.0, ""
        cutoff = time.time() - self._window_sec
        total = 0.0
        last_price = 0.0
        oldest_ts: str = ""
        try:
            with self._liq_csv.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    raw_ts = row.get("ts_utc", "")
                    try:
                        ts_epoch = datetime.fromisoformat(raw_ts).timestamp()
                    except (ValueError, TypeError):
                        continue
                    if ts_epoch < cutoff:
                        continue
                    if str(row.get("side", "")).lower() == self._trigger_side:
                        total += float(row.get("qty", 0) or 0)
                        p = float(row.get("price", 0) or 0)
                        if p:
                            last_price = p
                        if not oldest_ts or raw_ts < oldest_ts:
                            oldest_ts = raw_ts
        except Exception:
            logger.exception("counter_long.liq_read_failed")
        qty_rounded = round(total, 1)
        cascade_key = f"{qty_rounded}@{oldest_ts[:16]}" if oldest_ts else ""
        return round(total, 4), last_price, cascade_key

    def portfolio_short_btc(self) -> float:
        """Sum |position| of short bots (position < 0 in BTC) from latest snapshot."""
        if not self._snaps_dir.exists():
            return 0.0
        candidates = sorted(
            self._snaps_dir.glob("snapshots*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return 0.0
        total = 0.0
        try:
            with candidates[0].open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    try:
                        pos = float(row.get("position") or 0)
                    except (ValueError, TypeError):
                        continue
                    if pos < 0:
                        total += abs(pos)
        except Exception:
            logger.exception("counter_long.snaps_read_failed path=%s", candidates[0])
        return round(total, 4)

    async def _check_new_cascade(self) -> None:
        now = time.time()
        if now - self._last_fired < self._dedup_sec:
            return

        qty_btc, price, cascade_key = self._sum_long_liq()
        if qty_btc < self._min_qty_btc:
            return
        if self._max_qty_btc is not None and qty_btc > self._max_qty_btc:
            return

        # Fingerprint dedup: same cascade key seen within key_dedup_sec → skip
        if cascade_key and cascade_key in self._fired_keys:
            if now - self._fired_keys[cascade_key] < self._key_dedup_sec:
                logger.info(
                    "counter_long.cascade_key_dedup key=%s age=%.1fmin",
                    cascade_key, (now - self._fired_keys[cascade_key]) / 60,
                )
                return

        short_btc = self.portfolio_short_btc()
        if short_btc < self._min_short_btc:
            logger.info(
                "counter_long.guard_skip qty=%.2f short_btc=%.4f threshold=%.1f",
                qty_btc, short_btc, self._min_short_btc,
            )
            return

        self._last_fired = now
        if cascade_key:
            self._fired_keys[cascade_key] = now
            # Evict keys older than 2x dedup window to avoid unbounded growth
            cutoff = now - 2 * self._key_dedup_sec
            self._fired_keys = {k: v for k, v in self._fired_keys.items() if v > cutoff}
        entry_price = price if price > 0 else self._current_price()
        ts_now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        logger.info(
            "counter_long.triggered qty=%.2f entry=%.2f short_btc=%.4f",
            qty_btc, entry_price, short_btc,
        )
        self._pending.append({
            "ts": ts_now,
            "qty_btc": qty_btc,
            "entry_price": entry_price,
            "cascade_key": cascade_key,
            "resolve_after": now + self._timeout_min * 60,
        })
        # Log trigger to JSONL immediately (outcome appended separately after resolve)
        self._log_event({
            "event": "trigger",
            "ts": ts_now,
            "qty_btc": qty_btc,
            "price": entry_price,
            "cascade_key": cascade_key,
        })
        if self._dual_alert:
            trigger_text = (
                f"🟡 COUNTER-LONG триггер: каскад {qty_btc:.1f} BTC at {entry_price:,.0f}\n"
                f"Post-hoc resolve через {self._timeout_min}мин."
            )
            await self._notify(trigger_text)

    async def _resolve_pending(self) -> None:
        now = time.time()
        resolved = [e for e in self._pending if now >= e["resolve_after"]]
        self._pending = [e for e in self._pending if now < e["resolve_after"]]
        for ev in resolved:
            await self._process_event(ev)

    async def _process_event(self, ev: dict[str, Any]) -> None:
        sim = simulate_posthoc(
            ev["ts"],
            ev["entry_price"],
            self._market_1m_csv,
            target_pct=self._target_pct,
            stoploss_pct=self._stoploss_pct,
            timeout_min=self._timeout_min,
        )

        n_prev, wins_prev = self._read_stats_raw()
        is_win = sim["outcome"] == "target"
        n_now = n_prev + 1
        wins_now = wins_prev + (1 if is_win else 0)
        wr = round(wins_now / n_now * 100, 1) if n_now > 0 else 0.0

        outcome_icons = {
            "target": "✅", "stop": "🛑",
            "timeout": "⏱", "error": "❌", "insufficient_data": "❓",
        }
        outcome_icon = outcome_icons.get(sim["outcome"], "❓")
        header_icon = "🟢" if sim["outcome"] == "target" else "🔴"
        sign = "+" if sim["pnl_pct"] >= 0 else ""
        text = (
            f"{header_icon} COUNTER-LONG outcome: каскад {ev['qty_btc']:.1f} BTC\n"
            f"При size={self._size_btc} BTC inverse, "
            f"target +{self._target_pct:.2f}%, "
            f"stop -{self._stoploss_pct:.2f}%, "
            f"timeout {self._timeout_min}мин\n"
            f"→ {outcome_icon} outcome={sim['outcome']}, "
            f"pnl={sign}{sim['pnl_pct']:.2f}%, "
            f"duration={sim['duration_min']:.0f}мин\n"
            f"Cumulative N={n_now}, win-rate={wr:.0f}%"
        )

        self._log_event({
            "ts": ev["ts"],
            "qty_btc": ev["qty_btc"],
            "price": ev["entry_price"],
            "target_pct": self._target_pct,
            "stoploss_pct": self._stoploss_pct,
            "outcome": sim["outcome"],
            "pnl_pct": sim["pnl_pct"],
            "duration_min": sim["duration_min"],
            "cumulative_n": n_now,
            "win_rate_pct": wr,
        })
        await self._notify(text)

    # ------------------------------------------------------------------ helpers

    def _current_price(self) -> float:
        try:
            with self._market_1m_csv.open(newline="", encoding="utf-8") as fh:
                last = 0.0
                for row in csv.DictReader(fh):
                    try:
                        last = float(row["close"])
                    except (KeyError, ValueError):
                        pass
                return last
        except Exception:
            return 0.0

    def _iter_log(self):
        if not self._log_path.exists():
            return
        try:
            with self._log_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            pass
        except Exception:
            logger.exception("counter_long.iter_log_failed")

    def _read_stats_raw(self) -> tuple[int, int]:
        """Return (total_n, wins_n) from JSONL log."""
        n, wins = 0, 0
        for ev in self._iter_log():
            n += 1
            if ev.get("outcome") == "target":
                wins += 1
        return n, wins

    def _log_event(self, event: dict[str, Any]) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
                fh.flush()
        except Exception:
            logger.exception("counter_long.log_failed")

    async def _notify(self, text: str) -> None:
        from services.telegram_alert_service import send_telegram_alert
        await send_telegram_alert(text)
