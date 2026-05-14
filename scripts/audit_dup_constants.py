"""Поиск дублирующихся UPPER_SNAKE-констант с одинаковым значением в
разных .py файлах. Помогает выявить кандидатов на вынос в core/constants.

Запуск: python scripts/audit_dup_constants.py

Output: docs/DUP_CONSTANTS_AUDIT_<date>.md
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {"tests", "frozen", "__pycache__", ".venv", "legacy", "docs", "scripts/research_archive"}

CONST_RE = re.compile(r"^([A-Z][A-Z0-9_]{3,})\s*=\s*(.+?)(?:\s*#|$)", re.M)


def main() -> int:
    defs: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    files_scanned = 0

    for py in ROOT.rglob("*.py"):
        parts = set(py.relative_to(ROOT).parts)
        if parts & EXCLUDE:
            continue
        files_scanned += 1
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in CONST_RE.finditer(text):
            name = m.group(1)
            val = m.group(2).strip().rstrip(",")
            if val.startswith(("{", "[", "(")) and not val.endswith(("}", "]", ")")):
                continue
            if val.startswith(("Dict", "List", "Optional", "Union", "Type", "type:", "Final[")) or val == "":
                continue
            line = text[: m.start()].count("\n") + 1
            defs[(name, val)].append((str(py.relative_to(ROOT)), line))

    dups = []
    for (name, val), occurrences in defs.items():
        files = {f for f, _ in occurrences}
        if len(files) >= 2:
            dups.append((name, val, sorted(occurrences)))

    dups.sort(key=lambda d: (-len(d[2]), d[0]))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = ROOT / "docs" / f"DUP_CONSTANTS_AUDIT_{today}.md"

    md = [
        f"# Аудит дублирующихся констант — {today}",
        "",
        f"_Сгенерирован {Path(__file__).name}, просканировано {files_scanned} .py файлов_",
        "",
        f"Уникальных пар (имя, значение): **{len(defs)}**, "
        f"из них дублей в 2+ файлах: **{len(dups)}**",
        "",
        "## Топ-30 дублирующихся констант",
        "",
        "| # | Имя | Значение | Копий | Файлы |",
        "|---|-----|----------|-------|-------|",
    ]
    for i, (name, val, occ) in enumerate(dups[:30], 1):
        val_s = val if len(val) < 40 else val[:37] + "..."
        files_s = "<br>".join(f"`{f}:{ln}`" for f, ln in occ[:5])
        if len(occ) > 5:
            files_s += f"<br>...+{len(occ) - 5}"
        md.append(f"| {i} | `{name}` | `{val_s}` | {len(occ)} | {files_s} |")

    md.extend(
        [
            "",
            "## Приоритеты для рефакторинга",
            "",
            "1. **Численные пороги/комиссии** (TAKER_FEE_PCT, BASE_SIZE_USD, N_FOLDS) — "
            "вынести в `core/constants.py` или `config.py`. Если BitMEX поменяет комиссию, "
            "изменения в одном месте, не в 8.",
            "2. **Пути к данным** (LIQ_CSV, ICT_PARQUET, PARQUET, DATA_1M) — вынести в `core/paths.py`.",
            "3. **SIM_START/SIM_END даты** — это backtest window. Вынести в `services/backtest/window.py`.",
            "4. **`ROOT = Path(__file__).resolve().parents[N]`** — это ИДИОМА, не баг (137 копий). "
            "Каждый файл должен иметь свой расчёт ROOT относительно своего расположения.",
            "",
            "## Перегенерация",
            "",
            "```bash",
            "python scripts/audit_dup_constants.py",
            "```",
        ]
    )
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"Просканировано файлов: {files_scanned}")
    print(f"Дублей в 2+ файлах: {len(dups)}")
    print(f"Отчёт: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
