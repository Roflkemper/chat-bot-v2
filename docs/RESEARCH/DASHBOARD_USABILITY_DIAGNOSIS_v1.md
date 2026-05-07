# DASHBOARD_USABILITY_DIAGNOSIS_v1

## Scope

Goal: diagnose why the operator assesses the current dashboard and Telegram stream as having "0 practical use", then propose usability-focused improvements tied to the current regulation.

Inputs used:
- operator-reported screenshot observations
- [REGULATION_v0_1_1.md](C:/bot7/docs/REGULATION_v0_1_1.md)
- [HYSTERESIS_CALIBRATION_v1.md](C:/bot7/docs/RESEARCH/HYSTERESIS_CALIBRATION_v1.md)
- current implementation paths:
  - [state_builder.py](C:/bot7/services/dashboard/state_builder.py)
  - [dashboard.js](C:/bot7/docs/dashboard.js)
  - [telegram_runtime.py](C:/bot7/services/telegram_runtime.py)
  - [virtual_trader.py](C:/bot7/services/market_forward_analysis/virtual_trader.py)
  - [dashboard_state.json](C:/bot7/docs/STATE/dashboard_state.json)

Out of scope:
- new ML models
- regime classifier redesign
- regulation rewrite
- performance claims beyond current evidence

## Executive diagnosis

The dashboard is not useless because it lacks data. It is useless because it stops one level too early.

Current operator problem:
1. The dashboard exposes model internals such as `prob_up`, Brier, and raw trigger streams.
2. The regulation is phrased in bot-activation terms: which bot role is allowed, in which regime, and when activation is conditional.
3. The operator-facing layer does not translate (1) into (2).

Result:
- regime label is usable because it directly maps to regulation context
- probability output near `0.50` is not usable because it does not cross an action threshold
- Telegram alerts are noisy because they are trigger-centric, not decision-centric
- virtual trader `0/0/0/0` is not interpretable because the upstream forecast snapshot shown in dashboard is stale

The core usability failure is therefore not "bad model", but "missing decision translation layer from forecast + regime + regulation into operator action state".

---

## §1 Brier score interpretation

### What the numbers mean operationally

Current dashboard values:
- `1h = 0.2467`
- `4h = 0.2478`
- `1d = 0.2502`

Reference points already encoded in code:
- [state_builder.py](C:/bot7/services/dashboard/state_builder.py) and [multiplier.py](C:/bot7/services/sizing/multiplier.py) use:
  - `GREEN <= 0.22`
  - `YELLOW <= 0.265`
  - `RED > 0.265`
- calibration baseline in the forecast stack is `0.25` random baseline

Implication:
- `0.2467-0.2502` is only marginally better than random
- it is not broken, but it is not operator-grade directional conviction
- this is exactly the class of number that should not be shown as if it were actionable

### Why the current visual treatment is misleading

The dashboard marks these as `yellow`, which is technically consistent with code, but operator-usability is different from technical-validity:
- `yellow` in the current UI reads like "caution but still useful"
- for a human operator, `0.247` with `prob_up ~ 0.52-0.53` is effectively "no directional edge"

That is the gap.

### Actionable threshold for operator

For operator use, the threshold should be stricter than the machine entry threshold.

Recommended interpretation layer:
- `Brier <= 0.22`: actionable-quality forecast, allowed to influence operator bias
- `0.22 < Brier <= 0.24`: weak support only, may color context but not drive action
- `Brier > 0.24`: display as informational only, not actionable

And probability should be paired with distance from neutral:
- `prob_up >= 0.60` or `<= 0.40`: actionable directional bias candidate
- `0.45 < prob_up < 0.55`: explicitly "neutral / no edge"
- `0.55-0.60` and `0.40-0.45`: weak lean, not action by itself

This is consistent with DRIFT history: do not treat near-baseline Brier as "good enough" just because it is numerically below `0.265`.

Conclusion:
- current `1h/4h/1d` outputs should be rendered as context, not as operator signal
- the operator is correct that `53% prob_up` has near-zero practical value

---

## §2 Regime classifier output usability

### What is useful now

