# bot7 на Mac — быстрый старт (вариант C: dev-параллель)

**Что получаем:** Mac работает параллельно с Win. Mac шлёт алерты в **dev-канал** `-1003883390537`, Win продолжает в основной чат. Никаких конфликтов. Если Mac упал ночью — Win всё равно работает, prod не пострадает.

**Что НЕ запускаем на Mac:** ginarea_tracker (он на Win) — чтобы не было двух одновременных GinArea-сессий.

## Шаг 1. Перенести 4 файла на Mac

На Win в папке `C:\bot7-transfer\` лежат:
- `bot7_state_<date>.tar.gz` (7.6 MB)
- `bot7_ginarea_live_<date>.tar.gz` (3 MB)
- `bot7_market_live_<date>.tar.gz` (0.3 MB)
- `mac_env_local.txt` (готовый .env.local для Mac)

Способы переноса:
- **AirDrop** (если Mac и iPhone/Win-устройство в одной сети) — простейший
- **iCloud Drive** — закинул на Win → скачал на Mac
- **Google Drive / Dropbox** — то же самое
- **USB-флешка**

Всё в `~/Downloads/` на маке.

## Шаг 2. Установить Python и git на Mac

Открой **Terminal** (Spotlight: ⌘+Space → "Terminal"):

```bash
# Установить Homebrew (если ещё нет)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python 3.10 + git
brew install python@3.10 git
```

## Шаг 3. Склонировать репо

```bash
mkdir -p ~/code && cd ~/code
git clone https://github.com/<твой-username>/<repo-name>.git bot7
# Если репо приватный — нужен PAT или ssh ключ.
# Альтернатива: скопировать всю папку c:\bot7 на Mac через AirDrop как ZIP.
cd bot7
```

Если нет GitHub remote — можно перенести репо через ZIP:
- На Win: правый клик на `C:\bot7` → Send to → Compressed (zip)
- AirDrop / iCloud → распаковать на Mac в `~/code/bot7/`

## Шаг 4. Виртуальное окружение

```bash
cd ~/code/bot7
python3.10 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt pytest-httpx
```

## Шаг 5. Распаковать архивы данных

```bash
cd ~/code/bot7
tar xzf ~/Downloads/bot7_state_*.tar.gz
tar xzf ~/Downloads/bot7_ginarea_live_*.tar.gz
tar xzf ~/Downloads/bot7_market_live_*.tar.gz

# Проверка
ls state/ | wc -l        # ~137 файлов
ls ginarea_live/         # snapshots.csv, events.csv, params.csv
ls market_live/          # market_1m.csv, liquidations.csv, signals.csv
```

## Шаг 6. Создать .env.local

```bash
cp ~/Downloads/mac_env_local.txt ~/code/bot7/.env.local
```

Проверь содержимое — должен быть **dev-токен** (`8850451381:...`) и dev-канал (`-1003883390537`).

```bash
cat ~/code/bot7/.env.local
```

## Шаг 7. Smoke test (5 минут)

```bash
cd ~/code/bot7
source .venv/bin/activate
python app_runner.py
```

Через ~30 секунд в **dev-канале** должно прилететь стартап-сообщение от мака (`liq_pre_cascade.start`, `cascade_alert.start` и т.д.).

Если работает — нажми **Ctrl+C** (бот остановится). Переходим к фоновому запуску.

## Шаг 8. Запретить мак засыпать (только в charger)

```bash
sudo pmset -c sleep 0       # на charger не засыпать
sudo pmset -c disksleep 0   # диски не парковать
sudo pmset -c powernap 0    # отключить PowerNap
sudo pmset -c standby 0     # отключить deep sleep

# Проверка
pmset -g | grep -i sleep
```

Закрытие крышки на charger — OK, мак продолжит работать (если использовать caffeinate, см. шаг 9).

## Шаг 9. Запустить в фоне через launchd

Самый простой вариант — один файл `com.bot7.app-runner.plist`:

```bash
export BOT7_PATH=$HOME/code/bot7
mkdir -p $BOT7_PATH/logs

sed -e "s|%BOT7_PATH%|$BOT7_PATH|g" \
    $BOT7_PATH/docs/launchd_templates/com.bot7.app-runner.plist \
    > ~/Library/LaunchAgents/com.bot7.app-runner.plist

launchctl load ~/Library/LaunchAgents/com.bot7.app-runner.plist

# Через 30 секунд проверка
sleep 30
launchctl list | grep com.bot7
ps aux | grep app_runner | grep -v grep
```

Также можно подгрузить **market_collector** (он будет собирать live данные параллельно с Win — это нормально, оба источника):

```bash
sed -e "s|%BOT7_PATH%|$BOT7_PATH|g" \
    $BOT7_PATH/docs/launchd_templates/com.bot7.market-collector.plist \
    > ~/Library/LaunchAgents/com.bot7.market-collector.plist
launchctl load ~/Library/LaunchAgents/com.bot7.market-collector.plist
```

**НЕ** загружай `com.bot7.ginarea-tracker.plist` — это на Win.

## Управление

```bash
# Остановить
launchctl unload ~/Library/LaunchAgents/com.bot7.app-runner.plist

# Запустить
launchctl load ~/Library/LaunchAgents/com.bot7.app-runner.plist

# Рестарт (после git pull)
launchctl unload ~/Library/LaunchAgents/com.bot7.app-runner.plist
launchctl load ~/Library/LaunchAgents/com.bot7.app-runner.plist

# Логи
tail -f ~/code/bot7/logs/launchd_app_runner.log
tail -f ~/code/bot7/logs/app.log
```

## Что должно работать после установки

- В **dev-канале** Telegram прилетают алерты с **мака** (LEVEL_BREAK, cascade, exhaustion, etc)
- В **prod-канале** продолжают прилетать алерты с **Win** (как обычно)
- Никаких дублей — каждая машина шлёт в свой канал

Если что-то не работает:
- Проверь логи: `tail -20 ~/code/bot7/logs/launchd_app_runner.log`
- Если есть ошибка `Unauthorized` или `Forbidden` — токен/chat_id неправильный в `.env.local`
- Если есть ошибка `ModuleNotFoundError` — pip установка не прошла, повтори шаг 4

## Удаление при необходимости

```bash
launchctl unload ~/Library/LaunchAgents/com.bot7.*.plist 2>/dev/null
rm ~/Library/LaunchAgents/com.bot7.*.plist
rm -rf ~/code/bot7  # осторожно — удалит всё
```
