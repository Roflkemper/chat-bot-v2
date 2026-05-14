# MARKET_DECISION_SUPPORT_RESEARCH_v1_codex

## Scope and method

Goal: investigate open-source, academic, practitioner, and community approaches for **operator-actionable trading decision support** under this frozen context:
- human-in-the-loop
- manual approval remains required
- regime classifier works
- raw forecast probabilities are currently not operator-useful
- grid bots are activated manually via regulation-like rules
- alert budget must stay around `5-15 actionable alerts/day`

Evidence rubric used in this report:
- `academic-peer-reviewed`
- `production-deployed`
- `community-anecdotal`
- `single-blog`
- `unverified`

Important interpretation rule:
- this report ranks **decision-support fit**, not pure predictive novelty
- approaches that may work in research but do not translate into sparse, explicit operator actions are ranked down

---

## Section 1: Found approaches per Q1-Q7

### Q1. Probability-to-action translation

#### Q1-A. Cost-loss / expected-value thresholding instead of raw probability display
- Sources:
  - [Decision-making from probability forecasts based on forecast value](https://www.cambridge.org/core/journals/meteorological-applications/article/decisionmaking-from-probability-forecasts-based-on-forecast-value/E0DAE4195878D32304DF2E2CB6012F67)
  - [A skill score based on economic value for probability forecasts](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/03BE0974B95CD792EDF5F3F93B1F6081/S1350482701002092a.pdf/a-skill-score-based-on-economic-value-for-probability-forecasts.pdf)
  - [Log-Optimal Economic Evaluation of Probability Forecasts](https://academic.oup.com/jrsssa/article/175/3/661/7077615)
- Summary:
  - The strongest recurring guidance is that probability forecasts become useful only after mapping them into a decision-maker’s payoff structure.
  - The literature does not offer one universal Brier cutoff that automatically means “trade now”; it instead recommends comparing expected cost/loss of acting versus not acting.
  - This matches the operator complaint: `prob_up=0.53` is not actionable because it lacks a utility mapping.
- Evidence basis: `academic-peer-reviewed`
- Applicability: `yes`
  - This maps directly to “activate bot / wait / keep off” and is more appropriate than displaying naked probabilities.

#### Q1-B. Abstention band: explicit “no edge / no action” region
- Sources:
  - [An economic basis for certain methods of evaluating probabilistic forecasts](https://www.sciencedirect.com/science/article/pii/S0020737378800108)
  - [On the impact of reliability of probabilistic event-time forecasts on cost-loss analyses by decision makers](https://www.sciencedirect.com/science/article/pii/S0022169425013241)
  - [A Set of New Tools to Measure the Effective Value of Probabilistic Forecasts of Continuous Variables](https://www.mdpi.com/2571-9394/7/2/30)
- Summary:
  - The decision literature consistently implies that not every probabilistic forecast should trigger action.
  - If forecast reliability is weak or economic value is small, abstaining is rational.
  - In trading-system terms, this means explicitly labeling a middle zone as `NO EDGE`, not pretending that every deviation from `0.50` matters.
- Evidence basis: `academic-peer-reviewed`
- Applicability: `yes`
  - This is a clean answer to the operator pain around `0.53`.

#### Q1-C. Calibration gates and quality bands before action
- Sources:
  - [Freqtrade documentation](https://www.freqtrade.io/en/stable/)
  - [Jesse GitHub](https://github.com/jesse-ai/jesse)
  - [Market regime detection using Hidden Markov Models in QSTrader](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/)
- Summary:
  - Production frameworks rarely expose one probability and tell the operator to act directly.
  - They more often combine thresholds, risk controls, or strategy-specific gates.
  - Practitioner implementations tend to use confidence bands as filters rather than as standalone actions.
- Evidence basis: `production-deployed` + `single-blog`
- Applicability: `partial`
  - Strong fit as a support layer, but still needs regulation translation on top.

#### Q1-D. Practitioner takeaway on Brier thresholds
- Sources:
  - [Freqtrade strategy customization](https://docs.freqtrade.io/en/2025.5/strategy-customization/)
  - [Human Factors in Financial Trading](https://pubmed.ncbi.nlm.nih.gov/27142394/)
- Summary:
  - I did not find a finance-specific, peer-reviewed standard saying “Brier X is actionable in trading”.
  - The robust cross-domain pattern is instead: actionability depends on calibration plus payoff asymmetry plus operator tolerance for false alarms.
  - For this case, your existing practical interpretation already aligns with the literature: around `0.25` is too weak to drive manual actions.
- Evidence basis: `academic-peer-reviewed` + `production-deployed`
- Applicability: `yes`

**Q1 conclusion:** the best-supported approach is **probability-to-action translation via utility bands and abstention**, not more raw forecast display.

---

### Q2. Multi-timeframe synthesis

#### Q2-A. Top-down MTF: higher timeframe for admissibility, lower timeframe for entry
- Sources:
  - [Freqtrade informative pairs](https://docs.freqtrade.io/en/2025.5/strategy-customization/)
  - [Hummingbot candles](https://hummingbot.org/strategies/v2-strategies/candles/)
  - [Jesse multi-timeframe support](https://github.com/jesse-ai/jesse)
  - [Reddit algotrading discussion on timeframes](https://www.reddit.com/r/algotrading/comments/1sotx2j/what_time_frame_yall_using/)
- Summary:
  - OSS frameworks support multi-timeframe inputs primarily as a **hierarchical context mechanism**.
  - Higher timeframe establishes direction/regime/context; lower timeframe is used for execution or tactical confirmation.
  - Community practice also converges on this, even if the exact indicators differ.
- Evidence basis: `production-deployed` + `community-anecdotal`
- Applicability: `yes`
  - Strong match for “1d/4h/1h context, minute-bar grid execution”.

#### Q2-B. MTF disagreement as veto, not weighted averaging
- Sources:
  - [Freqtrade strategy customization](https://docs.freqtrade.io/en/2025.5/strategy-customization/)
  - [Jesse gathering ML data with data_routes](https://docs.jesse.trade/docs/research/ml/gathering-data)
  - [Jesse regression docs](https://docs.jesse.trade/docs/research/ml/regression)
- Summary:
  - The platforms expose MTF data, but do not prescribe naive averaging across timeframes.
  - The cleaner production pattern is conditional gating: if higher timeframe disagrees strongly, suppress lower-timeframe action.
  - This fits your operator requirement that **agreement should reduce alerting**, while disagreement should be the event.
- Evidence basis: `production-deployed`
- Applicability: `yes`

#### Q2-C. Multiple timeframe support in open-source platforms is infrastructural, not decision-complete
- Sources:
  - [Hummingbot controllers](https://hummingbot.org/strategies/v2-strategies/controllers/)
  - [Hummingbot scripts](https://hummingbot.org/strategies/scripts/)
  - [Freqtrade stable home](https://www.freqtrade.io/en/stable/)
- Summary:
  - Hummingbot, Freqtrade, and Jesse all support MTF data ingestion and combination.
  - None of them solve your last-mile operator problem by default.
  - They provide the plumbing; the operator-decision layer is still strategy-specific.
- Evidence basis: `production-deployed`
- Applicability: `yes`

#### Q2-D. Renko-based MTF has weak research support for this use case
- Sources:
  - [Extracting the multi-timescale activity patterns of online financial markets](https://www.nature.com/articles/s41598-018-29537-w)
  - [Reddit discussion on MTF and timeframe noise](https://www.reddit.com/r/algotrading/comments/ptt9ec)
- Summary:
  - I found community usage of alternative bars, but not strong, repeated evidence that Renko-based MTF materially improves operator-actionable crypto decision support.
  - Academic multi-timescale work exists, but not specifically validating Renko as a production decision-support layer for grid activation.
  - For this case, Renko looks more like a research branch than a high-confidence immediate improvement.
- Evidence basis: `community-anecdotal` + `academic-peer-reviewed` but indirect
- Applicability: `partial/no`

**Q2 conclusion:** best practice is **top-down MTF gating** with disagreement treated as a **veto/alert trigger**, not as a weighted average.

---

### Q3. Regime + price action combination

#### Q3-A. Regime as a trade/risk filter over a simpler tactical engine
- Sources:
  - [Market Regime Detection using Hidden Markov Models in QSTrader](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/)
  - [Regime-Switching Factor Investing with Hidden Markov Models](https://www.mdpi.com/1911-8074/13/12/311)
  - [Hidden Markov Model for Stock Selection](https://www.mdpi.com/2227-9091/3/4/455)
- Summary:
  - The repeated pattern is not “regime predicts exact trade”.
  - It is “regime constrains when tactical logic is allowed to operate”.
  - This is almost exactly what your regulation does already.
- Evidence basis: `academic-peer-reviewed` + `single-blog`
- Applicability: `yes`

#### Q3-B. Confidence-weighted regime gating
- Sources:
  - [Multi-agent platform to support trading decisions in the FOREX market](https://link.springer.com/article/10.1007/s10489-024-05770-x)
  - [Toward a unified agentic framework for regime-aware portfolio optimization with LLM signals](https://link.springer.com/article/10.1007/s41060-026-01066-0)
- Summary:
  - Decision-support systems often combine latent state classification with confidence, then modulate downstream actions.
  - Confidence is usually used to gate aggressiveness, recommendation strength, or need for human review.
  - This supports your current `ON / CONDITIONAL / OFF` pattern more than raw forecasting.
- Evidence basis: `academic-peer-reviewed`
- Applicability: `yes`

#### Q3-C. HMMs have real traction as regime detectors, but mainly as overlays
- Sources:
  - [Regime-Switching Factor Investing with Hidden Markov Models](https://www.scholars.northwestern.edu/en/publications/regime-switching-factor-investing-with-hidden-markov-models/)
  - [A hidden Markov regime-switching smooth transition model](https://researchers.mq.edu.au/en/publications/a-hidden-markov-regime-switching-smooth-transition-model/)
  - [QuantStart HMM regime detection](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/)
- Summary:
  - HMMs do appear in both academic and practitioner regime work.
  - The strongest use case is as a **risk or regime overlay**, not as a direct minute-level action predictor.
  - This matters because it argues against rebuilding your architecture around fine-grained forecast probabilities first.
- Evidence basis: `academic-peer-reviewed` + `single-blog`
- Applicability: `partial/yes`
  - Useful conceptually, but you already have a working classifier.

#### Q3-D. Hidden states plus raw structure beats either alone
- Sources:
  - [Multi-agent platform to support trading decisions in the FOREX market](https://link.springer.com/article/10.1007/s10489-024-05770-x)
  - [Freqtrade strategy customization](https://docs.freqtrade.io/en/2025.5/strategy-customization/)
  - [Hummingbot controllers](https://hummingbot.org/strategies/v2-strategies/controllers/)
- Summary:
  - Production systems generally do not rely on latent state alone.
  - They combine higher-level regime or context with concrete features such as trend, volatility, volatility expansion, or price-location logic.
  - For your case that means regime should decide **which bot families are admissible**, while price action decides **whether now is the moment**.
- Evidence basis: `production-deployed` + `academic-peer-reviewed`
- Applicability: `yes`

**Q3 conclusion:** the evidence strongly supports **regime-conditioned activation plus price-action trigger**, which is very close to your current direction.

---

### Q4. Operator-in-the-loop systems

#### Q4-A. HITL systems work best when they structure review points, not when they spam context
- Sources:
  - [AI-Assisted Value Investing: A Human-in-the-Loop Framework for Prompt-Guided Financial Analysis and Decision Support](https://www.mdpi.com/2079-9292/15/6/1155)
  - [Human Factors in Financial Trading](https://pubmed.ncbi.nlm.nih.gov/27142394/)
- Summary:
  - HITL finance literature emphasizes governance, traceability, and human verification at key checkpoints.
  - It does not support dumping all raw intermediate analytics on the user.
  - The human should review **decision-ready summaries**, not endless metric streams.
- Evidence basis: `academic-peer-reviewed`
- Applicability: `yes`

#### Q4-B. Incident reduction requires strong interface discipline
- Sources:
  - [Human Factors in Financial Trading](https://journals.sagepub.com/doi/10.1177/0018720816644872)
  - [An adaptive stock index trading decision support system](https://www.sciencedirect.com/science/article/abs/pii/S0957417416301919)
- Summary:
  - Financial incident research points to human-factor failures, not just model failures.
  - DSS research emphasizes consistency of workflow and explicit action support.
  - This supports a dashboard that says `activate X`, `keep Y off`, `watch Z level`, instead of just exposing confidence and probability.
- Evidence basis: `academic-peer-reviewed`
- Applicability: `yes`

#### Q4-C. Solo-operator systems need compression, prioritization, and auditability
- Sources:
  - [Flexible Decision Support System for Algorithmic Trading](https://www.researchgate.net/publication/357854091_Flexible_Decision_Support_System_for_Algorithmic_Trading_Empirical_Application_on_Crude_Oil_Markets)
  - [Multi-agent platform to support trading decisions in the FOREX market](https://link.springer.com/article/10.1007/s10489-024-05770-x)
- Summary:
  - Research systems that remain usable expose a compressed recommendation layer plus explainability and logs.
  - They assume the user cannot continuously triage every signal by hand.
  - This maps directly to your requirement of sparse, explicit, accountable alerts.
- Evidence basis: `academic-peer-reviewed`
- Applicability: `yes`

#### Q4-D. Full autonomy is not required for good decision support
- Sources:
  - [Jesse GitHub](https://github.com/jesse-ai/jesse)
  - [Freqtrade home](https://www.freqtrade.io/en/stable/)
  - [Hummingbot scripts vs controllers](https://hummingbot.org/strategies/scripts/)
- Summary:
  - Production trading frameworks support dry-run, paper trading, alerts, dashboards, and semi-automated workflows.
  - The common pattern is that automation can handle dataflow and execution mechanics while humans approve strategy-level changes.
  - This is aligned with your desired architecture.
- Evidence basis: `production-deployed`
- Applicability: `yes`

**Q4 conclusion:** the strongest HITL pattern is **decision-ready summaries + explicit review gates + audit trail**, not more analytics exposed to the operator.

---

### Q5. Grid bot management literature

#### Q5-A. Grid bots are repeatedly positioned as range/sideways tools
- Sources:
  - [3Commas: Grid Bot - How it Works and Why Use It](https://help.3commas.io/en/articles/7941367-grid-bot-how-it-works-and-why-use-it)
  - [3Commas: Choosing a Strategy or Trading Pair](https://help.3commas.io/en/articles/7931795-grid-bot-choosing-a-strategy-or-a-trading-pair)
  - [Pionex Grid Trading Bot](https://support.pionex.com/hc/en-us/articles/45085712163225-Grid-Trading-Bot)
- Summary:
  - Across established grid-bot platforms, the most consistent claim is: classic grid performs best in sideways/range conditions.
  - Trend-adapted variants exist, but base grid is repeatedly framed as a range-harvesting tool.
  - This matches your regulation’s emphasis on selective regime-based activation.
- Evidence basis: `production-deployed`
- Applicability: `yes`

#### Q5-B. Trend variants exist, but they are usually separate bot modes, not small tweaks
- Sources:
  - [3Commas main settings and options](https://help.3commas.io/en/articles/7932030-grid-bots-main-settings-and-options)
  - [Pionex Infinity Grid](https://pionexus.zendesk.com/hc/en-us/articles/19926174007833-Infinity-Grid)
  - [Pionex Futures Grid Bot](https://support.pionex.com/hc/en-us/articles/45343668185113-Futures-Grid-Bot)
- Summary:
  - Official docs distinguish between stable/range grids and trend-following grid variants like trailing or infinity grids.
  - That is evidence against treating all grid bots as one generic object.
  - In your context this supports the separate roles already validated in regulation.
- Evidence basis: `production-deployed`
- Applicability: `yes`

#### Q5-C. Position caps, stop-losses, and out-of-range handling are first-class controls
- Sources:
  - [3Commas FAQ](https://help.3commas.io/en/articles/7936273-grid-bots-faq)
  - [3Commas bot management](https://help.3commas.io/en/articles/7936262-grid-bots-bots-management)
  - [Pionex Grid Trading Bot](https://support.pionex.com/hc/en-us/articles/45085712163225-Grid-Trading-Bot)
- Summary:
  - Production grid platforms repeatedly emphasize price-range boundaries, stop-loss, trailing, and behavior outside the grid.
  - They also describe cases where bot operation pauses when price leaves the range, then resumes when price returns.
  - That is directly relevant to your cleanup and position-cap concerns.
- Evidence basis: `production-deployed`
- Applicability: `yes`

#### Q5-D. Cleanup is usually managed by staged closure or restart, not by magical self-healing
- Sources:
  - [3Commas bot management](https://help.3commas.io/en/articles/7936262-grid-bots-bots-management)
  - [3Commas statistics page](https://help.3commas.io/en/articles/11388471-grid-bot-statistics-page)
  - [Pionex Grid Trading Bot](https://support.pionex.com/hc/en-us/articles/45085712163225-Grid-Trading-Bot)
- Summary:
  - Platform documentation does not reveal a universal “optimal cleanup algorithm” for accumulated inventory.
  - The practical pattern is monitoring, staged closure, stop-loss, close-bot decisions, and strategy restarts with new parameters.
  - This fits your operator-managed cleanup approach much more than a fully autonomous unwind fantasy.
- Evidence basis: `production-deployed`
- Applicability: `yes`

**Q5 conclusion:** strongest evidence supports **range-first activation, explicit risk caps, and manual/structured cleanup procedures**.

---

### Q6. Alert fatigue solutions

#### Q6-A. State-change alerts outperform continuous trigger spam
- Sources:
  - [Development of a context model to prioritize alerts](https://link.springer.com/article/10.1186/1472-6947-11-35)
  - [Effects of workload, work complexity, and repeated alerts on alert fatigue](https://bmcmedinformdecismak.biomedcentral.com/articles/10.1186/s12911-017-0430-8)
  - [On the alert: future priorities for alerts in clinical decision support](https://link.springer.com/article/10.1186/1472-6947-13-111)
- Summary:
  - The strongest alert-fatigue literature is outside trading, but the pattern is highly transferable.
  - Repetition without incremental value desensitizes users and lowers response quality.
  - This strongly supports alerting on **state changes** or material escalations only.
- Evidence basis: `academic-peer-reviewed`
- Applicability: `yes`

#### Q6-B. Contextual prioritization and severity hierarchies are necessary
- Sources:
  - [Development of a Standardized Rating Tool for Drug Alerts to Reduce Information Overload](https://pubmed.ncbi.nlm.nih.gov/27782288/)
  - [Human Factors in Financial Trading](https://pubmed.ncbi.nlm.nih.gov/27142394/)
- Summary:
  - Alert systems become usable when alerts carry severity, context, and prioritization criteria.
  - In your context that maps to `P0 margin emergency`, `P1 activation-state change`, `P2 watchlist/context`, `VERBOSE digest`.
  - Without that hierarchy, Telegram remains a transport pipe for noise.
- Evidence basis: `academic-peer-reviewed`
- Applicability: `yes`

#### Q6-C. Alert aggregation and entropy-based dedup are real techniques, but usually secondary
- Sources:
  - [An Efficient Alert Aggregation Method Based on Conditional Rough Entropy and Knowledge Granularity](https://www.mdpi.com/1099-4300/22/3/324)
  - [Influence, Information Overload, and Information Technology in Health Care](https://www.nber.org/papers/w14159)
- Summary:
  - There are formal methods for clustering redundant alerts and reducing overload.
  - However, aggregation alone does not solve bad alert semantics.
  - The higher-value fix is still deciding **what deserves an alert at all**.
- Evidence basis: `academic-peer-reviewed`
- Applicability: `partial`

#### Q6-D. Stale-data invalidation is underappreciated but critical
- Sources:
  - [Freqtrade home](https://www.freqtrade.io/en/stable/)
  - [Jesse GitHub](https://github.com/jesse-ai/jesse)
  - [Human Factors in Financial Trading](https://pubmed.ncbi.nlm.nih.gov/27142394/)
- Summary:
  - Frameworks and human-factors research both imply that stale or untrustworthy signals must be clearly marked.
  - A stale forecast that still renders as “live context” is dangerous because it creates false operator confidence.
  - In your current stack this is a priority fix.
- Evidence basis: `production-deployed` + `academic-peer-reviewed`
- Applicability: `yes`

**Q6 conclusion:** the right alert model is **state-change + severity hierarchy + stale-data invalidation**, with dedup as a secondary control.

---

### Q7. Vision-based chart analysis

#### Q7-A. Vision models can read some chart information, but financial-chart benchmarks show clear limitations
- Sources:
  - [FinChart-Bench](https://huggingface.co/papers/2507.14823)
  - [UniChart](https://huggingface.co/papers/2305.14761)
  - [StockGenChaR](https://www.polyu.edu.hk/lst/research/publications/others/2025/1101-stockgenchar/?sc_lang=en)
- Summary:
  - Financial chart comprehension is now a real benchmark area.
  - The main result is not “solved problem”; it is that even strong VLMs have limitations on financial charts and instruction-following.
  - This argues for using chart vision as an auxiliary context layer, not as a primary execution authority.
- Evidence basis: `academic/preprint`
- Applicability: `partial`

#### Q7-B. Vision-based price prediction is promising but not mature enough for your minute-bar operator workflow
- Sources:
  - [VISTA](https://huggingface.co/papers/2505.18570)
  - [From vision to value](https://www.sciencedirect.com/science/article/pii/S1544612326001169)
- Summary:
  - Recent work suggests chart-image information may contain predictive value.
  - But the stronger papers are either preprints or oriented toward slower-horizon factor construction and asset pricing, not minute-level operator alerts.
  - That is materially different from your use case.
- Evidence basis: `academic-peer-reviewed` + `preprint`
- Applicability: `partial/no`

#### Q7-C. The best near-term use of chart vision is human explanation, not autonomous decisioning
- Sources:
  - [StockGenChaR](https://www.researchgate.net/publication/395810749_StockGenChaR_A_Study_on_the_Evaluation_of_Large_Vision-Language_Models_on_Stock_Chart_Captioning)
  - [FinChart-Bench PDF mirror](https://www.researchgate.net/publication/393889577_FinChart-Bench_Benchmarking_Financial_Chart_Comprehension_in_Vision-Language_Models)
  - [AI-Assisted Value Investing HITL](https://www.mdpi.com/2079-9292/15/6/1155)
- Summary:
  - The most credible integration path is explanation or captioning that a human can accept/reject.
  - That fits your operator-in-the-loop design much better than letting a VLM decide activations.
  - Even then, evidence is still early and should be treated as exploratory.
- Evidence basis: `preprint` + `academic-peer-reviewed`
- Applicability: `partial`

#### Q7-D. Failed/weakly supported use case: chart-VLM as first-line signal engine
- Sources:
  - [FinChart-Bench](https://huggingface.co/papers/2507.14823)
  - [VISTA ResearchGate mirror](https://www.researchgate.net/publication/392106223_VISTA_Vision-Language_Inference_for_Training-Free_Stock_Time-Series_Analysis)
- Summary:
  - I did not find repeated, production-grade evidence that chart-VLMs are reliable enough to become a primary control plane for live trading support in a setup like yours.
  - Most available evidence is benchmarking, captioning, or preprint forecasting claims.
  - That is too weak for immediate operational reliance.
- Evidence basis: `preprint`
- Applicability: `no`

**Q7 conclusion:** chart vision is interesting for **secondary explanation**, but not yet strong enough to drive your main decision-support layer.

---

## Section 2: Approach comparison matrix

| Approach | Q-source | Operator-decision-supporting | Impl effort | Live data req | Compute cost | Evidence basis | Applicability |
|---|---|---|---|---|---|---|---|
| Cost-loss / expected-value action mapping | Q1 | High | Medium | Medium | Low | academic-peer-reviewed | High |
| Abstention / no-edge band | Q1 | High | Low | Low | Low | academic-peer-reviewed | High |
| Calibration gates before action | Q1 | High | Low | Low | Low | production-deployed | High |
| Raw probability display only | Q1 | Low | Low | Low | Low | common practice, weak support | Low |
| HTF admissibility + LTF trigger | Q2 | High | Medium | Medium | Low | production-deployed | High |
| MTF disagreement veto | Q2 | High | Medium | Medium | Low | production-deployed | High |
| MTF weighted averaging | Q2 | Medium | Medium | Medium | Low | weak direct evidence | Partial |
| Renko-first MTF | Q2 | Low | Medium | Medium | Medium | community-anecdotal | Low |
| Regime as risk/activation filter | Q3 | High | Low | Medium | Low | academic-peer-reviewed + practitioner | High |
| Confidence-weighted ON/CONDITIONAL/OFF | Q3 | High | Low | Medium | Low | academic-peer-reviewed | High |
| HMM regime overlay | Q3 | Medium | Medium | Medium | Medium | academic-peer-reviewed | Partial/High |
| Regime-only without price action | Q3 | Medium | Low | Low | Low | weak standalone support | Partial |
| HITL review gates + audit trail | Q4 | High | Medium | Low | Low | academic-peer-reviewed | High |
| Decision-ready summaries | Q4 | High | Medium | Low | Low | academic-peer-reviewed | High |
| Full autonomy | Q4 | Low | High | High | Medium | production-deployed elsewhere, poor fit here | Low |
| Solo-operator compression / prioritization | Q4 | High | Medium | Low | Low | academic-peer-reviewed | High |
| Range-first grid activation | Q5 | High | Low | Medium | Low | production-deployed | High |
| Trend-specific grid variants as separate roles | Q5 | High | Medium | Medium | Low | production-deployed | High |
| Position caps / hard bounds / stop-loss | Q5 | High | Low | Medium | Low | production-deployed | High |
| Autonomous cleanup optimizer | Q5 | Low | High | High | Medium | weak evidence | Low |
| State-change alerts only | Q6 | High | Medium | Medium | Low | academic-peer-reviewed | High |
| Severity hierarchy P0/P1/P2 | Q6 | High | Low | Low | Low | academic-peer-reviewed | High |
| Entropy/dedup aggregation | Q6 | Medium | Medium | Medium | Medium | academic-peer-reviewed | Partial |
| Stale-data invalidation | Q6 | High | Low | Low | Low | production-deployed + HF logic | High |
| Chart-VLM explanation assistant | Q7 | Medium | Medium | High | High | preprint + early academic | Partial |
| Chart-VLM primary signal engine | Q7 | Low | High | High | High | preprint / unverified in production | Low |
| Image-based slow-horizon factors | Q7 | Low for this case | High | High | High | academic-peer-reviewed | Low/Partial |

---

## Section 3: Top 3 recommendations

### 1. Build a regulation-state decision layer above forecasts
- Core approach:
  - combine `Q1 abstention/cost-loss mapping` + `Q3 regime-conditioned activation`
- What it would do for us:
  - translate regime + forecast-quality + price-action context into discrete operator outputs:
    - `ACTIVATE CFG-L-RANGE`
    - `KEEP CFG-S-RANGE-DEFAULT CONDITIONAL`
    - `NO EDGE - DO NOTHING`
- What it complements/replaces:
  - complements the current regime classifier and regulation
  - replaces raw `prob_up=0.53` as the main operator message
- Implementation path:
  1. formalize action states and abstention band
  2. map regime states to admissible config roles
  3. add one “direction edge / no edge” gate
  4. render this in dashboard + Telegram
- Required follow-up:
  - define payoff/risk thresholds for `activate`, `conditional`, `watch`, `ignore`
- Why ranked #1:
  - highest evidence fit
  - smallest architecture change relative to current validated regulation
  - directly attacks the operator’s stated pain

### 2. Use top-down MTF gating with disagreement-as-veto
- Core approach:
  - combine `Q2 HTF admissibility + LTF trigger` + `Q2 disagreement veto`
- What it would do for us:
  - use `1d/4h/1h` to define context and admissibility
  - use lower timeframe only for timing within already-allowed roles
  - trigger alerts when HTF and LTF materially disagree
- What it complements/replaces:
  - complements regime classification
  - replaces ad hoc MTF reading by a repeatable gating policy
- Implementation path:
  1. define HTF context state
  2. define LTF trigger state
  3. define disagreement matrix
  4. alert only when disagreement or state transition changes action
- Required follow-up:
  - decide exact timeframes and veto logic
- Why ranked #2:
  - strong OSS/practitioner support
  - fits operator desire for sparse alerts
  - avoids trying to recover actionability from a weak probability alone

### 3. Convert Telegram into a state-change / severity-routed control channel
- Core approach:
  - combine `Q6 state-change alerts` + `severity hierarchy` + `stale-data invalidation`
- What it would do for us:
  - keep alerts under budget
  - make every alert explicitly tied to a regulation consequence or risk state
  - block false confidence from stale analytics
- What it complements/replaces:
  - complements existing dedup/routing
  - replaces generic indicator/event spam as operator-facing output
- Implementation path:
  1. define P0/P1/P2 alert taxonomy
  2. route only state changes to PRIMARY
  3. push repetitive context to VERBOSE digest
  4. suppress forecast-dependent alerts when inputs are stale
- Required follow-up:
  - choose exact PRIMARY budget and digest cadence
- Why ranked #3:
  - immediate usability gain
  - minimal model dependency
  - strongly supported by alert-fatigue literature and your operator constraints

---

## Section 4: What to NOT do

### Anti-1. Do not rebuild the operator layer around raw probabilities first
- Sources:
  - [Decision-making from probability forecasts based on forecast value](https://www.cambridge.org/core/journals/meteorological-applications/article/decisionmaking-from-probability-forecasts-based-on-forecast-value/E0DAE4195878D32304DF2E2CB6012F67)
  - [Log-Optimal Economic Evaluation of Probability Forecasts](https://academic.oup.com/jrsssa/article/175/3/661/7077615)
- Why anti:
  - probability without utility mapping does not solve the operator’s “what should I do?” problem
  - in your current Brier range it is especially weak

### Anti-2. Do not treat marginal forecasts as mandatory alerts
- Sources:
  - [Effects of workload, work complexity, and repeated alerts on alert fatigue](https://bmcmedinformdecismak.biomedcentral.com/articles/10.1186/s12911-017-0430-8)
  - [Human Factors in Financial Trading](https://pubmed.ncbi.nlm.nih.gov/27142394/)
- Why anti:
  - this creates alert fatigue and lower compliance
  - repeated weak signals degrade trust in the system

### Anti-3. Do not make Renko or exotic bars the primary redesign axis
- Sources:
  - [Extracting the multi-timescale activity patterns of online financial markets](https://www.nature.com/articles/s41598-018-29537-w)
  - [Reddit MTF discussion](https://www.reddit.com/r/algotrading/comments/ptt9ec)
- Why anti:
  - I found weak evidence that this specifically solves your operator-action problem
  - it risks a detour into representation changes instead of decision translation

### Anti-4. Do not make chart-VLM/CV the first-line decision engine
- Sources:
  - [FinChart-Bench](https://huggingface.co/papers/2507.14823)
  - [VISTA](https://huggingface.co/papers/2505.18570)
- Why anti:
  - evidence is early, mixed, and mostly benchmark/preprint-grade
  - too weak for primary live control of grid-bot activations

### Anti-5. Do not pursue full autonomy before sparse decision support works
- Sources:
  - [AI-Assisted Value Investing HITL](https://www.mdpi.com/2079-9292/15/6/1155)
  - [Human Factors in Financial Trading](https://pubmed.ncbi.nlm.nih.gov/27142394/)
- Why anti:
  - operator explicitly wants approval gates
  - the present failure mode is interpretability/usability, not lack of autonomy

---

## Section 5: Open questions

1. I found **no strong finance-specific academic consensus** on a universal Brier cutoff that automatically means “actionable trade support”.
   - The literature is much stronger on utility/cost-loss mapping than on numeric cutoffs.

2. I found **little rigorous evidence for Renko-based MTF** as a superior operator-decision architecture in crypto futures.
   - There is community use, but not strong comparative validation.

3. I found **limited direct research on solo crypto grid-bot operator UIs**.
   - Most HITL and alert-fatigue literature comes from adjacent decision-support domains.

4. I found **weak production-grade evidence for chart-VLM systems in live trading support**.
   - Most material is benchmark, captioning, or preprint forecasting.

5. BitMEX-specific human-in-the-loop studies were sparse.
   - Most transferable evidence comes from broader finance, OSS trading frameworks, and platform docs.

---

## CP report

- Worker ID: `codex`
- Main output: [MARKET_DECISION_SUPPORT_RESEARCH_v1_codex.md](C:/bot7/docs/RESEARCH/MARKET_DECISION_SUPPORT_RESEARCH_v1_codex.md)
- Raw output: [_market_decision_support_research_raw_codex.json](C:/bot7/docs/RESEARCH/_market_decision_support_research_raw_codex.json)

Approaches reviewed per question:
- `Q1`: 4
- `Q2`: 4
- `Q3`: 4
- `Q4`: 4
- `Q5`: 4
- `Q6`: 4
- `Q7`: 4

Top 3 recommendations:
1. Build a regulation-state decision layer above forecasts.
2. Use top-down multi-timeframe gating with disagreement-as-veto.
3. Convert Telegram into a state-change and severity-routed control channel.

Anti-recommendations count: `5`

Source links count: `39`

Research gaps with little direct evidence:
- universal Brier-to-action cutoffs in finance
- Renko-first MTF evidence
- solo-operator crypto grid decision-support UI studies
- production-grade chart-VLM trading support evidence
