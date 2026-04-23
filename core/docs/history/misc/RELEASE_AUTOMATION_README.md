# Release automation pack v2

Скопируй содержимое архива в корень проекта.

Запуск:
- двойной клик по `START_RELEASE.cmd`

Что делает:
- автоматически прерывает незавершённый rebase/merge
- повышает версию в `VERSION.txt` (если формат `Vx.y.z`)
- пересобирает `PROJECT_MANIFEST.md`
- обновляет `CHANGELOG.md`
- коммитит изменения
- пушит локальную версию в GitHub через `--force-with-lease`
- собирает ZIP в папку `releases`
- проверяет ZIP
- открывает папку `releases`


Исправление v3: устранена ошибка PowerShell `Missing an argument for parameter 'Args'`.
