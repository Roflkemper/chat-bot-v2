"""Auto-tune helper для liq-cluster threshold.

Раз в неделю:
1. Читает journal `state/liq_pre_cascade_fires.jsonl` — все сработавшие alert.
2. Читает `market_live/liquidations.csv` — реальные каскады за тот же период.
3. Для каждого fire проверяет случился ли каскад same-side в +0..30 мин.
4. Считает hit-rate, recall, FP rate.
5. Возвращает рекомендацию по threshold (без авто-применения — только в TG-отчёт).

Применение: в weekly_self_report добавить секцию "🎯 LIQ-CLUSTER AUTO-TUNE"
с рекомендациями.
"""
from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

JOURNAL_PATH = Path("state/liq_pre_cascade_fires.jsonl")
LIQ_CSV_PATH = Path("market_live/liquidations.csv")

PREDICTION_WINDOW_MIN = 30
CASCADE_THRESHOLD = 5.0
CASCADE_WINDOW_MIN = 5


def _read_fires(journal: Path, *, since: datetime) -> list[dict]:
    if not journal.exists():
        return []
    out = []
    try:
        for line in journal.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                ts = datetime.fromisoformat(e.get("ts", ""))
            except ValueError:
                continue
            if ts >= since:
                e["_ts"] = ts
                out.append(e)
    except OSError:
        return out
    return out


def _find_cascades_since(liq_csv: Path, *, since: datetime) -> list[tuple[datetime, str, float]]:
    """Cascade detection same as production (sliding 5min, dedup 30min per side)."""
    if not liq_csv.exists():
        return []
    rows = []
    try:
        with liq_csv.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    ts = datetime.fromisoformat(r["ts_utc"])
                    side = (r.get("side") or "").lower()
                    qty = float(r["qty"]) if r["qty"] else 0.0
                except (ValueError, KeyError):
                    continue
                if qty <= 0 or side not in ("long", "short") or ts < since:
                    continue
                rows.append((ts, side, qty))
    except OSError:
        return []
    rows.sort(key=lambda x: x[0])

    cascades = []
    last_per_side: dict[str, datetime] = {}
    for i, (ts, _s, _q) in enumerate(rows):
        window_start = ts - timedelta(minutes=CASCADE_WINDOW_MIN)
        long_t = short_t = 0.0
        j = i
        while j >= 0 and rows[j][0] >= window_start:
            if rows[j][1] == "long":
                long_t += rows[j][2]
            elif rows[j][1] == "short":
                short_t += rows[j][2]
            j -= 1
        for s, total in (("long", long_t), ("short", short_t)):
            if total >= CASCADE_THRESHOLD:
                prev = last_per_side.get(s)
                if prev is None or (ts - prev).total_seconds() >= 1800:
                    cascades.append((ts, s, total))
                    last_per_side[s] = ts
    return cascades


