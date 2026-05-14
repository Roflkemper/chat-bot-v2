"""Ежедневная сводка bot7 — что произошло за последние 24 часа.

Рендерит markdown-отчёт в docs/CHANGELOG_DAILY.md, объединяя:
  - git-коммиты за 24ч (одной строкой темы)
  - воронку pipeline (с расшифровкой почему режется)
  - перезапуски app_runner
  - P-15 lifecycle с PnL/WR/avg win-loss/MaxDD
  - решения GC (boost/penalty/pass-through)
  - сравнение с baseline (вчерашний день из архива)

Output: docs/CHANGELOG_DAILY.md (перезаписывается каждый запуск; полная
история в git log + docs/changelog_archive/).

Cron: bot7-daily-change-log-09am (после daily KPI).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "CHANGELOG_DAILY.md"
ARCHIVE_DIR = ROOT / "docs" / "changelog_archive"
WINDOW_H = 24

STAGE_RU = {
    "env_disabled": "выключен в env",
    "combo_blocked": "режим/комбо блокирует",
    "type_pair_dedup_skip": "дедуп по типу+паре",
    "semantic_dedup_skip": "семантический дедуп",
    "emitted": "отправлен в TG",
    "gc_shadow": "GC shadow-mode",
    "mtf_conflict": "конфликт таймфреймов",
    "mtf_neutral": "MTF neutral (нет согласия)",
    "low_confidence": "низкий confidence",
    "killed_by_filter": "убит фильтром",
}


def _git_commits_last_24h() -> list[tuple[str, str]]:
    """Возвращает (hash, subject) коммитов за WINDOW_H часов.

    Forces UTF-8 decoding via env. На Windows git log по умолчанию отдаёт
    байты в cp1251 — без явного encoding получалось mojibake типа
    'СЃРёРјРјРµС‚СЂРёС‡РЅС‹Р№' вместо 'симметричный'.
    """
    env = {**os.environ, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        result = subprocess.run(
            ["git", "log", f"--since={WINDOW_H} hours ago",
             "--pretty=format:%h|%s"],
            cwd=str(ROOT), capture_output=True, timeout=10, env=env,
        )
        if result.returncode != 0:
            return []
        text = result.stdout.decode("utf-8", errors="replace")
        out = []
        for line in text.splitlines():
            if "|" not in line:
                continue
            h, subject = line.split("|", 1)
            out.append((h.strip(), subject.strip()))
        return out
    except Exception:
        return []


def _read_jsonl_window(path: Path, hours: int, offset_h: int = 0) -> list[dict]:
    """Читает jsonl в окне [now-offset_h-hours, now-offset_h]."""
    if not path.exists():
        return []
    now_ts = datetime.now(timezone.utc).timestamp()
    start_ts = now_ts - (offset_h + hours) * 3600
    end_ts = now_ts - offset_h * 3600
    out = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = rec.get("ts")
                if not ts:
                    continue
                try:
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    t = dt.timestamp()
                    if start_ts <= t < end_ts:
                        out.append(rec)
                except ValueError:
                    continue
        return out
    except OSError:
        return []


def _disabled_detectors_human() -> list[str]:
    """Возвращает русские названия отключенных детекторов из DISABLED_DETECTORS."""
    raw = os.environ.get("DISABLED_DETECTORS", "")
    if not raw:
        env_local = ROOT / ".env.local"
        if env_local.exists():
            for line in env_local.read_text(encoding="utf-8").splitlines():
                if line.startswith("DISABLED_DETECTORS="):
                    raw = line.split("=", 1)[1].strip()
                    break
    if not raw:
        return []
    try:
        from services.common.humanize import humanize_setup_type
    except Exception:
        humanize_setup_type = lambda s: s  # noqa: E731
    return [humanize_setup_type(s.strip()) for s in raw.split(",") if s.strip()]


def _trend_arrow(today: float, yesterday: float | None, lower_is_better: bool = False) -> str:
    """▲/▼/= с учётом направления интереса."""
    if yesterday is None or yesterday == 0:
        return ""
    delta = today - yesterday
    if abs(delta) / max(abs(yesterday), 1e-9) < 0.05:
        return " (≈ вчера)"
    arrow = "▲" if delta > 0 else "▼"
    pct = abs(delta) / max(abs(yesterday), 1e-9) * 100
    return f" ({arrow} {pct:.0f}% vs вчера)"


def _p15_stats(events: list[dict]) -> dict:
    """Считает PnL/WR/avg win-loss/MaxDD/biggest по equity-событиям."""
    pnls = [float(e.get("realized_pnl_usd") or 0) for e in events if e.get("realized_pnl_usd") is not None]
    closed = [p for p in pnls if p != 0]
    wins = [p for p in closed if p > 0]
    losses = [p for p in closed if p < 0]

    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        running += p
        peak = max(peak, running)
        max_dd = min(max_dd, running - peak)

    return {
        "pnl_total": sum(pnls),
        "trades_closed": len(closed),
        "wr_pct": (len(wins) / len(closed) * 100) if closed else 0.0,
        "avg_win": (sum(wins) / len(wins)) if wins else 0.0,
        "avg_loss": (sum(losses) / len(losses)) if losses else 0.0,
        "biggest_win": max(wins) if wins else 0.0,
        "biggest_loss": min(losses) if losses else 0.0,
        "max_dd": max_dd,
    }


def _read_baseline_metrics() -> dict | None:
    """Подгружает метрики предыдущего дня из архива JSON для сравнения."""
    if not ARCHIVE_DIR.exists():
        return None
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    p = ARCHIVE_DIR / f"{yesterday}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    now = datetime.now(timezone.utc)
    baseline = _read_baseline_metrics()
    today_metrics: dict = {}

    lines: list[str] = []
    lines.append(f"# Ежедневная сводка bot7 — {now:%Y-%m-%d}")
    lines.append("")
    lines.append(f"_Сгенерирован {now.strftime('%H:%M UTC')}, окно {WINDOW_H}ч_")
    lines.append("")

    # ── Коммиты ────────────────────────────────────────────────────────────
    commits = _git_commits_last_24h()
    today_metrics["commits"] = len(commits)
    lines.append(f"## Коммиты ({len(commits)}{_trend_arrow(len(commits), baseline.get('commits') if baseline else None)})")
    lines.append("")
    if commits:
        for h, subject in commits:
            lines.append(f"- `{h}` {subject}")
    else:
        lines.append("- (нет)")
    lines.append("")

    # ── Pipeline ──────────────────────────────────────────────────────────
    metrics = _read_jsonl_window(ROOT / "state" / "pipeline_metrics.jsonl", WINDOW_H)
    if metrics:
        stage_counts = Counter(m.get("stage_outcome") for m in metrics)
        emitted = stage_counts.get("emitted", 0)
        total = len(metrics)
        env_disabled = stage_counts.get("env_disabled", 0)
        today_metrics["pipeline_total"] = total
        today_metrics["pipeline_emitted"] = emitted

        emit_pct = emitted / total * 100 if total else 0
        bl_emit = baseline.get("pipeline_emitted") if baseline else None
        lines.append(f"## Pipeline — {total} событий, {emitted} в TG ({emit_pct:.2f}%{_trend_arrow(emitted, bl_emit)})")
        lines.append("")

        # Funnel одной строкой
        funnel_order = ["env_disabled", "combo_blocked", "mtf_conflict", "mtf_neutral",
                        "type_pair_dedup_skip", "semantic_dedup_skip", "gc_shadow", "emitted"]
        funnel_parts = []
        for k in funnel_order:
            if stage_counts.get(k):
                funnel_parts.append(f"{k}={stage_counts[k]}")
        if funnel_parts:
            lines.append("Воронка: " + " → ".join(funnel_parts))
            lines.append("")

        # Расшифровка стадий
        for stage, n in stage_counts.most_common():
            ru = STAGE_RU.get(stage, stage)
            extra = ""
            if stage == "env_disabled" and env_disabled > 0:
                disabled = _disabled_detectors_human()
                if disabled:
                    extra = f" (отключены: {', '.join(disabled)})"
            lines.append(f"- {stage}: {n} — {ru}{extra}")
        lines.append("")

    # ── Перезапуски ───────────────────────────────────────────────────────
    restarts = _read_jsonl_window(ROOT / "state" / "app_runner_starts.jsonl", WINDOW_H)
    n_restarts = len(restarts)
    today_metrics["restarts"] = n_restarts
    if restarts:
        bl_r = baseline.get("restarts") if baseline else None
        lines.append(f"## Перезапуски app_runner: {n_restarts}{_trend_arrow(n_restarts, bl_r, lower_is_better=True)}")
        # Распределение по часам — отделяет таймер от случайных крэшей
        by_hour = Counter()
        for r in restarts:
            ts = r.get("ts", "")
            m = re.match(r"\d{4}-\d{2}-\d{2}T(\d{2}):", ts)
            if m:
                by_hour[int(m.group(1))] += 1
        if by_hour:
            avg_per_hour = n_restarts / max(len(by_hour), 1)
            uniform = max(by_hour.values()) - min(by_hour.values()) <= 2 and avg_per_hour > 5
            if uniform:
                lines.append(f"  • Равномерно {avg_per_hour:.0f}/час по {len(by_hour)} часам — похоже на штатный таймер, не крэши")
            elif n_restarts > 50:
                lines.append("  • [ВНИМАНИЕ] высокая частота — посмотри watchdog audit + последние Traceback в логах")
            else:
                lines.append("  • Распределение нормальное")
        lines.append("")

    # ── P-15 ──────────────────────────────────────────────────────────────
    p15_events = _read_jsonl_window(ROOT / "state" / "p15_equity.jsonl", WINDOW_H)
    if p15_events:
        st = _p15_stats(p15_events)
        opens = sum(1 for e in p15_events if e.get("stage") == "OPEN")
        closes = sum(1 for e in p15_events if e.get("stage") == "CLOSE")
        harvests = sum(1 for e in p15_events if e.get("stage") == "HARVEST")
        today_metrics["p15_pnl"] = st["pnl_total"]
        today_metrics["p15_trades"] = st["trades_closed"]

        bl_pnl = baseline.get("p15_pnl") if baseline else None
        lines.append("## P-15 lifecycle")
        lines.append("")
        lines.append(f"- PnL за день: ${st['pnl_total']:+.2f}{_trend_arrow(st['pnl_total'], bl_pnl)}")
        if st["trades_closed"] > 0:
            lines.append(
                f"- Закрытых сделок: {st['trades_closed']} | "
                f"WR: {st['wr_pct']:.0f}% | "
                f"avg win: ${st['avg_win']:+.2f} | "
                f"avg loss: ${st['avg_loss']:+.2f}"
            )
            lines.append(
                f"- Лучшая: ${st['biggest_win']:+.2f} | "
                f"худшая: ${st['biggest_loss']:+.2f} | "
                f"MaxDD по equity: ${st['max_dd']:.2f}"
            )
        lines.append(f"- Стадии: OPEN={opens}, HARVEST={harvests}, CLOSE={closes}")
        if opens > 0:
            lines.append(f"- HARVEST/OPEN ratio: {harvests / opens:.2f} (>1 = частичные фиксации активны)")
        lines.append("")

    # ── Paper trader (одиночные сетапы) ───────────────────────────────────
    paper_events = _read_jsonl_window(ROOT / "state" / "paper_trades.jsonl", WINDOW_H)
    if paper_events:
        st = _p15_stats(paper_events)
        if st["trades_closed"] > 0:
            today_metrics["paper_pnl"] = st["pnl_total"]
            today_metrics["paper_trades"] = st["trades_closed"]
            bl_pnl = baseline.get("paper_pnl") if baseline else None
            lines.append("## Paper trader (одиночные сетапы)")
            lines.append("")
            lines.append(f"- PnL за день: ${st['pnl_total']:+.2f}{_trend_arrow(st['pnl_total'], bl_pnl)}")
            lines.append(
                f"- Закрытых сделок: {st['trades_closed']} | "
                f"WR: {st['wr_pct']:.0f}% | "
                f"avg win: ${st['avg_win']:+.2f} | "
                f"avg loss: ${st['avg_loss']:+.2f}"
            )
            pf = sum(p for p in (float(e.get("realized_pnl_usd") or 0) for e in paper_events) if p > 0) / \
                 max(abs(sum(p for p in (float(e.get("realized_pnl_usd") or 0) for e in paper_events) if p < 0)), 1e-9)
            lines.append(
                f"- Лучшая: ${st['biggest_win']:+.2f} | "
                f"худшая: ${st['biggest_loss']:+.2f} | "
                f"MaxDD: ${st['max_dd']:.2f} | "
                f"Profit factor: {pf:.2f}"
            )
            # Распределение по сторонам
            sides = {}
            for e in paper_events:
                s = e.get("side") or e.get("direction")
                v = float(e.get("realized_pnl_usd") or 0)
                if s and v != 0:
                    sides.setdefault(s, []).append(v)
            if sides:
                side_strs = []
                for s, vs in sorted(sides.items(), key=lambda x: -sum(x[1])):
                    ws = sum(1 for v in vs if v > 0)
                    side_strs.append(f"{s.upper()} ${sum(vs):+.0f} ({len(vs)} сд, WR {ws/len(vs)*100:.0f}%)")
                lines.append(f"- По сторонам: {' | '.join(side_strs)}")
            lines.append("")

    # ── GC решения ────────────────────────────────────────────────────────
    audit = _read_jsonl_window(ROOT / "state" / "gc_confirmation_audit.jsonl", WINDOW_H)
    if audit:
        decisions = Counter(str(r.get("decision", "")).split("(")[0].strip() for r in audit)
        today_metrics["gc_total"] = sum(decisions.values())
        lines.append("## Решения Grid Coordinator")
        lines.append("")
        for d, n in decisions.most_common():
            lines.append(f"- {d}: {n}")
        boost = sum(v for k, v in decisions.items() if "boost" in k.lower())
        penalty = sum(v for k, v in decisions.items() if "penalty" in k.lower())
        if boost or penalty:
            ratio = boost / max(penalty, 1)
            interp = "перевес в сторону усиления" if ratio > 1.5 else \
                     "перевес в сторону осторожности" if ratio < 0.7 else "сбалансировано"
            lines.append(f"- boost:penalty = {boost}:{penalty} ({ratio:.1f}, {interp})")
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(lines)
    OUT.write_text(body, encoding="utf-8")
    print(f"[change-log] записан {OUT}")

    # Архив: markdown + JSON (для сравнения с предыдущими днями)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_md = ARCHIVE_DIR / f"{now.strftime('%Y-%m-%d')}.md"
    archive_md.write_text(body, encoding="utf-8")
    archive_json = ARCHIVE_DIR / f"{now.strftime('%Y-%m-%d')}.json"
    archive_json.write_text(json.dumps(today_metrics, indent=2), encoding="utf-8")
    print(f"[change-log] архивирован {archive_md.name} + .json")

    # Чистка архивов старше 90 дней
    import time
    cutoff_ts = time.time() - 90 * 86400
    for old in ARCHIVE_DIR.glob("*"):
        try:
            if old.stat().st_mtime < cutoff_ts:
                old.unlink()
                print(f"[change-log] удалён старый {old.name}")
        except OSError:
            pass

    # Усечение launchd .err логов: launchd не ротирует stderr-захват сам.
    # Если файл > 10 MB, оставляем последние 1 MB. Python-логирование
    # параллельно пишет в logs/app.log с RotatingFileHandler — там полная
    # история сохраняется.
    LOGS_DIR = ROOT / "logs"
    LOG_MAX_BYTES = 10 * 1024 * 1024
    LOG_KEEP_BYTES = 1 * 1024 * 1024
    for log in LOGS_DIR.glob("launchd_*.err"):
        try:
            sz = log.stat().st_size
            if sz > LOG_MAX_BYTES:
                with log.open("rb") as f:
                    f.seek(-LOG_KEEP_BYTES, 2)
                    tail_bytes = f.read()
                log.write_bytes(tail_bytes)
                print(f"[change-log] усечён {log.name}: {sz // 1024 // 1024} MB → 1 MB")
        except OSError:
            pass

    print("\n".join(lines[:30]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
