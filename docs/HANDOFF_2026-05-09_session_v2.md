# SESSION HANDOFF — 2026-05-09 v2 (после Stage B/C/D работы)

**Last commits (newest first):**
- `39a5306` fix(supervisor): CREATE_BREAKAWAY_FROM_JOB
- `bf5a60e` feat: Stage B3/B4/C4/D2/D3
- `cdea3ab` feat: 6-task batch — supervisor stab + Stage B2/C2 + defensive
- `4d70804` docs: Stage B/C/D/E roadmap

---

## ⚡ Health-check (5 мин)

```bash
# Supervisor стабильность (ключевое — было сломано в начале этой сессии)
grep "Supervisor started\|tick=" logs/current/supervisor.log | tail -10
cat run/supervisor.pid    # должно быть = PID живого pythonw процесса

# Сервисы запущены?
grep -E "spike_alert\.start|pre_cascade\.start|regime_shadow\.start|test3_tpflat\.start" logs/app.log | tail -6

# Регулярные проверки
python tools/_dl_validate.py | tail -25
ls -la state/regime_shadow.jsonl state/test3_tpflat_paper.jsonl
```

**Что должно быть зелёным:**
- supervisor PID живёт >5 мин (tick≥10) и не рестартует каждые 2 мин
- 4 новых сервиса запущены: `spike_alert.start`, `test3_tpflat.start`, `regime_shadow.start`, `pre_cascade.start`
- `state/regime_shadow.jsonl` растёт каждые 5 мин
- `state/test3_tpflat_paper.jsonl` появляется при первом OPEN

---

## 📦 Что сделано в этой сессии (commits cdea3ab → 39a5306)

| TZ | Файлы | Тесты |
|---|---|---|
| XRP-fix | app_runner.py:179 | – |
| spike-defensive | services/spike_alert/ | 9 ✓ |
| test3-tpflat-sim | services/test3_tpflat_simulator/ | 6 ✓ |
| /bots_kpi | services/bots_kpi/ + telegram_runtime.py | 5 ✓ |
| Stage B2 — 3-asset confluence | services/setup_detector/multi_asset_confluence_v2.py | 7 ✓ |
| Stage C2 — confluence matrix | tools/_setup_correlation_matrix.py + docs/STRATEGY_CONFLUENCE_MATRIX.md | – |
| Stage B3 — regime shadow | services/regime_shadow/ | 9 ✓ |
| Stage B4 — pre-cascade alert | services/pre_cascade_alert/ | 11 ✓ |
| Stage C4 — walkfwd leaderboard | tools/_walkfwd_historical_setups.py + docs/STRATEGY_LEADERBOARD.md | – |
| Stage D2 — weekly cron | scripts/leaderboard_weekly.py | – |
| Stage D3 — P-15 auto-tuner | tools/_p15_auto_tuner.py | – |
| Supervisor stabilization | src/supervisor/daemon.py + bot7/__main__.py + scripts/keepalive_check.py | – |

Total: **47 unit tests + 11 services/tools + 3 docs**

---

## 🔬 Полезные находки

### Strategy Leaderboard (data/historical_setups_y1, 4-fold walkfwd)
- **STABLE:** `long_pdl_bounce` (PF=1.55, 3/4 folds positive)
- **OVERFIT:** `long_dump_reversal`, `short_pdh_rejection`, `short_rally_fade`,
  `short_overbought_fade`, `grid_booster`
- → **Решение к обсуждению с оператором:** отключить OVERFIT детекторы
  (4 SHORT + 1 grid) — все стабильно деградируют на свежих fold'ах

### Confluence Matrix
- **Лучший pair:** `long_dump_reversal + long_pdl_bounce` — N=425 co-fires,
  WR=42.8% vs 35.9/37.1% alone → +5.7 pp boost
- → **Идея для B5:** mega-setup detector — fire ТОЛЬКО когда оба agree

### P-15 Auto-tuner verdict (30d window)
- prod params (R=0.3, K=1.0, dd=3.0) дают +$3339 SHORT, +$1485 LONG за 30d
- лучший alternative: R=0.5, K=0.5, dd=3 — но N меньше, score ниже
- → **KEEP PROD** (auto-tuner подтверждает)

---

## 🚧 Stage E (не сделано — тяжёлые вычислительно)

### E1 — Genetic detector search
- Genome: RSI threshold, lookback, gate, indicator combo
- GA на 2y data ≈ сутки compute
- → **оставлено на отдельную сессию когда есть compute time**

### E2 — LLM regime narrator
- Раз в час GPT-4 принимает derived features + 6h history
- Пишет narrative в TG: «Range $80,200-$80,500, ОИ накапливается shorts...»
- → **требует API key выбора** + cost/usage обсуждения с оператором

---

## 🎯 Open questions

1. **OVERFIT детекторы** — отключить сейчас или подождать ещё одну walkfwd run для уверенности?
2. **TEST_3 TP-flat dry-run** — после 7 дней accumulation решение о migration GinArea
3. **regime_shadow** — после 30 дней посмотреть accuracy delta vs Classifier A,
   решение о switch DL R-* rules на B
4. **B5 — mega-setup detector** для лучшей confluence пары?

---

## 🚫 НЕ ДЕЛАТЬ

(те же 5 правил из v1 handoff: GinArea indicator vs trigger, не удалять много
PRIMARY rules сразу, не перезапускать вручную в начале сессии, не предлагать
"почистим дубли", не спрашивать "хочешь чтоб я сделал".)

Дополнительно:
6. **НЕ редактировать** `services/regime_red_green/rules.py` — auto-generated
   from `decision_tree.json`. Re-train через `runner.py train`.
7. **НЕ менять P-15 params** в `services/setup_detector/p15_rolling.py`
   без явного operator-go-ahead — auto-tuner verdict пока KEEP.
