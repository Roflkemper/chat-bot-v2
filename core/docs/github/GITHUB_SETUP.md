# GitHub setup for private repo

Репозиторий:
- `https://github.com/Roflkemper/chat-bot-v2`
- тип: private

## Рекомендуемый первый пуш
Открой терминал в корне проекта и выполни:

```bash
git init
git branch -M main
git add .
git commit -m "V17.7.1 GitHub integration pack"
git remote add origin https://github.com/Roflkemper/chat-bot-v2.git
git push -u origin main
```

## Рекомендуемая схема дальше
```bash
git checkout -b dev
# работа над следующим релизом
# после проверки:
git checkout main
git merge dev
git tag v17.7.1
git push origin main --tags
```

## Что обязательно проверить перед первым push
- в проекте нет `.env`
- в проекте нет токенов Telegram
- в проекте нет `bot_local_config.json`
- в проекте нет логов и runtime state

## Как выпускать релиз
1. Обновить `VERSION.txt`
2. Обновить `CHANGELOG.md`
3. Добавить release notes
4. Сделать commit
5. Создать tag
6. Прикрепить ZIP к GitHub Release вручную

## Минимальная модель веток
- `main` — стабильная
- `dev` — рабочая

## Не делать сейчас
- не включать секреты в GitHub Secrets без необходимости
- не тащить CI/CD
- не делать автодеплой
- не хранить боевые ZIP внутри репозитория
