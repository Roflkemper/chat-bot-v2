# ONE CLICK GITHUB FLOW

Репозиторий:
- `Roflkemper/chat-bot-v2`
- тип: `private`

## Что сделано в пакете V17.7.2
- добавлены BAT-файлы для почти автоматической работы с GitHub
- добавлен GitHub Actions workflow для автоматической сборки ZIP
- добавлен workflow для автоматического GitHub Release по тегу `v*`
- обновлены README / CHANGELOG / VERSION / release notes

## Первый запуск — один раз
1. Распакуй проект.
2. Запусти `INIT_GITHUB_PRIVATE_REPO.bat`.
3. При первом push GitHub может открыть браузер и попросить вход.
4. После успешного push база уже привязана.

## Дальше обычный режим
Для простого обновления:
- запусти `PUSH_UPDATE.bat`

Что произойдёт:
- `git add .`
- commit по версии из `VERSION.txt`
- push в `main`
- если GitHub Actions включены, ZIP-сборка стартует автоматически

## Релизный режим
Для релизного тега:
- запусти `MAKE_RELEASE_TAG.bat`

Что произойдёт:
- commit недостающих изменений
- создание тега
- push тега в GitHub
- GitHub Actions создаст release ZIP и приложит его к GitHub Release

## Где смотреть результат
- вкладка `Actions` — ход сборки
- вкладка `Releases` — готовые релизные ZIP по тегам
- `Artifacts` внутри workflow — ZIP после обычного push в `main`

## Что может потребоваться один раз руками
### Если GitHub Actions не создаёт релиз по тегу
Проверь в репозитории:
- `Settings` → `Actions` → `General`
- разрешены workflows
- у `Workflow permissions` включено как минимум чтение и запись для `GITHUB_TOKEN`, если хочешь автоматическое создание release

## Что не хранить в репозитории
- `.env`
- Telegram токены
- `bot_local_config.json`
- логи
- runtime state

Это уже прикрыто `.gitignore`, но перед первым push всё равно полезно визуально проверить список файлов.
