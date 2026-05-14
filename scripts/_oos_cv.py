"""OOS CV for all 3 regimes x 3 horizons x 5 windows."""
import sys, time, json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.market_forward_analysis.calibration import (
    _compute_outcomes, _compute_signals_batch, _signals_to_prob_up, _brier_score, _weight_perturbations
)
from services.market_forward_analysis.regime_models.markup import _MARKUP_BASE_WEIGHTS
from services.market_forward_analysis.regime_models.markdown import _MARKDOWN_BASE_WEIGHTS
from services.market_forward_analysis.regime_models.range import _RANGE_BASE_WEIGHTS

t0 = time.time()

regimes = {
    "MARKUP":   ("data/forecast_features/regime_splits/regime_markup.parquet",   _MARKUP_BASE_WEIGHTS),
    "MARKDOWN": ("data/forecast_features/regime_splits/regime_markdown.parquet", _MARKDOWN_BASE_WEIGHTS),
    "RANGE":    ("data/forecast_features/regime_splits/regime_range.parquet",    _RANGE_BASE_WEIGHTS),
}


def cv_run(parquet_path, base_weights):
    df = pd.read_parquet(parquet_path)
    outcomes = _compute_outcomes(df["close"])
    valid = outcomes.notna().all(axis=1)
    df = df[valid]; outcomes = outcomes[valid]
    n = len(df)

    win_specs = [
        ("W1", 0, int(n * 0.50), int(n * 0.50), int(n * 0.62)),
        ("W2", 0, int(n * 0.62), int(n * 0.62), int(n * 0.74)),
        ("W3", 0, int(n * 0.74), int(n * 0.74), int(n * 0.86)),
        ("W4", 0, int(n * 0.86), int(n * 0.95), n),
        ("W5", 0, int(n * 0.80), int(n * 0.80), n),
    ]

    results = {hz: {} for hz in ["1h", "4h", "1d"]}
    for label, tr_lo, tr_hi, te_lo, te_hi in win_specs:
        tf = df.iloc[tr_lo:tr_hi]; te = df.iloc[te_lo:te_hi]
        to = outcomes.iloc[tr_lo:tr_hi]; teo = outcomes.iloc[te_lo:te_hi]
        test_period = "%s..%s" % (df.index[te_lo].date(), df.index[te_hi - 1].date())
        for hz in ["1h", "4h", "1d"]:
            train_sigs = _compute_signals_batch(tf, horizon=hz)
            test_sigs  = _compute_signals_batch(te, horizon=hz)
            ta  = to[f"actual_dir_{hz}"].values
            tea = teo[f"actual_dir_{hz}"].values
            bw = base_weights[hz]
            best_w = list(bw)
            best_b = _brier_score(_signals_to_prob_up(train_sigs, bw), ta)
            for dw in _weight_perturbations(bw, n_trials=400):
                b = _brier_score(_signals_to_prob_up(train_sigs, dw), ta)
                if b < best_b:
                    best_b = b; best_w = dw
            test_brier = _brier_score(_signals_to_prob_up(test_sigs, best_w), tea)
            sharp = float(_signals_to_prob_up(test_sigs, best_w).std())
            up = float((tea == 1).mean()); dn = float((tea == -1).mean()); rng = float((tea == 0).mean())
            results[hz][label] = {
                "brier": round(test_brier, 4),
                "sharp": round(sharp, 4),
                "period": test_period,
                "up_frac": round(up, 3),
                "down_frac": round(dn, 3),
                "range_frac": round(rng, 3),
                "weights": [round(w, 3) for w in best_w],
            }
    return results


full_report = {}
for regime_name, (path, bw) in regimes.items():
    sys.stdout.buffer.write(("Running CV for %s...\n" % regime_name).encode("utf-8", "replace"))
    full_report[regime_name] = cv_run(path, bw)

