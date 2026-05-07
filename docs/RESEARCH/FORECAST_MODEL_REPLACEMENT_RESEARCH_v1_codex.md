# FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_codex

## Scope

This report is about the **forecast model itself**, not the operator UX layer above it.

Question:
- what approaches have credible evidence of producing **non-zero resolution** and potentially **Brier < 0.22** for BTC/crypto direction forecasting on roughly `1h / 4h / 1d` horizons?

Frozen constraints:
- BTC / BitMEX context
- solo operator
- hourly-bar infrastructure is realistic
- current decommissioned model had `Brier 0.2569` and `resolution ≈ 0`
- vision-first chart models are already anti-recommended

Evidence rubric:
- `peer-reviewed`
- `preprint / SSRN`
- `production-deployed`
- `community-anecdotal`
- `marketing / weak`

Core conclusion up front:
- the literature remains **skeptical** about easy crypto forecasting
- but it is **not uniformly nihilistic**
- the strongest repeated signal is that **feature engineering + regime conditioning + richer crypto-native features** beats generic “deep model on OHLCV” approaches
- even then, **live Brier < 0.22 on BTC 1h/4h/1d is hard and uncertain**, especially beyond short horizons

---

## Section 1: Approaches per Q1-Q7

### Q1. Crypto-specific forecasting research

