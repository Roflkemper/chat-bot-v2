"""State Snapshot — collect current project state into MD + JSON.

Usage:
    python scripts/state_snapshot.py
    python scripts/state_snapshot.py --no-api
    python scripts/state_snapshot.py --lookback-hours 48
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATE_DIR = ROOT / "docs" / "STATE"
STATE_DIR.mkdir(parents=True, exist_ok=True)

SNAPSHOTS_CSV = ROOT / "ginarea_live" / "snapshots.csv"
BOT_MANAGER_STATE = ROOT / "state" / "bot_manager_state.json"
GRID_PORTFOLIO = ROOT / "state" / "grid_portfolio.json"
RUN_DIR = ROOT / "run"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_tz() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _age_minutes(path: Path) -> float | None:
    if not path.exists():
        return None
    return (time.time() - path.stat().st_mtime) / 60


def _fmt_age(minutes: float | None) -> str:
    if minutes is None:
        return "N/A"
    if minutes < 60:
        return f"{minutes:.0f}min"
    return f"{minutes/60:.1f}h"


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None


def _is_valid_bot_row(bot_id: str, bot_name: str) -> bool:
    """GinArea bot IDs are 7–12 digit numeric strings; name must not be a float."""
    if not bot_id.isdigit():
        return False
    if not (7 <= len(bot_id) <= 12):
        return False
    try:
        float(bot_name)
        return False  # name parses as number → garbage row
    except ValueError:
        return True


def _infer_position_unit(position: float | None) -> str:
    """USD if |position| > 100 (USDT-M linear contract), else BTC."""
    if position is None:
        return "BTC"
    return "USD" if abs(position) > 100 else "BTC"


# ---------------------------------------------------------------------------
# Source: snapshots.csv (tail last lookback_hours)
# ---------------------------------------------------------------------------

def _load_snapshots(lookback_hours: int) -> dict:
    result: dict = {"status": "unavailable", "reason": "file not found", "rows": [], "last_ts": None}
    if not SNAPSHOTS_CSV.exists():
        return result

    cutoff_dt = _now_tz() - timedelta(hours=lookback_hours)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%dT%H:%M")

    rows: list[dict] = []
    header: list[str] = []

    with open(SNAPSHOTS_CSV, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if i == 0:
                header = line.split(",")
                continue
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < len(header):
                parts += [""] * (len(header) - len(parts))
            row = dict(zip(header, parts))
            if row.get("ts_utc", "") >= cutoff_str:
                rows.append(row)

    if not rows and header:
        # At least read last line for freshness check
        with open(SNAPSHOTS_CSV, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > 1:
            last = lines[-1].strip().split(",")
            if len(last) >= len(header):
                rows = [dict(zip(header, last))]

    last_ts = rows[-1].get("ts_utc") if rows else None
    age_min = _age_minutes(SNAPSHOTS_CSV)

    return {
        "status": "ok",
        "path": str(SNAPSHOTS_CSV.relative_to(ROOT)),
        "last_ts": last_ts,
        "age_min": age_min,
        "rows_in_window": len(rows),
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Source: bot_manager_state.json (AGM state)
# ---------------------------------------------------------------------------

def _load_bot_manager() -> dict:
    result: dict = {"status": "unavailable", "reason": "file not found", "bots": {}}
    if not BOT_MANAGER_STATE.exists():
        return result
    try:
        data = json.loads(BOT_MANAGER_STATE.read_text(encoding="utf-8"))
        age_min = _age_minutes(BOT_MANAGER_STATE)
        return {
            "status": "ok",
            "path": str(BOT_MANAGER_STATE.relative_to(ROOT)),
            "updated_at": data.get("updated_at"),
            "age_min": age_min,
            "bots": data.get("bots", {}),
        }
    except Exception as e:
        return {"status": "unavailable", "reason": str(e), "bots": {}}


# ---------------------------------------------------------------------------
# Source: grid_portfolio.json (orchestrator categories)
# ---------------------------------------------------------------------------

def _load_grid_portfolio() -> dict:
    result: dict = {"status": "unavailable", "reason": "file not found", "categories": {}}
    if not GRID_PORTFOLIO.exists():
        return result
    try:
        data = json.loads(GRID_PORTFOLIO.read_text(encoding="utf-8"))
        age_min = _age_minutes(GRID_PORTFOLIO)
        return {
            "status": "ok",
            "path": str(GRID_PORTFOLIO.relative_to(ROOT)),
            "updated_at": data.get("updated_at"),
            "age_min": age_min,
            "categories": data.get("categories", {}),
        }
    except Exception as e:
        return {"status": "unavailable", "reason": str(e), "categories": {}}


# ---------------------------------------------------------------------------
# Source: runtime (run/*.pid)
# ---------------------------------------------------------------------------

def _load_runtime() -> dict:
    components = {}
    for name in ("supervisor", "app_runner", "tracker", "collectors"):
        pid_file = RUN_DIR / f"{name}.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                # Check if process is alive
                try:
                    os.kill(pid, 0)
                    alive = True
                except OSError:
                    alive = False
                age_min = _age_minutes(pid_file)
                components[name] = {"pid": pid, "alive": alive, "pid_age_min": age_min}
            except Exception:
                components[name] = {"pid": None, "alive": False}
    app_alive = components.get("app_runner", {}).get("alive", False)
    return {
        "status": "ok",
        "running": app_alive,
        "components": components,
    }


# ---------------------------------------------------------------------------
# Source: GinArea API (optional)
# ---------------------------------------------------------------------------

def _init_ginarea_client() -> tuple[Any, str | None]:
    """Create and login GinAreaClient from env vars.

    Returns (client, None) on success, (None, error_str) on failure.
    """
    try:
        from dotenv import load_dotenv  # load .env if present
        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass

    try:
        from ginarea_tracker.ginarea_client import GinAreaClient
    except ImportError as e:
        return None, f"import error: {e}"

    api_url = os.environ.get("GINAREA_API_URL", "")
    email = os.environ.get("GINAREA_EMAIL", "")
    password = os.environ.get("GINAREA_PASSWORD", "")
    totp = os.environ.get("GINAREA_TOTP_SECRET", "")

    if not all([api_url, email, password, totp]):
        missing = [k for k, v in [
            ("GINAREA_API_URL", api_url), ("GINAREA_EMAIL", email),
            ("GINAREA_PASSWORD", password), ("GINAREA_TOTP_SECRET", totp),
        ] if not v]
        return None, f"missing env: {missing}"

    try:
        client = GinAreaClient(api_url, email, password, totp)
        client.login()
        return client, None
    except Exception as e:
        return None, str(e)


def _load_ginarea_api(client: Any = None) -> dict:
    """Fetch bots list from GinArea API.

    Accepts pre-initialized client to avoid double login.
    If client is None, creates one from env vars.
    """
    if client is None:
        client, err = _init_ginarea_client()
        if client is None:
            return {"status": "unavailable", "reason": err, "bots": []}
    try:
        bots = client.get_bots()
        return {"status": "ok", "bots": bots, "fetched_at": _now_tz().isoformat()}
    except Exception as e:
        return {"status": "unavailable", "reason": str(e), "bots": []}


def _normalize_bot_config(raw: dict) -> dict:
    """Map raw /bots/{id}/params API response to normalized config schema.

    All fields written explicitly — null for missing/unknown, never omitted.
    Field mapping derived from GinArea API observed in ginarea_live/params.csv.
    """
    gap = raw.get("gap") or {}
    border = raw.get("border") or {}
    in_ = raw.get("in") or {}

    # Entry trigger extraction from nested in.start.cnds[0]
    entry_trigger_raw: str | None = None
    entry_trigger_value: float | None = None
    try:
        cnds = (in_.get("start") or {}).get("cnds") or []
        if cnds:
            first_cnd = cnds[0]
            items = first_cnd.get("items") or []
            params = first_cnd.get("params") or {}
            if items and params:
                op = items[0].get("op", ">")
                p = items[0].get("p")
                tf = params.get("tf", "1m")
                d = params.get("d", "?")
                entry_trigger_raw = f"PRICE%-{tf}-{d}-1 {op} {p}"
                entry_trigger_value = _safe_float(p)
    except (KeyError, IndexError, TypeError):
        pass

    return {
        "target_pct": _safe_float(gap.get("tog")),
        "instop_pct": _safe_float(gap.get("isg")),
        "min_stop_pct": _safe_float(gap.get("minS")),
        "max_stop_pct": _safe_float(gap.get("maxS")),
        "grid_step_pct": _safe_float(raw.get("gs")),
        "grid_step_ratio": _safe_float(raw.get("gsr")),
        "n_orders": _safe_float(raw.get("maxOp")),
        "order_size": None,           # not in /params endpoint
        "order_size_unit": None,      # not in /params endpoint
        "border_top": _safe_float(border.get("top")),
        "border_bottom": _safe_float(border.get("bottom")),
        "leverage": _safe_float(raw.get("leverage")),
        "dsblin": raw.get("dsblin"),
        "dsblin_outside_borders": raw.get("dsblinbap"),
        "entry_trigger_raw": entry_trigger_raw,
        "entry_trigger_value": entry_trigger_value,
        "percent_mode": raw.get("gsr") is not None,
    }


def _load_params_csv_cache() -> dict[str, dict]:
    """Read ginarea_live/params.csv → {bot_id: normalized_config}.

    Uses the raw_params_json column written by the tracker.
    Returns latest row per bot_id. Empty dict if file unavailable.
    """
    params_csv = ROOT / "ginarea_live" / "params.csv"
    if not params_csv.exists():
        return {}
    cache: dict[str, dict] = {}
    try:
        import csv as _csv
        with open(params_csv, encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                bid = row.get("bot_id", "")
                if not bid:
                    continue
                raw_json = row.get("raw_params_json", "")
                if not raw_json:
                    continue
                try:
                    raw = json.loads(raw_json)
                    cache[bid] = _normalize_bot_config(raw)
                    cache[bid]["_source"] = f"params_csv@{row.get('ts_utc', '')[:16]}"
                except (json.JSONDecodeError, Exception):
                    pass
    except Exception:
        pass
    return cache


def _enrich_bot_configs(
    bots: list[dict],
    client: Any,
    ts_str: str,
    anomalies: list[str],
) -> None:
    """Inject config into bots[*].config from GinArea API or params.csv fallback.

    Priority:
      1. Live API call via client (when credentials available)
      2. Fallback: ginarea_live/params.csv raw_params_json (always fresh from tracker)

    Uses 0.2s pause between API requests per TZ rate-limit spec.
    On both sources unavailable: config={}, config_source="unavailable".
    Status filter: all bots (numeric status codes 2/12, no "Working" string mapping).
    """
    csv_cache = _load_params_csv_cache()

    for i, bot in enumerate(bots):
        bot_id = bot.get("id", "")
        if not bot_id:
            continue

        config_set = False

        # Try API first
        if client is not None:
            try:
                raw = client.get_bot_params(bot_id)
                bot["config"] = _normalize_bot_config(raw)
                bot["config_source"] = f"api@{ts_str}"
                config_set = True
            except Exception as e:
                anomalies.append(
                    f"bot {bot_id} API config fetch failed ({type(e).__name__}), using csv fallback"
                )
            if i < len(bots) - 1:
                time.sleep(0.2)

        # Fallback: params.csv
        if not config_set:
            if bot_id in csv_cache:
                cfg = dict(csv_cache[bot_id])
                src_tag = cfg.pop("_source", f"params_csv@{ts_str}")
                bot["config"] = cfg
                bot["config_source"] = src_tag
            else:
                bot["config"] = {}
                bot["config_source"] = "unavailable"
                anomalies.append(f"bot {bot_id} config not available from API or params.csv")


# ---------------------------------------------------------------------------
# Build bots table from snapshots
# ---------------------------------------------------------------------------

def _build_bots_from_snapshots(snap_data: dict) -> tuple[list[dict], int]:
    """Returns (bots, garbage_row_count)."""
    rows = snap_data.get("rows", [])
    if not rows:
        return [], 0

    # Get latest snapshot per bot_id; filter garbage simultaneously
    latest: dict[str, dict] = {}
    garbage_count = 0
    for row in rows:
        bid = row.get("bot_id", "")
        bname = row.get("bot_name", "")
        if not _is_valid_bot_row(bid, bname):
            garbage_count += 1
            continue
        latest[bid] = row

    bots = []
    for bot_id, row in latest.items():
        pos = _safe_float(row.get("position"))
        liq = _safe_float(row.get("liquidation_price"))
        profit = _safe_float(row.get("current_profit"))
        avg_price = _safe_float(row.get("average_price"))
        volume = _safe_float(row.get("trade_volume"))
        status_code = row.get("status", "")

        pos_unit = _infer_position_unit(pos)
        # Convert USD contracts to BTC equivalent using avg_entry as proxy for mark
        if pos_unit == "USD" and pos is not None and avg_price and avg_price > 1000:
            pos_btc_eq = round(pos / avg_price, 6)
        else:
            pos_btc_eq = pos

        direction = "short" if (pos is not None and pos < 0) else (
            "long" if (pos is not None and pos > 0) else "flat"
        )
        bots.append({
            "name": row.get("bot_name", ""),
            "id": bot_id,
            "alias": row.get("alias", ""),
            "direction": direction,
            "pair": "BTCUSDT",
            "contract_type": "inverse" if pos_unit == "USD" else "linear",
            "config": {},
            "live": {
                "position": pos,
                "position_unit": pos_unit,
                "position_btc_equivalent": pos_btc_eq,
                "avg_entry": avg_price if avg_price and avg_price > 1000 else None,
                "mark": None,
                "liq_price": liq,
                "unrealized_usd": profit,
                "realized_usd": _safe_float(row.get("profit")),
                "volume_total": volume,
                "dwell_hours": None,
            },
            "status": status_code,
            "last_ts": row.get("ts_utc"),
        })
    return bots, garbage_count


# ---------------------------------------------------------------------------
# Build exposure aggregate
# ---------------------------------------------------------------------------

def _build_exposure(bots: list[dict]) -> dict:
    shorts_btc = 0.0
    longs_btc = 0.0
    nearest_short_liq: dict | None = None
    nearest_long_liq: dict | None = None
    mark_price: float | None = None

    for bot in bots:
        live = bot.get("live", {})
        pos_eq = live.get("position_btc_equivalent")
        liq = live.get("liq_price")

        if pos_eq is None:
            continue
        if pos_eq < 0:
            shorts_btc += pos_eq
            if liq and liq > 0:
                if nearest_short_liq is None or liq < nearest_short_liq["price"]:
                    nearest_short_liq = {"price": liq, "distance_pct": None}
        elif pos_eq > 0:
            longs_btc += pos_eq
            if liq and liq > 0:
                if nearest_long_liq is None or liq > nearest_long_liq["price"]:
                    nearest_long_liq = {"price": liq, "distance_pct": None}

    # Try to get mark price from snapshots (balance column can be a proxy)
    # We'll use avg_entry as fallback; mark must come from API in real use
    net_btc = shorts_btc + longs_btc
    net_notional = None  # requires mark price; fill if available

    return {
        "shorts_btc": round(shorts_btc, 4),
        "longs_btc": round(longs_btc, 4),
        "net_btc": round(net_btc, 4),
        "net_notional_usd": net_notional,
        "nearest_short_liq": nearest_short_liq,
        "nearest_long_liq": nearest_long_liq,
    }


# ---------------------------------------------------------------------------
# Build AGM 24h summary
# ---------------------------------------------------------------------------

def _build_agm_24h(bm_data: dict, bots: list[dict]) -> list[dict]:
    bm_bots = bm_data.get("bots", {})
    result = []

    # Map alias → bot_id from snapshot bots
    alias_to_id: dict[str, str] = {b.get("alias", ""): b["id"] for b in bots if b.get("id")}

    for key, state in bm_bots.items():
        last_action = state.get("last_action")
        updated_at = state.get("updated_at")
        bot_id = alias_to_id.get(key, key)
        result.append({
            "bot_key": key,
            "bot_id": bot_id,
            "phase": state.get("phase"),
            "last_action": last_action,
            "last_action_ts": updated_at,
            "tighten_count": 0,
            "release_count": 0,
        })
    return result


# ---------------------------------------------------------------------------
# Build DD recovery 24h (shorts only from snapshots)
# ---------------------------------------------------------------------------

def _build_dd_recovery(snap_data: dict, bots: list[dict]) -> list[dict]:
    rows = snap_data.get("rows", [])
    if not rows:
        return []

    # Group rows by bot_id, find min unrealized — skip garbage rows
    by_bot: dict[str, list[dict]] = {}
    for row in rows:
        bid = row.get("bot_id", "")
        bname = row.get("bot_name", "")
        if not _is_valid_bot_row(bid, bname):
            continue
        pos = _safe_float(row.get("position"))
        if bid and pos is not None and pos < 0:
            by_bot.setdefault(bid, []).append(row)

    result = []
    # Current live unrealized by bot_id
    current_unreal: dict[str, float] = {}
    for bot in bots:
        live = bot.get("live", {})
        val = live.get("unrealized_usd")
        if val is not None:
            current_unreal[bot["id"]] = val

    for bot_id, bot_rows in by_bot.items():
        profits = [(r.get("ts_utc", ""), _safe_float(r.get("current_profit"))) for r in bot_rows]
        profits = [(ts, p) for ts, p in profits if p is not None]
        if not profits:
            continue
        ts_min, p_min = min(profits, key=lambda x: x[1])
        current = current_unreal.get(bot_id)
        recovered = None
        if p_min is not None and p_min < 0 and current is not None:
            recovered = round((current - p_min) / abs(p_min) * 100, 1) if p_min != 0 else None

        result.append({
            "bot_id": bot_id,
            "unreal_min": round(p_min, 2) if p_min is not None else None,
            "ts_min": ts_min,
            "unreal_current": round(current, 2) if current is not None else None,
            "recovered_pct": recovered,
        })
    return result


# ---------------------------------------------------------------------------
# Build anomalies
# ---------------------------------------------------------------------------

def _build_anomalies(snap_data: dict, api_data: dict, bm_data: dict,
                     garbage_count: int = 0, valid_bot_count: int = 0) -> list[str]:
    anomalies: list[str] = []

    if snap_data.get("status") != "ok":
        anomalies.append(f"snapshots.csv unavailable: {snap_data.get('reason')}")

    age = snap_data.get("age_min")
    if age is not None and age > 60:
        anomalies.append(f"snapshots.csv is stale: last update {_fmt_age(age)} ago")

    if garbage_count > 0:
        anomalies.append(
            f"filtered {garbage_count} garbage rows from snapshots.csv "
            f"(bot_id non-numeric or name is float — possible column shift in tracker writer)"
        )

    if bm_data.get("status") != "ok":
        anomalies.append(f"bot_manager_state.json unavailable: {bm_data.get('reason')}")

    if api_data.get("status") == "ok":
        # Check if API bots appear in snapshots
        snap_ids = {r.get("bot_id") for r in snap_data.get("rows", [])}
        for bot in api_data.get("bots", []):
            bid = str(bot.get("id", ""))
            if bid and bid not in snap_ids:
                name = bot.get("name", bid)
                anomalies.append(f"Bot {name} ({bid}) in API but absent from snapshots")

    return anomalies


# ---------------------------------------------------------------------------
# Render markdown
# ---------------------------------------------------------------------------

def _render_markdown(ts_str: str, sources: dict, bots: list[dict],
                     exposure: dict, agm_24h: list[dict],
                     dd_recovery: list[dict], anomalies: list[str],
                     skills_applied: list[str],
                     data_health: str = "ok") -> str:
    lines: list[str] = [f"# CURRENT_STATE {ts_str}", ""]
    if data_health == "critical":
        lines += [f"**⚠ snapshots.csv likely corrupted, fewer than 5 valid bot rows recovered**", ""]

    # Section 0: Sources
    lines += ["## 0. Sources & freshness", ""]
    snap = sources.get("snapshots", {})
    bm = sources.get("bot_manager", {})
    rt = sources.get("runtime", {})
    api = sources.get("ginarea_api", {})

    snap_status = snap.get("status", "unavailable")
    snap_ts = snap.get("last_ts", "N/A")
    snap_age = _fmt_age(snap.get("age_min"))
    lines.append(f"- snapshots: {snap.get('path', 'N/A')} last_row_ts={snap_ts} age={snap_age} [{snap_status}]")

    bm_status = bm.get("status", "unavailable")
    bm_ts = bm.get("updated_at", "N/A")
    bm_age = _fmt_age(bm.get("age_min"))
    lines.append(f"- bot_manager_state: {bm.get('path', 'N/A')} updated={bm_ts} age={bm_age} [{bm_status}]")

    rt_status = "running" if rt.get("running") else "stopped"
    lines.append(f"- runtime: {rt_status} (app_runner={rt.get('components', {}).get('app_runner', {}).get('alive', False)})")

    api_status = api.get("status", "not_attempted")
    if api_status == "ok":
        lines.append(f"- ginarea_api: ok ({len(api.get('bots', []))} bots fetched at {api.get('fetched_at', 'N/A')})")
    else:
        lines.append(f"- ginarea_api: {api_status} ({api.get('reason', '')})")
    lines.append("")

    # Section 1: Bots
    lines += ["## 1. Bots — config + live", ""]
    if bots:
        lines.append("| alias | id | dir | position | unit | pos_btc_eq | avg_entry | liq_price | unreal_usd | last_ts |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for bot in bots:
            live = bot.get("live", {})
            alias = bot.get("alias") or bot.get("name", "")[:20]
            bid = bot.get("id", "")
            direction = bot.get("direction", "")
            pos = live.get("position")
            pos_unit = live.get("position_unit", "BTC")
            pos_eq = live.get("position_btc_equivalent")
            avg = live.get("avg_entry")
            liq = live.get("liq_price")
            unreal = live.get("unrealized_usd")
            last_ts = bot.get("last_ts", "")[:16] if bot.get("last_ts") else ""

            def _f(v: Any, fmt: str = ".4f") -> str:
                return format(v, fmt) if v is not None else "N/A"

            lines.append(f"| {alias} | {bid} | {direction} | {_f(pos)} | {pos_unit} | {_f(pos_eq)} | {_f(avg, '.0f')} | {_f(liq, '.0f')} | {_f(unreal, '.2f')} | {last_ts} |")
    else:
        lines.append("_(no bot data available)_")
    lines.append("")

    # Section 2: Manual positions
    lines += ["## 2. Manual positions", ""]
    lines.append("_not_tracked (positions_manual.json not present)_")
    lines.append("")

    # Section 3: Aggregate exposure
    lines += ["## 3. Aggregate exposure", ""]
    lines.append(f"- shorts_total_btc: {exposure.get('shorts_btc', 'N/A')}")
    lines.append(f"- longs_total_btc: {exposure.get('longs_btc', 'N/A')}")
    lines.append(f"- net_btc: {exposure.get('net_btc', 'N/A')}")
    nn = exposure.get("net_notional_usd")
    lines.append(f"- net_notional_usd: {nn if nn is not None else 'N/A (mark price not available from snapshots)'}")
    sl = exposure.get("nearest_short_liq")
    ll = exposure.get("nearest_long_liq")
    if sl:
        pct = f" ({sl['distance_pct']}%)" if sl.get("distance_pct") else ""
        lines.append(f"- nearest_short_liq: ${sl['price']:,.0f}{pct}")
    else:
        lines.append("- nearest_short_liq: N/A")
    if ll:
        pct = f" ({ll['distance_pct']}%)" if ll.get("distance_pct") else ""
        lines.append(f"- nearest_long_liq: ${ll['price']:,.0f}{pct}")
    else:
        lines.append("- nearest_long_liq: N/A")
    lines.append("")

    # Section 4: AGM activity 24h
    lines += ["## 4. AGM activity 24h", ""]
    if agm_24h:
        lines.append("| bot_key | phase | last_action | last_action_ts |")
        lines.append("|---|---|---|---|")
        for a in agm_24h:
            lines.append(f"| {a['bot_key']} | {a.get('phase','N/A')} | {a.get('last_action','N/A')} | {a.get('last_action_ts','N/A')} |")
    else:
        lines.append("_(no AGM data)_")
    lines.append("")

    # Section 5: DD recovery 24h
    lines += ["## 5. DD recovery cycle 24h (shorts only)", ""]
    if dd_recovery:
        lines.append("| bot_id | unreal_min_24h | ts_min | unreal_current | recovered_pct |")
        lines.append("|---|---|---|---|---|")
        for d in dd_recovery:
            lines.append(
                f"| {d['bot_id']} | {d.get('unreal_min','N/A')} | {d.get('ts_min','N/A')[:16] if d.get('ts_min') else 'N/A'} "
                f"| {d.get('unreal_current','N/A')} | {d.get('recovered_pct','N/A')} |"
            )
    else:
        lines.append("_(no DD data in window)_")
    lines.append("")

    # Section 6: Anomalies
    lines += ["## 6. Аномалии", ""]
    if anomalies:
        for a in anomalies:
            lines.append(f"- ⚠️ {a}")
    else:
        lines.append("_(none)_")
    lines.append("")

    # Section 7: Skills applied
    lines += ["## 7. Skills applied", ""]
    for s in skills_applied:
        lines.append(f"- {s}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ROADMAP parsing
# ---------------------------------------------------------------------------

ROADMAP_PATH = ROOT / "docs" / "STATE" / "ROADMAP.md"

_STATUS_MAP = {
    "in_progress": "in_progress",
    "in progress": "in_progress",
    "planned": "planned",
    "blocked": "blocked",
    "done": "done",
}


def _parse_roadmap() -> dict:
    """Parse ROADMAP.md into a structured dict for state_latest.json."""
    if not ROADMAP_PATH.exists():
        return {"status": "unavailable", "reason": "ROADMAP.md not found"}

    text = ROADMAP_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()

    phases: list[dict] = []
    current_phase: dict | None = None
    current_section = ""
    recently_completed: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Phase header: ### ФАЗА X — Name
        if stripped.startswith("### ФАЗА") or (stripped.startswith("### ФА") ):
            if current_phase:
                phases.append(current_phase)
            name = stripped.lstrip("#").strip()
            current_phase = {"name": name, "status": "unknown", "active_tasks": [], "exit_criteria": []}
            current_section = ""
            continue

        if current_phase is None:
            continue

        # Status line
        if stripped.lower().startswith("status:"):
            raw_status = stripped.split(":", 1)[1].strip().lower().replace(" ", "_")
            current_phase["status"] = _STATUS_MAP.get(raw_status, raw_status)
            continue

        # Section markers
        if "active tasks" in stripped.lower() or "active задачи" in stripped.lower():
            current_section = "active_tasks"
            continue
        if "exit criteria" in stripped.lower():
            current_section = "exit_criteria"
            continue
        if "pre-requisites" in stripped.lower():
            current_section = "prereqs"
            continue
        if stripped.startswith("Goal:") or stripped.startswith("Status:"):
            current_section = ""
            continue

        # List items
        if stripped.startswith("- ") and current_section in ("active_tasks", "exit_criteria"):
            item = stripped[2:].strip()
            if current_section == "active_tasks":
                current_phase["active_tasks"].append(item)
                if "[DONE" in item:
                    recently_completed.append(item)
            else:
                current_phase["exit_criteria"].append(item)

    if current_phase:
        phases.append(current_phase)

    # Find current phase (first in_progress)
    current = next((p for p in phases if p["status"] == "in_progress"), None)
    next_phase = None
    if current:
        idx = phases.index(current)
        if idx + 1 < len(phases):
            next_phase = phases[idx + 1]["name"]

    # Pending tasks (not DONE) from current phase
    pending_tasks: list[dict] = []
    if current:
        for task in current["active_tasks"]:
            status = "done" if "[DONE" in task else "pending"
            pending_tasks.append({"id": task.split("[")[0].strip(), "status": status})

    return {
        "current_phase": current["name"] if current else "unknown",
        "current_phase_status": current["status"] if current else "unknown",
        "active_tasks": pending_tasks,
        "next_phase": next_phase,
        "milestones_completed": recently_completed,
        "phases": [{"name": p["name"], "status": p["status"]} for p in phases],
    }


# ---------------------------------------------------------------------------
# PROJECT_MAP generation
# ---------------------------------------------------------------------------

_MAP_WALK_DIRS = ["src", "services", "scripts", "handlers", "telegram_ui", "collectors"]
_MAP_EXTRA_DIRS = ["_recovery", "_backup", "deprecated", "old"]
_MAP_SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", ".pytest_cache"}
_MAP_SKIP_FILE_PREFIXES = ("test_",)
_MAP_SKIP_SUFFIXES = ("_test.py",)


def _is_test_file(name: str) -> bool:
    return name.startswith(_MAP_SKIP_FILE_PREFIXES) or name.endswith(_MAP_SKIP_SUFFIXES)


def _extract_module_meta(path: Path, root: Path) -> dict:
    """Read first 80 lines of a .py file; extract docstring, imports, top-level symbols."""
    rel = str(path.relative_to(root)).replace("\\", "/")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"path": rel, "lines": 0, "description": "", "imports": [], "symbols": []}

    raw_lines = text.splitlines()
    lines_total = len(raw_lines)
    head = raw_lines[:80]

    # One-line description: first non-empty line of module docstring
    description = ""
    in_docstring = False
    for ln in head:
        stripped = ln.strip()
        if not description and stripped.startswith('"""'):
            content = stripped[3:].strip().rstrip('"""').strip()
            if content:
                description = content.split("\n")[0][:120]
                break
            in_docstring = True
        elif in_docstring:
            if stripped:
                description = stripped[:120]
            break

    # Imports: first 5 unique top-level module names
    imports: list[str] = []
    for ln in head:
        stripped = ln.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            parts = stripped.split()
            mod = parts[1] if len(parts) > 1 else ""
            mod_root = mod.split(".")[0]
            if mod_root and mod_root not in imports:
                imports.append(mod_root)
            if len(imports) >= 5:
                break

    # Top-level symbols: def/class at column 0
    symbols: list[str] = []
    for ln in head:
        if ln.startswith("def ") or ln.startswith("class ") or ln.startswith("async def "):
            parts = ln.split("(")[0].split()
            name = parts[-1] if parts else ""
            if name and name not in symbols:
                symbols.append(name)
            if len(symbols) >= 10:
                break

    return {
        "path": rel,
        "lines": lines_total,
        "description": description,
        "imports": imports,
        "symbols": symbols,
    }


