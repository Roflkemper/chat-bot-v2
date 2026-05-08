"""Validation metrics for regime classification."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute accuracy, precision, recall per class.

    Parameters
    ----------
    y_true : array-like of int (0=RANGE, 1=TREND)
    y_pred : array-like of int (0=RANGE, 1=TREND)

    Returns
    -------
    dict with keys: accuracy, range_precision, range_recall, trend_precision,
                    trend_recall, confusion_matrix
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    accuracy = float(np.mean(y_true == y_pred))
    prec, rec, _, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=[0, 1], zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])

    return {
        "accuracy": accuracy,
        "range_precision": float(prec[0]),
        "range_recall": float(rec[0]),
        "trend_precision": float(prec[1]),
        "trend_recall": float(rec[1]),
        "confusion_matrix": cm.tolist(),
    }


def transition_accuracy(
    labels_series: pd.Series,
    preds_series: pd.Series,
    tolerance_h: int = 2,
) -> float:
    """Check how well predicted transitions align with ground-truth transitions.

    For each ground truth transition (RANGE->TREND or TREND->RANGE),
    check if there's a predicted transition within ±tolerance_h hours.

    Returns hit_rate in [0.0, 1.0]. Returns 0.0 if no transitions exist.
    """
    # Align on common index
    common_idx = labels_series.index.intersection(preds_series.index).sort_values()
    if len(common_idx) < 2:
        return 0.0

    labels = labels_series.loc[common_idx]
    preds = preds_series.loc[common_idx]

    # Find ground truth transition indices (position-based)
    label_vals = labels.values
    gt_transitions = []
    for i in range(1, len(label_vals)):
        if label_vals[i] != label_vals[i - 1]:
            gt_transitions.append(i)

    if not gt_transitions:
        return 0.0

    # Find predicted transition positions
    pred_vals = preds.values
    pred_transitions = set()
    for i in range(1, len(pred_vals)):
        if pred_vals[i] != pred_vals[i - 1]:
            pred_transitions.add(i)

    hits = 0
    for gt_pos in gt_transitions:
        for offset in range(-tolerance_h, tolerance_h + 1):
            if (gt_pos + offset) in pred_transitions:
                hits += 1
                break

    return hits / len(gt_transitions)
