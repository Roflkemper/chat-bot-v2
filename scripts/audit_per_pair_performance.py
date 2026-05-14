"""Анализ paper-результатов по парам (BTC vs ETH vs XRP) и сетапам.

REGULATION_v0_1_1 валидирована только на BTC, но live торгует BTC+ETH+XRP.
Этот скрипт показывает где лонги/шорты работают по парам, какие сетапы
универсальны, а какие — только-BTC. Базис для multi-asset extension.

Источник: state/paper_trades.jsonl + state/p15_paper_trades.jsonl

Output: docs/PER_PAIR_PERFORMANCE_<date>.md
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def stats(trades: list[float]) -> dict:
    """Для списка PnL значений."""
    if not trades:
        return {"n": 0, "pnl": 0, "wr": 0, "pf": 0, "avg_w": 0, "avg_l": 0, "best": 0, "worst": 0}
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    pf = sum(wins) / abs(sum(losses)) if losses else float("inf")
    return {
        "n": len(trades),
        "pnl": sum(trades),
        "wr": len(wins) / len(trades) * 100 if trades else 0,
        "pf": pf,
        "avg_w": sum(wins) / len(wins) if wins else 0,
        "avg_l": sum(losses) / len(losses) if losses else 0,
        "best": max(trades),
        "worst": min(trades),
    }


def fmt_stats(s: dict) -> str:
    if s["n"] == 0:
        return "—"
    pf_s = f"{s['pf']:.2f}" if s["pf"] != float("inf") else "∞"
    return (
        f"${s['pnl']:+.0f} (n={s['n']}, WR={s['wr']:.0f}%, "
        f"PF={pf_s}, avg+={s['avg_w']:+.0f}, avg-={s['avg_l']:+.0f})"
    )


def main() -> int:
    paper = load_jsonl(ROOT / "state" / "paper_trades.jsonl")
    p15 = load_jsonl(ROOT / "state" / "p15_paper_trades.jsonl")

    # paper: pair → side → list[pnl]
    paper_by_pair_side: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    paper_by_pair_setup: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for e in paper:
        pnl = e.get("realized_pnl_usd")
        if pnl is None or pnl == 0:
            continue
        pair = e.get("pair") or "?"
        side = e.get("side") or e.get("direction") or "?"
        stype = e.get("setup_type") or "?"
        paper_by_pair_side[pair][side].append(float(pnl))
        paper_by_pair_setup[pair][stype].append(float(pnl))

    # p15: то же
    p15_by_pair_side: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for e in p15:
        pnl = e.get("realized_pnl_usd")
        if pnl is None or pnl == 0:
            continue
        pair = e.get("pair") or "?"
        side = e.get("side") or e.get("direction") or "?"
        p15_by_pair_side[pair][side].append(float(pnl))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = ROOT / "docs" / f"PER_PAIR_PERFORMANCE_{today}.md"

    md = [
        f"# Производительность по парам — {today}",
        "",
        f"_Сгенерирован `scripts/audit_per_pair_performance.py`. "
        f"Источник: paper_trades.jsonl ({len(paper)} событий), "
        f"p15_paper_trades.jsonl ({len(p15)} событий)._",
        "",
        "Зачем: REGULATION валидирована только на BTC, но live торгует BTC+ETH+XRP.",
        "Если ETH/XRP убыточны — нужна либо отдельная конфигурация, либо отключение.",
        "",
    ]

    # ── Paper trader: по парам × сторонам ──────────────────────────────────
    md.extend([
        "## Paper trader — по паре × стороне",
        "",
        "| Пара | LONG | SHORT |",
        "|------|------|-------|",
    ])
    for pair in sorted(paper_by_pair_side.keys()):
        long_s = stats(paper_by_pair_side[pair].get("long", []))
        short_s = stats(paper_by_pair_side[pair].get("short", []))
        md.append(f"| **{pair}** | {fmt_stats(long_s)} | {fmt_stats(short_s)} |")
    md.append("")

    # ── Paper trader: по паре × setup_type (топ-10 по объёму) ──────────────
    md.extend([
        "## Paper trader — топ-сетапы по парам",
        "",
    ])
    for pair in sorted(paper_by_pair_setup.keys()):
        md.append(f"### {pair}")
        md.append("")
        md.append("| Сетап | PnL | n | WR | PF | avg win | avg loss |")
        md.append("|-------|-----|---|-----|-----|---------|----------|")
        items = sorted(paper_by_pair_setup[pair].items(),
                       key=lambda x: -sum(x[1]))
        for stype, pnls in items[:10]:
            s = stats(pnls)
            pf_s = f"{s['pf']:.2f}" if s['pf'] != float("inf") else "∞"
            md.append(
                f"| `{stype}` | ${s['pnl']:+.0f} | {s['n']} | "
                f"{s['wr']:.0f}% | {pf_s} | ${s['avg_w']:+.1f} | ${s['avg_l']:+.1f} |"
            )
        md.append("")

    # ── P-15 по парам ───────────────────────────────────────────────────────
    if p15_by_pair_side:
        md.extend([
            "## P-15 (хедж-сетки) — по паре × стороне",
            "",
            "| Пара | LONG | SHORT |",
            "|------|------|-------|",
        ])
        for pair in sorted(p15_by_pair_side.keys()):
            long_s = stats(p15_by_pair_side[pair].get("long", []))
            short_s = stats(p15_by_pair_side[pair].get("short", []))
            md.append(f"| **{pair}** | {fmt_stats(long_s)} | {fmt_stats(short_s)} |")
        md.append("")

    # ── Выводы ──────────────────────────────────────────────────────────────
    md.extend([
        "## Выводы для REGULATION-extension",
        "",
        "1. **Если у пары PF < 1.0 в paper-симе** — на real-money это убытки,",
        "   стратегия не подходит для пары как есть. Нужна либо отдельная",
        "   конфигурация порогов, либо HARD BAN для этой пары.",
        "",
        "2. **Если LONG работает а SHORT убыточен** — это симптом текущего bull-режима,",
        "   а не сломанной логики. Подождать bear-сэмпла перед выводами.",
        "",
        "3. **Если конкретный setup_type работает на BTC и не работает на ETH/XRP** —",
        "   значит features (volume, liquidity, OI) разные. Нужна нормализация",
        "   порогов на пару (например, ATR в %% от цены вместо абсолютного USD).",
        "",
        "## Перегенерация",
        "",
        "```bash",
        "python scripts/audit_per_pair_performance.py",
        "```",
    ])
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"Отчёт: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
