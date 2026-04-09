# chat-bot-v2

Закрытый репозиторий проекта **«чат бот версия 2»**.

Текущий пакет: **V17.7.2 — ONE CLICK GITHUB PUSH + AUTO RELEASE PACK**  
Базовая торговая логика: **V17.7 — FINAL SIGNAL MODEL (PROP LEVEL)**

## Назначение проекта
Это не «аналитик рынка», а **трейдерский ассистент** под практическое управление сетками и действиями вокруг Ginarea-логики.

Базовый конвейер проекта:

`data → features → context → decision → execution → render`

## Что уже закреплено в текущей базе
- RANGE / GRID логика
- decision layer с authority / runtime / scenario / risk
- signal system V17
- change tracking + signal memory
- signal delta strength + action impact
- полный RU output
- отключён legacy renderer
- execution advisor
- V17.7 final signal model: debounce / hysteresis / alignment / hard execution rules

## Что делает пакет V17.7.2
Этот пакет не меняет торговую логику. Он доводит GitHub-интеграцию до почти автоматического режима:
- добавляет BAT-файлы для первого init, обычного push и release tag
- добавляет GitHub Actions workflow для автоматической сборки ZIP
- добавляет workflow для автоматического GitHub Release по тегу `v*`
- обновляет README, changelog и release notes
- сохраняет проект в режиме private repo без секретов в git

## Быстрый старт локально
1. Скопируй `.env.example` в `.env`
2. Заполни Telegram-переменные
3. Установи зависимости из `requirements.txt`
4. Запусти `RUN_BOT.bat`

## Что нельзя коммитить
В GitHub нельзя отправлять:
- `.env`
- `bot_local_config.json`
- токены и ключи
- рабочие логи
- runtime state
- ZIP-архивы релизов

Это уже исключено через `.gitignore`.

## Рекомендуемый Git workflow
- `main` — стабильная линия
- `dev` — следующая рабочая версия
- release tag — `v17.7`, `v17.7.1`, далее по релизу

## GitHub
Репозиторий создан как **private**: `Roflkemper/chat-bot-v2`.

Порядок первого пуша описан в:
- `docs/github/GITHUB_SETUP.md`

## Основные release-файлы
- `VERSION.txt`
- `CHANGELOG.md`
- `RELEASE_NOTES_V17_7.txt`
- `RELEASE_NOTES_V17_7_1_GITHUB.txt`
- `RELEASE_NOTES_V17_7_2_ONE_CLICK_GITHUB.txt`

## One-click GitHub
Для почти автоматической работы с GitHub смотри:
- `docs/github/ONE_CLICK_SETUP.md`
- `INIT_GITHUB_PRIVATE_REPO.bat`
- `PUSH_UPDATE.bat`
- `MAKE_RELEASE_TAG.bat`
