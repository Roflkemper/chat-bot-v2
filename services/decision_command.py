"""Operator /decision command — record annotated decision with market snapshot."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_JOURNAL_DIR = _ROOT / "data" / "operator_journal"
_DECISIONS_JSONL = _JOURNAL_DIR / "manual_decisions.jsonl"
_ICT_PARQUET = _ROOT / "data" / "ict_levels" / "BTCUSDT_ict_levels_1m.parquet"
_ADVISE_SIGNALS = _ROOT / "state" / "advise_signals.jsonl"
_SNAPSHOTS_CSV = _ROOT / "ginarea_live" / "snapshots.csv"
_BOT_ALIASES_JSON = _ROOT / "ginarea_tracker" / "bot_aliases.json"

MAX_NOTES = 500

HELP_TEXT = """/decision <action> [notes]

Записывает решение оператора с авто-снапшотом рынка.

Действия:
  close_long / close_short / close_all
  pause / resume / stop
  raise_boundary / lower_boundary
  stack_short / stack_long
  manual

Примеры:
  /decision close_long Закрыл LONG at 78050. Breakout Be-OB. Жду откат 77400.
  /decision pause Жду откат.
  /decision manual Скорректировал границы TEST_3.

/decisions list [N] — последние N решений (default 5)
/decisions stats — статистика"""


def _make_decision_id(ts: datetime) -> str:
    return "dec_" + ts.strftime("%Y-%m-%dT%H-%M-%S")


def _load_prices() -> dict[str, float | None]:
    try:
        if not _ADVISE_SIGNALS.exists():
            return {"price_btc": None, "price_eth": None, "price_xrp": None}
        lines = _ADVISE_SIGNALS.read_text(encoding="utf-8").splitlines()
        for raw in reversed(lines):
            raw = raw.strip()
            if not raw:
                continue
            data = json.loads(raw)
            mc = data.get("market_context") or {}
            return {
                "price_btc": mc.get("price_btc"),
                "price_eth": mc.get("price_eth"),
                "price_xrp": mc.get("price_xrp"),
            }
    except Exception:
        logger.exception("decision_command.load_prices_failed")
    return {"price_btc": None, "price_eth": None, "price_xrp": None}


def _session_from_utc(ts: datetime) -> str:
    """Compute approximate ICT session label from UTC time without requiring the parquet."""
    try:
        from zoneinfo import ZoneInfo
        nyc = ts.astimezone(ZoneInfo("America/New_York"))
        h = nyc.hour + nyc.minute / 60.0
        if 20.0 <= h < 24.0:
            return "asia"
        if 2.0 <= h < 5.0:
            return "london"
        if 9.5 <= h < 11.0:
            return "ny_am"
        if 12.0 <= h < 13.0:
            return "ny_lunch"
        if 13.5 <= h < 16.0:
            return "ny_pm"
        return "dead"
    except Exception:
        return "dead"


def _load_ict_context(ts: datetime) -> dict[str, Any]:
    try:
        from services.setup_detector.ict_context import ICTContextReader
        reader = ICTContextReader.load(str(_ICT_PARQUET))
        ctx = reader.lookup(ts)
        if ctx:
            return ctx
        # Parquet is stale (>5 min gap) — compute session from clock, leave levels as None
        return {"session_active": _session_from_utc(ts)}
    except Exception:
        logger.exception("decision_command.ict_context_failed")
        return {"session_active": _session_from_utc(ts)}


def _load_operator_bot_ids() -> set[str]:
    """Return set of bot_id strings that belong to the operator (from bot_aliases.json)."""
    try:
        if not _BOT_ALIASES_JSON.exists():
            return set()
        data = json.loads(_BOT_ALIASES_JSON.read_text(encoding="utf-8"))
        return {str(k) for k in data.keys()}
    except Exception:
        return set()


def _bot_id_str(val: object) -> str:
    """Normalize float/int bot_id from CSV to integer string ('5196832375.0' → '5196832375')."""
    try:
        return str(int(float(str(val))))
    except Exception:
        return str(val)


def _load_bots_state() -> tuple[dict[str, Any], float | None, float | None]:
    try:
        import pandas as pd
        if not _SNAPSHOTS_CSV.exists():
            return {}, None, None
        df = pd.read_csv(_SNAPSHOTS_CSV)
        if df.empty:
            return {}, None, None
        df = df.sort_values("ts_utc").groupby("bot_id").last().reset_index()
        # Filter to operator's own bots only
        operator_ids = _load_operator_bot_ids()
        if operator_ids:
            mask = df["bot_id"].apply(_bot_id_str).isin(operator_ids)
            df = df[mask]
        bots: dict[str, Any] = {}
        for _, row in df.iterrows():
            bot_id = _bot_id_str(row.get("bot_id", ""))
            unrealized = float(row["current_profit"]) if pd.notna(row.get("current_profit")) else None
            bots[bot_id] = {
                "alias": str(row.get("alias") or row.get("bot_name") or bot_id),
                "state": str(row.get("status") or ""),
                "position": str(row.get("position") or ""),
                "unrealized_pnl": unrealized,
                "profit_total": float(row["profit"]) if pd.notna(row.get("profit")) else None,
            }
        total_unrealized: float | None = None
        vals = [v["unrealized_pnl"] for v in bots.values() if v["unrealized_pnl"] is not None]
        if vals:
            total_unrealized = round(sum(vals), 2)
        return bots, total_unrealized, None
    except Exception:
        logger.exception("decision_command.bots_state_failed")
        return {}, None, None


def _load_recent_param_events(ts: datetime, window_sec: int = 300) -> list[str]:
    try:
        import pandas as pd
        parquet_path = _JOURNAL_DIR / "decisions.parquet"
        if not parquet_path.exists():
            return []
        df = pd.read_parquet(parquet_path)
        if df.empty or "id" not in df.columns:
            return []
        ts_col = next((c for c in ("ts", "timestamp", "ts_utc") if c in df.columns), None)
        if ts_col is None:
            return []
        ts_ref = pd.Timestamp(ts)
        window = pd.Timedelta(seconds=window_sec)
        ts_series = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        mask = (ts_series >= ts_ref - window) & (ts_series <= ts_ref + window)
        return list(df.loc[mask, "id"].astype(str))
    except Exception:
        return []


def build_decision_record(action: str, notes: str) -> dict[str, Any]:
    ts = datetime.now(timezone.utc)
    prices = _load_prices()
    ict = _load_ict_context(ts)
    bots_state, total_unrealized, total_realized_24h = _load_bots_state()
    related = _load_recent_param_events(ts)
    return {
        "id": _make_decision_id(ts),
        "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "action": action,
        "notes": notes,
        "price_btc": prices.get("price_btc"),
        "price_eth": prices.get("price_eth"),
        "price_xrp": prices.get("price_xrp"),
        "session_active": ict.get("session_active"),
        "dist_to_pdh_pct": ict.get("dist_to_pdh_pct"),
        "dist_to_nearest_unmitigated_high_pct": ict.get("dist_to_nearest_unmitigated_high_pct"),
        "dist_to_nearest_unmitigated_low_pct": ict.get("dist_to_nearest_unmitigated_low_pct"),
        "bots_state": bots_state,
        "total_unrealized_pnl": total_unrealized,
        "total_realized_pnl_24h": total_realized_24h,
        "related_param_changes": related,
    }


def append_decision(record: dict[str, Any]) -> None:
    _JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    with _DECISIONS_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def parse_decision_command(original_text: str) -> tuple[str | None, str, str | None]:
    """
    Parse '/decision <action> [notes]' from original (case-preserved) text.
    Returns (action, notes, truncation_warning).
    action=None means no args → show help.
    """
    stripped = original_text.strip()
    parts = stripped.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return None, "", None
    rest = parts[1].strip()
    tokens = rest.split(maxsplit=1)
    action = tokens[0].lower()
    notes = tokens[1].strip() if len(tokens) > 1 else ""
    warning: str | None = None
    if len(notes) > MAX_NOTES:
        notes = notes[:MAX_NOTES]
        warning = f"⚠️ Notes обрезаны до {MAX_NOTES} символов."
    return action, notes, warning


def build_confirmation_reply(record: dict[str, Any], truncation_warning: str | None = None) -> str:
    lines = [
        "✅ Decision logged",
        f"ID: {record['id']}",
    ]
    price_btc = record.get("price_btc")
    if price_btc:
        lines.append(f"Price BTC: {price_btc:,.0f}")
    session = record.get("session_active") or "—"
    lines.append(f"Session: {session}")
    bots = record.get("bots_state") or {}
    lines.append(f"Bots: {len(bots)} tracked")
    total_upl = record.get("total_unrealized_pnl")
    if total_upl is not None:
        sign = "+" if total_upl >= 0 else ""
        lines.append(f"Unrealized PnL: {sign}{total_upl:,.2f}")
    notes = record.get("notes") or ""
    if notes:
        short = notes[:120] + ("..." if len(notes) > 120 else "")
        lines.append(f"Notes: {short}")
    if truncation_warning:
        lines.append(truncation_warning)
    return "\n".join(lines)


def load_recent_decisions(n: int = 5) -> list[dict[str, Any]]:
    if not _DECISIONS_JSONL.exists():
        return []
    raw_lines = [l for l in _DECISIONS_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    records = []
    for line in raw_lines[-n:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def build_decisions_list_text(n: int = 5) -> str:
    records = load_recent_decisions(n)
    if not records:
        return "Нет записей."
    lines = [f"Последние {len(records)} решений:"]
    for r in reversed(records):
        ts_short = (r.get("ts") or "")[:16].replace("T", " ")
        action = r.get("action") or "?"
        notes = (r.get("notes") or "")[:60]
        suffix = "..." if len(r.get("notes") or "") > 60 else ""
        price = r.get("price_btc")
        price_str = f" | BTC {price:,.0f}" if price else ""
        lines.append(f"{ts_short} {action}{price_str} — {notes}{suffix}")
    return "\n".join(lines)


def build_decisions_stats_text() -> str:
    if not _DECISIONS_JSONL.exists():
        return "Нет записей."
    raw_lines = [l for l in _DECISIONS_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    records = []
    for line in raw_lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not records:
        return "Нет записей."
    from collections import Counter
    counts: Counter[str] = Counter(r.get("action") or "unknown" for r in records)
    by_action = ", ".join(f"{a}={c}" for a, c in counts.most_common())
    lines = [
        f"Всего решений: {len(records)}",
        f"По действиям: {by_action}",
    ]
    return "\n".join(lines)
