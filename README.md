# чат бот версия 2

Трейдерский Telegram-бот для анализа BTC/рынка, сценариев входа, сопровождения позиций и подсказок по сеточным ботам.

## Что важно сейчас
- проект работает только поверх последнего архива
- Regression Shield обязателен перед commit / push / release
- новые фичи не добавляются, пока не закрыт текущий жёсткий этап плана
- корень проекта очищен: в релизе оставлен только минимальный боевой набор bat-файлов

## Быстрый старт
1. Создать и активировать `.venv`
2. Установить зависимости: `pip install -r requirements.txt`
3. Прогнать тесты: `python -B -m pytest tests -q`
4. Запустить бота: `python main.py`

## Основные команды в корне
- `RUN_BOT.bat` — обычный запуск бота
- `RUN_TESTS.bat` — ручной прогон Regression Shield
- `SMOKE_TEST.bat` — разовый live smoke test через реальный API
- `INSTALL_GIT_HOOKS.bat` — установка и проверка pre-commit / pre-push hooks
- `MAKE_RELEASE.bat` — локальная сборка релизного ZIP
- `PUSH_RELEASE.bat` — commit / sync / release через Git

## Что убрано из корня
Старые bat/cmd-скрипты не удалены, а перенесены в `tools/legacy_bat/`, чтобы не перегружать релиз и не путать рабочий контур.

## Структура
- `core/` — пайплайн, decision/execution/render логика
- `advisors/` — торговые и grid/advisor блоки
- `handlers/` — Telegram-команды и маршрутизация
- `tests/` — Regression Shield и acceptance tests
- `manifest/` — источники для сборки `PROJECT_MANIFEST.md`
- `docs/` — история релизов, чеклисты, старые заметки и служебная документация
- `releases/` — локальные собранные ZIP-архивы
- `tools/legacy_bat/` — старые служебные bat/cmd-файлы, убранные из корня

## Документы-источники истины
- `PROJECT_MANIFEST.md`
- `CHANGELOG.md`
- `NEXT_CHAT_PROMPT.txt`
- `VERSION.txt`


## Build / release safety

- `RUN_TESTS.bat` — regression shield
- `SMOKE_TEST.bat` — one live run against the real market API
- `MAKE_RELEASE.bat` — tests + smoke + zip build + zip verify
- `PUSH_RELEASE.bat` — tests + smoke + git sync + push + zip build
