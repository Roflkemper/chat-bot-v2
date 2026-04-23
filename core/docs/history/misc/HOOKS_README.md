# Git hooks — Regression Shield

## Что делают
- `pre-commit` запускает `python -B -m pytest tests -q`
- `pre-push` запускает `python -B -m pytest tests -q`
- если есть хотя бы один failed тест, commit/push блокируется

## Как включить
Запусти:

```bat
INSTALL_GIT_HOOKS.bat
```

## Как проверить
Запусти:

```bat
VERIFY_GIT_HOOKS.bat
```

Ожидаемый результат:

```text
[OK] core.hooksPath=.githooks
```
