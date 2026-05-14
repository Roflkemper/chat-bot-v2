# Аудит дублирующихся констант — 2026-05-14

_Сгенерирован скриптом, просканировано 959 .py файлов_

Всего уникальных пар (имя, значение): 1316, из них дублей в 2+ файлах: **218**

## Топ-30 дублирующихся констант

| # | Имя | Значение | Копий | Файлы |
|---|-----|----------|-------|-------|
| 1 | `ROOT` | `Path(__file__).resolve().parents[1]` | 137 | `bot7/__main__.py:22`<br>`collectors/main.py:22`<br>`core/tools/health_check.py:7`<br>`core/tools/reset_runtime_state.py:6`<br>`scripts/_dedup_dry_run_decisionlog.py:19`<br>...+132 |
| 2 | `ROOT` | `Path(__file__).resolve().parents[2]` | 37 | `services/backtest/walk_forward_t2mega.py:25`<br>`services/bitmex_account/poller.py:19`<br>`services/bots_kpi/builder.py:10`<br>`services/calibration/models.py:27`<br>`services/calibration/reconcile_v3.py:29`<br>...+32 |
| 3 | `DATA_1M` | `ROOT / "backtests" / "frozen" / "BTCU...` | 22 | `scripts/gc_block_coverage_check.py:31`<br>`scripts/p15_auto_tuner.py:33`<br>`tools/_backtest_cascade_ginarea_v3.py:38`<br>`tools/_backtest_cascade_ginarea_v4.py:38`<br>`tools/_backtest_cascade_grid.py:38`<br>...+17 |
| 4 | `N_FOLDS` | `4` | 21 | `tools/_a2_tick_edge_mining.py:51`<br>`tools/_backtest_cascade_grid.py:53`<br>`tools/_backtest_cascade_grid_v2.py:55`<br>`tools/_backtest_confluence.py:59`<br>`tools/_backtest_cross_asset_lead.py:61`<br>...+16 |
| 5 | `BASE_SIZE_USD` | `1000.0` | 11 | `tools/_backtest_confluence.py:61`<br>`tools/_backtest_cross_asset_lead.py:59`<br>`tools/_backtest_funding_extremes.py:60`<br>`tools/_backtest_funding_flip.py:65`<br>`tools/_backtest_p15_dd_cap_sweep.py:50`<br>...+6 |
| 6 | `LOOKBACK_DAYS` | `365` | 9 | `tools/_grid_intraday_backtest.py:34`<br>`tools/_h10_honest_backtest.py:36`<br>`tools/_h10_param_sweep.py:36`<br>`tools/_mega_cross_symbol.py:33`<br>`tools/_mega_quad_quintet.py:40`<br>...+4 |
| 7 | `LIQ_CSV` | `ROOT / "market_live" / "liquidations....` | 8 | `scripts/audit_paper_trader_filters.py:28`<br>`scripts/research_precascade_clustering.py:23`<br>`scripts/validate_liq_cluster_hitrate.py:23`<br>`services/cascade_alert/loop.py:16`<br>`services/paper_trader/audit_report.py:23`<br>...+3 |
| 8 | `TAKER_FEE_PCT` | `0.075` | 8 | `tools/_backtest_confluence.py:62`<br>`tools/_backtest_cross_asset_lead.py:60`<br>`tools/_backtest_funding_extremes.py:61`<br>`tools/_backtest_funding_flip.py:66`<br>`tools/_backtest_sb_pairs.py:36`<br>...+3 |
| 9 | `WINDOW_MIN` | `60` | 8 | `tools/_grid_coordinator_vs_detectors.py:47`<br>`tools/_mega_cross_symbol.py:34`<br>`tools/_mega_early_exit_gc.py:40`<br>`tools/_mega_quad_quintet.py:41`<br>`tools/_mega_setup_backtest.py:50`<br>...+3 |
| 10 | `DEDUP_HOURS` | `4` | 7 | `tools/_mega_adaptive_retune.py:40`<br>`tools/_mega_cross_symbol.py:35`<br>`tools/_mega_early_exit_gc.py:41`<br>`tools/_mega_quad_quintet.py:42`<br>`tools/_mega_setup_backtest.py:51`<br>...+2 |
| 11 | `ICT_PARQUET` | `ROOT / "data" / "ict_levels" / "BTCUS...` | 7 | `services/defensive_actions_research/runner.py:17`<br>`services/defensive_actions_research/v3_aggressive_widen.py:17`<br>`services/defensive_actions_research/v3_cross_check.py:21`<br>`services/defensive_actions_research/v4_disable_in.py:17`<br>`services/exhaustion_management_research/runner.py:17`<br>...+2 |
| 12 | `PARQUET` | `ROOT / "data" / "forecast_features" /...` | 7 | `scripts/research_archive/_forecast_calibration_diagnostic.py:24`<br>`scripts/research_archive/_hysteresis_calibration.py:26`<br>`scripts/research_archive/_regime_overlay_v2.py:23`<br>`scripts/research_archive/_regime_overlay_v2_1.py:27`<br>`scripts/research_archive/_regime_overlay_v3.py:35`<br>...+2 |
| 13 | `POLL_INTERVAL_SEC` | `60` | 7 | `services/bitmex_account/poller.py:23`<br>`services/cascade_alert/loop.py:19`<br>`services/decision_layer/telegram_emitter.py:49`<br>`services/pre_cascade_alert/liq_clustering.py:43`<br>`services/pre_cascade_alert/loop.py:27`<br>...+2 |
| 14 | `SIM_END` | `"2026-04-29T23:59:59+00:00"` | 7 | `services/calibration/models.py:32`<br>`services/coordinated_grid/grid_search.py:22`<br>`services/coordinated_grid/trim_analyzer.py:26`<br>`tools/_backtest_cascade_ginarea_v3.py:69`<br>`tools/_backtest_cascade_ginarea_v4.py:65`<br>...+2 |
| 15 | `SIM_START` | `"2025-05-01T00:00:00+00:00"` | 7 | `services/calibration/models.py:31`<br>`services/coordinated_grid/grid_search.py:21`<br>`services/coordinated_grid/trim_analyzer.py:25`<br>`tools/_backtest_cascade_ginarea_v3.py:68`<br>`tools/_backtest_cascade_ginarea_v4.py:64`<br>...+2 |
| 16 | `COOLDOWN_HOURS` | `4` | 6 | `services/defensive_actions_research/v3_aggressive_widen.py:30`<br>`services/defensive_actions_research/v4_disable_in.py:28`<br>`services/setup_detector/rsi_momentum_ga.py:52`<br>`tools/_backtest_confluence.py:58`<br>`tools/_backtest_cross_asset_lead.py:57`<br>...+1 |
| 17 | `FEE_BPS` | `5.0` | 6 | `tools/_backtest_dual_independent.py:33`<br>`tools/_backtest_dual_leg.py:36`<br>`tools/_backtest_p15_full.py:30`<br>`tools/_backtest_p15_honest.py:32`<br>`tools/_backtest_tp_autoupdate_vs_bag.py:38`<br>...+1 |
| 18 | `GC_SCORE_MIN` | `3` | 6 | `tools/_detectors_full_pipeline.py:45`<br>`tools/_grid_coordinator_vs_detectors.py:48`<br>`tools/_mega_short_v2_gc.py:48`<br>`tools/_p15_gc_confluence.py:41`<br>`tools/_p15_gc_per_trade.py:33`<br>...+1 |
| 19 | `LOOKBACK_DAYS` | `90` | 6 | `core/freeze_backtest_data.py:11`<br>`scripts/cross_asset_leadlag_1m.py:25`<br>`tools/_a2_tick_edge_mining.py:49`<br>`tools/_grid_coordinator_vs_detectors.py:46`<br>`tools/_night_grid_coordinator_research.py:46`<br>...+1 |
| 20 | `REGIME_NAME` | `{1: "MARKUP", -1: "MARKDOWN", 0: "RAN...` | 6 | `scripts/research_archive/_forecast_calibration_diagnostic.py:31`<br>`scripts/research_archive/_hysteresis_calibration.py:35`<br>`scripts/research_archive/_regime_overlay_v2.py:29`<br>`scripts/research_archive/_regime_overlay_v2_1.py:33`<br>`scripts/research_archive/_regime_overlay_v3.py:38`<br>...+1 |
| 21 | `SL_PCT` | `0.8` | 6 | `tools/_mega_cross_symbol.py:36`<br>`tools/_mega_early_exit_gc.py:42`<br>`tools/_mega_quad_quintet.py:43`<br>`tools/_mega_setup_backtest.py:52`<br>`tools/_mega_short_backtest.py:42`<br>...+1 |
| 22 | `TP1_RR` | `2.5` | 6 | `tools/_mega_cross_symbol.py:37`<br>`tools/_mega_early_exit_gc.py:43`<br>`tools/_mega_quad_quintet.py:44`<br>`tools/_mega_setup_backtest.py:53`<br>`tools/_mega_short_backtest.py:43`<br>...+1 |
| 23 | `TP2_RR` | `5.0` | 6 | `tools/_mega_cross_symbol.py:38`<br>`tools/_mega_early_exit_gc.py:44`<br>`tools/_mega_quad_quintet.py:45`<br>`tools/_mega_setup_backtest.py:54`<br>`tools/_mega_short_backtest.py:44`<br>...+1 |
| 24 | `DIRECTIONS` | `["both", "long_only", "short_only"]` | 5 | `tools/_backtest_cross_asset_lead.py:56`<br>`tools/_backtest_funding_extremes.py:57`<br>`tools/_backtest_funding_flip.py:62`<br>`tools/_backtest_volume_climax.py:59`<br>`tools/_backtest_volume_profile.py:43` |
| 25 | `FROZEN_1M` | `ROOT / "backtests" / "frozen" / "BTCU...` | 5 | `services/defensive_actions_research/runner.py:16`<br>`services/defensive_actions_research/v3_aggressive_widen.py:16`<br>`services/defensive_actions_research/v3_cross_check.py:20`<br>`services/defensive_actions_research/v4_disable_in.py:16`<br>`services/exhaustion_management_research/runner.py:16` |
| 26 | `MAKER_REBATE` | `-0.0125 / 100` | 5 | `tools/_backtest_detectors_honest.py:52`<br>`tools/_backtest_p15_dd_cap_sweep.py:39`<br>`tools/_backtest_p15_honest_v2.py:45`<br>`tools/_backtest_p15_hysteresis.py:49`<br>`tools/_backtest_p15_reentry_sweep.py:44` |
| 27 | `SETUPS_PATH` | `Path("state/setups.jsonl")` | 5 | `services/advisor/advisor_v2.py:23`<br>`services/advisor/daily_report.py:27`<br>`services/advisor/morning_brief.py:28`<br>`services/advisor/setups_15m.py:22`<br>`services/paper_trader/loop.py:32` |
| 28 | `YEAR_END` | `pd.Timestamp("2026-04-29T23:59:00Z")` | 5 | `services/defensive_actions_research/runner.py:21`<br>`services/defensive_actions_research/v3_aggressive_widen.py:21`<br>`services/defensive_actions_research/v3_cross_check.py:40`<br>`services/defensive_actions_research/v4_disable_in.py:21`<br>`services/exhaustion_management_research/runner.py:21` |
| 29 | `YEAR_START` | `pd.Timestamp("2025-05-01T00:00:00Z")` | 5 | `services/defensive_actions_research/runner.py:20`<br>`services/defensive_actions_research/v3_aggressive_widen.py:20`<br>`services/defensive_actions_research/v3_cross_check.py:39`<br>`services/defensive_actions_research/v4_disable_in.py:20`<br>`services/exhaustion_management_research/runner.py:20` |
| 30 | `ANALOG_JSON` | `Path("docs/ANALYSIS/_uptrend_analog_s...` | 4 | `scripts/research_archive/_oi_deep_dive.py:10`<br>`scripts/research_archive/_oi_deep_dive_cc.py:25`<br>`scripts/research_archive/_short_exit_multifactor.py:35`<br>`scripts/research_archive/_short_exit_options_analysis.py:11` |

## Рекомендация

Топ дублей по приоритету для рефакторинга:
1. **Numeric thresholds** (порядка 0.5-15) — вынести в `core/constants.py` или `config.py`
2. **String tags** (типа 'long_multi_divergence', 'trend_down') — уже есть `services/common/humanize.py`, дополнить enum
3. **Path-prefixes** (state/, frozen/) — вынести в `core/paths.py`

Файл сгенерирован автоматически. Перегенерация: `python scripts/audit_dup_constants.py`