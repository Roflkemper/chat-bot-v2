# state_drift_detector
Trigger: any task touching live bots, GinArea API, Bitmex positions, market_collector.

Before/after task verify:
- GinArea bots respond to API (GET /bots returns expected count).
- Bitmex positions match latest tracker snapshot.
- Recent liquidations present in market_collector parquets (last 1h).

On drift:
STATE DRIFT DETECTED:

[system]: expected [X], actual [Y]
last sync: [timestamp]
Operator action: investigate before continuing.


Drift = silent failure. Catch before it compounds.
