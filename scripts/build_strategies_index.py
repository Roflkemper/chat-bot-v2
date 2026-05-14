"""Сборка индекса для docs/STRATEGIES/.

68+ research-документов сложно навигировать без оглавления. Скрипт:
  - извлекает заголовок и первый абзац как preview
  - группирует файлы по теме (по ключевым словам в имени)
  - сортирует темы по числу файлов
  - даёт топ-10 свежих и топ-10 крупных

Output: docs/STRATEGIES/INDEX.md (перезаписывается).

Запуск: python scripts/build_strategies_index.py
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGIES = ROOT / "docs" / "STRATEGIES"
INDEX_OUT = STRATEGIES / "INDEX.md"

THEMES = [
    ("CASCADE", "Каскады ликвидаций"),
    ("LIQ", "Ликвидации"),
    ("PRE_CASCADE", "Pre-cascade"),
    ("SHORT_T1", "SHORT T1"),
    ("MEGA", "MEGA-сетапы"),
    ("DOUBLE_BOTTOM", "Double bottom"),
    ("DIVERGENCE", "Дивергенции"),
    ("MULTI_DIVERGENCE", "Multi-divergence"),
    ("REGIME", "Regime detection"),
    ("PDL", "PDL/PDH"),
    ("PDH", "PDL/PDH"),
    ("GA_", "Genetic search"),
    ("GENETIC", "Genetic search"),
    ("GINAREA", "GinArea"),
    ("GRID", "Grid стратегии"),
    ("P15", "P-15 хеджи"),
    ("P-15", "P-15 хеджи"),
    ("RSI", "RSI"),
    ("MFI", "MFI"),
    ("CONFLUENCE", "Confluence"),
    ("EXIT", "Exit логика"),
    ("BACKTEST", "Backtest"),
    ("CALIBRATION", "Калибровка"),
    ("FORWARD", "Forward analysis"),
    ("REPORT", "Отчёты"),
    ("PLAYBOOK", "Playbook"),
]


def extract_meta(path: Path) -> dict:
    text = ""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        pass
    title = ""
    preview = ""
    for line in text.splitlines():
        line = line.strip()
        if not title and (line.startswith("# ") or line.startswith("## ")):
            title = line.lstrip("#").strip()
        elif title and not preview and line and not line.startswith(("#", "-", "*", "|", "_")):
            preview = line[:120]
            if len(line) > 120:
                preview += "…"
            break
    stat = path.stat()
    return {
        "name": path.name,
        "title": title or path.stem.replace("_", " ").title(),
        "preview": preview,
        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        "size_kb": stat.st_size // 1024,
    }


def detect_theme(name: str) -> str:
    upper = name.upper()
    for kw, theme in THEMES:
        if kw in upper:
            return theme
    return "Прочее"


def main() -> int:
    files = sorted(p for p in STRATEGIES.glob("*.md") if p.name != "INDEX.md")
    items = [extract_meta(p) for p in files]

    by_theme: dict[str, list] = {}
    for it, p in zip(items, files):
        theme = detect_theme(p.name)
        by_theme.setdefault(theme, []).append(it)

    ordered_themes = sorted(by_theme.items(), key=lambda x: (-len(x[1]), x[0]))

    now = datetime.now(timezone.utc)
    md = [
        f"# Индекс STRATEGIES/ — {now:%Y-%m-%d}",
        "",
        f"_Авто-сгенерирован `scripts/build_strategies_index.py`. "
        f"Файлов: **{len(items)}**, тем: **{len(by_theme)}**._",
        "",
        "Перегенерация: `python scripts/build_strategies_index.py`",
        "",
        "## По темам",
        "",
    ]
    for theme, files_in_theme in ordered_themes:
        files_in_theme.sort(key=lambda x: -x["mtime"].timestamp())
        md.append(f"### {theme} ({len(files_in_theme)})")
        md.append("")
        md.append("| Файл | Дата | KB | Заголовок |")
        md.append("|------|------|-----|-----------|")
        for it in files_in_theme:
            date_s = it["mtime"].strftime("%Y-%m-%d")
            title_s = it["title"][:80]
            md.append(f"| [`{it['name']}`]({it['name']}) | {date_s} | {it['size_kb']} | {title_s} |")
        md.append("")

    items_sorted = sorted(items, key=lambda x: -x["mtime"].timestamp())
    md.extend([
        "## Топ-10 свежих (по mtime)",
        "",
        "| Файл | Дата | Превью |",
        "|------|------|--------|",
    ])
    for it in items_sorted[:10]:
        date_s = it["mtime"].strftime("%Y-%m-%d %H:%M")
        preview_s = (it["preview"] or "—")[:100]
        md.append(f"| [`{it['name']}`]({it['name']}) | {date_s} | {preview_s} |")
    md.append("")

    items_size = sorted(items, key=lambda x: -x["size_kb"])
    md.extend([
        "## Топ-10 крупных (по размеру)",
        "",
        "| Файл | KB | Дата |",
        "|------|-----|------|",
    ])
    for it in items_size[:10]:
        md.append(f"| [`{it['name']}`]({it['name']}) | {it['size_kb']} | "
                  f"{it['mtime'].strftime('%Y-%m-%d')} |")
    md.append("")

    INDEX_OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"Индекс записан: {INDEX_OUT}")
    print(f"Файлов: {len(items)}, тем: {len(by_theme)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