def _walk_dir(base: Path, root: Path, skip_tests: bool = True) -> list[dict]:
    modules: list[dict] = []
    if not base.exists():
        return modules
    for path in sorted(base.rglob("*.py")):
        if any(part in _MAP_SKIP_DIRS for part in path.parts):
            continue
        if skip_tests and _is_test_file(path.name):
            continue
        if "tests" in path.parts and skip_tests:
            continue
        modules.append(_extract_module_meta(path, root))
    return modules


# Whitelist patterns from CONFLICTS_TRIAGE_2026-04-29T204605Z.
# Each entry: path_prefix_a, path_prefix_b, symbol_set (overlap must be subset to suppress).
# If BOTH paths match their respective prefix AND overlap is a subset of symbol_set → suppress.
_CONFLICT_WHITELIST: list[dict] = [
    {
        "prefix_a": "collectors/",
        "prefix_b": "collectors/",
        "symbols": {"_parse", "run", "_build_url", "_main"},
        "reason": "WebSocket collector interface — every collector has _parse/run. N×M cross-product is always false positive.",
    },
    {
        "prefix_a": "src/features/",
        "prefix_b": "src/features/",
        "symbols": {"compute"},
        "reason": "Standard feature module interface — every feature module exposes compute(df).",
    },
    {
        "prefix_a": "scripts/",
        "prefix_b": "scripts/",
        "symbols": {"_run", "_main"},
        "reason": "Generic script entrypoint names appear in all script utilities.",
    },
    # Also suppress when one side is in _recovery/ (non-restored) scripts vs active scripts
    {
        "prefix_a": "scripts/",
        "prefix_b": "_recovery/",
        "symbols": {"_run", "_main"},
        "reason": "Generic entrypoint names in _recovery/ dev scripts vs active scripts.",
    },
]


