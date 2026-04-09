# Changelog

## V17.7.2 — ONE CLICK GITHUB PUSH + AUTO RELEASE PACK
- Добавлены `INIT_GITHUB_PRIVATE_REPO.bat`, `PUSH_UPDATE.bat`, `MAKE_RELEASE_TAG.bat`
- Добавлен `docs/github/ONE_CLICK_SETUP.md`
- Добавлен workflow `.github/workflows/build_release_zip.yml` для автоматической сборки ZIP после push в `main`
- Добавлен workflow `.github/workflows/release_on_tag.yml` для автоматического релиза ZIP по тегу `v*`
- Обновлены `README.md` и `VERSION.txt`
- Торговая логика V17.7 не менялась

## V17.7.1 — GITHUB INTEGRATION PACK
- Подготовлен пакет под приватный GitHub-репозиторий `Roflkemper/chat-bot-v2`
- Удалены `__pycache__` и `.pyc` из релизного архива
- Усилен `.gitignore` для защиты секретов, логов и runtime state
- Добавлен `.gitattributes`
- Обновлён `README.md`
- Добавлен `docs/github/GITHUB_SETUP.md`
- Добавлены release notes для GitHub integration pack
- Торговая логика V17.7 не менялась

## V17.7 — FINAL SIGNAL MODEL (PROP LEVEL)
- Final signal state machine
- Signal debounce
- Edge hysteresis
- Signal alignment with master decision
- Hard execution advisor rules
- Cleaner action output and telegram rendering
