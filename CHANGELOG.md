
## V17.8.4.3 - BIAS SCORE + FUNDING DELTA INTEGRATION
- Added bias score aggregation using HTF trend, flow pressure, funding regime, and leader context.
- Added funding regime / delta ratio / absorption score helpers.
- Added hedge trigger price to pre-hedge output.
- Expanded Telegram output with bias score and funding context.

## V17.8.4 - EXTERNAL MARKET BIAS + FLOW PRESSURE
- added external market bias layer (DXY / SPX-SPY / BTC dominance / BTC leader pressure)
- added flow pressure layer (delta proxy / taker pressure / absorption detector / OI fake-expansion logic)
- added PRE-HEDGE WARNING states
- integrated extern + flow pressure into execution advisor and Telegram output


## V17.8.3 - GRID LIFECYCLE MANAGER
- added grid lifecycle manager and lifecycle authority
- integrated lifecycle phase into execution advisor
- added Telegram block for grid lifecycle
- aligned lifecycle with consensus and hedge states

## V17.8.1 — CONTEXT CONSENSUS FILTER
- Добавлен слой market consensus context без ломки текущей архитектуры
- Добавлены HTF bias, trend pressure, BTC/ETH leader pressure и sentiment overlay
- Consensus filter теперь умеет ослаблять или блокировать сторону
- Execution advisor получил modifiers: reduce aggression / no add / hedge prepare by consensus
- В Telegram-вывод добавлен блок «КОНТЕКСТ РЫНКА»

V17.7.4 - PATTERN SUPPRESSION + NON-MATERIAL FLIP FILTER

- pattern-memory suppressed in PAUSE + MID RANGE + CHOP + unconfirmed breakout
- non-material directional flips are rendered as context-only instead of long/short bias
- formatter neutralizes pattern bias when master action remains pause / no entry

## V17.7.3 - ZERO CLICK MODE

- Added `_GITHUB_RUNTIME.bat` for automatic Git and GitHub CLI discovery.
- Updated init/push/tag scripts to reduce manual setup.
- Added fallback support for GitHub Desktop bundled Git.
- Added `OPEN_GITHUB_ACTIONS.bat`.
- No trading logic changes.

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

## V17.8.2 - HEDGE ACTION REFINEMENT
- added hedge action refinement layer with effective delta and grid stress
- added hedge modes OFF/WATCH/ARM/READY/REDUCE/EXIT
- integrated hedge action into execution advisor
- added dedicated Telegram block for hedge / protection
