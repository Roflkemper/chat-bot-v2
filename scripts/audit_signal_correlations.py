"""Корреляционная матрица сигналов детекторов.

Если P-2 и P-7 срабатывают в одном 5-минутном окне 80% времени — это
не два независимых сигнала, а один в двух обёртках. Confluence-score и
risk-сайзинг должны это учитывать.

Метрика: P(B сработал в окне | A сработал в окне) для каждой пары
detector'ов. Окно = 5 минут.

Источник: state/pipeline_metrics.jsonl (события с stage_outcome=emitted).

Output: docs/SIGNAL_CORRELATIONS_<date>.md

Запуск: python scripts/audit_signal_correlations.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSONL = ROOT / "state" / "pipeline_metrics.jsonl"
WINDOW_MINUTES = 5
MIN_OCCURRENCES = 5  # пары с N<5 не показываем (статистически шумно)


def parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def bucket(dt: datetime, minutes: int) -> int:
    return int(dt.timestamp() // (minutes * 60))


def main() -> int:
    if not JSONL.exists():
        print(f"Нет {JSONL}")
        return 1

    # bucket → set(detector_keys)
    buckets: dict[int, set[str]] = defaultdict(set)
    detector_counts: Counter = Counter()

    n_events = 0
    n_emitted = 0
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        n_events += 1
        if r.get("stage_outcome") != "emitted":
            continue
        n_emitted += 1
        dt = parse_ts(r.get("ts", ""))
        t = r.get("setup_type") or r.get("type") or r.get("detector")
        pair = r.get("pair", "?")
        if not dt or not t:
            continue
        # Ключ детектора с парой — сигналы по разным парам не коррелируют напрямую
        key = f"{t}@{pair}"
        b = bucket(dt, WINDOW_MINUTES)
        buckets[b].add(key)
        detector_counts[key] += 1

    # Co-occurrence: pair_co[(A, B)] = N окон где сработали оба
    pair_co: Counter = Counter()
    for keys in buckets.values():
        keys_list = sorted(keys)
        for i, a in enumerate(keys_list):
            for b in keys_list[i + 1:]:
                pair_co[(a, b)] += 1

    # P(B|A) = N(A∧B) / N(A)
    rows = []
    for (a, b), n_both in pair_co.items():
        n_a = detector_counts[a]
        n_b = detector_counts[b]
        if n_a < MIN_OCCURRENCES or n_b < MIN_OCCURRENCES:
            continue
        p_b_given_a = n_both / n_a
        p_a_given_b = n_both / n_b
        # симметричный jaccard
        jaccard = n_both / (n_a + n_b - n_both)
        rows.append({
            "a": a, "b": b,
            "n_a": n_a, "n_b": n_b, "n_both": n_both,
            "p_b_given_a": p_b_given_a,
            "p_a_given_b": p_a_given_b,
            "jaccard": jaccard,
        })

    rows.sort(key=lambda r: -r["jaccard"])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = ROOT / "docs" / f"SIGNAL_CORRELATIONS_{today}.md"

    md = [
        f"# Корреляции сигналов детекторов — {today}",
        "",
        f"_Сгенерирован `scripts/audit_signal_correlations.py`. "
        f"Источник: `state/pipeline_metrics.jsonl`._",
        "",
        f"- Всего событий в pipeline: **{n_events}**",
        f"- Из них emitted (отправлены в TG): **{n_emitted}**",
        f"- Уникальных детекторов (по setup_type@pair): **{len(detector_counts)}**",
        f"- Окно агрегации: **{WINDOW_MINUTES} мин**",
        f"- Минимум срабатываний детектора для попадания в матрицу: **{MIN_OCCURRENCES}**",
        "",
        "## Что значат метрики",
        "",
        "- **N(A∧B)** — в скольких 5-мин окнах сработали оба детектора",
        "- **P(B|A)** — вероятность что B сработает если уже сработал A",
        "- **Jaccard** = N(A∧B) / (N(A) + N(B) − N(A∧B)) — симметричная мера пересечения, от 0 до 1",
        "",
        "## Интерпретация Jaccard",
        "",
        "- **>0.5** — сигналы фактически дублируют друг друга, использовать как 1 источник",
        "- **0.2–0.5** — сильно скоррелированы, в confluence-score веса должны быть снижены",
        "- **0.05–0.2** — частичная корреляция, норма для родственных сетапов",
        "- **<0.05** — независимы, можно складывать confluence напрямую",
        "",
        "## Топ-30 пар по Jaccard (по убыванию схожести)",
        "",
        "| # | Детектор A | Детектор B | N(A) | N(B) | N(A∧B) | P(B\\|A) | P(A\\|B) | Jaccard |",
        "|---|------------|------------|------|------|--------|---------|---------|---------|",
    ]

    for i, r in enumerate(rows[:30], 1):
        md.append(
            f"| {i} | `{r['a']}` | `{r['b']}` | {r['n_a']} | {r['n_b']} | "
            f"{r['n_both']} | {r['p_b_given_a']:.2f} | {r['p_a_given_b']:.2f} | "
            f"{r['jaccard']:.3f} |"
        )

    md.extend([
        "",
        "## Топ-15 детекторов по числу срабатываний (за всю историю)",
        "",
        "| Детектор | Срабатываний (emitted) |",
        "|----------|------------------------|",
    ])
    for det, n in detector_counts.most_common(15):
        md.append(f"| `{det}` | {n} |")

    md.extend([
        "",
        "## Что делать с найденными корреляциями",
        "",
        "1. **Пары с Jaccard >0.5** — задизайнить как один сигнал.",
        "   - Либо явно слить в один setup_type",
        "   - Либо в confluence_score не суммировать их веса (max() вместо +)",
        "",
        "2. **Пары с Jaccard 0.2–0.5** — пересчитать веса в",
        "   `services/setup_detector/confluence_score.py`. Сейчас, скорее всего,",
        "   суммируются как независимые → завышенный confluence_pct.",
        "",
        "3. **Пары между разными парами (BTC↔ETH↔XRP)** — это cross-asset",
        "   confluence, обычно полезный сигнал. Не убирать.",
        "",
        "## Перегенерация",
        "",
        "```bash",
        "python scripts/audit_signal_correlations.py",
        "```",
    ])
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"Корреляций пар (после фильтра N≥{MIN_OCCURRENCES}): {len(rows)}")
    print(f"Топ-3 по Jaccard:")
    for r in rows[:3]:
        print(f"  {r['jaccard']:.3f}  {r['a']}  ↔  {r['b']}")
    print(f"Отчёт: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
