"""Advisor v0.1 — single-text synthesis of live state + reconciled foundation.

Read-only. Reads:
  - state/regime_state.json (live Classifier A via regime_adapter)
  - docs/STATE/state_latest.json (exposure, bots, margin block)
  - hard-coded reconciled foundation numbers from
    docs/ANALYSIS/SHORT_FINAL_RECONCILED_2026-05-06.md (v4)

Outputs: one Telegram-ready text message. No trading advice. No predictions.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REGIME_STATE_PATH = Path("state/regime_state.json")
STATE_LATEST_PATH = Path("docs/STATE/state_latest.json")

# Reconciled v3 / v4 foundation — pinned numbers
RECONCILED_GROUP = {
    "name": "vola_compressing + fund_neg",
    "n": 52,
    "down_to_anchor_pct": 0.0,
    "up_extension_pct": 46.2,
    "pullback_continuation_pct": 53.8,
    "sideways_pct": 0.0,
    "source": "SHORT_FINAL_RECONCILED v4 / SHORT_EXIT_OPTIONS_2026-05-06.md",
}

CRITICAL_LEVELS = [78739, 80000, 82400, 96497]
P2_PROXIMITY_USD = 300

# Position reference (operator-provided)
SHORT_ENTRY = 79036.0
SHORT_REFERENCE_SIZE_BTC = 1.434  # snapshot from state_latest at last read
ANCHOR = 75200.0


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _read_regime() -> dict:
    raw = _load_json(REGIME_STATE_PATH)
    btc = (raw.get("symbols") or {}).get("BTCUSDT") or {}
    return btc


def _project_3state(primary: str | None) -> str:
    if not primary:
        return "?"
    mapping = {
        "TREND_UP": "MARKUP", "CASCADE_UP": "MARKUP",
        "TREND_DOWN": "MARKDOWN", "CASCADE_DOWN": "MARKDOWN",
        "RANGE": "RANGE", "COMPRESSION": "RANGE",
    }
    return mapping.get(primary, primary)


def _funding_percentile_label(funding_8h: float | None) -> str:
    """Classify funding by 1y distribution (computed earlier, hard-coded thresholds)."""
    if funding_8h is None:
        return "n/a"
    # 1y BTCUSDT funding distribution (from v3 sanity check):
    #  min -1.5e-4, p10 -3.1e-5, p25 +4.7e-6, median +3.7e-5, p75 +7.2e-5
    # Operator -8.2e-5 is below p10 -> percentile ~1.6%
    if funding_8h < -8e-5:
        return "deeply negative (~p1.6, lower 2%)"
    if funding_8h < -3e-5:
        return "moderately negative (~p10)"
    if funding_8h < 0:
        return "slightly negative"
    if funding_8h < 5e-5:
        return "near zero"
    return "positive"


def _format_distance(target: float, current: float) -> str:
    if current is None or target is None or current == 0:
        return "n/a"
    pct = (target - current) / current * 100
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f}%"


def _build_position_block(state: dict, mark: float | None) -> list[str]:
    expo = state.get("exposure") or {}
    net_btc = expo.get("net_btc")
    shorts_btc = expo.get("shorts_btc")
    longs_btc = expo.get("longs_btc")
    margin = state.get("margin") or {}
    avail = margin.get("available_margin_usd")
    dist_liq = margin.get("distance_to_liquidation_pct")
    margin_age_min = margin.get("data_age_minutes")
    margin_source = margin.get("source")

    lines = ["", "ПОЗИЦИЯ"]
    if shorts_btc is not None:
        lines.append(f"  SHORT: {shorts_btc:+.3f} BTC")
    if longs_btc is not None and longs_btc != 0:
        lines.append(f"  LONG (бот-агрегат): {longs_btc:+.3f} BTC")
    if net_btc is not None:
        lines.append(f"  Net BTC: {net_btc:+.3f}")

    # Unrealized for SHORT side at reference entry
    if shorts_btc is not None and mark is not None:
        unreal = abs(shorts_btc) * (SHORT_ENTRY - mark)
        sign = "+" if unreal > 0 else ""
        lines.append(f"  SHORT unrealized @ {mark:.0f}: {sign}{unreal:.0f} USD (entry {SHORT_ENTRY:.0f})")

    if avail is not None:
        lines.append(f"  Available margin: {avail:,.0f} USD")
    if dist_liq is not None:
        lines.append(f"  Distance to liq: {dist_liq}%")
    if margin_age_min is not None:
        if margin_age_min > 720:
            lines.append(f"  ⚠️ /margin update {margin_age_min:.0f}min stale (>12h, D-4 PRIMARY)")
        elif margin_age_min > 360:
            lines.append(f"  ⚠️ /margin update {margin_age_min:.0f}min stale (>6h, D-4 INFO)")
        else:
            lines.append(f"  /margin updated {margin_age_min:.0f}min ago ({margin_source})")
    return lines


def _build_regime_block(regime: dict) -> list[str]:
    primary = regime.get("current_primary")
    proj_3state = _project_3state(primary)
    age_bars = regime.get("regime_age_bars", 0)
    pending = regime.get("pending_primary")
    counter = regime.get("hysteresis_counter", 0)
    modifiers = list((regime.get("active_modifiers") or {}).keys())

    # Computed confidence/stability per regime_adapter logic
    if pending is None:
        confidence = 1.0
    else:
        confidence = min(1.0, counter / 2)
    stability = min(1.0, age_bars / 12) if age_bars > 0 else 0.0

    lines = ["РЫНОК"]
    if primary:
        lines.append(f"  Regime: {primary} → {proj_3state} | age {age_bars}h | conf {confidence:.1f} | stab {stability:.2f}")
    else:
        lines.append("  Regime: нет данных")
    if pending:
        lines.append(f"  ⚠️ Pending: {pending} (counter {counter}/2)")
    if modifiers:
        lines.append(f"  Modifiers: {', '.join(modifiers)}")
    return lines


def _build_funding_block(state: dict) -> list[str]:
    margin = state.get("margin") or {}
    # We don't have live funding stream; use last operator-supplied value if any.
    # For now reference the known position funding (-0.0082%/8h, source v4 doc).
    lines = []
    funding_8h = -8.2e-5  # operator-supplied snapshot; future: read from live source
    pct = funding_8h * 100
    label = _funding_percentile_label(funding_8h)
    lines.append(f"  Funding: {pct:.4f}%/8h ({label})")
    return lines


def _build_levels_block(mark: float | None) -> list[str]:
    if mark is None:
        return []
    lines = ["", "КЛЮЧЕВЫЕ УРОВНИ"]
    levels = [(SHORT_ENTRY, "entry/BE"), (ANCHOR, "anchor роста")]
    levels += [(lvl, f"P-2 critical") for lvl in CRITICAL_LEVELS]
    # Sort by distance from mark, mark targets above first
    above = sorted([l for l in levels if l[0] > mark], key=lambda x: x[0])
    below = sorted([l for l in levels if l[0] <= mark], key=lambda x: -x[0])
    for lvl, lbl in above:
        d = _format_distance(lvl, mark)
        proximity_flag = " ⚡ near" if abs(lvl - mark) <= P2_PROXIMITY_USD else ""
        lines.append(f"  ↑ {lvl:>6,.0f} ({lbl}) | {d}{proximity_flag}")
    for lvl, lbl in below:
        d = _format_distance(lvl, mark)
        proximity_flag = " ⚡ near" if abs(lvl - mark) <= P2_PROXIMITY_USD else ""
        lines.append(f"  ↓ {lvl:>6,.0f} ({lbl}) | {d}{proximity_flag}")
    return lines


def _build_foundation_block() -> list[str]:
    lines = ["", "ИСТОРИЧЕСКИЙ КОНТЕКСТ"]
    lines.append(f"  Setup match: {RECONCILED_GROUP['name']} (n={RECONCILED_GROUP['n']})")
    lines.append(f"  Distribution исходов:")
    lines.append(f"    down_to_anchor:        {RECONCILED_GROUP['down_to_anchor_pct']:.1f}%")
    lines.append(f"    up_extension (+5%):    {RECONCILED_GROUP['up_extension_pct']:.1f}%")
    lines.append(f"    pullback_continuation: {RECONCILED_GROUP['pullback_continuation_pct']:.1f}%")
    lines.append(f"    sideways:              {RECONCILED_GROUP['sideways_pct']:.1f}%")
    return lines


def _build_bots_block(state: dict) -> list[str]:
    bots = state.get("bots") or []
    lines = ["", "БОТЫ"]
    active = [b for b in bots if (b.get("live") or {}).get("position", 0) != 0]
    if not active:
        lines.append("  Активных позиций нет в state_latest")
        return lines
    for b in active[:5]:
        live = b.get("live") or {}
        name = b.get("name", "?")[:30]
        pos = live.get("position", 0)
        pos_unit = live.get("position_unit", "")
        unreal = live.get("unrealized_usd", 0)
        sign = "+" if unreal > 0 else ""
        lines.append(f"  {name}: {pos} {pos_unit} | {sign}{unreal:.0f} USD")
    if len(active) > 5:
        lines.append(f"  ... +{len(active)-5} more")
    return lines


def _build_watch_block() -> list[str]:
    return [
        "",
        "WATCH-LIST",
        "  • Funding flip к ≥0 — historical 100% случаев в neg-funding setups (median 65h)",
        "  • OI падает >5% → 100% pullback signal (n=42)",
        "  • OI divergence (price↑ + OI↓) → 84.4% pullback (n=96)",
        "  • Цена 82,400 → P-2 fire (94.6% historical reach, 99.2% false breakout)",
    ]


def _build_gaps_block() -> list[str]:
    return [
        "",
        "⚠️ Foundation gaps",
        "  • Bear-window не покрыт (1y data bull-skewed)",
        "  • Live OI отсутствует (last update 2026-04-30)",
        "  • Reconciled v3 build от 2026-05-06; live numbers могут drift'нуть",
    ]


def build_advisor_text(
    *,
    state_latest_path: Path = STATE_LATEST_PATH,
    regime_path: Path = REGIME_STATE_PATH,
    now: datetime | None = None,
) -> str:
    """Build advisor text. Pure function — no side effects, all paths injectable."""
    now = now or datetime.now(timezone.utc)
    state_latest = _load_json(state_latest_path)
    regime = _load_json(regime_path).get("symbols", {}).get("BTCUSDT", {}) if regime_path.exists() else {}

    # Mark price: prefer signals.csv path... but use bots[].live.mark or state currently-shown
    bots = state_latest.get("bots") or []
    marks = [b.get("live", {}).get("mark") for b in bots if b.get("live", {}).get("mark")]
    mark = float(max(marks)) if marks else None
    if mark is None:
        mark = state_latest.get("current_price_btc")
    if mark is None:
        # Last-resort fallback: read from market_live/market_1m.csv
        live_csv = Path("market_live/market_1m.csv")
        if live_csv.exists():
            try:
                with live_csv.open("r", encoding="utf-8") as fh:
                    last_line = None
                    for line in fh:
                        if line.strip():
                            last_line = line
                if last_line:
                    parts = last_line.strip().split(",")
                    # Format: ts_utc,open,high,low,close,volume
                    if len(parts) >= 5:
                        mark = float(parts[4])
            except (OSError, ValueError):
                pass
    if mark is None:
        # Try dashboard_state
        ds = _load_json(Path("docs/STATE/dashboard_state.json"))
        mark = ds.get("current_price_btc")

    lines: list[str] = []
    lines.append(f"🎯 ADVISOR v0.1 — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    if mark is None:
        lines.append("⚠️ Mark price недоступен; некоторые расчёты могут быть n/a")
    else:
        lines.append(f"BTC mark: {mark:,.0f}")
    lines.append("")
    lines.extend(_build_regime_block(regime))
    lines.extend(_build_funding_block(state_latest))
    lines.extend(_build_position_block(state_latest, mark))
    lines.extend(_build_foundation_block())
    lines.extend(_build_levels_block(mark))
    lines.extend(_build_bots_block(state_latest))
    lines.extend(_build_watch_block())
    lines.extend(_build_gaps_block())

    return "\n".join(lines)
