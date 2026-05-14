# PROJECT MANIFEST — чат бот версия 2

## Миссия проекта
Сделать трейдерский инструмент для ручной торговли и сеточных ботов, который понимает рынок, даёт чёткие действия и помогает зарабатывать.

## Ключевой фокус
- ликвидность
- ликвидации
- реакция цены на блоки
- fake move
- impulse / continuation
- grid logic
- trader-oriented output

## Неприкосновенные правила
- не писать код в чат без прямого запроса
- отдавать только готовые ZIP-решения
- перед выдачей проверять архив на целостность, непустоту и работоспособность
- работать поверх последней актуальной версии проекта
- не ломать уже согласованные блоки
- не возвращать старую legacy-логику
- Telegram-выводы должны быть понятными, на русском, без мусора

## Архитектурный стандарт
Pipeline:
data → features → context → strategies → decision → execution → render

Слои:
1. Market Data Layer
2. Feature Layer
3. Context Layer
4. Strategy Layer
5. Decision Layer
6. Execution Layer
7. Presentation Layer
8. State & Learning Layer
9. Observability Layer

## Текущий статус
Regression Shield внедрён и проходит зелёный прогон: 44 passed.
Regression Shield закреплён на уровне commit/push/release.
Cleanup base выполнен: корень репозитория очищен, история вынесена в docs/history/, README/CHANGELOG/NEXT_CHAT_PROMPT приведены в рабочее состояние.

- Git/release flow: single-owner mode, local branch is source of truth, push via force-with-lease, no pull --rebase.

## Следующий этап
1. Держать Regression Shield зелёным перед каждым изменением.
2. Дальше делать только согласованный следующий функциональный этап поверх cleanup base.
3. Не возвращать мусор в корень репозитория: release notes, архивные чеклисты и служебные заметки складывать в docs/history/.
4. Любой новый релиз обязан сохранять стабильный release-контур: tests -> manifest -> ZIP -> verify.

## Правила релизов
Каждый релиз обязан обновлять:
- VERSION.txt
- CHANGELOG.md
- PROJECT_MANIFEST.md
- NEXT_CHAT_PROMPT.txt

Если PROJECT_MANIFEST.md не обновлён — релиз считается неполным.

## Короткий контекст для нового чата
- Проект: «чат бот версия 2»
- Работать только поверх последней версии проекта
- Код в чат не писать без прямого запроса
- Отдавать только готовые проверенные ZIP-решения
- PROJECT_MANIFEST.md считается главным файлом-источником истины по проекту
