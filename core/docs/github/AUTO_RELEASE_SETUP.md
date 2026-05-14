# AUTO RELEASE SETUP

## Что это делает

### 1. build_release_zip.yml
- запускается при push в main
- собирает ZIP
- кладет его в Artifacts

### 2. release_on_tag.yml
- запускается при push тега вида v*
- собирает ZIP
- создает GitHub Release
- прикладывает ZIP как asset

## Что нужно включить на GitHub

Открой репозиторий:
Settings -> Actions -> General

Проверь:
- Actions permissions: Allow all actions and reusable workflows
- Workflow permissions: Read and write permissions

Без `Read and write permissions` workflow не сможет создать Release.

## Как пользоваться

### Обычный push
Запусти:
PUSH_UPDATE.bat

Потом на GitHub:
Actions -> Build Release ZIP

Там появится artifact с архивом.

### Полноценный релиз
Запусти:
MAKE_RELEASE_TAG.bat

Это отправит тег `v...`.
После этого workflow `Release On Tag`:
- создаст Release
- прикрепит ZIP

## Что не попадет в ZIP
- .git
- .venv
- logs
- .env
- pyc / __pycache__

## Если Release не создался
Проверь:
1. tag начинается с v
2. workflow permissions = Read and write
3. Actions не выключены для репозитория