def _canonical_path(path: str) -> str:
    """Strip _recovery/*/  prefix so restored paths compare like active paths."""
    p = path.replace("\\", "/")
    # Strip leading _recovery/<anything>/ up to first known package root
    import re
    m = re.match(r"^_recovery/[^/]+/(.+)$", p)
    return m.group(1) if m else p


def _is_whitelisted(path_a: str, path_b: str, overlap: set[str]) -> str:
    """Return whitelist reason if pair should be suppressed, else empty string."""
    ca = _canonical_path(path_a)
    cb = _canonical_path(path_b)

    # Same canonical path = one is backup of the other (RESTORED_VS_ACTIVE)
    if ca == cb:
        return "RESTORED_VS_ACTIVE — same file in active and _recovery/; active is authoritative"

    for wl in _CONFLICT_WHITELIST:
        pa = wl["prefix_a"]
        pb = wl["prefix_b"]
        if (ca.startswith(pa) and cb.startswith(pb)) or \
           (ca.startswith(pb) and cb.startswith(pa)):
            if overlap and overlap.issubset(wl["symbols"]):
                return wl["reason"]
    return ""


def _detect_conflicts(active: list[dict], restored: list[dict]) -> tuple[list[dict], list[dict]]:
    """Find pairs where symbol overlap > 50%.

    Returns (real_conflicts, whitelisted_pairs).
    """
    conflicts: list[dict] = []
    whitelisted: list[dict] = []
    for rm in restored:
        rs = set(rm["symbols"])
        if not rs:
            continue
        for am in active:
            as_ = set(am["symbols"])
            if not as_:
                continue
            overlap = rs & as_
            ratio = len(overlap) / max(len(rs), len(as_))
            if ratio > 0.5:
                wl_reason = _is_whitelisted(am["path"], rm["path"], overlap)
                entry = {
                    "active": am["path"],
                    "restored": rm["path"],
                    "overlap_symbols": sorted(overlap)[:5],
                    "overlap_ratio": round(ratio, 2),
                }
                if wl_reason:
                    entry["whitelist_reason"] = wl_reason
                    whitelisted.append(entry)
                else:
                    conflicts.append(entry)
    return conflicts, whitelisted