#### Q1-A. Crypto-native feature stacks beat pure OHLCV baselines
- Sources:
  - [Deep learning for Bitcoin price direction prediction: models and trading strategies empirically compared](https://link.springer.com/article/10.1186/s40854-024-00643-1)
  - [Bitcoin price direction prediction using on-chain data and feature selection](https://www.sciencedirect.com/science/article/pii/S266682702500057X)
  - [Bitcoin price direction forecasting and market variables (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5053931)
- Summary:
  - Recent crypto-specific papers repeatedly argue that BTC forecasting improves when the model uses more than price history.
  - The recurring additions are on-chain metrics, cross-market variables, and market-structure variables.
  - This is one of the clearest themes in the 2022-2026 literature.
- Evidence level: `peer-reviewed` + `SSRN`
- Applicability: `yes`

#### Q1-B. On-chain features can help, but not as a standalone miracle
- Sources:
  - [Bitcoin price direction prediction using on-chain data and feature selection](https://www.sciencedirect.com/science/article/pii/S266682702500057X)
  - [Deep learning for Bitcoin price direction prediction](https://link.springer.com/article/10.1186/s40854-024-00643-1)
  - [Glassnode docs](https://docs.glassnode.com/)
- Summary:
  - On-chain data has some evidence of predictive relevance, especially when filtered/selected instead of dumped wholesale.
  - Papers do not support the claim that on-chain alone solves BTC direction forecasting.
  - The better use is as a complementary feature family.
- Evidence level: `peer-reviewed` + `production-deployed data vendor`
- Applicability: `partial/yes`

#### Q1-C. Derivatives positioning and funding data matter in crypto specifically
- Sources:
  - [Kaiko: The State of Crypto Derivatives](https://research.kaiko.com/insights/the-state-of-crypto-derivatives)
  - [Kaiko: Perps are Coming to America](https://www.kaiko.com/reports/perps-are-coming-to-america)
  - [Glassnode insights portal](https://insights.glassnode.com/)
- Summary:
  - Crypto differs from equities in how much perpetual-futures structure, open interest, and funding influence short-horizon price behavior.
  - Practitioner-grade research repeatedly treats funding and open-interest extremes as useful state variables.
  - This is especially relevant for BTC on BitMEX-like perps.
- Evidence level: `production-deployed`
- Applicability: `yes`

#### Q1-D. Order book / order flow information is one of the few strong short-horizon edges
- Sources:
  - [Forecasting Bitcoin price movements using multivariate Hawkes processes and limit order book data](https://link.springer.com/article/10.1007/s10203-026-00570-z)
  - [Nowcasting bitcoin’s crash risk with order imbalance](https://pmc.ncbi.nlm.nih.gov/articles/PMC10040314/)
  - [Deep order flow imbalance: Extracting alpha at multiple horizons from the limit order book](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3900141)
- Summary:
  - The cleanest positive findings are often in order flow and LOB research, especially at short horizons.
  - These approaches look materially more credible for `1h` or below than for `1d`.
  - The catch is infrastructure cost and weaker portability to slower horizons.
- Evidence level: `peer-reviewed` + `SSRN`
- Applicability: `yes for 1h`, `partial for 4h/1d`

#### Q1-E. What definitely fails repeatedly: generic price-only directional modeling
- Sources:
  - [G-Research competition wrap-up](https://www.gresearch.com/news/wrapping-up-the-g-research-crypto-forecasting-competition/)
  - [Random forests forecasting Bitcoin price direction](https://www.sciencedirect.com/science/article/pii/S266682702200055X)
  - [Rakotomarolahy 2021 direction forecasting](https://journals.sagepub.com/doi/10.3233/MAS-210530)
- Summary:
  - The recurring failure mode is hoping that generic classifiers on lagged prices / standard indicators alone will produce robust edge.
  - Even when papers show accuracy improvements, live-like or out-of-sample usefulness often collapses.
  - The G-Research result that winners emphasized feature engineering over model novelty is important here.
- Evidence level: `peer-reviewed` + `production competition`
- Applicability: `yes as anti-pattern`

---

### Q2. Model architectures with evidence

#### Q2-A. Gradient-boosted trees remain the most credible baseline
- Sources:
  - [G-Research competition wrap-up](https://www.gresearch.com/news/wrapping-up-the-g-research-crypto-forecasting-competition/)
  - [A novel cryptocurrency price trend forecasting model based on LightGBM](https://www.sciencedirect.com/science/article/pii/S1544612318307918)
  - [Random forests forecasting Bitcoin direction](https://www.sciencedirect.com/science/article/pii/S266682702200055X)
- Summary:
  - Among approaches with repeated practical traction, boosted trees are hard to ignore.
  - G-Research explicitly states that all top three teams used LightGBM, while also stressing feature engineering over architecture.
  - This is the most credible replacement-family starting point.
- Evidence level: `production-deployed/competition` + `peer-reviewed`
- Applicability: `high`

#### Q2-B. LSTM/GRU/CNN-LSTM can work, but evidence is less stable than hype suggests
- Sources:
  - [Deep learning for Bitcoin price direction prediction](https://link.springer.com/article/10.1186/s40854-024-00643-1)
  - [Cryptocurrency price prediction using frequency decomposition and deep learning](https://www.mdpi.com/2504-3110/7/10/708)
  - [Crypto foretell](https://link.springer.com/article/10.1186/s40537-025-01291-7)
- Summary:
  - Sequence models do produce positive research results.
  - But much of the edge seems to come from decomposition, preprocessing, and feature design, not from “LSTM magic”.
  - Reproducibility and live robustness remain questionable.
- Evidence level: `peer-reviewed`
- Applicability: `partial`

#### Q2-C. Transformer-style architectures are promising, but production evidence is thin
- Sources:
  - [N-BEATS Perceiver](https://link.springer.com/article/10.1007/s10614-023-10470-8)
  - [Crypto foretell](https://link.springer.com/article/10.1186/s40537-025-01291-7)
  - [Hugging Face BTCUSDT 1h finetune example](https://huggingface.co/lc2004/kronos_base_model_BTCUSDT_1h_finetune)
- Summary:
  - Transformer-like architectures appear in recent crypto forecasting research.
  - The issue is not absence of results, but absence of strong repeated live validation.
  - Public model cards are especially weak evidence compared to papers or competitions.
- Evidence level: `peer-reviewed` + `weak public model cards`
- Applicability: `partial`

#### Q2-D. Hybrid / ensemble approaches are more believable than single-architecture bets
- Sources:
  - [Regime-aware adaptive forecasting framework for Bitcoin prices](https://link.springer.com/article/10.1007/s10614-026-11338-3)
  - [Deep learning for Bitcoin price direction prediction](https://link.springer.com/article/10.1186/s40854-024-00643-1)
  - [G-Research competition wrap-up](https://www.gresearch.com/news/wrapping-up-the-g-research-crypto-forecasting-competition/)
- Summary:
  - Recent work increasingly combines decomposition, multiple feature families, or regime switching.
  - This is more credible than searching for one universally dominant network.
  - It also matches the low-signal/high-noise nature of BTC.
- Evidence level: `peer-reviewed` + `production competition`
- Applicability: `high`

#### Q2-E. DRL is not the right first replacement path
- Sources:
  - [Deep Reinforcement Learning for Cryptocurrency Trading: Practical Approach to Address Backtest Overfitting](https://ideas.repec.org/p/arx/papers/2209.05559.html)
  - [All that Glitters Is Not Gold](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2745220)
- Summary:
  - DRL can be interesting, but the literature itself emphasizes overfitting risk and the need to reject overfit agents.
  - For replacing a broken forecast model, DRL is too indirect and too fragile.
  - It is not the shortest path to positive resolution.
- Evidence level: `preprint` + `SSRN`
- Applicability: `low`

---

### Q3. Feature engineering for crypto

#### Q3-A. Order-flow / OFI / LOB imbalance features
- Sources:
  - [Forecasting Bitcoin price movements using multivariate Hawkes processes and limit order book data](https://link.springer.com/article/10.1007/s10203-026-00570-z)
  - [Forecasting high-frequency order flow imbalance using Hawkes processes](https://econpapers.repec.org/article/kapcompec/v_3a67_3ay_3a2026_3ai_3a1_3ad_3a10.1007_5fs10614-025-11039-3.htm)
  - [Deep order flow imbalance](https://econpapers.repec.org/RePEc%3Abla%3Amathfi%3Av%3A33%3Ay%3A2023%3Ai%3A4%3Ap%3A1044-1081)
- Summary:
  - Among feature families, order flow imbalance has some of the strongest direct predictive evidence.
  - It is especially valuable for short-horizon return sign or volatility.
  - Infrastructure and exchange-specific data capture are the main barriers.
- Evidence level: `peer-reviewed`
- Applicability: `high for 1h`, `medium for 4h`, `low for 1d`

#### Q3-B. On-chain features with selection / dimensionality control
- Sources:
  - [Bitcoin price direction prediction using on-chain data and feature selection](https://www.sciencedirect.com/science/article/pii/S266682702500057X)
  - [Glassnode docs](https://docs.glassnode.com/)
  - [Numerai Crypto data](https://docs.numer.ai/numerai-crypto/data)
- Summary:
  - On-chain data may help, but papers emphasize feature selection because raw on-chain breadth is noisy.
  - Exchange flows, supply state, and network activity are plausible candidates.
  - This is more realistic for `4h/1d` than for fast `1h` tactical turning points.
- Evidence level: `peer-reviewed` + `production data docs`
- Applicability: `medium/high`

#### Q3-C. Derivatives features: funding, open interest, basis, liquidations
- Sources:
  - [Kaiko derivatives research](https://research.kaiko.com/insights/the-state-of-crypto-derivatives)
  - [Kaiko perps report](https://www.kaiko.com/reports/perps-are-coming-to-america)
  - [Glassnode insights](https://insights.glassnode.com/)
- Summary:
  - Funding and OI extremes are repeatedly used in practitioner crypto research.
  - These features look especially relevant for BTC because perps structurally influence price formation.
  - For BitMEX-specific deployment, this is one of the most natural feature families.
- Evidence level: `production-deployed`
- Applicability: `high`

#### Q3-D. Cross-asset and macro features can help, but likely as secondary features
- Sources:
  - [Bitcoin price direction forecasting and market variables](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5053931)
  - [Random forests forecasting Bitcoin direction](https://www.sciencedirect.com/science/article/pii/S266682702200055X)
  - [Regime-Aware LightGBM for Stock Market Forecasting](https://www.mdpi.com/2079-9292/15/6/1334)
- Summary:
  - Market indices, rates, volatility indices, and related assets sometimes contribute signal.
  - But the evidence is weaker and less crypto-specific than for derivatives and order flow.
  - Useful as complements, not as the center of the feature stack.
- Evidence level: `peer-reviewed`
- Applicability: `partial`

#### Q3-E. Generic technical indicators are not enough on their own
- Sources:
  - [G-Research competition wrap-up](https://www.gresearch.com/news/wrapping-up-the-g-research-crypto-forecasting-competition/)
  - [Numerai Crypto overview](https://docs.numer.ai/numerai-crypto/crypto-overview)
  - [Deep learning for Bitcoin direction prediction](https://link.springer.com/article/10.1186/s40854-024-00643-1)
- Summary:
  - Technical indicators still show up as useful ingredients, but not as a sufficient edge by themselves.
  - The evidence favors blending them with richer crypto-native signals.
  - This directly argues against another pure-indicator replacement.
- Evidence level: `production-deployed` + `peer-reviewed`
- Applicability: `yes as complement`, `no as sole core`

---

### Q4. Regime-aware forecasting

#### Q4-A. Regime-aware switching has direct recent support in Bitcoin literature
- Sources:
  - [Regime-Aware Adaptive Forecasting Framework for Bitcoin Prices Using Probabilistic Generative Models](https://link.springer.com/article/10.1007/s10614-026-11338-3)
  - [Regime-Switching Factor Investing with Hidden Markov Models](https://www.scholars.northwestern.edu/en/publications/regime-switching-factor-investing-with-hidden-markov-models/)
  - [QSTrader HMM regime detection](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/)
- Summary:
  - Recent work directly supports regime-aware BTC forecasting.
  - The common idea is not that one model fits all states, but that different states need different dynamics or parameterizations.
  - This is highly relevant because your current model failed especially in trend regimes.
- Evidence level: `peer-reviewed`
- Applicability: `high`

#### Q4-B. Separate model per regime is more plausible than one universal model
- Sources:
  - [Regime-aware adaptive forecasting framework](https://link.springer.com/article/10.1007/s10614-026-11338-3)
  - [Regime-Aware LightGBM framework](https://www.mdpi.com/2079-9292/15/6/1334)
  - [All that Glitters Is Not Gold](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2745220)
- Summary:
  - The empirical logic is strong: low-signal systems overfit when forced into one global model.
  - Switching or conditioning models by market state is one of the more defensible responses.
  - This is probably the most important architecture lesson for your replacement effort.
- Evidence level: `peer-reviewed` + `SSRN`
- Applicability: `high`

#### Q4-C. Online adaptation may help, but it raises maintenance risk
- Sources:
  - [Regime-Aware Adaptive Forecasting Framework](https://link.springer.com/article/10.1007/s10614-026-11338-3)
  - [Interpretable Hypothesis-Driven Trading walk-forward framework](https://papers.cool/arxiv/2512.12924)
- Summary:
  - Adaptive or online components can be useful when regimes shift.
  - But they also create more retraining, monitoring, and overfit risk.
  - For a solo operator, this should be adopted cautiously.
- Evidence level: `peer-reviewed` + `preprint`
- Applicability: `partial`

#### Q4-D. HMMs are viable as regime detectors, not necessarily as end-to-end forecasters
- Sources:
  - [Regime-Switching Factor Investing with HMMs](https://www.mdpi.com/1911-8074/13/12/311)
  - [A hidden Markov regime-switching smooth transition model](https://researchers.mq.edu.au/en/publications/a-hidden-markov-regime-switching-smooth-transition-model/)
- Summary:
  - HMMs continue to appear in regime literature because they are interpretable and operationally useful.
  - Their value in your context is likely as a conditioning layer, not as the final forecast model.
  - Since you already have a regime classifier, the question is whether to improve conditioning, not whether to replace everything with HMM.
- Evidence level: `peer-reviewed`
- Applicability: `partial/high`

---

### Q5. Evaluation methodology

#### Q5-A. Walk-forward validation is non-negotiable
- Sources:
  - [All that Glitters Is Not Gold](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2745220)
  - [Interpretable hypothesis-driven trading walk-forward framework](https://papers.cool/arxiv/2512.12924)
  - [finlab_crypto overfitting docs](https://ai.finlab.tw/finlab_crypto/overfitting.html)
- Summary:
  - The strongest repeated message is that classical backtests are weak filters for real edge.
  - Rolling or walk-forward out-of-sample evaluation is essential.
  - Probability of backtest overfitting should be explicitly estimated where possible.
- Evidence level: `peer-reviewed` + `preprint` + `production tool docs`
- Applicability: `high`

#### Q5-B. Murphy decomposition is necessary when Brier is the metric
- Sources:
  - [Simplifying and generalising Murphy's Brier score decomposition](https://ore.exeter.ac.uk/repository/handle/10871/34847)
  - [Two Extra Components in the Brier Score Decomposition](https://www.researchgate.net/publication/253893961_Two_Extra_Components_in_the_Brier_Score_Decomposition)
  - [Probabilistic Forecasts: Scoring Rules and Their Decomposition](https://www.mdpi.com/1099-4300/17/8/5450)
- Summary:
  - If the target is a probabilistic directional model, Murphy decomposition is not optional.
  - A model can have an acceptable average score while contributing almost zero resolution.
  - That is directly relevant because your decommissioned model failed on resolution.
- Evidence level: `peer-reviewed`
- Applicability: `high`

#### Q5-C. Look-ahead bias is easy to create in crypto and must be audited explicitly
- Sources:
  - [All that Glitters Is Not Gold](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2745220)
  - [Deep Reinforcement Learning for Cryptocurrency Trading: Practical Approach to Address Backtest Overfitting](https://ideas.repec.org/p/arx/papers/2209.05559.html)
  - [G-Research competition](https://www.gresearch.com/news/wrapping-up-the-g-research-crypto-forecasting-competition/)
- Summary:
  - Crypto data updates, leakage from future-aligned features, and “live-like but not live” evaluation are recurrent traps.
  - Any replacement model must enforce information-set discipline rigorously.
  - Competition-style delayed live evaluation is more convincing than standard holdout splits.
- Evidence level: `SSRN` + `production competition` + `preprint`
- Applicability: `high`

#### Q5-D. Resolution is harder than calibration
- Sources:
  - [Weighted Brier score decompositions for tournaments](https://www.cambridge.org/core/journals/judgment-and-decision-making/article/weighted-brier-score-decompositions-for-topically-heterogenous-forecasting-tournaments/8172E04F2DBC601DA5D953D4685CA346)
  - [Effective scoring rules for probabilistic forecasts](https://pubsonline.informs.org/doi/pdf/10.1287/mnsc.29.4.447)
- Summary:
  - Proper scoring-rule literature reinforces that being better than climatology requires real discrimination.
  - For your replacement target, “sub-0.22 Brier” without positive resolution is not sufficient.
  - The model must separate states meaningfully, not merely stay calibrated near the mean.
- Evidence level: `peer-reviewed`
- Applicability: `high`

---

### Q6. Production deployments

#### Q6-A. Strongest public production-style evidence is competition/live-eval, not vendor marketing
- Sources:
  - [G-Research competition wrap-up](https://www.gresearch.com/news/wrapping-up-the-g-research-crypto-forecasting-competition/)
  - [Numerai Crypto overview](https://docs.numer.ai/numerai-crypto/crypto-overview)
  - [Numerai Crypto data docs](https://docs.numer.ai/numerai-crypto/data)
- Summary:
  - Public production evidence for crypto forecasting is scarce.
  - The most credible sources are competition structures with delayed live scoring, or meta-model ecosystems like Numerai.
  - Even there, the target/task often differs from BTC 1h/4h/1d direction.
- Evidence level: `production-deployed`
- Applicability: `partial`

#### Q6-B. Numerai Crypto is evidence that crypto signals can exist, but the target is mismatched
- Sources:
  - [Numerai Crypto overview](https://docs.numer.ai/numerai-crypto/crypto-overview)
  - [Numerai Crypto data](https://docs.numer.ai/numerai-crypto/data)
- Summary:
  - Numerai Crypto demonstrates that an ecosystem of useful crypto signals is plausible.
  - But its target is cross-sectional, 30-day, bucketed returns across a token universe, not BTC 1h/4h/1d binary direction.
  - It supports the existence of signal, not direct portability to your exact task.
- Evidence level: `production-deployed`
- Applicability: `partial`

#### Q6-C. OSS orderbook repos show some real reproducible alpha at short horizons
- Sources:
  - [deep-orderbook GitHub](https://github.com/Globe-Research/deep-orderbook)
  - [exploring-order-book-predictability GitHub](https://github.com/toma-x/exploring-order-book-predictability)
  - [Forecasting Bitcoin price movements using multivariate Hawkes processes and limit order book data](https://link.springer.com/article/10.1007/s10203-026-00570-z)
- Summary:
  - Of the public reproducible stacks, orderbook-focused repositories are among the few claiming nontrivial walk-forward-like performance.
  - They are useful evidence that short-horizon crypto prediction is not pure fiction.
  - But they are operationally heavier and may not transfer to slower horizons.
- Evidence level: `OSS reproducible` + `peer-reviewed`
- Applicability: `yes for 1h`, `partial otherwise`

#### Q6-D. Public model cards on Hugging Face are not strong evidence
- Sources:
  - [BTCUSDT 1h finetune model card](https://huggingface.co/lc2004/kronos_base_model_BTCUSDT_1h_finetune)
  - [BTCUSDT 4h finetune model card](https://huggingface.co/lc2004/kronos_base_model_BTCUSDT_4h_finetune)
  - [Financial-Time-Series model card](https://huggingface.co/Tasfiya025/Financial-Time-Series)
- Summary:
  - Public model cards exist, but they usually lack rigorous live validation and proper scoring-rule reporting.
  - They are useful as signals of experimentation, not as evidence for replacement decisions.
  - This category should not drive your architecture choice.
- Evidence level: `weak public evidence`
- Applicability: `low`

#### Q6-E. Failure cases are much easier to find than robust live BTC forecast track records
- Sources:
  - [All that Glitters Is Not Gold](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2745220)
  - [Deep RL for crypto trading overfitting paper](https://ideas.repec.org/p/arx/papers/2209.05559.html)
  - [r/algotrading skepticism thread](https://www.reddit.com/r/algotrading/comments/1f7bx7a)
- Summary:
  - The live failure / overfit warning is not a fringe view; it is heavily represented in the literature and community.
  - This means the right question is not “what sounds powerful?” but “what has the lowest false-discovery risk?”
  - That pushes the ranking toward simpler, auditable models with richer features.
- Evidence level: `peer-reviewed` + `community-anecdotal`
- Applicability: `high`

---

### Q7. Specific feasibility for our case

#### Q7-A. Most realistic path: regime-conditional boosted trees with crypto-native features
- Sources:
  - [G-Research competition wrap-up](https://www.gresearch.com/news/wrapping-up-the-g-research-crypto-forecasting-competition/)
  - [LightGBM crypto trend paper](https://www.sciencedirect.com/science/article/pii/S1544612318307918)
  - [Regime-aware adaptive forecasting framework](https://link.springer.com/article/10.1007/s10614-026-11338-3)
- Summary:
  - This is the best fit on evidence, complexity, and maintenance.
  - It leverages your existing regime system instead of discarding it.
  - It also matches the strongest public competition takeaway: feature engineering plus robust tabular learners.
- Evidence level: `production competition` + `peer-reviewed`
- Applicability: `high`

#### Q7-B. Best short-horizon upgrade path: add derivatives + OFI/orderbook features for 1h only
- Sources:
  - [Hawkes + LOB Bitcoin paper](https://link.springer.com/article/10.1007/s10203-026-00570-z)
  - [Deep order flow imbalance](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3900141)
  - [Nowcasting bitcoin’s crash risk with order imbalance](https://pmc.ncbi.nlm.nih.gov/articles/PMC10040314/)
- Summary:
  - If the target is specifically improving `1h`, this is the most evidence-backed feature expansion.
  - It is less convincing for `1d`.
  - It comes with the highest data-engineering burden among realistic recommendations.
- Evidence level: `peer-reviewed`
- Applicability: `high for 1h`

#### Q7-C. Most realistic slower-horizon enhancement: on-chain + derivatives + cross-market features
- Sources:
  - [On-chain feature selection paper](https://www.sciencedirect.com/science/article/pii/S266682702500057X)
  - [Bitcoin market variables SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5053931)
  - [Glassnode docs](https://docs.glassnode.com/)
- Summary:
  - For `4h/1d`, richer macro/crypto-state features are more realistic than raw orderbook modeling.
  - This is likely the better path for improving resolution at slower horizons.
  - The tradeoff is data acquisition cost and feature maintenance.
- Evidence level: `peer-reviewed` + `production data docs`
- Applicability: `high for 4h/1d`

#### Q7-D. Pure deep learning replacement without data expansion is unrealistic
- Sources:
  - [Deep learning for Bitcoin direction prediction](https://link.springer.com/article/10.1186/s40854-024-00643-1)
  - [Crypto foretell](https://link.springer.com/article/10.1186/s40537-025-01291-7)
  - [N-BEATS Perceiver](https://link.springer.com/article/10.1007/s10614-023-10470-8)
- Summary:
  - Deep architectures can work in papers, but they do not change the core signal problem.
  - Without better features and better validation, this is likely to repeat the old failure mode in a more complex form.
  - This is not the most realistic first replacement path.
- Evidence level: `peer-reviewed`
- Applicability: `low/partial`

---

## Section 2: Comparison matrix

| Approach | Evidence basis | Required infrastructure | Compute cost | Maintenance overhead | Probability of Brier <0.22 | Applicability |
|---|---|---|---|---|---|---|
| Regime-conditional LightGBM / XGBoost with technical + derivatives features | production competition + peer-reviewed | Medium | Low | Medium | Medium | High |
| Regime-conditional boosted trees + on-chain + derivatives + cross-market | peer-reviewed + production data vendor | Medium/High | Low/Medium | High | Medium | High |
| Order-flow / OFI / LOB model for 1h | peer-reviewed + OSS | High | Medium/High | High | Medium for 1h, Low for 1d | High for 1h |
| LSTM / GRU on enriched features | peer-reviewed | Medium | Medium | Medium/High | Low/Medium | Partial |
| Transformer / TFT / N-BEATS style on enriched features | peer-reviewed | Medium/High | High | High | Low/Medium | Partial |
| Hybrid decomposition + deep learning | peer-reviewed | Medium/High | High | High | Medium in-sample/OOS papers, unclear live | Partial |
| HMM regime overlay + separate forecasters | peer-reviewed | Medium | Low/Medium | Medium | Medium | High |
| Pure OHLCV technical-indicator model | weak repeated evidence | Low | Low | Low | Low | Low |
| Public HF BTC model cards | weak public evidence | Low | Medium | Unknown | Very Low | Low |
| DRL trading agent as replacement forecaster | preprint / overfit-prone | High | High | High | Very Low | Low |

---

## Section 3: Top 3 recommendations

### 1. Regime-conditional boosted-tree stack with derivatives-first feature expansion
- Sources:
  - [G-Research competition wrap-up](https://www.gresearch.com/news/wrapping-up-the-g-research-crypto-forecasting-competition/)
  - [LightGBM crypto trend paper](https://www.sciencedirect.com/science/article/pii/S1544612318307918)
  - [Regime-aware adaptive forecasting framework](https://link.springer.com/article/10.1007/s10614-026-11338-3)
- What it would produce:
  - the most realistic candidate for positive resolution across `1h/4h/1d`
  - best chance of improving Brier without exploding complexity
- Estimated Brier based on literature similarity:
  - plausible band: `~0.22-0.24` if feature engineering and validation are good
  - sub-`0.22` possible but not something the literature lets us assume
- Required data:
  - OHLCV
  - funding, open interest, basis, liquidation proxies
  - existing regime label as a conditioning variable or splitter
- Rough TZ sequence:
  1. define forecast targets per horizon
  2. add derivatives feature set
  3. split by regime / train per regime
  4. walk-forward + Murphy decomposition
  5. live shadow run
- Realistic timeline:
  - first research-quality prototype: `2-4 weeks`
  - trustworthy live-shadow evaluation: `1-3 months`
- Probability of success:
  - highest of all options here, but still only `moderate`

### 2. 1h specialist model with order-flow / OFI enrichment
- Sources:
  - [Hawkes + LOB Bitcoin paper](https://link.springer.com/article/10.1007/s10203-026-00570-z)
  - [Deep order flow imbalance](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3900141)
  - [deep-orderbook OSS](https://github.com/Globe-Research/deep-orderbook)
- What it would produce:
  - a more realistic chance of genuine short-horizon discrimination than generic bar-based models
  - likely best focused on `1h`, not all horizons simultaneously
- Estimated Brier:
  - not enough papers report Brier directly, but this family is among the few with credible short-horizon alpha evidence
  - if any path has a real shot at `<0.22` on `1h`, this is one candidate
- Required data:
  - live order book / order flow history
  - exchange-specific microstructure pipelines
- Rough TZ sequence:
  1. data capture and normalization
  2. OFI / imbalance feature build
  3. short-horizon regime-conditioned model
  4. walk-forward live shadow
- Realistic timeline:
  - `4-8+ weeks` due to data infra
- Probability of success:
  - `moderate for 1h`, `low for 4h/1d`

### 3. 4h/1d hybrid model with on-chain + derivatives + cross-market features
- Sources:
  - [On-chain feature selection paper](https://www.sciencedirect.com/science/article/pii/S266682702500057X)
  - [Bitcoin market variables SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5053931)
  - [Glassnode docs](https://docs.glassnode.com/)
- What it would produce:
  - a slower-horizon model that is better matched to BTC macro/positioning context than to microstructure
  - likely more useful for `4h/1d` than for `1h`
- Estimated Brier:
  - plausible improvement over the old failed model, but literature does not justify confidently projecting `<0.22`
- Required data:
  - on-chain data vendor or internally curated subset
  - derivatives data
  - cross-market features
- Rough TZ sequence:
  1. feature vendor selection
  2. slow-horizon feature selection
  3. regime-conditional model training
  4. out-of-sample Murphy evaluation
- Realistic timeline:
  - `3-6 weeks` prototype, longer if vendor onboarding is needed
- Probability of success:
  - `low to moderate`

---

## Section 4: Anti-recommendations

### Anti-1. Pure OHLCV + generic technical indicators as the replacement
- Why anti:
  - too close to the already-failed pattern class
  - evidence repeatedly shows richer features matter more than model novelty
- Sources:
  - [G-Research wrap-up](https://www.gresearch.com/news/wrapping-up-the-g-research-crypto-forecasting-competition/)
  - [Rakotomarolahy 2021](https://journals.sagepub.com/doi/10.3233/MAS-210530)

### Anti-2. Generic deep net swap without feature/data redesign
- Why anti:
  - likely just adds complexity to a low-resolution signal
  - many positive DL papers still depend on richer inputs or preprocessing
- Sources:
  - [Deep learning for Bitcoin direction prediction](https://link.springer.com/article/10.1186/s40854-024-00643-1)
  - [Crypto foretell](https://link.springer.com/article/10.1186/s40537-025-01291-7)

### Anti-3. Public Hugging Face crypto models as evidence of viability
- Why anti:
  - weak validation disclosures
  - no convincing live scoring / Brier decomposition
- Sources:
  - [BTCUSDT 1h finetune](https://huggingface.co/lc2004/kronos_base_model_BTCUSDT_1h_finetune)
  - [Financial-Time-Series model card](https://huggingface.co/Tasfiya025/Financial-Time-Series)

### Anti-4. DRL as first replacement path
- Why anti:
  - overfitting risk is explicitly acknowledged in the literature
  - it solves a broader control problem, not your immediate forecast-resolution failure
- Sources:
  - [DRL overfitting paper](https://ideas.repec.org/p/arx/papers/2209.05559.html)

### Anti-5. Vision / chart-image forecasting
- Why anti:
  - already established as weak for this use case
  - benchmark progress does not equal production-grade BTC directional edge
- Sources:
  - [FinChart-Bench](https://huggingface.co/papers/2507.14823)
  - [VISTA](https://huggingface.co/papers/2505.18570)

---

## Section 5: Realistic assessment

This section is intentionally conservative.

### What is most likely true

1. **A better model than the decommissioned one is plausible.**
   - The old failure pattern (`Brier 0.2569`, near-zero resolution) is consistent with a weak-signal architecture, not proof that BTC is completely unforecastable.

2. **Sub-0.22 Brier is hard.**
   - The literature does not justify assuming that a competent rebuild will automatically reach `<0.22` live on BTC `1h/4h/1d`.
   - Especially at `1d`, evidence is weaker than at shorter horizons.

3. **The best chance comes from richer features plus regime conditioning, not fancier networks.**
   - If a replacement succeeds, it is more likely to look like “carefully engineered, regime-aware tabular/hybrid system” than “pure end-to-end deep net”.

### Honest probability assessment

For **any** replacement effort achieving **live** `Brier < 0.22` with positive resolution:

- `1h` horizon:
  - `moderate but far from guaranteed`
  - strongest chance if derivatives + OFI/order-flow features are added

- `4h` horizon:
  - `low to moderate`
  - strongest chance from regime-conditional boosted trees with derivatives + selected on-chain/cross-market features

- `1d` horizon:
  - `low`
  - literature is much less convincing here for BTC directional edge strong enough to hit `<0.22`

For **all three horizons simultaneously** under one replacement program:
- `low`

### Best realistic expectation

The most realistic win condition is probably:
- restore **positive resolution**
- reduce Brier materially below the failed `0.2569`
- maybe achieve `<0.22` on **one horizon** first, most likely `1h` or a regime-conditional subset

That is a much more defensible target than assuming all horizons will become strongly actionable at once.

---

## Section 6: Open questions

1. How much BitMEX-specific microstructure differs from the exchanges studied in public LOB papers.
2. Whether funding / OI / liquidation features can be captured historically at sufficient quality for long walk-forward windows.
3. Whether your current regime labels are already good enough for conditioning, or whether regime refinement would materially improve forecast resolution.
4. Whether the right target is binary `up/down`, or a thresholded move definition that better matches trading relevance.
5. Whether 1d should remain a forecast objective at all, or be reframed as a slower context model instead of a direct probabilistic predictor.

---

## CP report

- Worker ID: `codex`
- Main output: [FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_codex.md](C:/bot7/docs/RESEARCH/FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_codex.md)
- Raw output: [_forecast_model_replacement_research_raw_codex.json](C:/bot7/docs/RESEARCH/_forecast_model_replacement_research_raw_codex.json)

Approaches per question:
- `Q1`: 5
- `Q2`: 5
- `Q3`: 5
- `Q4`: 4
- `Q5`: 4
- `Q6`: 5
- `Q7`: 4

Top 3 recommendations summary:
1. Regime-conditional boosted trees with derivatives-first features are the most realistic first replacement path.
2. For `1h`, the strongest evidence-backed upgrade is order-flow / OFI / LOB enrichment.
3. For `4h/1d`, the most realistic hybrid is on-chain + derivatives + cross-market features under regime conditioning.

Realistic probability assessment:
- best-case realistic outcome is probably restoring positive resolution and materially beating `0.2569`
- `Brier < 0.22` is plausible on a subset/horizon, but unlikely across all three horizons simultaneously
- `1h` has the best chance, `1d` the weakest

Source links count: `33`