matrix = {}
for regime, hz_results in full_report.items():
    matrix[regime] = {}
    for hz, win_data in hz_results.items():
        briers = [v["brier"] for v in win_data.values()]
        matrix[regime][hz] = {
            "min": round(min(briers), 4),
            "max": round(max(briers), 4),
            "mean": round(float(np.mean(briers)), 4),
            "median": round(float(np.median(briers)), 4),
            "variance": round(max(briers) - min(briers), 4),
            "windows": win_data,
        }


def cell_verdict(stats):
    m = stats["mean"]; mx = stats["max"]; var = stats["variance"]
    if m <= 0.22 and mx <= 0.25:
        return "GREEN"
    if m <= 0.25 and mx <= 0.28:
        return "YELLOW"
    if var > 0.05 or mx > 0.28:
        return "WINDOW-SENS" if m <= 0.27 else "QUALITATIVE"
    if m > 0.28:
        return "QUALITATIVE"
    return "YELLOW"


for regime in matrix:
    for hz in matrix[regime]:
        matrix[regime][hz]["verdict"] = cell_verdict(matrix[regime][hz])

lines = ["", "=== OOS CV MATRIX (5 windows) ===", ""]
lines.append("%-9s %-3s | %-7s %-7s %-7s %-7s | %-12s" % ("Regime", "Hz", "min", "max", "mean", "range", "verdict"))
lines.append("-" * 80)
for regime in ["MARKUP", "MARKDOWN", "RANGE"]:
    for hz in ["1h", "4h", "1d"]:
        s = matrix[regime][hz]
        lines.append("%-9s %-3s | %.4f  %.4f  %.4f  %.4f  | %s" % (
            regime, hz, s["min"], s["max"], s["mean"], s["variance"], s["verdict"]))
    lines.append("-" * 80)

lines.append("")
lines.append("=== Per-window Brier ===")
for regime in ["MARKUP", "MARKDOWN", "RANGE"]:
    lines.append("")
    lines.append("--- %s ---" % regime)
    for hz in ["1h", "4h", "1d"]:
        win_data = full_report[regime][hz]
        b_str = "  ".join("%s=%.4f" % (w, win_data[w]["brier"]) for w in ["W1", "W2", "W3", "W4", "W5"])
        lines.append("  %s  %s" % (hz, b_str))

lines.append("")
lines.append("=== Regime-Transition Zones (variance >0.05) ===")
for regime in ["MARKUP", "MARKDOWN", "RANGE"]:
    for hz in ["1h", "4h", "1d"]:
        s = matrix[regime][hz]
        if s["variance"] > 0.05:
            worst_w = max(s["windows"].items(), key=lambda x: x[1]["brier"])
            wd = worst_w[1]
            lines.append("  %s %s var=%.4f worst=%s brier=%.4f period=%s outcome=d%.0f%%/u%.0f%%/r%.0f%%" % (
                regime, hz, s["variance"], worst_w[0], wd["brier"], wd["period"],
                wd["down_frac"] * 100, wd["up_frac"] * 100, wd["range_frac"] * 100))

lines.append("")
lines.append("=== FINAL VALIDATED HYBRID DELIVERY MATRIX ===")
lines.append("%-9s | %-12s %-12s %-12s" % ("Regime", "1h", "4h", "1d"))
lines.append("-" * 55)
for regime in ["MARKUP", "MARKDOWN", "RANGE"]:
    row = [regime] + [matrix[regime][hz]["verdict"] for hz in ["1h", "4h", "1d"]]
    lines.append("%-9s | %-12s %-12s %-12s" % tuple(row))

numeric = sum(1 for r in matrix for h in matrix[r] if matrix[r][h]["verdict"] in ("GREEN", "YELLOW", "WINDOW-SENS"))
lines.append("")
lines.append("Numeric cells: %d/9" % numeric)

ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
report_path = Path("data/calibration") / f"oos_validation_{ts}.json"
report_path.write_text(json.dumps({"matrix": matrix, "full": full_report}, indent=2, default=str), encoding="utf-8")
lines.append("")
lines.append("Report: %s" % report_path)
lines.append("Wall-clock: %.1fs" % (time.time() - t0))

sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8", "replace"))