def _detect_missing_deps(active: list[dict], restored: list[dict]) -> list[dict]:
    """Find imports in active modules that don't exist in active but do in restored."""
    active_paths = {m["path"] for m in active}
    restored_paths = {m["path"] for m in restored}
    active_modules = {
        m["path"].replace("/", ".").replace("\\", ".").removesuffix(".py")
        for m in active
    }
    restored_modules = {
        m["path"].replace("/", ".").replace("\\", ".").removesuffix(".py")
        for m in restored
    }

    missing: list[dict] = []
    for m in active:
        for imp in m["imports"]:
            # Only internal imports (src.*, services.*, collectors.*, etc.)
            if "." not in imp and not imp.startswith("src"):
                continue
            norm = imp.replace("/", ".").replace("\\", ".")
            in_active = any(am.startswith(norm) or norm in am for am in active_modules)
            in_restored = any(rm.startswith(norm) or norm in rm for rm in restored_modules)
            if not in_active and in_restored:
                missing.append({
                    "importer": m["path"],
                    "missing_import": imp,
                    "found_in_restored": True,
                })
    return missing


def _build_project_map(root: Path) -> tuple[dict, str]:
    """Walk codebase and build PROJECT_MAP dict + markdown string."""
    active_modules: list[dict] = []
    for d in _MAP_WALK_DIRS:
        active_modules.extend(_walk_dir(root / d, root, skip_tests=True))

    restored_modules: list[dict] = []
    for d in _MAP_EXTRA_DIRS:
        restored_modules.extend(_walk_dir(root / d, root, skip_tests=True))

    conflicts, whitelisted_conflicts = _detect_conflicts(active_modules, restored_modules)
    missing_deps = _detect_missing_deps(active_modules, restored_modules)

    # Pre-computed assets scan
    assets: list[dict] = []
    features_out = root / "_recovery" / "restored" / "features_out"
    if features_out.exists():
        parquets = list(features_out.rglob("*.parquet"))
        assets.append({
            "name": "features_out (restored)",
            "path": "_recovery/restored/features_out/",
            "count": len(parquets),
            "note": "Pre-computed 1m feature parquets. Ready to use.",
        })
    market_live = root / "market_live"
    if market_live.exists():
        parquets = list(market_live.rglob("*.parquet"))
        assets.append({
            "name": "market_live",
            "path": "market_live/",
            "count": len(parquets),
            "note": "Live collector output parquets.",
        })

    # Skills list
    skills_dir = root / ".claude" / "skills"
    skills = [p.stem for p in sorted(skills_dir.glob("*.md"))] if skills_dir.exists() else []

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    project_map = {
        "ts": ts,
        "active_modules": active_modules,
        "restored_modules": restored_modules,
        "conflicts": conflicts,
        "whitelisted_conflicts": whitelisted_conflicts,
        "missing_deps": missing_deps,
        "assets": assets,
        "skills": skills,
    }

    # Render markdown
    lines: list[str] = [
        "# PROJECT_MAP",
        f"_Generated: {ts}_",
        "",
        "## 1. Active modules",
        "",
        f"Walk: {', '.join(_MAP_WALK_DIRS)}",
        "",
        "| Path | Lines | Description |",
        "|------|-------|-------------|",
    ]
    for m in active_modules:
        desc = m["description"][:80].replace("|", "¦") if m["description"] else "—"
        lines.append(f"| {m['path']} | {m['lines']} | {desc} |")

    lines += [
        "",
        "## 2. Restored modules (_recovery/ + _backup/ + deprecated/)",
        "",
        "| Path | Lines | Recommendation |",
        "|------|-------|----------------|",
    ]
    for m in restored_modules:
        desc = m["description"][:80].replace("|", "¦") if m["description"] else "—"
        lines.append(f"| {m['path']} | {m['lines']} | {desc} |")

    lines += [
        "",
        f"## 3. Potential conflicts (symbol overlap > 50%) — {len(conflicts)} real, {len(whitelisted_conflicts)} whitelisted",
        "",
    ]
    if conflicts:
        lines += [
            "| Active | Restored | Overlap ratio | Shared symbols |",
            "|--------|----------|---------------|----------------|",
        ]
        for c in conflicts:
            shared = ", ".join(c["overlap_symbols"])
            lines.append(f"| {c['active']} | {c['restored']} | {c['overlap_ratio']} | {shared} |")
    else:
        lines.append("_(none detected)_")

    lines += ["", "## 3b. Whitelisted conflicts (suppressed — known false positives)", ""]
    if whitelisted_conflicts:
        lines += [
            "| Active | Restored | Shared symbols | Whitelist reason |",
            "|--------|----------|----------------|-----------------|",
        ]
        for c in whitelisted_conflicts:
            shared = ", ".join(c["overlap_symbols"])
            reason = c.get("whitelist_reason", "")[:60]
            lines.append(f"| {c['active']} | {c['restored']} | {shared} | {reason} |")
    else:
        lines.append("_(none)_")

    lines += ["", "## 4. Missing dependencies (active imports not in active, found in restored)", ""]
    if missing_deps:
        lines += ["| Importer | Missing import | In restored? |", "|----------|----------------|--------------|"]
        for d in missing_deps[:30]:
            lines.append(f"| {d['importer']} | {d['missing_import']} | {'yes' if d['found_in_restored'] else 'no'} |")
    else:
        lines.append("_(none detected)_")

    lines += ["", "## 5. Pre-computed assets", ""]
    if assets:
        for a in assets:
            lines.append(f"- **{a['name']}** (`{a['path']}`): {a['count']} files — {a['note']}")
    else:
        lines.append("_(none)_")

    lines += ["", "## 6. Skills available", ""]
    for s in skills:
        lines.append(f"- {s}")

    lines.append("")
    return project_map, "\n".join(lines)