`RANGE confidence 0.85` is useful because it maps into the regulation:
- [REGULATION_v0_1_1.md](C:/bot7/docs/REGULATION_v0_1_1.md) §3 says:
  - `CFG-L-RANGE`: ON in RANGE
  - `CFG-L-FAR`: ON in RANGE
  - `CFG-S-RANGE-DEFAULT`: ON in RANGE
  - suspended configurations remain OFF

So regime label already answers a real operator question:
"Which bot families are even admissible right now?"

### What is not useful now

`53% neutral prob_up` is not useful because:
- it does not cross a strong directional threshold
- it does not map to a bot activation decision in the regulation
- it does not answer "launch / keep off / monitor / wait"

### Where the missing actionable layer should sit

The missing layer belongs between regime label and direction probability:

1. Regime decides admissible bot set from regulation §3.
2. Forecast quality decides whether direction bias is trustworthy enough to expose.
3. Probability magnitude decides whether there is any directional edge at all.
4. Output to operator should be:
   - allowed bot roles
   - blocked bot roles
   - whether current direction signal is actionable, weak, or neutral

That is the layer currently absent from both dashboard and Telegram.

### Concrete translation example

Current live state in [dashboard_state.json](C:/bot7/docs/STATE/dashboard_state.json):
- regime `RANGE`
- confidence `0.85`
- forecast `1h prob_up = 0.5243`
- Brier `0.2467`

Operator-meaningful rendering should be:
- Regime: `RANGE`
- Allowed by regulation: `CFG-L-RANGE`, `CFG-L-FAR`, `CFG-S-RANGE-DEFAULT`
- Suspended: `CFG-S-INDICATOR`, `CFG-L-DEFAULT`
- Direction bias: `NONE`
- Reason: `prob_up too close to 0.50 and Brier too weak for operator action`

That message is useful. The current message is not.

---

## §3 Telegram alert stream quality

### Current failure mode

The Telegram stream is trigger-centric.

Observed and code-confirmed behavior:
- [telegram_runtime.py](C:/bot7/services/telegram_runtime.py) forwards raw signal events such as `RSI_EXTREME`
- dedup is based on rounded RSI plus cooldown, not on decision relevance
- historical recovered `signals.csv` shows repeated `RSI_EXTREME` prints across consecutive 15m/1h snapshots
- operator example "6+ RSI overbought in 90 minutes" is therefore structurally expected, not accidental

### Why this is noise under the regulation

The regulation is not trigger-based. It is activation-matrix-based.

Examples:
- `SHORT indicator` is suspended everywhere under §2-§3
- `LONG default` is suspended everywhere
- therefore an alert stream dominated by generic RSI events has no clean mapping to any admissible operational action

Even worse:
- alert messages do not say whether the signal is relevant to any currently allowed bot role
- alert messages do not say whether the current regime allows that role
- alert messages do not say whether the event changes the operator's action state

So the operator receives events, but not decisions.

### Required filter principle

Telegram should emit only if the event is relevant to the regulation state machine.

Alert classes that are worth keeping:
- regulation-state change
- admissible bot role became ON/OFF/CONDITIONAL
- forecast bias crossed an actionable threshold
- risk/cleanup alerts related to current live exposure
- transition note only if it changes allowed action, not just because `TRANSITION` exists

Alert classes that should be demoted or suppressed:
- repeated RSI extremes without regulation consequence
- generic LEVEL_BREAK without bot-role implication
- repeated neutral forecast drift around `0.50`

---

## §4 Virtual trading `0/0/0/0`

### Question

Why no signals in 7 days: broken, or correctly absent?

### Implementation facts

The virtual trader in [virtual_trader.py](C:/bot7/services/market_forward_analysis/virtual_trader.py) opens only when:
- `prob_up >= 0.55` and regime in `{MARKUP, RANGE}` for long
- `prob_down >= 0.55` and regime in `{MARKDOWN, RANGE}` for short
- only one open position max

The dashboard aggregates this from `data/virtual_trader/positions_log.jsonl` via [state_builder.py](C:/bot7/services/dashboard/state_builder.py).

### Why the current `0/0/0/0` is not trustworthy as a KPI

