"""Auto-generated regime classifier — DO NOT EDIT.

Generated: 2026-05-01T20:34:26+00:00
Train accuracy: 77.5%
"""
from __future__ import annotations

FEATURE_NAMES = [
    "price_band_height_pct_24h",
    "price_band_height_pct_48h",
    "time_inside_band_24h_pct",
    "pivot_density_24h",
    "body_to_range_max_4h",
    "single_bar_roc_max_pct_4h",
    "displacement_count_4h",
    "closed_outside_band_24h",
    "vol_z_score_4h",
    "vol_cumulative_4h_vs_avg",
    "roc_4h_pct",
    "roc_12h_pct",
    "roc_24h_pct",
    "consec_higher_highs_4h",
    "consec_lower_lows_4h",
    "atr_14h",
    "atr_inside_band_ratio",
]

THRESHOLDS: dict = {
    "price_band_height_pct_24h": 0.454539523864814,
    "pivot_density_24h": 0.2205573146191288,
    "vol_cumulative_4h_vs_avg": 0.12870817363750417,
    "roc_24h_pct": 0.07230859308053579,
    "atr_inside_band_ratio": 0.05774034024989178
}


def classify(features: dict) -> str:
    """Return 'TREND', 'RANGE', or 'AMBIGUOUS'.

    features: dict with keys matching FEATURE_NAMES.
    AMBIGUOUS when the dominant class probability < 0.60.
    """
    def _get(k: str, default: float = 0.0) -> float:
        return float(features.get(k, default) or default)

    # --- tree rules (depth <= 4, extracted from sklearn tree) ---
    # Generated from DecisionTreeClassifier trained on btc_1h_v1.json labels
    # Train accuracy: 77.5%

    if True:
        if _get('price_band_height_pct_24h') <= 4.973230:
            if _get('pivot_density_24h') <= 11.500000:
                if _get('pivot_density_24h') <= 10.500000:
                    if _get('atr_inside_band_ratio') <= 0.157171:
                        return 'RANGE'  # conf=0.74, n=0
                    else:  # > 0.157171
                        return 'RANGE'  # conf=0.99, n=1
                else:  # > 10.500000
                    if _get('atr_inside_band_ratio') <= 0.229114:
                        return 'RANGE'  # conf=0.68, n=0
                    else:  # > 0.229114
                        return 'RANGE'  # conf=0.91, n=0
            else:  # > 11.500000
                if _get('vol_cumulative_4h_vs_avg') <= 0.541944:
                    if _get('price_band_height_pct_48h') <= 5.451666:
                        return 'RANGE'  # conf=0.88, n=1
                    else:  # > 5.451666
                        return 'AMBIGUOUS'  # conf=0.52
                else:  # > 0.541944
                    if _get('roc_24h_pct') <= -0.251817:
                        return 'TREND'  # conf=0.69, n=0
                    else:  # > -0.251817
                        return 'AMBIGUOUS'  # conf=0.57
        else:  # > 4.973230
            if _get('atr_inside_band_ratio') <= 0.200179:
                if _get('pivot_density_24h') <= 10.500000:
                    if _get('roc_12h_pct') <= 2.864755:
                        return 'AMBIGUOUS'  # conf=0.54
                    else:  # > 2.864755
                        return 'TREND'  # conf=0.96, n=0
                else:  # > 10.500000
                    if _get('price_band_height_pct_48h') <= 5.652842:
                        return 'AMBIGUOUS'  # conf=0.60
                    else:  # > 5.652842
                        return 'TREND'  # conf=0.94, n=0
            else:  # > 0.200179
                return 'RANGE'  # conf=0.65, n=1
