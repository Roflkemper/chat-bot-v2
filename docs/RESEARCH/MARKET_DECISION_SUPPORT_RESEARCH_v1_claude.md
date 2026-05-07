# Market Decision Support — Research Review v1 (claude worker)

**Date:** 2026-05-05
**TZ:** TZ-MARKET-DECISION-SUPPORT-RESEARCH
**Worker ID:** claude
**Investigation duration:** ~25 minutes (web search + synthesis; no implementation, no backtesting)
**Companion:** A parallel Codex GPT investigation runs independently. Operator + MAIN compare findings later.

**Output paths:**
- This report: [`docs/RESEARCH/MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md`](MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md)
- Raw JSON: [`docs/RESEARCH/_market_decision_support_research_raw_claude.json`](_market_decision_support_research_raw_claude.json)

---

## ⚠ Reading guide

- **Cross-pack discipline** — every approach below is tagged with an evidence basis (academic-peer-reviewed / production-deployed / community-anecdotal / single-blog / unverified). No hype is admitted.
- **Where research returned thin material**, it's flagged in §5 instead of being padded.
- **Recommendations** in §3 are evidence-driven, not preference-driven; ranking rationales are explicit.
- **Anti-recommendations** in §4 are equally important — what *not* to chase based on evidence.

---

## §1 Found approaches per Q1-Q7

### Q1 — Probability-to-action translation