The dashboard currently shows:
- `forecast.source = live`
- but `forecast.bar_time = 2026-05-01T00:00:00+00:00`
- while dashboard snapshot time is `2026-05-05T16:38:30Z`

That means the forecast shown to the dashboard is stale by about 4.7 days.

Implication:
- if forecast updates are stale, `virtual_trader 0/0/0/0` cannot be read as "market produced no valid signals"
- it is equally plausible that the virtual trader was not fed fresh forecast states

### Secondary explanation

Even if the feed were fresh, a `prob_up ~ 0.52` state would correctly produce no signal because it is below `0.55` threshold.

So the correct diagnosis is:
- `0/0/0/0` is not proof of breakage by itself
- but in the current dashboard snapshot it is not decision-usable because upstream forecast freshness is already compromised

Operational conclusion:
- first classify virtual trader as `stale / not diagnostic`
- only then ask whether there were truly no threshold-crossing signals

---

## §5 Gaps versus regulation

### Gap 1: no regulation-aware action layer

Current dashboard shows:
- regime
- forecast
- virtual trader

But the regulation is about:
- admissible bot roles
- activation state by regime
- suspended roles
- conditional regimes

The missing card is: "What is currently allowed by regulation?"

### Gap 2: no distinction between informational and actionable forecast

Current dashboard prints all numeric forecasts similarly.
It does not separate:
- strong edge
- weak lean
- neutral / no edge

### Gap 3: Telegram alerts ignore regulation relevance

Current stream forwards raw signal events even when they do not imply any allowed action under §3.

### Gap 4: transition finding is not translated

`H=1` means transition is only `7.35%` of year, and regulation §4 says no global pause.
That should simplify operator messaging:
- do not create a separate noisy transition mode
- only mention transition if it changes per-bot status

### Gap 5: staleness is visible but not blocking

Freshness exists in the dashboard, but stale forecast data does not invalidate downstream cards strongly enough.
The operator can still read forecast and virtual trader as if they were current.

---

## §6 Improvement proposals

### Proposal 1 — Add regulation action card

- Change: add a top-level card `Allowed Now / Conditional / Off` derived from regulation §3.
- Output example for current state:
  - Allowed now: `CFG-L-RANGE`, `CFG-L-FAR`, `CFG-S-RANGE-DEFAULT`
  - Suspended: `CFG-S-INDICATOR`, `CFG-L-DEFAULT`
  - Direction edge: `none`
- Tied to regulation: §2-§4
- Priority: `HIGH`
- Effort: `Medium`

### Proposal 2 — Reclassify forecast into operator bands

- Change: convert raw forecast display into:
  - `Actionable`
  - `Weak lean`
  - `Neutral / no edge`
  based on both Brier and distance from `0.50`
- Suggested thresholds:
  - actionable only if `Brier <= 0.22` and `prob_up >= 0.60 or <= 0.40`
  - weak lean if `Brier <= 0.24` and `prob_up` outside `0.45-0.55`
  - otherwise neutral
- Tied to regulation: supports §3 decisions without rewriting them
- Priority: `HIGH`
- Effort: `Low`

### Proposal 3 — Telegram alert gating by regulation relevance

- Change: suppress or demote alerts that do not affect an admissible bot role.
- Example:
  - do not push repeated `RSI_EXTREME` if it does not change allowed action under §3
  - push only when event changes launch / keep-off / conditional-monitor state
- Tied to regulation: §3 activation matrix
- Priority: `HIGH`
- Effort: `Medium`

### Proposal 4 — Staleness hard-stop on forecast-dependent panels

- Change: if forecast age > 120 min, replace forecast and virtual trader cards with `STALE - not decision-usable`.
- Current need is evidenced by [dashboard_state.json](C:/bot7/docs/STATE/dashboard_state.json), where forecast bar time is several days old.
- Tied to regulation: prevents false operational reading of §3 support signals
- Priority: `HIGH`
- Effort: `Low`

### Proposal 5 — Add "why this matters" line to each Telegram alert

- Change: every emitted operator alert must include one line:
  - `Effect on regulation: none / enables LONG range / keeps SHORT default conditional / risk only`