# ---------------------------------------------------------------------------
# Generate state_inline.js for dashboard
# ---------------------------------------------------------------------------

def _write_inline_js(state_json: dict) -> None:
    js_path = ROOT / "docs" / "state_inline.js"
    # Embed QUEUE.md content for dashboard rendering
    queue_md = ""
    queue_path = ROOT / "docs" / "STATE" / "QUEUE.md"
    if queue_path.exists():
        queue_md = queue_path.read_text(encoding="utf-8")
    enriched = dict(state_json)
    enriched["_queue_md"] = queue_md
    content = "window.STATE = " + json.dumps(enriched, ensure_ascii=False, default=str) + ";\n"
    js_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import io as _io
    if hasattr(sys.stdout, "buffer") and sys.stdout.encoding and \
            sys.stdout.encoding.lower().replace("-", "") not in ("utf8", "utf8bom"):
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="State Snapshot")
    parser.add_argument("--no-api", action="store_true", help="Skip GinArea API calls")
    parser.add_argument("--lookback-hours", type=int, default=24)
    args = parser.parse_args()

    t0 = time.time()
    ts = _now_tz()
    ts_str = ts.strftime("%Y-%m-%dT%H:%M%z")
    ts_file = ts.strftime("%Y-%m-%d_%H%M")

    skills_applied = [
        "state_first_protocol", "encoding_safety",
        "regression_baseline_keeper", "operator_role_boundary",
    ]

    print(f"[state_snapshot] {ts_str} — collecting state...")

    snap_data = _load_snapshots(args.lookback_hours)
    print(f"  snapshots: {snap_data['status']} ({snap_data.get('rows_in_window', 0)} rows in {args.lookback_hours}h window)")

    bm_data = _load_bot_manager()
    print(f"  bot_manager_state: {bm_data['status']}")

    gp_data = _load_grid_portfolio()
    print(f"  grid_portfolio: {gp_data['status']}")

    rt_data = _load_runtime()
    print(f"  runtime: {'running' if rt_data['running'] else 'stopped'}")

    ginarea_client_obj: Any = None
    api_data: dict = {"status": "skipped", "reason": "--no-api", "bots": []}
    if not args.no_api:
        print("  ginarea_api: logging in...")
        ginarea_client_obj, _cli_err = _init_ginarea_client()
        if ginarea_client_obj is not None:
            api_data = _load_ginarea_api(ginarea_client_obj)
        else:
            api_data = {"status": "unavailable", "reason": _cli_err or "login failed", "bots": []}
        print(f"  ginarea_api: {api_data['status']}")
    else:
        print("  ginarea_api: skipped (--no-api)")

    bots, garbage_count = _build_bots_from_snapshots(snap_data)

    config_errors: list[str] = []
    print(f"  enriching bot configs ({len(bots)} bots)...")
    _enrich_bot_configs(bots, ginarea_client_obj, ts_str, config_errors)
    ok_count = sum(1 for b in bots if b.get("config"))
    err_count = sum(1 for b in bots if not b.get("config"))
    print(f"  configs: {ok_count} ok, {err_count} empty, {len(config_errors)} errors")

    exposure = _build_exposure(bots)
    agm_24h = _build_agm_24h(bm_data, bots)
    dd_recovery = _build_dd_recovery(snap_data, bots)
    anomalies = _build_anomalies(snap_data, api_data, bm_data,
                                 garbage_count=garbage_count,
                                 valid_bot_count=len(bots))
    anomalies.extend(config_errors)

    sources = {
        "snapshots": snap_data,
        "bot_manager": bm_data,
        "grid_portfolio": gp_data,
        "runtime": rt_data,
        "ginarea_api": api_data,
    }

    data_health = "critical" if len(bots) < 5 else "ok"

    roadmap_data = _parse_roadmap()

    # Margin block — surfaced from services.margin (TZ-MARGIN-COEFFICIENT-INPUT-WIRE).
    # Source resolution: newer of state/manual_overrides/margin_overrides.jsonl
    # (operator /margin command) and state/margin_automated.jsonl (reserved for
    # future TZ-EXCHANGE-WALLET-FEED). When neither has data, margin = None and
    # Decision Layer M-* rules stay dormant.
    try:
        from services.margin import read_latest_margin

        _margin = read_latest_margin()
    except Exception as _margin_err:  # never let margin reader crash the snapshot
        print(f"  margin: reader error — {_margin_err}")
        _margin = None
    if _margin is not None:
        try:
            _margin_dt = datetime.fromisoformat(_margin.ts.replace("Z", "+00:00"))
            _age_min = (datetime.now(timezone.utc) - _margin_dt).total_seconds() / 60.0
        except (ValueError, AttributeError):
            _age_min = None
        margin_block = {
            "coefficient": _margin.coefficient,
            "available_margin_usd": _margin.available_margin_usd,
            "distance_to_liquidation_pct": _margin.distance_to_liquidation_pct,
            "source": _margin.source,
            "updated_at": _margin.ts,
            "data_age_minutes": round(_age_min, 1) if _age_min is not None else None,
        }
    else:
        margin_block = None

    state_json = {
        "ts": ts.isoformat(),
        "data_health": data_health,
        "sources": {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in sources.items()},
        "bots": bots,
        "manual_positions": [],
        "exposure": exposure,
        "margin": margin_block,
        "agm_24h": agm_24h,
        "dd_recovery_24h": dd_recovery,
        "anomalies": anomalies,
        "roadmap": roadmap_data,
        "skills_applied": skills_applied,
    }

    print("  project_map: building...")
    try:
        project_map_data, project_map_md = _build_project_map(ROOT)
        pm_md_path = STATE_DIR / "PROJECT_MAP.md"
        pm_json_path = STATE_DIR / "project_map.json"
        pm_md_path.write_text(project_map_md, encoding="utf-8")
        pm_json_path.write_text(
            json.dumps(project_map_data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        n_active = len(project_map_data["active_modules"])
        n_conflicts = len(project_map_data["conflicts"])
        n_whitelisted = len(project_map_data["whitelisted_conflicts"])
        n_missing = len(project_map_data["missing_deps"])
        print(f"  project_map: {n_active} active modules, {n_conflicts} real conflicts (+{n_whitelisted} whitelisted), {n_missing} missing deps")
        print(f"  PROJECT_MAP: {pm_md_path}")
    except Exception as _pm_err:
        print(f"  project_map: ERROR — {_pm_err}")

    md_path = STATE_DIR / f"CURRENT_STATE_{ts_file}.md"
    latest_json_path = STATE_DIR / "state_latest.json"
    latest_md_path = STATE_DIR / "CURRENT_STATE_latest.md"

    md_content = _render_markdown(
        ts_str, sources, bots, exposure, agm_24h, dd_recovery, anomalies, skills_applied,
        data_health=data_health,
    )

    md_path.write_text(md_content, encoding="utf-8")
    latest_json_path.write_text(
        json.dumps(state_json, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    latest_md_path.write_text(md_content, encoding="utf-8")
    _write_inline_js(state_json)

    elapsed = time.time() - t0
    print(f"\n[state_snapshot] Done in {elapsed:.1f}s")
    print(f"  MD:   {md_path}")
    print(f"  JSON: {latest_json_path}")
    print(f"  JS:   {ROOT / 'docs' / 'state_inline.js'}")
    if anomalies:
        print(f"\n  ⚠️  {len(anomalies)} anomalies:")
        for a in anomalies:
            print(f"    - {a}")


if __name__ == "__main__":
    main()
