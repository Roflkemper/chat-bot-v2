"""Добавить запись в docs/SESSION_LOG.md за текущую дату.

SESSION_LOG ведётся вручную, авто-CHANGELOG_DAILY его не заменяет
(там только метрики, без human context: «почему я это сделал»).

Использование:
    python scripts/append_session.py "TZ-XXX: Заголовок" "Краткое резюме"

Или интерактивно (без аргументов спросит):
    python scripts/append_session.py

После TZ-067 (15 дней молчания) восстановлено как обязательное правило.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION_LOG = ROOT / "docs" / "SESSION_LOG.md"


def main() -> int:
    if len(sys.argv) >= 3:
        title = sys.argv[1]
        body = sys.argv[2]
    elif len(sys.argv) == 2:
        title = sys.argv[1]
        print("Тело записи (Ctrl-D для завершения):")
        body = sys.stdin.read().strip()
    else:
        print("Заголовок (например 'TZ-067: краткое описание'):")
        title = input("> ").strip()
        if not title:
            print("Заголовок не может быть пустым.")
            return 1
        print("Тело (Ctrl-D для завершения):")
        body = sys.stdin.read().strip()

    if not body:
        print("Тело не может быть пустым.")
        return 1

    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y-%m-%d")
    time_part = now.strftime("%H:%M UTC")

    entry = "\n".join([
        "",
        "---",
        "",
        f"## {date_part} ({time_part}) — {title}",
        "",
        body,
        "",
    ])

    if not SESSION_LOG.exists():
        SESSION_LOG.write_text("# Session Log\n", encoding="utf-8")

    with SESSION_LOG.open("a", encoding="utf-8") as f:
        f.write(entry)

    print(f"[session] добавлено в {SESSION_LOG.relative_to(ROOT)}")
    print(f"  {date_part} ({time_part}) — {title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
