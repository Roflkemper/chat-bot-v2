"""Liquidation-based pre-cascade signal (Phase-1 R&D, 2026-05-13).

R&D (docs/STRATEGIES/PRE_CASCADE_SIGNAL_R&D.md) показал:
- Перед LONG-каскадом >=5 BTC за 15-20 мин накапливается ~0.44 BTC мелких liq
  на той же стороне (baseline ~0.005 BTC) — z=20, 88× выше нормы.
- SHORT: z=4.2 за 10-15 мин (22× выше baseline).

Live signal (Phase-1, консервативный):
- Окно: последние 5 мин.
- Trigger: на одной стороне >= LIQ_CLUSTER_THRESHOLD_BTC (0.3) накоплено,
  И ни один cascade>=5 BTC ещё не сработал за это окно (иначе тривиально —
  каскад уже идёт), И прошло >= cooldown с прошлого alert этой стороны.
- Side mapping: long-liq кластер → expects LONG cascade (continuation),
                short-liq кластер → expects SHORT cascade.

Цель: оператор получает info-alert "возможен каскад через 10-20 мин"
и не открывает новые позиции на этой стороне.
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
LIQ_CSV = ROOT / "market_live" / "liquidations.csv"
STATE_PATH = ROOT / "state" / "liq_pre_cascade_state.json"
JOURNAL_PATH = ROOT / "state" / "liq_pre_cascade_fires.jsonl"

# Tunables (можно править в env позже)
WINDOW_MINUTES = 5
LIQ_CLUSTER_THRESHOLD_BTC = 0.3       # Phase-1 conservative (R&D mean 0.44)
CASCADE_SUPPRESS_THRESHOLD_BTC = 5.0   # если >=5 BTC уже было — каскад уже идёт
COOLDOWN_SEC = 1800                    # 30 min per (side)
POLL_INTERVAL_SEC = 60


def _read_state(path: Path = STATE_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(state: dict, path: Path = STATE_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("liq_pre_cascade.write_state_failed")


def _append_journal(entry: dict, path: Path = JOURNAL_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("liq_pre_cascade.journal_failed")


def _liq_window_sums(now_utc: datetime, window_min: int,
                     liq_csv: Path = LIQ_CSV) -> tuple[float, float]:
    """Sum liq qty per side in [now-window, now]."""
    if not liq_csv.exists():
        return 0.0, 0.0
    cutoff = now_utc - timedelta(minutes=window_min)
    long_btc = 0.0
    short_btc = 0.0
    try:
        with liq_csv.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    ts = datetime.fromisoformat(r["ts_utc"])
                except (ValueError, KeyError):
                    continue
                if ts < cutoff or ts > now_utc:
                    continue
                try:
                    qty = float(r.get("qty") or 0.0)
                except ValueError:
                    continue
                if qty <= 0:
                    continue
                side = (r.get("side") or "").lower()
                if side == "long":
                    long_btc += qty
                elif side == "short":
                    short_btc += qty
    except OSError:
        logger.exception("liq_pre_cascade.read_failed")
    return long_btc, short_btc


def _format_alert(side: str, qty_btc: float) -> str:
    direction_word = "LONG" if side == "long" else "SHORT"
    return (
        f"🔍 PRE-CASCADE liq cluster: {direction_word}\n"
        f"За последние {WINDOW_MINUTES} мин: {qty_btc:.2f} BTC liq на стороне {side}\n"
        f"(baseline ~0.01 BTC за 5 мин)\n"
        f"\n"
        f"R&D-сигнал: возможен каскад >=5 BTC через 10-20 мин в эту же сторону.\n"
        f"Совет: не открывать новые {direction_word}-позиции в ближайшие 20 мин.\n"
        f"\n"
        f"Phase-1 conservative threshold (см. PRE_CASCADE_SIGNAL_R&D.md)."
    )


def check_and_alert(
    *,
    send_fn: Callable[[str], None],
    now: Optional[datetime] = None,
    state_path: Path = STATE_PATH,
    journal_path: Path = JOURNAL_PATH,
    liq_csv: Path = LIQ_CSV,
    window_min: int = WINDOW_MINUTES,
    cluster_threshold: float = LIQ_CLUSTER_THRESHOLD_BTC,
    cascade_suppress: float = CASCADE_SUPPRESS_THRESHOLD_BTC,
    cooldown_sec: int = COOLDOWN_SEC,
) -> list[dict]:
    """One tick of pre-cascade liq-cluster check.

    Returns list of fired-alert dicts (empty if nothing fired).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    long_btc, short_btc = _liq_window_sums(now, window_min, liq_csv=liq_csv)

    state = _read_state(state_path)
    fired: list[dict] = []

    for side, qty in (("long", long_btc), ("short", short_btc)):
        # Suppress если уже каскад
        if qty >= cascade_suppress:
            continue
        if qty < cluster_threshold:
            continue
        # Cooldown
        last_iso = state.get(f"last_alert_{side}")
        if last_iso:
            try:
                last_alert = datetime.fromisoformat(last_iso)
                if (now - last_alert).total_seconds() < cooldown_sec:
                    continue
            except ValueError:
                pass

        text = _format_alert(side, qty)
        try:
            send_fn(text)
        except Exception:
            logger.exception("liq_pre_cascade.send_failed side=%s", side)
            continue

        entry = {
            "ts": now.isoformat(timespec="seconds"),
            "side": side,
            "qty_btc": round(qty, 4),
            "window_min": window_min,
            "threshold_btc": cluster_threshold,
        }
        _append_journal(entry, journal_path)
        fired.append(entry)
        state[f"last_alert_{side}"] = now.isoformat(timespec="seconds")

    if fired:
        _write_state(state, state_path)
    return fired


async def liq_pre_cascade_loop(stop_event, *, send_fn=None,
                               interval_sec: int = POLL_INTERVAL_SEC) -> None:
    import asyncio
    if send_fn is None:
        logger.warning("liq_pre_cascade.no_send_fn — alerts будут только в логе")
    logger.info("liq_pre_cascade.start interval=%ds threshold=%.2fBTC window=%dmin",
                interval_sec, LIQ_CLUSTER_THRESHOLD_BTC, WINDOW_MINUTES)
    while not stop_event.is_set():
        try:
            if send_fn is not None:
                fired = check_and_alert(send_fn=send_fn)
                for entry in fired:
                    logger.info("liq_pre_cascade.fired side=%s qty=%.2f",
                                entry["side"], entry["qty_btc"])
        except Exception:
            logger.exception("liq_pre_cascade.tick_failed")
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue
    logger.info("liq_pre_cascade.stopped")
