# state_first_protocol

**Trigger:** start of any new chat session involving Grid Orchestrator; any task involving project state, positions, bots, performance, live trading decisions; any request for action report, advise, risk analysis, liq distances.

---

## Rule: read state before asking operator

ПЕРЕД тем как задавать оператору вопросы про числа из state:

1. Запросить через Code: `python scripts/state_snapshot.py` (или прочитать `docs/STATE/state_latest.json` если он не старше 15 минут)
2. Прочитать markdown отчёт `docs/STATE/CURRENT_STATE_latest.md`
3. Прочитать `docs/HANDOFF_<latest>.md`
4. Прочитать `docs/STATE/QUEUE.md`
5. ТОЛЬКО ПОСЛЕ этого задавать вопросы — и только о том, чего нет в state

## Forbidden (есть в state — не спрашивать у оператора)

- Параметры ботов (есть в snapshots.csv → state)
- Текущая позиция / liq / unrealized (есть в snapshots.csv → state)
- AGM за последние сутки (есть в bot_manager_state.json → state)
- Содержимое HANDOFF — читать через Code, не спрашивать

## Allowed to ask operator

- Намерения и приоритеты ("гасить ли LONG-D?", "стартуем с A1 или A2?")
- Manual positions если tracker не ведётся (manual_positions: not_tracked в state)
- Торговые решения, выбор между альтернативами

## Trader-first reminder

Этот skill = (в) защита капитала. Совет на устаревших данных может стоить депозита.
Freshness порог: state_latest.json возраст > 15 мин → перегенерировать перед анализом.