- Tied to regulation: §3-§4
- Priority: `MEDIUM`
- Effort: `Medium`

### Proposal 6 — Add cleanup-risk overlay for current live state

- Change: because current session is blocked on SHORT cleanup, dashboard should show a dedicated operator block:
  - `Regulation activation blocked until cleanup complete`
  - this should dominate generic forecast cards
- Tied to regulation/session state: current operational blocker, not a new strategy rule
- Priority: `MEDIUM`
- Effort: `Low`

### Proposal 7 — Collapse repetitive RSI/LEVEL alerts into digest mode

- Change: instead of sending every repeated event, send one summary per cooldown window:
  - `RSI overbought repeated 6x in 90m; no regulation action change`
- Tied to regulation: makes explicit that raw trigger intensity did not alter §3 state
- Priority: `MEDIUM`
- Effort: `Low`

### Proposal 8 — Expose virtual trader reason-for-no-signal

- Change: if virtual trader has zero trades, show why:
  - `No fresh forecast`
  - or `prob_up never crossed 0.55 / 0.45`
  - or `max one open position`
- Tied to regulation: indirect support for actionability; avoids false "dead system" reading
- Priority: `MEDIUM`
- Effort: `Low`

### Proposal 9 — Replace generic confidence wording with action wording

- Change: instead of `confidence 0.85` plus `prob_up 0.53`, render:
  - `Regime known`
  - `Direction unknown`
- Tied to regulation: §3 uses regime first; direction is secondary
- Priority: `LOW`
- Effort: `Low`

### Proposal 10 — Add transition simplification note

- Change: add compact note:
  - `Transition mode is rare (7.35%); no global pause rule`
- This prevents operator from over-reading regime flickers or waiting for a special transition action that regulation does not support.
- Tied to regulation: §4 and hysteresis calibration
- Priority: `LOW`
- Effort: `Low`

---

## §7 Priority ranking

### High

1. Add regulation action card
2. Reclassify forecast into operator bands
3. Telegram gating by regulation relevance
4. Staleness hard-stop on forecast-dependent panels

### Medium

5. Add "effect on regulation" line to alerts
6. Add cleanup-risk overlay
7. Collapse repetitive alerts into digest mode
8. Expose virtual trader reason-for-no-signal

### Low

9. Replace confidence wording with action wording
10. Add transition simplification note

---

## §8 Implementation paths

### Path A — Fast usability patch

Target:
- dashboard only

Changes:
- add regulation action card
- add operator forecast bands
- hard-stop stale forecast panels
- expose reason-for-no-signal on virtual trader

Likely files:
- [state_builder.py](C:/bot7/services/dashboard/state_builder.py)
- [dashboard.js](C:/bot7/docs/dashboard.js)

Effort:
- `Low to Medium`

Expected effect:
- dashboard becomes interpretable without touching models or classifier

### Path B — Alert stream repair

Target:
- Telegram signal quality

Changes:
- regulation relevance filter
- digest repeated RSI/LEVEL events
- attach `effect on regulation` line

Likely files:
- [telegram_runtime.py](C:/bot7/services/telegram_runtime.py)
- possibly alert formatting helpers

Effort:
- `Medium`

Expected effect:
- sharp reduction in noise and better operator trust

### Path C — Operator-state integration

Target:
- align dashboard with current execution reality

Changes:
- add cleanup blocker banner
- add allowed/conditional/off state from regulation
- emphasize that direction is neutral unless thresholds are crossed

Likely files:
- [state_builder.py](C:/bot7/services/dashboard/state_builder.py)
- [dashboard.js](C:/bot7/docs/dashboard.js)

Effort:
- `Medium`

Expected effect:
- dashboard shifts from "analytics panel" to "operator control surface"

---

## Final assessment

The operator's "0 practical use" judgment is defensible.

The reason is not that the system has no data. The reason is that the current UX presents:
- regime as a label,
- forecast as a probability,
- alerts as raw triggers,

but does not present the one thing the operator actually needs:
- what action state follows from the regulation right now.

The shortest path to usefulness is therefore not better prediction. It is regulation-aware decision translation, alert suppression by relevance, and stale-data invalidation.
