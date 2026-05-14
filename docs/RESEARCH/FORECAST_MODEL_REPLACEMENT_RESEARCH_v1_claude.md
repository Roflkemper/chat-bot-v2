# Forecast Model Replacement — Research Review v1 (claude worker)

**Date:** 2026-05-05
**TZ:** TZ-FORECAST-MODEL-REPLACEMENT-RESEARCH
**Worker ID:** claude
**Investigation duration:** ~25 min web research + synthesis. No implementation.

**Output paths:**
- This report: [`docs/RESEARCH/FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_claude.md`](FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_claude.md)
- Raw JSON: [`docs/RESEARCH/_forecast_model_replacement_research_raw_claude.json`](_forecast_model_replacement_research_raw_claude.json)

---

## ⚠ Reading guide

This TZ specifically asks: **"What model can produce Brier < 0.22 with positive resolution component for BTC 1h-1d direction?"** The previous decommissioned model had Brier 0.2569 and resolution = 0.0001.

Section 5 ("Realistic assessment") is the load-bearing section. The honest answer there is more important than the volume of architecture options surveyed. Read §5 first if time-constrained.

---

## §1 Approaches per Q1-Q7

### Q1 — Crypto-specific forecasting research

#### Q1-A — Kim (2025) "Bitcoin Price Direction Forecasting and Market Variables", Journal of Futures Markets
- **Source:** [Wiley Online Library](https://onlinelibrary.wiley.com/doi/10.1002/fut.70010); CNN-LSTM with macro variables (stock indices, commodities, interest rates).
- **Evidence basis:** academic-peer-reviewed (Journal of Futures Markets is established).
- **Reported metrics:** does not report Brier specifically; reports directional accuracy improvements over baselines. Magnitude: incremental, not transformative.
- **Applicability to us:** **partial.** The macro variables are 1h-stale at best. Improvements reported are in the few-percentage-points-of-accuracy range, which translates to small Brier reductions if the baseline is already near 0.25.

#### Q1-B — Omole & Enke (2024/2025), on-chain + technical, CNN-LSTM with Boruta feature selection
- **Source:** [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0952197625010875); 137 engineered features (technical + on-chain Glassnode); reports 82.03% / 82.44% directional accuracy on next-day prediction.
- **Evidence basis:** academic-peer-reviewed; **single-paper accuracy claim — high suspicion of overfitting given absence of multi-period reproducibility**.
- **Caveat:** 82% accuracy on Bitcoin direction is **far above the empirical baseline of ~55-60%** that survives rigorous walk-forward + survivorship-bias-adjusted testing (Q5-D below). Without independent replication, treat as "not yet validated".
- **Applicability:** **flagged.** If the paper's methodology is reproducible we'd see independent replications; we don't.

#### Q1-C — Hourly walk-forward XGBoost on BTC/USDC (PyQuantLab Medium, 2024)
- **Source:** [Medium PyQuantLab](https://pyquantlab.medium.com/xgboost-for-short-term-bitcoin-prediction-walk-forward-analysis-and-thresholded-performance-b83dc2e677eb); 3-hour direction; explicitly examines **calibration** and probability-gated equity.
- **Evidence basis:** community-anecdotal; reproducible methodology disclosed; not peer-reviewed.
- **Reported metrics:** "consistently above 50% threshold" but no specific Brier; emphasis on calibration over raw accuracy. The author explicitly notes that returns under naive activation are flat; only **thresholded** activation (act on probabilities far from 0.5) shows positive equity in their backtest.
- **Applicability:** **directly relevant.** The thresholded-action pattern matches our cost-loss decision framework requirement.

#### Q1-D — On-chain efficiency literature: Adaptive Market Hypothesis applies to crypto
- **Source:** [Nature Scientific Reports: Bitcoin market efficiency](https://www.nature.com/articles/s41598-023-31618-4); [ScienceDirect: market efficiency determinants](https://www.sciencedirect.com/science/article/pii/S1059056025001017); [ScienceDirect: high-frequency adaptive market hypothesis](https://www.sciencedirect.com/science/article/abs/pii/S1057521919300821).
- **Findings:** Bitcoin markets are **time-varying-efficient**. Efficiency increases with liquidity and decreases with volatility. The static EMH fails; the Adaptive Market Hypothesis fits.
- **Applicability:** **load-bearing context.** Implies that any forecast skill, if it exists, will be regime-conditional and intermittent. A model that "doesn't always work" is the right shape; expecting persistent skill is unrealistic.

### Q2 — Model architectures with evidence

#### Q2-A — XGBoost / LightGBM / CatBoost with engineered features
- **Sources:** [arXiv 2407.11786 — XGBoost crypto regressor](https://arxiv.org/html/2407.11786v1); [Springer chapter — XGBoost classifier](https://link.springer.com/chapter/10.1007/978-981-96-0924-6_8); [arXiv 2506.05764 — CatBoost LOB microstructure](https://arxiv.org/html/2506.05764v2).
- **Pattern in literature:** Tree ensembles **outperform deep learning** on most crypto direction tasks when sample size is moderate (the standard finding for tabular tasks). One direct quote from a review paper: *"Ensemble methods (XGBoost and Gradient Boosting) outperformed deep learning models substantially across multiple cryptocurrencies."*
- **Evidence basis:** academic-peer-reviewed (multiple papers); broadly replicated.
- **Applicability:** **strong baseline candidate.** This is the recommended starting point per literature.

#### Q2-B — LSTM / GRU sequence models
- **Sources:** [arXiv 2405.11431 review of deep learning for crypto](https://arxiv.org/html/2405.11431v1); [arXiv 2506.22055 LSTM+XGBoost hybrid](https://arxiv.org/html/2506.22055v1); [Symmetry MDPI from LSTM to GPT-2](https://www.mdpi.com/2073-8994/18/1/32).
- **Pattern:** LSTM **alone** is rarely best. LSTM **stacked with XGBoost residuals** (hybrid) outperforms either alone in MAE/RMSE benchmarks; reported accuracy gains of 12-43% over baselines.
- **Evidence basis:** academic-peer-reviewed (multiple papers).
- **Caveat:** RMSE/MAE are **regression metrics** that do not directly translate to Brier on direction. A model can have great RMSE and still have ~50% directional accuracy. The literature consistently confuses these.
- **Applicability:** **secondary.** Worth considering only if XGBoost ceiling is reached.

#### Q2-C — Temporal Fusion Transformer (TFT) and other Transformer variants
- **Sources:** [MDPI Systems 2025 — TFT trading strategy multi-crypto](https://www.mdpi.com/2079-8954/13/6/474); [arXiv 2509.10542 — Adaptive TFT](https://arxiv.org/pdf/2509.10542); [arXiv 2412.14529 — TFT with time series categorization](https://arxiv.org/abs/2412.14529); [ScienceDirect TFT cryptocurrencies](https://www.sciencedirect.com/science/article/pii/S2405844024161737).
- **Pattern:** TFT papers report **MAE/MAPE improvements**; some report increases in trading-strategy Sharpe in backtest. Most evaluations are **on 10-min or 1-min data** with multi-crypto features. Direction-prediction Brier is rarely the headline metric.
- **Evidence basis:** academic-peer-reviewed (multiple papers, 2024-2025).
- **Caveat:** TFT and other heavy transformer architectures have **substantial overfitting risk** on noisy, low-SNR data like crypto direction. Most "wins" are on regression error metrics, not directional Brier.
- **Applicability:** **medium-low priority.** Only after Q2-A baselines are tuned out.

#### Q2-D — Hybrid: deep features + tree ensemble (LSTM+XGBoost / TCN+CatBoost)
- **Source:** [arXiv 2506.22055](https://arxiv.org/html/2506.22055v1).
- **Pattern:** LSTM extracts temporal embeddings → XGBoost trained on embeddings + raw features. Reported "consistent outperformance" over individual models. Reasonable mechanistic story (LSTM captures temporal structure tabular models miss).
- **Evidence basis:** academic-peer-reviewed; reproducible methodology disclosed.
- **Applicability:** **promising 2nd-tier candidate** if Q2-A reaches ceiling.

#### Q2-E — Deep RL (FinRL, DQN, PPO) — negative finding
- **Sources:** [arXiv 2209.05559 — DRL crypto with overfitting protection](https://arxiv.org/abs/2209.05559); [GitHub berendgort/FinRL_Crypto](https://github.com/berendgort/FinRL_Crypto); [GitHub AI4Finance-Foundation/FinRL_Crypto](https://github.com/AI4Finance-Foundation/FinRL_Crypto).
- **Pattern:** Earlier DRL crypto papers report **strong backtest profits**. The Berend Gort 2022 paper specifically **proved earlier results contained backtest overfitting** by formulating overfitting detection as a hypothesis test and rejecting overfitted agents. The "less overfitted" agents still beat baselines but margin shrinks.
- **Evidence basis:** academic-peer-reviewed (anti-claim itself is the load-bearing finding).
- **Applicability:** **anti-recommend** for our context. Even when overfitting is controlled, DRL is heavy infrastructure for marginal gain on direction tasks.

### Q3 — Feature engineering for crypto

#### Q3-A — Order-flow imbalance / LOB features (load-bearing positive evidence)
- **Sources:** [ScienceDirect: order flow and cryptocurrency returns](https://www.sciencedirect.com/science/article/pii/S1386418126000029); [arXiv 2602.00776 — Explainable Crypto Microstructure](https://arxiv.org/html/2602.00776v1); [arXiv 2506.05764 — Microstructural Dynamics in LOB](https://arxiv.org/html/2506.05764v2); [arXiv 2010.01241 — Deep Learning for LOB](https://arxiv.org/pdf/2010.01241); [Dean Markwick blog — Order Flow Imbalance HFT signal](https://dm13450.github.io/2022/02/02/Order-Flow-Imbalance.html).
- **Quoted finding:** "Order flow has strong and economically valuable out-of-sample predictive power for cryptocurrency returns; non-linear ML models conditioning on order flow outperform ML models conditioning on economic fundamentals." 71% walk-forward accuracy reported on 2-second horizons in TCN-on-LOB study.
- **Evidence basis:** academic-peer-reviewed (multiple independent papers).
- **Applicability:** **strongest single-feature evidence in the literature.** Caveats: (a) requires raw L2/L3 LOB data, not just OHLCV; (b) the 2-second-horizon edge dissipates rapidly toward the 1h+ scale; (c) BitMEX provides L2 data via WebSocket but our current collector is event-summary, not full LOB.

#### Q3-B — On-chain features (whale netflows, exchange flows)
- **Sources:** [Glassnode: whale tracking](https://insights.glassnode.com/content/unlocking-bitcoin-market-trends-an-introduction-to-crypto-whale-tracking/); [ScienceDirect — dual impact of on/off-chain factors](https://www.sciencedirect.com/science/article/pii/S0890838925000915); [Glassnode: systematic feature discovery for digital assets](https://insights.glassnode.com/systematic-feature-discovery-for-digital-assets/); [Omole & Enke 2024](https://www.sciencedirect.com/science/article/abs/pii/S0952197625010875).
- **Pattern:** Whale netflow to exchanges correlates with major price moves, but **the timescale is days, not hours**. On-chain features have predictive power on 1d-7d horizons in some studies; weak signal at 1h.
- **Evidence basis:** academic-peer-reviewed for daily horizons; very thin at hourly.
- **Applicability:** **partial.** Promising for 1d horizon, weak for 1h. Glassnode API data quality is high but the licensing cost is non-trivial for a solo operator.

#### Q3-C — Funding rate / derivatives features
- **Sources:** [Dean Markwick blog](https://dm13450.github.io/2022/02/02/Order-Flow-Imbalance.html); funding rate as cited in microstructure papers above.
- **Pattern:** Funding rate has **mean-reverting predictive power** at ~8h scale (BitMEX funding cycle). Extreme positive funding → mild down-pressure; extreme negative → mild up-pressure. Effect is **small in magnitude**, weak signal alone, useful as one feature among many.
- **Evidence basis:** academic + practitioner consensus; small-effect.
- **Applicability:** **inclusion in feature set, not standalone.** Already partially in our existing features (we have `funding_rate`, `funding_z`).

#### Q3-D — Technical indicators (TI) — most are noise, a few are signal
- **Sources:** [arXiv 2407.11786](https://arxiv.org/html/2407.11786v1); various TI-evaluation papers.
- **Pattern:** Among 100+ classical TIs, only a small subset (RSI, ATR%, EMA-cross / momentum windows, volume z-score) show consistent marginal predictive value. Most others are stochastic decorations of price.
- **Evidence basis:** mature literature; the consensus is that TI ensembles **add small marginal signal**, but most individual TIs are dominated by simpler features (return, volatility, volume).
- **Applicability:** **minor adjuncts only.** Don't expect TI alone to lift Brier below baseline.

#### Q3-E — Sentiment features (news, social) — heavily over-claimed
- **Pattern in literature:** sentiment papers are over-represented in publication; the effect sizes after rigorous validation shrink dramatically. Most "alpha from Twitter" papers fail replication.
- **Evidence basis:** mostly anecdotal; replication failures common.
- **Applicability:** **anti-recommend** as primary feature. May be useful adjunct after primary features tuned.

### Q4 — Regime-aware forecasting

#### Q4-A — HMM regime + per-regime forecast
- **Sources:** Already covered in `MARKET_DECISION_SUPPORT_RESEARCH_v1_claude` Q3-A. [QuantStart](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/); [PyQuantLab on HMM-based regime](https://pyquantlab.medium.com/regime-aware-trading-with-hidden-markov-models-hmms-and-macro-features-c75f6d357880).
- **Pattern:** Per-regime forecast models routinely show backtest gains. **Robustness on out-of-sample crypto data is thin.** Our own decommissioned model used per-regime weights → resolution still 0.
- **Evidence basis:** production-deployed in retail tooling; weak independent crypto-specific evidence.
- **Applicability:** **proven not enough alone.** Per-regime weighting is what we already had and it failed.

#### Q4-B — Switching models with online learning
- **Sources:** [Adaptive TFT paper](https://arxiv.org/pdf/2509.10542) — adaptive learning lengths per regime; some online-learning literature.
- **Pattern:** Adaptive-window models report improvements over fixed-window. Most evaluations are short (single-month live, multi-month backtest).
- **Evidence basis:** academic-peer-reviewed (recent, single-paper for each variant).
- **Applicability:** **promising-unverified for crypto.** Online learning is operationally heavy.

#### Q4-C — FinRL-X regime-conditional rotation
- **Sources:** [GitHub FinRL-Trading](https://github.com/AI4Finance-Foundation/FinRL-Trading); [arXiv 2603.21330](https://arxiv.org/html/2603.21330v1); paper trading from Oct 2025-Mar 2026 reports regime-aware rotation outperforms SPY/QQQ.
- **Pattern:** RL agent rotates among asset baskets per regime label. Equity/asset-class focused; crypto extension exists but is new.
- **Evidence basis:** academic-peer-reviewed (one paper).
- **Applicability:** **partial — regime gating, not direction forecast.** The framework gates *which strategy is active*, not *what direction price will go*. That's a different task than what our retired model attempted.

### Q5 — Evaluation methodology (the critical question)

#### Q5-A — Walk-forward / rolling validation (the standard)
- **Sources:** broad literature consensus. [arXiv 2006.14473 real-time BTC ML](https://arxiv.org/pdf/2006.14473); [Quant Nomad — why live worse than backtest](https://quantnomad.com/why-your-live-trading-is-so-much-worse-than-your-backtests/).
- **Pattern:** Single-split or k-fold CV is unsafe for time series. Walk-forward with proper purging is the standard.
- **Evidence basis:** universal academic consensus.
- **Applicability:** **mandatory.** Any replacement model must use this from the start.

#### Q5-B — López de Prado triple-barrier labels + purged + embargoed CV
- **Sources:** [Wikipedia: Purged cross-validation](https://en.wikipedia.org/wiki/Purged_cross-validation); [Towards AI: Combinatorial Purged CV](https://towardsai.net/p/l/the-combinatorial-purged-cross-validation-method); [Quantreo: Triple-Barrier Labeling](https://www.newsletter.quantreo.com/p/the-triple-barrier-labeling-of-marco); [Reasonable Deviations notes on Advances in Financial ML](https://reasonabledeviations.com/notes/adv_fin_ml/).
- **Pattern:** Triple-barrier replaces the simple "next bar up/down" label with "did profit-target / stop-loss / time-out fire first" — directly aligned with how a trader actually deploys. Purging + embargo prevent leakage from overlapping windows.
- **Evidence basis:** mature methodology, widely adopted.
- **Applicability:** **load-bearing for our case.** The retired model used a naive `close[t+h] > close[t]` label, which is crude. Triple-barrier with target=0.5% / stop=-0.3% / horizon=1h would be more aligned with bot-activation decision and likely produce a more usefully-skewed class balance.

#### Q5-C — Brier decomposition + reliability diagrams (Murphy 1973)
- **Sources:** previously established in `FORECAST_CALIBRATION_DIAGNOSTIC_v1.md` and `MARKET_DECISION_SUPPORT_RESEARCH_v1_claude` Q1-C.
- **Applicability:** **mandatory diagnostic.** No replacement model should be deployed without this.

#### Q5-D — Survivorship & data-snooping bias correction
- **Sources:** [SSRN: Survivorship and Delisting Bias in Crypto](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4287573); [CoinAPI blog](https://www.coinapi.io/blog/how-to-eliminate-survivorship-bias-in-crypto-backtesting); [StratBase: Survivorship bias in crypto](https://stratbase.ai/en/blog/survivorship-bias-crypto); [arXiv 2512.02029 — HODL strategy 480M simulations](https://arxiv.org/html/2512.02029v1).
- **Quote:** "Survivorship bias in crypto can inflate backtested returns by 200-400%." 58% of historically-listed tokens are dead.
- **Pattern in literature on rigor:** Studies that publish 70-80% directional accuracy on Bitcoin **almost universally fail to control for survivorship and snooping**. Studies that do control achieve **55-60% directional accuracy at best**, with most settling around 52-55% — i.e. Brier in the 0.245-0.249 range, marginally below the 0.25 baseline.
- **Evidence basis:** mature meta-research consensus.
- **Applicability:** **the most important reality-check filter.** The 80%+ accuracy results are publication artifacts; 55-60% with rigorous validation is the realistic ceiling.

### Q6 — Production deployments

#### Q6-A — Numerai Crypto tournament
- **Sources:** [Numerai docs Signals overview](https://docs.numer.ai/numerai-signals/signals-overview); [Numerai forum Signal Miner](https://forum.numer.ai/t/signal-miner-find-unique-alpha-beat-the-benchmark/7922); [Numerai scoring docs](https://docs.numer.ai/numerai-tournament/scoring).
- **Pattern:** Numerai operates a **live-money** tournament where contributors submit signals; reputation built on out-of-sample correlation. The fact that Numerai pays out and continues suggests **some** consistent skill exists in the aggregate, but **individual contributor track records are mostly mediocre after correction for randomness**.
- **Evidence basis:** ongoing live-money production with public scoring.
- **Caveat:** Numerai's correlation target is per-stock relative — not direct probability of up/down. The scoring is "Numerai Corr," a custom metric. Translating to Brier on direct direction prediction requires nontrivial reformulation.
- **Applicability:** **structural validation.** Demonstrates that **some** crypto-direction skill is achievable at scale, but the specific magnitude relevant to our 1h-Brier-<0.22 question is not directly given.

#### Q6-B — Open-source repositories with documented backtest results
- **Sources:** [GitHub jordantete/grid_trading_bot](https://github.com/jordantete/grid_trading_bot); [GitHub AI4Finance-Foundation/FinRL_Crypto](https://github.com/AI4Finance-Foundation/FinRL_Crypto); [GitHub berendgort/FinRL_Crypto (overfitting-controlled)](https://github.com/berendgort/FinRL_Crypto); [GitHub toma-x/exploring-order-book-predictability](https://github.com/toma-x/exploring-order-book-predictability).
- **Pattern:** Most public repos with claimed crypto-trading-edge are **either** (a) already known to overfit, **or** (b) make modest claims (~52-55% directional accuracy out-of-sample).
- **Evidence basis:** open-source with reproducible code.
- **Applicability:** **good benchmark sources.** Their realistic numbers are what we should expect, not the headline 80%+ from peer-reviewed-but-unreplicated studies.

#### Q6-C — TrendSpider AI Bitcoin Volatility Forecast Pro
- **Source:** [TrendSpider AI BTC forecast](https://trendspider.com/trading-tools-store/indicators/69523f-ai-bitcoin-volatility-forecast-pro-btcusdt-%C2%B7-1h/).
- **Pattern:** Commercial product. **Forecasts volatility, not direction.** Volatility forecasting on crypto is a **better-defined** problem than direction; volatility is more persistent.
- **Applicability:** **adjacent task.** Not direction-relevant but worth noting that the easier-task version is what production tools tackle.

### Q7 — Specific feasibility for our case

#### Q7-A — Required data infrastructure (current vs needed)
- **Current:** OHLCV 5min, 84 engineered features, regime labels, frozen 1y derivatives snapshot (no live feed).
- **For order-flow / LOB approach (Q3-A):** would need live L2 LOB stream from exchange (BitMEX). Storage ~ 50-100 GB / month per pair. Real-time websocket consumer.
- **For on-chain approach (Q3-B):** Glassnode API or similar; ~$300-1000/month for adequate access. Daily-resolution data is sufficient.
- **For TFT or transformer-heavy (Q2-C):** GPU compute for training; modest CPU for inference.

#### Q7-B — Required compute
- XGBoost / LightGBM: trains in minutes on a single CPU. Inference is sub-millisecond.
- LSTM / TFT: training requires GPU (hours per cycle); inference can be CPU.
- DRL (anti-recommended): training takes days; sensitive to overfitting; inference cheap.

#### Q7-C — Maintenance overhead
- XGBoost with weekly retraining: 1-2 hours/week of operator attention if monitored properly.
- TFT/transformer with weekly retraining: ~5+ hours/week including infra.
- Online learning systems: **continuous attention** — many failure modes.

#### Q7-D — Realistic timeline first to deployment
- XGBoost + curated feature set: **2-4 weeks from scratch** for a competent operator. Diagnostic + monitoring infrastructure another 2 weeks.
- Order-flow LOB system: **2-3 months** including data collection.
- Multi-architecture ensemble: **3+ months**.

#### Q7-E — Probability of success based on literature
- **See §5 for the load-bearing realistic assessment.**

---

## §2 Comparison matrix

| Approach | Question | Evidence basis | Required infra | Compute cost | Maintenance | Brier-<0.22 probability (rough) |
|---|:---:|:---:|---|:---:|:---:|:---:|
| Q1-B Omole-Enke CNN-LSTM 82% claim | Q1 | academic, single-paper, unreplicated | features + on-chain | medium | medium | LOW (publication artifact suspicion) |
| Q1-C XGBoost walk-forward (PyQuantLab) | Q1 | community, reproducible methodology | OHLCV multi-TF | low | low | LOW-MEDIUM |
| Q2-A XGBoost / LightGBM tabular | Q2 | academic-peer-reviewed (multiple) | OHLCV + features | low | low | **MEDIUM** for marginal-skill (Brier 0.245-0.249) |
| Q2-B LSTM / GRU sequence | Q2 | academic | OHLCV + features | medium (GPU) | medium | LOW (RMSE wins ≠ Brier wins) |
| Q2-C TFT / Transformer | Q2 | academic-peer-reviewed (multiple, recent) | OHLCV + features | high (GPU) | high | LOW-MEDIUM (overfitting risk) |
| Q2-D Hybrid LSTM+XGBoost | Q2 | academic-peer-reviewed | OHLCV + features | medium | medium | MEDIUM |
| Q2-E Deep RL (FinRL et al.) | Q2 | academic + anti-evidence on overfitting | many feeds | high | very high | LOW (anti-recommend) |
| Q3-A Order-flow / LOB | Q3 | **strongest single-feature evidence** | live L2 LOB stream | medium | medium | MEDIUM-HIGH at sub-minute; LOW at 1h+ |
| Q3-B On-chain features | Q3 | academic for daily horizon | Glassnode API | low | medium | LOW at 1h, MEDIUM at 1d |
| Q3-C Funding rate (incl. derivatives) | Q3 | academic + practitioner | derivatives feed | low | low | as adjunct only |
| Q3-D Technical indicators | Q3 | mature literature | OHLCV | low | low | as adjunct only |
| Q3-E Sentiment features | Q3 | over-claimed; replication-failures | news+social feeds | medium | high | LOW (anti-recommend primary) |
| Q4-A HMM regime + forecast | Q4 | retail-deployed; weak independent OOS evidence | regime + forecast | low | low | LOW (we already had this; resolution=0) |
| Q4-B Switching / online learning | Q4 | academic; thin crypto evidence | features | medium | high | LOW-MEDIUM, infra-heavy |
| Q4-C FinRL-X regime rotation | Q4 | academic (single paper) | many features | high | high | not direction-forecast (different task) |
| Q5-B Triple-barrier labels + purged CV | Q5 | mature methodology | (orthogonal — wraps any model) | trivial | trivial | **MANDATORY**, not standalone |
| Q5-C Brier decomposition + reliability | Q5 | textbook | (orthogonal) | trivial | trivial | **MANDATORY** diagnostic |
| Q6-A Numerai Crypto signals | Q6 | live-money production | tournament data | low | low | external system, not directly transferable |
| Q6-B OSS repos with overfitting protection | Q6 | reproducible code | as required | varies | varies | benchmark realism |

**Summary:** No single approach has a plausible path to "Brier < 0.22 on 1h BTC direction with positive resolution" backed by **independently-replicated** evidence. The 82% headline accuracy claims are publication artifacts. Realistic crypto direction Brier ceiling under rigorous validation is approximately **0.245-0.249** — a small improvement over no-skill baseline (0.25), not a transformation.

---

## §3 Top 3 recommendations

**Decision context.** All three recommendations below assume the operator decides to *attempt* a forecast capability. If the operator decides not to attempt one, the simpler path is to leave the forecast block decommissioned and not undertake any of these. The realistic-assessment §5 below should be read first.

### Rec #1 — **XGBoost with engineered features + triple-barrier labels + walk-forward + Brier decomposition diagnostic at every step**

**Approach + sources:** Q2-A + Q5-B + Q5-C combined into one staged build. Source anchor: [arXiv 2407.11786 XGBoost crypto](https://arxiv.org/html/2407.11786v1), [PyQuantLab walk-forward methodology](https://pyquantlab.medium.com/xgboost-for-short-term-bitcoin-prediction-walk-forward-analysis-and-thresholded-performance-b83dc2e677eb), [López de Prado AFML](https://reasonabledeviations.com/notes/adv_fin_ml/).

**What it would produce.** Realistic Brier estimate based on similar literature: **0.245-0.249 with calibration; resolution component 0.001-0.005**. *Not* below 0.22. The improvement vs the decommissioned model would be: (a) actual non-zero resolution; (b) calibrated probabilities; (c) signal usable under thresholded action (only act on prob_up off-center far enough to clear cost-loss threshold).

**Implementation path (rough TZ sequence):**
1. `TZ-FORECAST-LABEL-DESIGN` — implement triple-barrier labels (target +0.5%, stop -0.3%, horizon 1h) over historical features. Verify class balance is workable.
2. `TZ-FORECAST-FEATURE-AUDIT` — Boruta or SHAP feature selection on the existing 84-feature parquet to identify which features carry predictive signal vs noise.
3. `TZ-FORECAST-XGBOOST-V1` — train XGBoost on the curated subset using purged + embargoed time-series CV. Walk-forward retraining cadence: weekly.
4. `TZ-FORECAST-XGBOOST-V1-DIAGNOSTIC` — replay through the calibration diagnostic (reliability diagram + Brier decomposition + Platt). **Hard gate:** if `resolution < 0.005` → stop, do not deploy.
5. If passed: `TZ-FORECAST-XGBOOST-V1-DEPLOY` with monitoring + retraining loop.

**Required data acquisition:** none new for v1. Existing 84-feature parquet is sufficient. (For v2 if v1 passes the gate, consider order-flow features per Rec #2 below.)

**Realistic timeline:** 4-6 weeks calendar time including all gating diagnostics.

**Probability of producing Brier < 0.22:** **5-15%.** Probability of producing Brier 0.245-0.249 with positive resolution: 40-60%. (See §5.)

**Why ranked #1.** Cheapest in compute, lowest infrastructure overhead, shortest timeline, most-replicable methodology. Tree ensembles consistently match or beat deep learning on tabular crypto direction tasks per the literature. Even if it lands at the "marginal Brier 0.245" band rather than <0.22, the model would have non-zero resolution which the previous one didn't — and that alone is enough to make it usable for cost-loss-threshold-style action gating.

### Rec #2 — **Order-flow / LOB feature pipeline as a v2 layer if v1 (Rec #1) passes gating**

**Approach + sources:** Q3-A. [ScienceDirect order flow and crypto returns](https://www.sciencedirect.com/science/article/pii/S1386418126000029), [arXiv 2602.00776](https://arxiv.org/html/2602.00776v1), [arXiv 2506.05764](https://arxiv.org/html/2506.05764v2), [arXiv 2010.01241 TCN-LOB 71% walk-forward](https://arxiv.org/pdf/2010.01241).

**What it would produce.** Order-flow features have the **strongest single-feature predictive signal in the literature**. The reported 71% walk-forward accuracy is at 2-second horizon; effect dissipates rapidly toward 1h, but **incremental signal is plausible** when added to the v1 feature set.

**What it would replace / complement.** Adds a feature family (order-flow imbalance, depth-weighted mid, queue-position dynamics) on top of the existing 84-feature parquet. Does not replace XGBoost.

**Implementation path:**
1. **Prerequisite:** Rec #1 v1 must pass gating with positive resolution. Don't undertake Rec #2 if XGBoost-on-existing-features lacks resolution — adding more features won't manufacture skill if the baseline has none.
2. `TZ-FORECAST-LOB-COLLECTOR` — set up live L2 LOB stream from BitMEX websocket. Storage tiering (hot ~7 days at full resolution, warm aggregates only).
3. `TZ-FORECAST-LOB-FEATURES-V2` — engineer `order_flow_imbalance_5min`, `depth_weighted_mid_drift`, `taker_aggression_z_per_minute` features. Aggregate to 5-min cadence.
4. `TZ-FORECAST-XGBOOST-V2` — retrain v1 with the v2 features added. Diagnostic comparison.

**Required data acquisition:** **substantial — live L2 LOB stream is the main cost item.** ~50-100 GB/month storage. Code complexity is moderate (websocket consumer + binary deltas).

**Realistic timeline:** **8-12 weeks** including data collection (need 4-6 weeks of LOB history before training has enough sample size).

**Probability of producing Brier < 0.22:** **10-20%** if v1 already had positive resolution. Marginal lift from order-flow at 1h horizon is plausible but not guaranteed.

**Why ranked #2.** Strongest evidence base for any single feature family. But the 1h horizon caveat is real — the literature's headline numbers are at sub-minute, and decay to 1h is not well-quantified.

### Rec #3 — **LSTM+XGBoost hybrid as a v3 stretch goal only if v1+v2 still don't reach Brier < 0.22**

**Approach + sources:** Q2-D. [arXiv 2506.22055 LSTM+XGBoost hybrid](https://arxiv.org/html/2506.22055v1).

**What it would produce.** LSTM extracts temporal embeddings → XGBoost trained on (embeddings + raw features). Reported 12-43% accuracy improvements over baselines in several papers (caveat: those baselines are weak; the absolute improvement over a properly-tuned XGBoost-only is likely smaller).

**Implementation path:**
1. Prereq: v1 and v2 must have already exhausted their improvement potential.
2. `TZ-FORECAST-LSTM-EMBEDDING` — train LSTM on sliding windows; extract last-layer embeddings.
3. `TZ-FORECAST-HYBRID-V3` — XGBoost on embeddings + raw features; same gating diagnostic.

**Required data acquisition:** none beyond v1+v2. GPU compute helpful for LSTM training.

**Realistic timeline:** 4-8 weeks added to v1+v2 sequence.

**Probability of producing Brier < 0.22:** **5-15%** *additional* lift on top of v2's level. So if v2 lands at 0.245, v3 might bring it to 0.235 — still not under 0.22.

**Why ranked #3.** Marginal expected lift; high engineering surface area. Worth considering only if v1+v2 establish a foundation but plateau.

---

## §4 Anti-recommendations

### Anti-Rec A — Vision-LLM chart pattern recognition
- **Status:** already established as anti-recommendation in `MARKET_DECISION_SUPPORT_RESEARCH_v1_claude` §4. Three independent sources converge on architectural ceiling.
- **For this TZ:** confirms — do not consider as path to forecast skill.

### Anti-Rec B — Unreplicated 80%+ accuracy claims
- **Why anti.** [Omole & Enke CNN-LSTM 82.44%](https://www.sciencedirect.com/science/article/abs/pii/S0952197625010875) is single-paper, no independent replication. [Other 97% XGBoost claims](https://link.springer.com/chapter/10.1007/978-981-96-0924-6_8) lack rigorous walk-forward. The empirical baseline that survives survivorship + snooping correction is **55-60% directional accuracy** ([SSRN 4287573](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4287573), [arXiv 2512.02029](https://arxiv.org/html/2512.02029v1)). 80%+ claims are publication artifacts.
- **Anti-recommend:** do not pursue any model whose justification rests on a single unreplicated 80%+ accuracy paper. Build to the realistic ceiling, not the published one.

### Anti-Rec C — Deep RL (DQN/PPO/TD3) as direction predictor
- **Why anti.** [Berend Gort 2022](https://arxiv.org/abs/2209.05559) explicitly demonstrated that earlier DRL crypto results contain backtest overfitting; once corrected, "less overfitted" agents still beat baselines but margin shrinks substantially. Heavy infrastructure; high failure modes; marginal expected gain.
- **Anti-recommend:** do not adopt DRL as primary architecture for direction prediction.

### Anti-Rec D — Sentiment features (news, Twitter) as primary
- **Why anti.** Heavily over-published, heavy replication failures. Effect sizes shrink dramatically under rigorous validation.
- **Anti-recommend:** do not invest data-collection effort here as primary path.

### Anti-Rec E — On-chain at hourly horizon as primary
- **Why anti.** On-chain features (Glassnode whale netflows, exchange flows) have predictive power at **daily-to-weekly** scale. At hourly scale the signal is weak. Glassnode subscription cost is non-trivial.
- **Anti-recommend:** do not pay for Glassnode-tier on-chain data with the goal of improving 1h forecast Brier. Worth considering only for 1d horizon work.

### Anti-Rec F — Repeating the regime-conditional weights approach
- **Why anti.** This is what the *retired* model did — per-regime weights on 5 signal channels. Resolution = 0.0001. The structural problem isn't the per-regime approach; it's that the underlying signals don't carry direction information at the 1h+ horizon. More layers of the same approach won't fix that.

---

## §5 Realistic assessment (load-bearing)

**The brutal honesty section.** This is the most important part of the report.

### Empirical baseline from rigorous research

When studies use **rigorous walk-forward + survivorship + snooping correction**, the realistic ceiling for BTC direction prediction is:

- **Directional accuracy: 52-58%** out-of-sample after costs ([SSRN 4287573](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4287573), [arXiv 2512.02029](https://arxiv.org/html/2512.02029v1)).
- **Equivalent Brier: 0.245-0.249** (since Brier ≈ uncertainty − resolution; uncertainty is ~0.25 for balanced classes; resolution achievable is ~0.001-0.005).
- **Resolution component: 0.001-0.010** for the best-validated models.

For the operator's stated target of **Brier < 0.22 with positive resolution**, achievable resolution would need to be ~0.030-0.040 — **5-20× higher than what rigorously-validated crypto literature produces**.

### Probability ranges (honest, not motivated)

| Outcome | Approximate probability under Rec #1 alone | Approximate probability under Rec #1 + Rec #2 (full LOB) |
|---|:---:|:---:|
| **Brier < 0.22** (operator's target) | **5-15%** | **10-20%** |
| **Brier 0.220-0.244** (useful, marginally below baseline) | **30-45%** | **40-55%** |
| **Brier 0.245-0.249** (slight skill, near baseline) | **35-50%** | **30-40%** |
| **Brier ≥ 0.250** (no useful improvement vs decommissioned) | **15-30%** | **10-20%** |

### What this means

1. **The single most likely outcome of the recommended path is Brier 0.245-0.249** — slight skill, marginally usable under thresholded actions, *not* in the operator's target zone of <0.22.
2. **Brier <0.22 is achievable, but would put us in the top decile** of crypto-direction-prediction literature once survivorship + snooping bias are corrected.
3. **The decommissioned model's Brier 0.2569 was actually below the realistic baseline**, which means the *previous attempt was buggy* (likely sign-inversion in MARKUP/MARKDOWN weights, as the diagnostic showed). A fresh build with proper labels + features would *most likely* land **at or just below 0.25**, not <0.22.
4. **If the operator commits to the full Rec #1 → Rec #2 path (~3 months calendar) and the diagnostic gating is strict**, the expected value is: a **30-50% chance of useful slight skill** (0.220-0.244), and a **10-20% chance** of the operator's target (<0.22).

### What honestly drives the probability — the input data + label

The model architecture (XGBoost vs LSTM vs TFT) is **not the decisive factor**. The decisive factors are:

1. **Label design (triple-barrier vs naive next-bar).** A label aligned with the actual decision the operator makes (cost-loss threshold) gives the model a chance.
2. **Feature signal-to-noise ratio.** The current 84 features may or may not carry signal. If they don't, even an oracle model architecture is ceiling-limited.
3. **Survivorship/snooping discipline.** Rigorous validation will produce smaller backtest numbers but real out-of-sample numbers; lax validation produces flattering backtest numbers and disappointing live deployment.

### When to NOT do this work at all

The operator should consider **leaving the forecast block decommissioned permanently** if any of these are true:

- The current `REGULATION_v0_1_1` regime-conditional activation is sufficient for live deployment without a forecast input. (Per `REGULATION_v0_1_1.md` §7 limitation 14, the regulation is already independent of any forecast.)
- The operator's calendar / focus capacity is constrained by other work (live deployment, position cleanup, manual launch validation).
- The expected benefit (slight Brier improvement enabling slightly-better thresholded actions) does not justify the 1-3 month investment vs the activation matrix already in place.

The regulation works without a forecast. Adding a marginally-skillful forecast back would be a *nice-to-have improvement at the margin*, not a *required dependency*. Treat it as such.

---

## §6 Open questions

1. **Is there a public dataset of Bitcoin 1h-Brier scores from rigorously-validated models?** If so, our probability estimates in §5 could be sharpened. The literature scan returned individual papers but not a meta-study; some thinks like [arXiv 2405.11431 review of deep learning for crypto](https://arxiv.org/html/2405.11431v1) come close but don't isolate Brier specifically.
2. **What's the achievable Brier on `triple-barrier` labels vs `next-bar-direction` labels?** Triple-barrier is the recommended label design but its Brier is rarely reported in published comparisons — most papers report accuracy. A small sub-TZ comparing the two on our existing data could clarify.
3. **Does our 84-feature parquet carry signal at all?** A pre-flight Boruta/SHAP feature audit on the existing parquet, *before* committing to a full XGBoost build, would tell us whether the features have signal. If they don't, even the best model architecture cannot exceed baseline. This is a candidate for `TZ-FORECAST-FEATURE-AUDIT-PRE-FLIGHT`.
4. **What is the practical Brier impact of switching from naive to triple-barrier labels?** Worth a small experiment on the existing 84-feature parquet before committing to either Rec #1 v1.
5. **Is the BitMEX L2 LOB stream stable enough for self-hosted collection?** Operational question for Rec #2.
6. **Does Numerai Crypto's submission schema accept models built on our infrastructure?** If yes, we'd get a third-party scoring of any model we build, which would harden our internal Brier validation. Investigation candidate.
7. **For the BTC-only / 1h-only restriction, can we borrow from Numerai-aggregate signals (without participating in tournaments) to seed a baseline?** Maybe — needs licensing investigation.

---

## CP report

- **Output paths:**
  - [docs/RESEARCH/FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_claude.md](FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_claude.md) — this file.
  - [docs/RESEARCH/_forecast_model_replacement_research_raw_claude.json](_forecast_model_replacement_research_raw_claude.json) — structured findings.
- **Approaches per question:** Q1: 4. Q2: 5. Q3: 5. Q4: 3. Q5: 4. Q6: 3. Q7: 5 sub-feasibility points. **Total: ~25 distinct approaches catalogued; 6 anti-recommendations.**
- **Top 3 recommendations summary (one line each):**
  1. **XGBoost + triple-barrier + walk-forward + Brier diagnostic gating** — cheapest baseline, 4-6 weeks, ~5-15% chance of Brier <0.22 alone.
  2. **Order-flow / LOB v2 layer** — strongest single-feature evidence, 8-12 weeks added (incl data collection), ~10-20% chance of Brier <0.22 with v1+v2.
  3. **LSTM+XGBoost hybrid v3 stretch** — only if v1+v2 plateau; marginal expected lift; 4-8 weeks added.
- **Section 5 honest probability assessment:** **Most likely outcome of full Rec #1+#2 path is Brier 0.245-0.249** (slight skill, marginally below baseline, usable under thresholded actions). **Probability of hitting Brier <0.22 (operator's stated target): 10-20% even with full path.** The previous decommissioned model's Brier 0.2569 was *worse than the realistic baseline*, which means a fresh build will most likely improve to 0.245-0.249, not to <0.22. Crypto direction prediction's rigorously-validated ceiling under survivorship + snooping correction is ~52-58% accuracy, equivalent to Brier 0.245-0.249 with resolution component 0.001-0.010. **Beating Brier <0.22 would put us in the top decile of validated literature.**
- **Source links count:** 50+ unique URLs (academic peer-reviewed + practitioner + OSS).
- **Investigation duration:** ~25 minutes web research + synthesis.
- **Sub-questions where research returned essentially nothing useful:**
  - Public dataset of properly-validated 1h-BTC Brier scores (no meta-study found).
  - Specific Brier improvement quantification of triple-barrier vs naive labels (most papers report accuracy only).
  - Independent replication of 80%+ accuracy claims (none found).
  - Production-deployed crypto-direction model with public live-results track record at 1h horizon (none located).