def analyze(
    *,
    now: Optional[datetime] = None,
    window_days: int = 7,
    journal: Path = JOURNAL_PATH,
    liq_csv: Path = LIQ_CSV_PATH,
) -> dict:
    """Return weekly hit-rate stats + recommendation."""
    if now is None:
        now = datetime.now(timezone.utc)
    since = now - timedelta(days=window_days)

    fires = _read_fires(journal, since=since)
    cascades = _find_cascades_since(liq_csv, since=since)

    result = {
        "window_days": window_days,
        "since": since.isoformat(timespec="seconds"),
        "fires_total": len(fires),
        "cascades_total": len(cascades),
        "hits": 0,
        "false_positives": 0,
        "missed_cascades": 0,
        "hit_rate": 0.0,
        "recall": 0.0,
        "by_side": {},
        "recommendation": "insufficient_data",
    }

    if not fires and not cascades:
        return result

    cascades_by_side = defaultdict(list)
    for ts, s, _ in cascades:
        cascades_by_side[s].append(ts)
    fires_by_side = defaultdict(list)
    for f in fires:
        fires_by_side[f["side"]].append(f["_ts"])

    # Hit rate
    hits = 0
    for f in fires:
        end_w = f["_ts"] + timedelta(minutes=PREDICTION_WINDOW_MIN)
        same_side = cascades_by_side.get(f["side"], [])
        if any(f["_ts"] <= c <= end_w for c in same_side):
            hits += 1

    # Recall
    caught = 0
    for ts, side, _ in cascades:
        start_w = ts - timedelta(minutes=PREDICTION_WINDOW_MIN)
        same_side = fires_by_side.get(side, [])
        if any(start_w <= f <= ts for f in same_side):
            caught += 1

    result["hits"] = hits
    result["false_positives"] = len(fires) - hits
    result["missed_cascades"] = len(cascades) - caught
    result["hit_rate"] = round(hits / len(fires), 3) if fires else 0.0
    result["recall"] = round(caught / len(cascades), 3) if cascades else 0.0

    # Per-side
    for side in ("long", "short"):
        side_fires = [f for f in fires if f["side"] == side]
        side_cascades = cascades_by_side.get(side, [])
        side_hits = 0
        for f in side_fires:
            end_w = f["_ts"] + timedelta(minutes=PREDICTION_WINDOW_MIN)
            if any(f["_ts"] <= c <= end_w for c in side_cascades):
                side_hits += 1
        result["by_side"][side] = {
            "fires": len(side_fires),
            "hits": side_hits,
            "hit_rate": round(side_hits / len(side_fires), 3) if side_fires else 0.0,
            "cascades": len(side_cascades),
        }

    # Recommendation
    if len(fires) < 5:
        result["recommendation"] = "insufficient_data"
        result["recommendation_text"] = f"<5 fires за {window_days} дней — нужно больше данных"
    elif result["hit_rate"] < 0.15:
        result["recommendation"] = "raise_threshold"
        result["recommendation_text"] = (
            f"Hit-rate {result['hit_rate']*100:.0f}% низкий. "
            f"Рекомендую threshold ↑ (0.5→0.7 BTC)."
        )
    elif result["hit_rate"] > 0.50 and result["recall"] > 0.80:
        result["recommendation"] = "lower_threshold"
        result["recommendation_text"] = (
            f"Hit-rate {result['hit_rate']*100:.0f}% высокий и recall {result['recall']*100:.0f}%. "
            f"Можно опустить threshold (0.5→0.3 BTC) для большего охвата."
        )
    elif result["recall"] < 0.50:
        result["recommendation"] = "lower_threshold_for_recall"
        result["recommendation_text"] = (
            f"Recall {result['recall']*100:.0f}% низкий — много блицев пропускается. "
            f"Можно опустить threshold (0.5→0.3 BTC)."
        )
    else:
        result["recommendation"] = "keep_current"
        result["recommendation_text"] = (
            f"Hit-rate {result['hit_rate']*100:.0f}%, recall {result['recall']*100:.0f}% — норма, threshold не трогать."
        )

    return result


def format_report_section(report: dict) -> str:
    """Render analyze() result for weekly TG report."""
    lines = ["🎯 LIQ-CLUSTER AUTO-TUNE"]
    if report["fires_total"] == 0 and report["cascades_total"] == 0:
        lines.append("  (нет данных за окно)")
        return "\n".join(lines)
    lines.append(f"  Окно: {report['window_days']}d, fires: {report['fires_total']}, "
                 f"каскадов: {report['cascades_total']}")
    lines.append(f"  Hit rate: {report['hit_rate']*100:.0f}% "
                 f"({report['hits']}/{report['fires_total']})")
    lines.append(f"  Recall: {report['recall']*100:.0f}% "
                 f"({report['cascades_total']-report['missed_cascades']}/{report['cascades_total']})")
    bs = report.get("by_side", {})
    long_s = bs.get("long", {})
    short_s = bs.get("short", {})
    if long_s:
        lines.append(f"    LONG: hit {long_s['hit_rate']*100:.0f}% ({long_s['hits']}/{long_s['fires']})")
    if short_s:
        lines.append(f"    SHORT: hit {short_s['hit_rate']*100:.0f}% ({short_s['hits']}/{short_s['fires']})")
    lines.append(f"  → {report.get('recommendation_text', report['recommendation'])}")
    return "\n".join(lines)