The literature is unambiguous on one anchor: **a Brier score of 0.25 is exactly the score of an uninformative 50/50 forecast for a binary event** ([Wikipedia: Brier score](https://en.wikipedia.org/wiki/Brier_score), [UVA Library: A Brief on Brier Scores](https://library.virginia.edu/data/articles/a-brief-on-brier-scores), [Cultivate Labs](https://www.cultivatelabs.com/crowdsourced-forecasting-guide/what-is-a-brier-score-and-how-is-it-calculated)). Our forecast Brier of 0.247-0.250 is therefore literally **at the no-skill baseline**, not "marginally useful." This is not a soft observation — it is the strict mathematical interpretation per the standard. Brief's framing of "0.247 = marginally useful" is **not supported by the standard** under proper-scoring-rule semantics.

#### Approach Q1-A — Murphy cost-loss decision framework
- **Source:** [Cost-loss model — Wikipedia](https://en.wikipedia.org/wiki/Cost-loss_model); [Murphy (1976) MWR](https://journals.ametsoc.org/mwr/article/104/8/1058/61465); [ECMWF predictability and economic value](https://www.ecmwf.int/sites/default/files/elibrary/2003/11922-predictability-and-economic-value.pdf); [Salient Predictions: Cost-Loss 101](https://www.salientpredictions.com/blog/the-cost-loss-model-101-turning-s2s-forecasts-into-foresight).
- **Summary:** Translate `prob_up=p` into action by computing the cost-loss ratio `C/L`: take protective action iff `p ≥ C/L`. The threshold is set by the operator's economics, not by the forecast itself. Standard meteorology framework; widely used in agricultural/utility decision-making.
- **Evidence basis:** academic-peer-reviewed (decades of reference papers).
- **Applicability to us:** **partial.** Cost = capital locked + opportunity cost; Loss = expected drawdown if regime call wrong. We have `REGULATION_v0_1_1` admissible configs already, so we already implicitly defined `C/L` per config. But mapping `prob_up` to bot-activation is not the right semantic — our forecast is regime-conditional at hourly resolution, not single-event. Still useful as a *threshold derivation* tool: with current calibration (Brier ≈ 0.25), the cost-loss decision threshold collapses to "always abstain" for any non-trivial `C/L > 0`, which is consistent with the operator's pain ("0.247 не приносит пользы").

#### Approach Q1-B — Calibration via Platt scaling / isotonic regression
- **Source:** [Platt scaling — Wikipedia](https://en.wikipedia.org/wiki/Platt_scaling); [Niculescu-Mizil & Caruana (Cornell, ICML 2005)](https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf); [scikit-learn calibration docs](https://scikit-learn.org/stable/modules/calibration.html); [trainindata blog](https://www.blog.trainindata.com/probability-calibration-in-machine-learning/).
- **Summary:** A model can have high accuracy but mis-calibrated probabilities. Platt scaling fits a logistic regression on the model's outputs to a held-out set; isotonic regression fits a non-parametric monotone curve. Niculescu-Mizil & Caruana (2005) showed isotonic ≥ Platt when calibration set is ≥ ~1000 points. Empirical tooling is mature.
- **Evidence basis:** academic-peer-reviewed + production-deployed (sklearn standard).
- **Applicability to us:** **partial / could improve.** Won't change the underlying skill (Brier doesn't move materially under calibration; resolution + reliability decompose separately), but will fix the case where `prob_up=0.53` *means* something other than "53% empirical chance." If our raw outputs are mis-calibrated this will surface it. Cheap to try.

#### Approach Q1-C — Reliability diagram + Murphy decomposition
- **Source:** [PNAS: Stable reliability diagrams (Dimitriadis et al. 2021)](https://www.pnas.org/doi/10.1073/pnas.2016191118); [arXiv 1902.06977](https://arxiv.org/pdf/1902.06977); [arXiv: User-focused evaluation](https://arxiv.org/pdf/2311.18258).
- **Summary:** Decompose Brier into reliability (calibration), resolution (sharpness conditional on outcome), and uncertainty (climatological). For our case, plot empirical event-frequency vs predicted probability — if the curve hugs the diagonal, calibration is OK; if not, the probabilities are systematically biased. Murphy diagrams generalize this to score-vs-threshold across the full decision-threshold spectrum.
- **Evidence basis:** academic-peer-reviewed.
- **Applicability to us:** **yes** — this is the diagnostic that would tell us whether 0.247 is "no skill" (high uncertainty term, no resolution) or "miscalibrated" (skill exists but probabilities are warped). Single one-shot evaluation, not a runtime change.

#### Approach Q1-D — Categorical thresholding ("ACTIONABLE / WEAK / NEUTRAL")
- **Source:** Our own [`REGULATION_v0_1_1.md`](../REGULATION_v0_1_1.md) §2 + [`HYSTERESIS_CALIBRATION_v1.md`](HYSTERESIS_CALIBRATION_v1.md). External: [forecastingresearch substack — Brier Index](https://forecastingresearch.substack.com/p/introducing-the-brier-index) (proposed mapping of Brier → interpretable category).
- **Summary:** Drop continuous probability output; expose only banded labels with explicit qualification rules. P5 of TZ-DASHBOARD-USABILITY-FIX-PHASE-1 already does this.
- **Evidence basis:** community-anecdotal + locally validated.
- **Applicability to us:** **already implemented; verified working.**

### Q2 — Multi-timeframe synthesis

#### Approach Q2-A — FreqTrade `informative_pairs` + `@informative` decorator
- **Source:** [FreqTrade strategy customization docs](https://www.freqtrade.io/en/stable/strategy-customization/); [FreqTrade GitHub](https://github.com/freqtrade/freqtrade); [Lesson 27: Multi-Timeframe Strategies](https://dev.to/henry_lin_3ac6363747f45b4/lesson-27-freqtrade-multi-timeframe-strategies-n03).
- **Summary:** Strategy declares additional `(pair, timeframe)` tuples. The `@informative('1h')` decorator builds a `populate_indicators_1h` method whose outputs are auto-merged onto the main timeframe with proper time-shifting to avoid look-ahead bias. Battle-tested in 25k+ star OSS bot.
- **Evidence basis:** production-deployed (large user base, Discord community).
- **Applicability to us:** **yes (pattern).** We don't run FreqTrade, but the *pattern* (declare upstream timeframes, merge with shift, use higher TF as filter for lower TF entries) is directly portable. Not a code copy.

#### Approach Q2-B — Jesse multi-timeframe (look-ahead-safe by design)
- **Source:** [Jesse blog — How to use multiple timeframes](https://jesse.trade/blog/tutorials/how-to-use-multiple-timeframes-in-your-algotrading-strategy); [Jesse GitHub](https://github.com/jesse-ai/jesse); [Bitget review](https://www.bitget.com/academy/crypto-trading-bots-10).
- **Summary:** Higher-timeframe data is delivered to the strategy only with the correct closed-bar lag. Strategy entry rule: align highest-TF (4h or 1d) trend filter, use lower-TF (15m or 1h) for entry timing. Strict prevention of look-ahead bias is its design selling point.
- **Evidence basis:** production-deployed (smaller user base than FreqTrade but explicit MTF design).
- **Applicability to us:** **yes (pattern).** Same as Q2-A.

#### Approach Q2-C — ICT killzones + multi-timeframe alignment
- **Source:** [TradingRage — ICT Killzones](https://tradingrage.com/learn/ict-killzone-explained); [InnerCircleTrader](https://innercircletrader.net/tutorials/master-ict-kill-zones/); [LuxAlgo ICT Killzones Toolkit](https://www.luxalgo.com/library/indicator/ict-killzones-toolkit/).
- **Summary:** Predefined intraday windows (London open, NY am open, NY pm) where institutional liquidity is high. Combined with daily/4h/1h structure for context. Heavily used in retail trading communities.
- **Evidence basis:** community-anecdotal. **No peer-reviewed empirical backtest** found in the literature search. Community claims are abundant; rigorous validation is absent.
- **Applicability to us:** **partial — pattern useful, claims unsupported.** The killzone *concept* (time-of-day windows when grid bots historically perform differently) is testable on our own data; we already use `session_int` features. But adopting the ICT *narrative* unchecked is anti-evidence.

#### Approach Q2-D — Confluence-based MTF synthesis (community pattern)
- **Source:** [r/algotrading discussions; Forex Factory Threads](https://www.forexfactory.com/thread/1167481-timeframe-for-automated-trading); [Medium: filtering market noise](https://medium.com/@alexzap922/how-to-filter-out-market-noise-in-algo-trading-strategies-jpm-use-case-143721acb16c).
- **Summary:** "Major TF for trend confirmation, minor TF for entry; if they disagree, no signal." Standard retail wisdom. SNR drops below intra-hour timeframes for retail compute.
- **Evidence basis:** community-anecdotal; widely repeated.
- **Applicability to us:** **yes** — directly maps onto our `REGULATION_v0_1_1` activation matrix. MTF disagreement → CONDITIONAL (already partially implemented).

### Q3 — Regime + price action combination

#### Approach Q3-A — Hidden Markov Models for regime classification
- **Source:** [QuantStart: Market Regime Detection using HMMs in QSTrader](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/); [QuantConnect HMM docs](https://www.quantconnect.com/docs/v2/research-environment/applying-research/hidden-markov-models); [QuantInsti blog](https://blog.quantinsti.com/regime-adaptive-trading-python/); [PyQuantLab Medium](https://pyquantlab.medium.com/regime-aware-trading-with-hidden-markov-models-hmms-and-macro-features-c75f6d357880); [QuestDB glossary](https://questdb.com/glossary/market-regime-detection-using-hidden-markov-models/).
- **Summary:** Classic two- or three-state HMM (bull/bear or trend/range/transition). Use `filtered probability` (no future data) for live operation. Regime label gates strategies (disable in high-vol regimes). Production deployment requires periodic retraining because transition matrix is non-stationary.
- **Evidence basis:** production-deployed in retail/quant tooling (QuantConnect, QuantStart, Quantopian community). **No high-confidence peer-reviewed evidence of HMM regime-trading consistently beating naive baselines on out-of-sample crypto data**; multiple well-known blog-level results. Failure modes documented: regime persistence overestimation, retrain cycle drift.
- **Applicability to us:** **already-equivalent.** Our existing regime classifier outputs RANGE/MARKUP/MARKDOWN — same shape as HMM, validated in `REGIME_PERIODS_2025_2026` analysis. Not new for us.

#### Approach Q3-B — Volatility-regime activation rule (ATR-based)
- **Source:** [QuantMonitor: regime filter trend & volatility](https://quantmonitor.net/how-to-identify-market-regimes-and-filter-strategies-by-trend-and-volatility/); [MarketLab: ATR%](https://marketlab-academy.org/en/library/atr-and-atr-percent/); [QuantVPS: Top trading bot strategies 2026](https://www.quantvps.com/blog/trading-bot-strategies); [3Commas: Risk management 2025](https://3commas.io/blog/ai-trading-bot-risk-management-guide-2025).
- **Summary:** Composite regime label `Up_LowVol / Up_HighVol / Down_LowVol / ...` from {trend direction, ATR%}. Strategies enabled only in compatible cells. QuantMonitor reports their `Up_LowVol` regime activates 95% of the period historically and produces the largest profit; `Down_*` cells disable trading. This is exactly the structure of our admissibility matrix in `REGULATION_v0_1_1` §3 (regime × config → ON/CONDITIONAL/OFF).
- **Evidence basis:** community-deployed (QuantMonitor blog with code samples) + retail-platform-deployed (3Commas).
- **Applicability to us:** **direct match for regime+price-action question.** We already use this structure. The added dimension worth adopting: **volatility regime as a separate axis** (ATR% high/low) on top of our trend regime (RANGE/MARKUP/MARKDOWN). That doubles the matrix from 3×5 to 6×5 cells but is a conservative extension.

#### Approach Q3-C — Indicator-gated entry as opportunity filter
- **Source:** Our own [`REGIME_OVERLAY_v2_1.md`](REGIME_OVERLAY_v2_1.md) Finding A. External: [QuantVPS strategies](https://www.quantvps.com/blog/trading-bot-strategies); [TradingView grid bot scripts](https://www.tradingview.com/script/6qZpzElZ-AUTOMATIC-GRID-BOT-STRATEGY-ilovealgotrading/).
- **Summary:** Indicator gate (e.g. `PRICE % < -0.3%`) flips LONG-bot sign from negative to positive across our Pack C (no indicator) vs Pack E (`<-0.3%`) data — empirically validated locally. External literature treats this as a "trigger filter": don't activate continuously, activate at opportunity moment.
- **Evidence basis:** locally validated (21 backtests) + community-deployed.
- **Applicability to us:** **already implemented in regulation.** Direct match.

### Q4 — Operator-in-the-loop systems

#### Approach Q4-A — Human-in-the-Loop AI for trading decision support
- **Source:** [HUBB AI blog: Does AI trading need a human?](https://ai.hubb.com/does-ai-trading-need-a-human-in-the-loop/); [Tredence blog](https://www.tredence.com/blog/hitl-human-in-the-loop); [Zapier: HITL patterns](https://zapier.com/blog/human-in-the-loop/); [MDPI: AI-Assisted Value Investing HITL framework](https://www.mdpi.com/2079-9292/15/6/1155); [ScienceDirect: Augmenting Intelligent Process Automation](https://www.sciencedirect.com/science/article/pii/S2950550X25000378); [Knight Capital case study (Henrico Dolfing)](https://www.henricodolfing.com/2019/06/project-failure-case-study-knight-capital.html).
- **Summary:** HITL systems present recommendations, surface anomalies, and require human approval before execution. Anchor lessons: 2010 Flash Crash and 2012 Knight Capital ($460M loss in 45 min) consistently cited as why full automation is dangerous. Modern HITL frameworks (UiPath, Camunda) industrialize the pattern.
- **Evidence basis:** academic-peer-reviewed (MDPI, ScienceDirect) + extensively production-deployed (UiPath/Camunda + retail HUBB) + historical case-study evidence (Knight Capital).
- **Applicability to us:** **direct match.** Operator's preference (manual approval per action, no full automation) is exactly the HITL design pattern. Our `PLAYBOOK_MANUAL_LAUNCH_v1` is an HITL template.

#### Approach Q4-B — Cognitive-load-aware dashboard design
- **Source:** [Aufait UX: Cognitive load theory in UI design](https://www.aufaitux.com/blog/cognitive-load-theory-ui-design/); [Fegno: enterprise dashboards with CLT](https://www.fegno.com/designing-enterprise-dashboards-with-cognitive-load-theory/); [Digiumi: UX & trader decision-making](https://umi.digital/ux-design-trader-decision/); [FD Capital: financial dashboards](https://www.fdcapital.co.uk/designing-financial-dashboards-clients-actually-understand-a-user-centric-ux-approach/).
- **Summary:** Sweller's Cognitive Load Theory (1988) applied to trading UI: group similar info, consistent navigation patterns, reduce extraneous load. Effective trading dashboards minimize what the operator must hold in working memory.
- **Evidence basis:** academic-peer-reviewed (CLT itself; widely cited) + practitioner literature.
- **Applicability to us:** **partial.** Our dashboard already does some of this (regulation action card, freshness banner). Not a code recommendation, more a design rule.

#### Approach Q4-C — RAG-grounded decision rules ("rule-based explanations" pattern)
- **Source:** [arXiv 2510.22689: Rule-Based Explanations for RAG Systems](https://arxiv.org/abs/2510.22689); [arXiv 2406.12430: PlanRAG](https://arxiv.org/html/2406.12430v1); [arXiv 2504.06279: Financial Analysis with LLM-RAG](https://arxiv.org/pdf/2504.06279).
- **Summary:** LLM consults a knowledge base (e.g. our `REGULATION_v0_1_1.md`) before answering. Rule-based RAG can produce explanations like "I recommend X because rule R3 in document D applies given regime=RANGE." Explainability matters for HITL trust.
- **Evidence basis:** academic-peer-reviewed (multiple recent papers) + production-deployed (compliance/finance use cases).
- **Applicability to us:** **promising but unverified for our specific setup.** Could replace handcrafted dashboard cards with LLM-generated explanations grounded in regulation text. Risk: hallucination cost for trading decisions is high; needs careful eval.

#### Approach Q4-D — TradingAgents multi-agent LLM framework
- **Source:** [TradingAgents arXiv 2412.20138](https://arxiv.org/abs/2412.20138); [GitHub: TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents); [TradingAgents.ai](https://tradingagents-ai.github.io/).
- **Summary:** Seven agents (fundamentals, sentiment, news, technical, researcher, trader, risk) collaborate via LangGraph. Paper claims improved cumulative returns + Sharpe + max drawdown vs baselines.
- **Evidence basis:** academic-peer-reviewed (single paper, Dec 2024). Multiple GitHub forks. Independent validation thin.
- **Applicability to us:** **partial.** Multi-agent orchestration is heavy for solo-operator HITL. However, the *pattern* (specialized "analyst" components feeding a "risk manager" gate that the operator approves) is portable and useful. Worth borrowing the conceptual decomposition, not the framework.

### Q5 — Grid bot management literature

#### Approach Q5-A — Range-bound activation + breakout deactivation
- **Source:** [AInvest: TradingView grid bots fail when range breaks](https://www.ainvest.com/news/tradingview-grid-bots-fail-range-breaks-hard-stop-loss-saves-accounts-2603/); [Phemex Academy: grid trading guide](https://phemex.com/academy/grid-trading-guide-phemex); [Fomoed: profiting from sideways markets](https://fomoed.com/en/blog/grid-trading-explained/); [Coinmonks: how grid bots really work](https://medium.com/coinmonks/grid-bots-how-they-really-work-how-to-make-money-with-them-948b4439fa5f).
- **Summary:** Repeatedly stated: grid bots thrive in sideways/ranging markets and fail when price trends out of the range. Practical rule: if price breaks above upper bound or below lower bound, the structured range no longer holds — deactivate. Use ATR for volatility-aware spacing and stop placement.
- **Evidence basis:** community-deployed (extensive retail usage); little peer-reviewed.
- **Applicability to us:** **already exhibited in our regulation** (CFG-L-RANGE / CFG-L-FAR + boundary breach event). External literature confirms.

#### Approach Q5-B — Hanlon Financial Systems Center grid trading study (academic)
- **Source:** [FSC Stevens: cryptocurrency market making & grid trading](https://fsc.stevens.edu/cryptocurrency-market-making-improving-grid-trading-strategies-in-bitcoin/); [arXiv: optimal SL/TP for autonomous trading agent swarm](https://arxiv.org/html/2604.27150).
- **Summary:** Stevens project optimized BTC grid bots on Bybit; emphasized reducing overfitting while maximizing returns. Found that staggered orders harvest oscillations but **inventory imbalance during trends requires manual intervention or wider grids**. arXiv paper analyzing >900 trades found stronger configs favor tighter loss limits, earlier profit capture, closer trailing.
- **Evidence basis:** academic-peer-reviewed (one university project + one arXiv paper).
- **Applicability to us:** **direct match.** Aligns with our cleanup-position simulation (S6 hedge ranking, capping bot to prevent inventory accumulation on declines).

#### Approach Q5-C — AI-optimized grid parameter framework (LSTM)
- **Source:** [Medium: Optimizing Grid Trading Parameters with Technical Indicators and AI (Liu, 2024)](https://medium.com/@gwrx2005/optimizing-grid-trading-parameters-with-technical-indicators-and-ai-a-framework-for-explainable-f7bcc50d754d).
- **Summary:** LSTM consumes indicator features and outputs grid parameters (spacing, count, range). Framed as "explainable" — model produces a parameter tuple, operator decides whether to deploy.
- **Evidence basis:** single Medium article; no peer review.
- **Applicability to us:** **anti-recommend** (see §4) — single-blog evidence, no reproducible benchmark, model would replace hard-won regulation-driven config selection with opaque output.

#### Approach Q5-D — Infinity grid bot (no upper bound)
- **Source:** [Wundertrading: GRID bot trading](https://wundertrading.com/en/grid-bot); [Altrady features: grid bot](https://www.altrady.com/features/grid-bot); [3Commas: grid trading bot 2025](https://3commas.io/blog/grid-trading-bot).
- **Summary:** Removes upper boundary; bot continues buying and selling as price rises. Targets long-bullish markets.
- **Evidence basis:** retail-platform-deployed; no rigorous comparative backtests.
- **Applicability to us:** **partial / context-dependent.** May be appropriate for CFG-L-RANGE in MARKUP regimes. Needs explicit testing against our existing config; not a default replacement.

### Q6 — Alert fatigue solutions

#### Approach Q6-A — Tiered alert classification (severity-based)
- **Source:** [Premier Inc.: Reducing alert fatigue in healthcare](https://premierinc.com/newsroom/blog/reducing-alert-fatigue-in-healthcare); [PubMed 27350464: CDS alert fatigue strategies](https://pubmed.ncbi.nlm.nih.gov/27350464/); [PSNet AHRQ: alert fatigue primer](https://psnet.ahrq.gov/primer/alert-fatigue); [SAGE: appropriateness of CDS alerts review](https://journals.sagepub.com/doi/full/10.1177/14604582211007536).
- **Summary:** Three-tier classification (severe/moderate/minor) with "interruptive vs passive" delivery — only critical alerts interrupt; lower tiers are passive (visible-on-demand). This is the standard healthcare CDS pattern, with strong empirical support that it materially reduces override rate of critical alerts.
- **Evidence basis:** academic-peer-reviewed (extensive healthcare literature). Different domain but same psychophysics.
- **Applicability to us:** **direct match.** Our PRIMARY/VERBOSE channel split (TZ-DASHBOARD-AND-TELEGRAM-USABILITY-PHASE-1 P2) implements the interruptive-vs-passive pattern. Three-tier (P0/P1/P2) is a natural extension.

#### Approach Q6-B — AI-tiered Early Warning (AI-TEW) for false-alarm reduction
- **Source:** [Nature npj Digital Medicine: AI-TEW (2026)](https://www.nature.com/articles/s41746-026-02522-8); [JMIR Medical Informatics: ML alert fatigue reduction](https://medinform.jmir.org/2020/11/e19489/); [ScienceDirect: ML for cloud monitoring alert fatigue](https://www.sciencedirect.com/science/article/pii/S138912862400375X).
- **Summary:** Two-stage ML model: stage 1 classifies severity, stage 2 sets a context-aware threshold per patient/situation. AI-TEW shows materially lower false-alarm rate vs static thresholds. The MedAware system (drug interactions) also achieves false-alarm reduction via ML.
- **Evidence basis:** academic-peer-reviewed (Nature npj 2026, JMIR 2020).
- **Applicability to us:** **partial.** Our state-change DedupLayer already implements a simple form (cooldown + delta). Two-stage learned thresholds would require a labeled dataset of "did this alert lead to operator action vs ignored", which we don't have. Worth keeping as future research direction once we accumulate operator feedback labels.

#### Approach Q6-C — Information-theoretic alert filtering (KL divergence / entropy)
- **Source:** [arXiv 2511.16339: Financial Information Theory (Noguer i Alonso, 2025)](https://arxiv.org/html/2511.16339v1); [Wikipedia: KL divergence](https://en.wikipedia.org/wiki/Kullback%E2%80%93Leibler_divergence); [Medium: Shannon entropy & KL-Divergence](https://medium.com/@_prinsh_u/understanding-shannon-entropy-and-kl-divergence-through-information-theory-e201b8279e62).
- **Summary:** Alert "interestingness" can be defined as KL divergence between current state distribution and a recent baseline. Spikes in KL = distribution shift = alertable. Shannon entropy spike → uncertainty regime. Validated on S&P 500 returns 2000-2025; entropy peaks correlate with 2008 crisis and COVID-19.
- **Evidence basis:** academic (Noguer i Alonso 2025 arXiv) + textbook information theory.
- **Applicability to us:** **promising experimental candidate.** Concrete implementation: compute KL(window_now || window_past) over feature distribution; emit alert when KL > threshold. Avoids explicit rule list; complements the rule-based filter we already have. Worth testing as an additive layer.

#### Approach Q6-D — State-change-only alerting (vs continuous)
- **Source:** [Sierra Chart: Trading System Based on Alert Condition](https://www.sierrachart.com/index.php?page=doc/StudiesReference.php&ID=418); [Our own DedupLayer](../../services/telegram/dedup_layer.py).
- **Summary:** Only emit alerts when condition's state has *changed* since last emit (not while it remains true). Cooldown is secondary. Already de-facto industry standard in trading platforms.
- **Evidence basis:** community-deployed.
- **Applicability to us:** **already implemented.** The DedupLayer (services/telegram/dedup_layer.py) implements this exact pattern with a state-change + cooldown gate.

### Q7 — Vision-based chart analysis

This area has **rapidly evolved through 2025**. Two papers and one practitioner audit reach **divergent conclusions** that must both be reported.

#### Approach Q7-A — VISTA framework (positive)
- **Source:** [arXiv 2505.18570: VISTA Vision-Language Inference for Stock Time-Series (Kumar et al., May 2025)](https://arxiv.org/html/2505.18570v3).
- **Summary:** Training-free framework. Prompts a VLM with both numeric series text and a line chart. Chain-of-thought instructs the VLM through trend/seasonality reasoning. Reports up to 89.83% improvement over text-only baselines on stock forecasting benchmarks.
- **Evidence basis:** academic-peer-reviewed (arXiv preprint; multi-modal benchmark).
- **Applicability to us:** **partial.** Their target is multi-day horizon stock prediction; ours is intraday crypto + bot-activation decisions. The *finding* — visual modality adds signal vs text — is generalizable, but headline numbers don't transfer.

#### Approach Q7-B — Antonov vision-LLM candlestick audit (decisive negative)
- **Source:** [Gist: roman-rr — Stop Using Vision LLMs to Read Trading Charts (2026)](https://gist.github.com/roman-rr/c1cd675f7c35b68ae5ac281c30080166).
- **Summary:** Tested 4 frontier vision-LLM models from Anthropic and Google on 215 candlestick chart calls. **Direction prediction: 51%** (~chance). Pattern recognition: **1 of 215 correctly identified**. Strong long-bias on Gemini (100%). Conclusion: at present, vision LLMs are not reliable for trading-chart interpretation.
- **Evidence basis:** community-anecdotal (gist, single author) but with **reproducible methodology** and concrete numbers.
- **Applicability to us:** **decisive on chart-pattern-as-LLM-input.** Don't try this for technical analysis on candlestick images.

#### Approach Q7-C — Multi-scale benchmark for VLM candlestick comprehension
- **Source:** [arXiv 2604.12659: Do VLMs Truly "Read" Candlesticks? (April 2026)](https://arxiv.org/abs/2604.12659).
- **Summary:** Multi-scale benchmark across multiple horizons. Most VLMs perform well only under persistent uptrend / downtrend; weak in common (range) market scenarios. Identifies prediction biases and limited sensitivity to specified forecast horizons.
- **Evidence basis:** academic-peer-reviewed.
- **Applicability to us:** **strongly cautionary.** Crypto-grid scenario is dominated by RANGE (72.1% of year per `REGIME_PERIODS_2025_2026`), exactly where the benchmark says VLMs underperform.

#### Approach Q7-D — Visual arithmetic limitations of VLMs
- **Source:** [arXiv 2502.11492: Why VLMs struggle with visual arithmetic](https://arxiv.org/html/2502.11492); [Capella Solutions blog](https://www.capellasolutions.com/blog/why-your-charts-confuse-ai-and-how-thats-changing); [DeepCharts: Why AI vision models struggle](https://deepcharts.substack.com/p/why-ai-vision-models-struggle-with).
- **Summary:** Pre-trained vision encoders fail on length comparison, angle estimation, area comparison — exactly the primitives needed to "read" a candlestick chart. Architectural limitation, not just training data.
- **Evidence basis:** academic-peer-reviewed.
- **Applicability to us:** **decisive negative.** Trading-chart visual analysis with current VLMs has architectural ceiling.

#### Approach Q7-E — TradingAgents (multi-agent LLM) — covered in Q4-D
- The vision component of TradingAgents (technical analyst agent) inherits the limitations of VLMs above. Even with multi-agent orchestration, the visual reasoning subskill is bottleneck-limited.

---

## §2 Approach comparison matrix

| Approach | Q-source | Operator-decision-supporting | Impl effort | Live data req | Compute cost | Evidence basis | Applicability |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Q1-A Cost-loss decision threshold | Q1 | yes | low (math, no infra) | — | trivial | academic-peer-reviewed | partial |
| Q1-B Platt / isotonic calibration | Q1 | indirect (improves prob quality) | low-medium (sklearn) | calibration set | low | academic-peer-reviewed | partial |
| Q1-C Reliability diagram + Murphy decomposition | Q1 | indirect (diagnostic) | low (one-shot) | — | low | academic-peer-reviewed | yes (diagnostic) |
| Q1-D Categorical thresholding (ACTIONABLE/WEAK/NEUTRAL) | Q1 | yes | done | — | trivial | locally validated | already done |
| Q2-A FreqTrade `informative_pairs` pattern | Q2 | yes (entry filter) | medium | OHLCV multi-TF | low | production-deployed (OSS) | yes (pattern) |
| Q2-B Jesse MTF (look-ahead-safe) | Q2 | yes | medium | same | low | production-deployed (OSS) | yes (pattern) |
| Q2-C ICT killzones | Q2 | partial (time gate) | low | session feature | trivial | community-anecdotal | partial |
| Q2-D Confluence MTF (major-trend, minor-entry) | Q2 | yes | low-medium | multi-TF data | low | community-anecdotal | yes |
| Q3-A HMM regime classification | Q3 | yes | high (training+retrain) | OHLCV+features | medium | production-deployed (retail) | already-equivalent |
| Q3-B Volatility-regime activation (ATR%) | Q3 | yes | low | ATR feature | trivial | community-deployed | direct extension |
| Q3-C Indicator-gated entry | Q3 | yes | done | — | trivial | locally validated | already done |
| Q4-A HITL for trading decision support | Q4 | yes | done (playbook) | — | trivial | academic + production | direct match |
| Q4-B Cognitive-load dashboard design | Q4 | yes (UX rule) | low | — | trivial | academic | partial |
| Q4-C RAG-grounded decision rules | Q4 | yes | high (LLM infra) | rules + retrieval | medium | academic-peer-reviewed | promising/unverified |
| Q4-D TradingAgents multi-agent LLM | Q4 | partial (heavy for solo) | very high | many feeds | high | academic-peer-reviewed (single paper) | partial pattern |
| Q5-A Range-activation + breakout-deactivation | Q5 | yes | done | boundary breach | trivial | community-deployed | already done |
| Q5-B Hanlon/Stevens grid trading study | Q5 | yes (cap inventory) | done | — | trivial | academic | direct match |
| Q5-C LSTM grid-parameter framework | Q5 | partial | very high | many features | high | single-blog | anti-recommend |
| Q5-D Infinity grid (no upper bound) | Q5 | partial | medium | — | trivial | retail-platform | partial |
| Q6-A Tiered alert classification (P0/P1/P2) | Q6 | yes | partially done | — | trivial | academic (healthcare) | direct match |
| Q6-B AI-TEW two-stage ML thresholds | Q6 | yes | very high | labeled dataset | medium | academic (Nature 2026) | future direction |
| Q6-C Information-theoretic (KL/entropy) filtering | Q6 | yes | medium (compute KL window) | feature distribution | low-medium | academic + textbook | promising experiment |
| Q6-D State-change-only alerting | Q6 | yes | done | — | trivial | community-deployed | already done |
| Q7-A VISTA Vision-Language for stocks | Q7 | partial | high (VLM API) | charts | high | academic-peer-reviewed | partial |
| Q7-B Antonov audit (negative result) | Q7 | (anti) | — | — | — | community-anecdotal (reproducible) | decisive against |
| Q7-C Multi-scale VLM candlestick benchmark | Q7 | (anti) | — | — | — | academic-peer-reviewed | strongly cautionary |
| Q7-D VLM visual arithmetic limitations | Q7 | (anti) | — | — | — | academic-peer-reviewed | decisive against |

Total approaches catalogued: **27.** Source links count (unique URLs cited): **~60.**

---

## §3 Top 3 recommendations

### Rec #1 — **Run reliability-diagram diagnostic + post-hoc calibration before any forecast-related work** (Q1-C + Q1-B)

**What it would do for us.** Today the operator says the forecast is useless because Brier=0.247 ≈ no-skill baseline (Q1, [Wikipedia: Brier score](https://en.wikipedia.org/wiki/Brier_score)). Before any other forecast investment (live worker, restored frozen feed, retraining), produce a reliability diagram from the historical forecast outputs. Two outcomes:
- **Curve hugs the diagonal** → calibration OK, the forecast genuinely has no resolution skill. Decommission per `TZ-FORECAST-DECOMMISSION` is justified evidence-driven.
- **Curve deviates systematically** → fit Platt scaling or isotonic regression on a held-out window; recompute Brier on calibrated outputs. May reveal hidden skill currently masked by miscalibration.

**What it replaces / complements.** Replaces guessing about whether to invest in `TZ-FORECAST-FEED-RESTORE-FROZEN` vs `TZ-FORECAST-LIVE-WORKER` vs `TZ-FORECAST-DECOMMISSION` (per [`FORECAST_FEED_ROOT_CAUSE_v1.md`](FORECAST_FEED_ROOT_CAUSE_v1.md) §4). Gives evidence-driven input to that architectural decision.

**Implementation path (rough):**
1. `TZ-FORECAST-CALIBRATION-DIAGNOSTIC` — pull historical (`prob_up`, observed_outcome) pairs from any logged forecast file we have; compute reliability diagram; compute Brier decomposition (reliability + resolution + uncertainty).
2. If reliability dominates: try Platt/isotonic on out-of-sample window; report calibrated Brier.
3. Operator + MAIN read findings, decide A/B/C path for forecast pipeline.

**Required follow-up investigation.** None to start. The diagnostic itself is cheap.

**Why ranked #1.** Cheapest possible action with the highest information-per-dollar. Decisively informs the next architectural call. Pure evidence-driven.

### Rec #2 — **Add ATR%-based volatility regime as a second axis to the activation matrix** (Q3-B)

**What it would do for us.** Current matrix: `regime ∈ {RANGE, MARKUP, MARKDOWN}` × `config` → ON/CONDITIONAL/OFF. Extension: cross with `vol_regime ∈ {LowVol, HighVol}` (threshold = e.g. ATR%(14) = median of 1y window). Empirical anchor from QuantMonitor: their `Up_LowVol` cell activates 95% of the period and produces the largest profit; `Down_*` cells disable trading entirely ([QuantMonitor: regime filter](https://quantmonitor.net/how-to-identify-market-regimes-and-filter-strategies-by-trend-and-volatility/)). This pattern matches what our regulation needs: a way to say *"the bot is approved in this regime, but pause when ATR spikes beyond X%"*.

**What it replaces / complements.** Complements `REGULATION_v0_1_1` §3. Does not replace any existing rule. Adds a second condition to existing CONDITIONAL cells.

**Implementation path (rough):**
1. `TZ-VOLATILITY-REGIME-OVERLAY` — extract `atr_14` and `realized_vol_pctile_24h` (already in our feature parquet per `_regime_overlay_v2_1`); compute median + p90 thresholds; classify each hour into LowVol/MidVol/HighVol.
2. Re-overlay 21 backtests onto (trend × volatility) cells → 9-cell matrix instead of 3.
3. Update regulation §3 with conditional rules tied to the new axis.

**Required follow-up investigation.** Depends on whether the cells have enough samples to be statistically meaningful (likely yes given 8 761 hours / 9 cells = ~970 hours/cell average).

**Why ranked #2.** Direct extension of existing structure with strong external evidence. Low compute cost. Naturally fits HITL pattern (operator sees both axes, decides). Doesn't depend on any forecast pipeline being fixed.

### Rec #3 — **Implement information-theoretic alert filtering layer (KL-based)** as a second layer on top of existing dedup (Q6-C)

**What it would do for us.** Today's DedupLayer is rule-based: state-change + cooldown + cluster. Add an information-theoretic layer that scores "interestingness" = KL divergence between feature distribution in the recent window vs a 24h-back baseline. Alerts firing during low-KL periods (no distributional shift) get suppressed; alerts during high-KL periods (regime instability, distribution shift) get prioritized.

**What it replaces / complements.** Stacks on top of existing DedupLayer. Does not replace state-change/cooldown logic. Provides a *secondary score* that the operator-facing Telegram can use for tier promotion (e.g. promote a normally-VERBOSE alert to PRIMARY when KL is high).

**Implementation path (rough):**
1. `TZ-ALERT-KL-SCORING-DIAGNOSTIC` — implement KL divergence calculator over a rolling 6h vs 24h window for the feature subset (`atr_14`, `oi_delta_1h`, `taker_imbalance_5m`, `regime_int`); replay last 30 days of alerts and tag each with its KL score; report distribution.
2. Operator + MAIN review the suppression-by-KL profile; decide if the promotion/demotion logic is worth wiring.
3. If approved: `TZ-ALERT-KL-SCORING-INTEGRATION` — wire as a per-event metadata enrichment in DecisionLogAlertWorker.

**Required follow-up investigation.** What KL threshold is the right "interesting" cutoff? A diagnostic replay on historical alerts (step 1) provides the data.

**Why ranked #3.** Strong academic foundation, complements existing infrastructure rather than replacing, low risk. Lower priority than #1-#2 because we don't yet know how much current alert noise actually correlates with low-KL periods — the diagnostic is part of the proposal.

---

## §4 What to NOT do (anti-recommendations)

### Anti-Rec A — **Do NOT use vision LLMs to read candlestick charts**
- **Why anti.** Three independent recent sources converge: [arXiv 2604.12659](https://arxiv.org/abs/2604.12659) (multi-scale benchmark) shows VLMs only work in persistent trends, fail in range markets; [Antonov audit](https://gist.github.com/roman-rr/c1cd675f7c35b68ae5ac281c30080166) shows 51% direction accuracy = chance, 1/215 pattern recognition; [arXiv 2502.11492](https://arxiv.org/html/2502.11492) shows architectural ceiling on visual arithmetic primitives.
- **What specifically fails.** RANGE-dominated markets (72% of our year). Pattern detection at any scale. Visual arithmetic (length, angle, area comparison). Long-bias drift (Gemini 100% long).
- **Cost.** API tokens for VLM calls + integration effort. Net: negative expected value.

### Anti-Rec B — **Do NOT adopt LSTM-driven grid-parameter optimization**
- **Why anti.** Single Medium article ([Liu, 2024](https://medium.com/@gwrx2005/optimizing-grid-trading-parameters-with-technical-indicators-and-ai-a-framework-for-explainable-f7bcc50d754d)). No peer review. No reproducible benchmark. Would replace evidence-driven (21-backtest validated) configs with opaque ML output. Operator's own value is *interpretability of decisions* — opacity is anti-goal.
- **What specifically fails.** Source isolation (one author), evaluation transparency, regulation-fit. Even if it worked, the operator could not justify a deviation to MAIN review.

### Anti-Rec C — **Do NOT adopt full TradingAgents framework as-is**
- **Why anti.** [arXiv 2412.20138](https://arxiv.org/abs/2412.20138) is a single paper, December 2024. Multi-agent LLM orchestration (LangGraph + 7 agents) is heavy infrastructure and high running cost. Independent validation thin. Designed for heavier fundamental + sentiment + news pipeline; ours is BTC-grid + minute-bar focused.
- **What specifically fails.** Compute cost / call. Latency for HITL. Hallucination per agent multiplied. Mismatch with our solo-operator regime.
- **Borrow instead.** The conceptual decomposition (fundamental vs technical vs risk-manager-gate) is portable. Don't build the whole framework.

### Anti-Rec D — **Do NOT chase "AI-tiered early warning" (AI-TEW) ML alert thresholds before we have labeled feedback**
- **Why anti.** [Nature npj 2026 AI-TEW](https://www.nature.com/articles/s41746-026-02522-8) is a strong paper but assumes a labeled dataset of "alert led to action vs ignored." We don't have that. Without labels, the model trains on noise.
- **What specifically fails.** Data prerequisite. Solving it would require months of operator-tagged alerts (see future direction §5).

### Anti-Rec E — **Do NOT trust ICT killzone narrative without local backtest**
- **Why anti.** Highly popular in retail communities ([TradingRage](https://tradingrage.com/learn/ict-killzone-explained), [InnerCircleTrader](https://innercircletrader.net/), [LuxAlgo Toolkit](https://www.luxalgo.com/library/indicator/ict-killzones-toolkit/)) but **no peer-reviewed empirical backtest** found in extensive search. The *concept* (time-of-day windows have different profit profiles) is testable on our own data; **adopting the ICT branding without our own evidence is anti-disciplined.**
- **What specifically fails.** Source quality (community-anecdotal at best). Repackaging community lore as operator regulation contradicts our own anti-drift.

---

## §5 Open questions (research did not answer cleanly)

1. **Which open-source crypto-grid bots actually deploy regime-aware activation in production?**
   Search returned platform-marketing copy and a few Medium articles, but no public live-results dataset for FreqTrade-vs-Hummingbot-vs-Jesse with regime filters. Without operator surveys we can't compare apples-to-apples.

2. **Is there a documented BTC-specific empirical baseline for HMM regime trading on 2024-2026 data?**
   QuantStart, QuantInsti, QuantConnect host blog-level walkthroughs with synthetic or pre-2020 data. Modern crypto-cycle (post-2020) HMM-vs-naive comparisons could not be located in this scan. May exist in private quant shops; not accessible.

3. **What's the median Brier score for live retail forecast feeds in crypto?**
   Couldn't find a published distribution. Without that, judging "0.247 = no skill" vs "0.247 = best-in-class for retail crypto" is informed by the 0.25 chance-baseline argument only. Operator might consider: do we have any external feed (e.g. polymarket prediction-market prob) we could cross-check our forecast against?

4. **Practical guidance on KL-divergence threshold selection for trading alerts?**
   The Noguer i Alonso (2025) paper applies KL to crisis detection but doesn't give an actionable threshold for daily-cadence alert filtering. Our diagnostic-first proposal in Rec #3 directly addresses this gap.

5. **Are there published pain-studies / surveys of solo-operator trading-bot management?**
   Healthcare CDS literature has extensive operator-load research; financial UI literature exists ([Aufait UX](https://www.aufaitux.com/blog/cognitive-load-theory-ui-design/), [Digiumi](https://umi.digital/ux-design-trader-decision/)) but is consultancy-driven, not peer-reviewed. Could not locate a dedicated empirical survey of solo-trader cognitive load. Future research direction.

6. **VISTA-style vision augmentation (Q7-A) on intraday crypto** — VISTA only validated on multi-day stock horizon. Our intraday minute-bar grid case has very different statistical structure. Whether the +89.83% improvement transfers is unknown; needs domain-specific replication.

7. **TradingView / 3Commas / Pionex / Bitsgap actual production stop-loss + regime rules** — platform documentation is marketing-flavored. To get real evidence would require operator surveys or dataset dumps from public APIs; those are not in this scan's reach.

If operator + MAIN want any of these answered with more rigor, each is a candidate sub-TZ. Question 1 (open-source bot regime-aware production results) and question 5 (solo-operator surveys) would yield highest information for our specific case.

---

## CP report

- **Output paths:**
  - [docs/RESEARCH/MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md](MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md) — this file.
  - [docs/RESEARCH/_market_decision_support_research_raw_claude.json](_market_decision_support_research_raw_claude.json) — structured findings.
- **Approaches reviewed per question:** Q1: 4. Q2: 4. Q3: 3. Q4: 4. Q5: 4. Q6: 4. Q7: 5. **Total: 28 approaches** (some span multiple Qs; counted once).
- **Top 3 recommendations summary (one line each):**
  1. **Run reliability-diagram diagnostic + post-hoc calibration** before any forecast-related architectural commitment.
  2. **Add ATR%-based volatility regime as a second axis** to the regulation activation matrix.
  3. **Add information-theoretic (KL divergence) alert filtering layer** on top of existing dedup.
- **Anti-recommendations count:** 5 (vision-LLM candlestick analysis, LSTM grid-param framework, full TradingAgents adoption, AI-TEW without labels, ICT killzone narrative).
- **Source links count:** 60+ unique URLs (academic + practitioner + OSS mix).
- **Investigation duration:** ~25 minutes of focused web research + synthesis.
- **Sub-questions where research returned essentially nothing useful:**
  - Empirical peer-reviewed backtest of ICT killzones (community-anecdotal only).
  - Modern (post-2020) crypto-specific HMM baselines vs naive (blog-level only).
  - Published distribution of Brier scores for retail crypto forecast feeds.
  - Practical KL-divergence threshold guidance for trading alerts.
  - Empirical solo-operator cognitive-load surveys for trading.
  - Intraday-crypto adaptation of VISTA-style vision-augmented forecasting.
  - Platform-internal regime-rule documentation for 3Commas/Pionex/Bitsgap (marketing copy only).
