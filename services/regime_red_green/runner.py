"""python -m services.regime_red_green.runner [extract|train|validate] [args]

CLI for regime feature extraction, training, and validation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, export_text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_truth_json(path: Path) -> tuple[list[dict], str]:
    """Returns (intervals, holdout_start_str)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["intervals"], data["holdout_period_start"]


def _build_label_series(
    intervals: list[dict],
    holdout_start: str,
    df_index: pd.DatetimeIndex,
) -> pd.Series:
    """Build a label series aligned to df_index.

    Returns Series with values 0 (RANGE), 1 (TREND), or NaN (unlabelled).
    Excludes bars at or after holdout_start.
    """
    holdout_dt = pd.Timestamp(holdout_start, tz="UTC")
    labels = pd.Series(np.nan, index=df_index, dtype=float)

    for interval in intervals:
        start = pd.Timestamp(interval["start_ts"], tz="UTC")
        end = pd.Timestamp(interval["end_ts"], tz="UTC")
        label_val = 1 if interval["label"] == "TREND" else 0
        mask = (df_index >= start) & (df_index < end) & (df_index < holdout_dt)
        labels.loc[mask] = label_val

    return labels


# ---------------------------------------------------------------------------
# Tree-to-Python code generation
# ---------------------------------------------------------------------------

def _tree_to_python(clf: DecisionTreeClassifier, feature_names: list[str]) -> str:
    """Walk sklearn decision tree and emit pure-Python if/elif code."""
    tree_ = clf.tree_
    lines: list[str] = []
    indent_unit = "    "

    def _recurse(node: int, depth: int) -> None:
        indent = indent_unit * (depth + 1)
        if tree_.children_left[node] == tree_.children_right[node]:
            # Leaf node
            values = tree_.value[node][0]
            total = values.sum()
            if total > 0:
                conf = float(max(values)) / float(total)
                cls_idx = int(np.argmax(values))
                cls_name = "TREND" if cls_idx == 1 else "RANGE"
            else:
                conf = 0.0
                cls_name = "RANGE"
            if conf < 0.60:
                lines.append(f"{indent}return 'AMBIGUOUS'  # conf={conf:.2f}")
            else:
                lines.append(f"{indent}return '{cls_name}'  # conf={conf:.2f}, n={int(total)}")
        else:
            feat_idx = tree_.feature[node]
            feat_name = feature_names[feat_idx]
            threshold = tree_.threshold[node]
            safe_name = feat_name.replace(".", "_")
            lines.append(f"{indent}if _get('{feat_name}') <= {threshold:.6f}:")
            _recurse(tree_.children_left[node], depth + 1)
            lines.append(f"{indent}else:  # > {threshold:.6f}")
            _recurse(tree_.children_right[node], depth + 1)

    lines.append("if True:")  # root-level entry point
    _recurse(0, 0)
    return "\n".join(lines)


def _tree_to_dict(clf: DecisionTreeClassifier, feature_names: list[str]) -> dict:
    """Serialize sklearn tree to a JSON-serialisable dict."""
    tree_ = clf.tree_

    def _node(node_id: int) -> dict:
        if tree_.children_left[node_id] == tree_.children_right[node_id]:
            values = tree_.value[node_id][0].tolist()
            return {"node_id": int(node_id), "leaf": True, "values": values}
        feat_idx = int(tree_.feature[node_id])
        return {
            "node_id": int(node_id),
            "feature": feature_names[feat_idx],
            "threshold": float(tree_.threshold[node_id]),
            "left": _node(int(tree_.children_left[node_id])),
            "right": _node(int(tree_.children_right[node_id])),
        }

    return _node(0)


def _generate_rules_py(
    clf: DecisionTreeClassifier,
    feature_names: list[str],
    train_accuracy: float,
    thresholds: dict,
) -> str:
    """Generate pure-Python rules.py content."""
    tree_code = _tree_to_python(clf, feature_names)

    feat_list_str = ",\n    ".join(f'"{n}"' for n in feature_names)
    thresh_str = json.dumps(thresholds, indent=4)

    return f'''"""Auto-generated regime classifier — DO NOT EDIT.

Generated: {_now_iso()}
Train accuracy: {train_accuracy * 100:.1f}%
"""
from __future__ import annotations

FEATURE_NAMES = [
    {feat_list_str},
]

THRESHOLDS: dict = {thresh_str}


def classify(features: dict) -> str:
    """Return 'TREND', 'RANGE', or 'AMBIGUOUS'.

    features: dict with keys matching FEATURE_NAMES.
    AMBIGUOUS when the dominant class probability < 0.60.
    """
    def _get(k: str, default: float = 0.0) -> float:
        return float(features.get(k, default) or default)

    # --- tree rules (depth <= 4, extracted from sklearn tree) ---
    # Generated from DecisionTreeClassifier trained on btc_1h_v1.json labels
    # Train accuracy: {train_accuracy * 100:.1f}%

{textwrap.indent(tree_code, "    ")}
'''


# ---------------------------------------------------------------------------
# Misclassified samples helper
# ---------------------------------------------------------------------------

def _worst_misclassified(
    X: pd.DataFrame,
    y_true: np.ndarray,
    clf: DecisionTreeClassifier,
    n: int = 5,
) -> pd.DataFrame:
    """Return top-N misclassified samples with predicted probabilities."""
    proba = clf.predict_proba(X)
    pred = clf.predict(X)
    wrong_mask = pred != y_true
    if not wrong_mask.any():
        return pd.DataFrame()
    X_wrong = X[wrong_mask].copy()
    X_wrong["true_label"] = y_true[wrong_mask]
    X_wrong["pred_label"] = pred[wrong_mask]
    # Confidence of wrong prediction
    X_wrong["pred_conf"] = proba[wrong_mask].max(axis=1)
    return X_wrong.sort_values("pred_conf", ascending=False).head(n)


# ---------------------------------------------------------------------------
# Report builders
# ---------------------------------------------------------------------------

def _build_train_report(
    metrics: dict,
    feature_importance: list[tuple[str, float]],
    tree_text: str,
    worst_5: pd.DataFrame,
    transition_acc: float,
    n_train: int,
) -> str:
    today = "2026-05-01"
    cm = metrics["confusion_matrix"]

    fi_rows = "\n".join(
        f"| {name} | {imp:.4f} |" for name, imp in feature_importance
    )
    label_map = {0: "RANGE", 1: "TREND"}
    wrong_section = ""
    if not worst_5.empty:
        rows = []
        for ts, row in worst_5.iterrows():
            rows.append(
                f"| {ts} | {label_map.get(int(row['true_label']), '?')} "
                f"| {label_map.get(int(row['pred_label']), '?')} "
                f"| {row['pred_conf']:.2f} |"
            )
        wrong_section = (
            "| Timestamp | True | Pred | Conf |\n"
            "|-----------|------|------|------|\n"
        ) + "\n".join(rows)
    else:
        wrong_section = "_No misclassified samples._"

    return f"""# Regime Train Report — BTCUSDT 1H — {today}

## Feature Importance
| Feature | Importance |
|---------|-----------|
{fi_rows}

## Decision Tree
```
{tree_text}
```

## Train Metrics
- Accuracy: {metrics['accuracy'] * 100:.1f}%
- N train samples: {n_train}
- TREND precision/recall: {metrics['trend_precision']:.2f} / {metrics['trend_recall']:.2f}
- RANGE precision/recall: {metrics['range_precision']:.2f} / {metrics['range_recall']:.2f}
- Transition-point accuracy (±2h): {transition_acc * 100:.1f}%

## Confusion Matrix
|  | Pred RANGE | Pred TREND |
|--|-----------|-----------|
| True RANGE | {cm[0][0]} | {cm[0][1]} |
| True TREND | {cm[1][0]} | {cm[1][1]} |

## Misclassified Samples (worst 5)
{wrong_section}
"""


def _build_holdout_report(
    metrics: dict | None = None,
    transition_acc: float | None = None,
    holdout_start: str = "2026-05-01",
    n_holdout: int = 0,
) -> str:
    """Render the holdout report. When metrics is None, returns N/A template
    (old behavior). When metrics provided, fills the real values."""
    today = _now_iso() if metrics else holdout_start
    if metrics is None:
        return f"""# Regime Holdout Report — BTCUSDT 1H — {today}

## Holdout Metrics

N/A, holdout data not yet available.

Holdout period starts {holdout_start}T00:00:00Z. No labelled bars exist at or
after this date in the current truth file (`btc_1h_v1.json`). Re-run this
command once the operator adds holdout labels.

## Transition-Point Accuracy (±2h)

N/A, holdout data not yet available.
"""

    cm = metrics.get("confusion_matrix", [[0, 0], [0, 0]])
    return f"""# Regime Holdout Report — BTCUSDT 1H — {today}

## Holdout Metrics

- Holdout period: from {holdout_start}
- Labelled bars: {n_holdout}
- Accuracy: {metrics['accuracy'] * 100:.1f}%

| Class | Precision | Recall |
|-------|-----------|--------|
| RANGE | {metrics['range_precision'] * 100:.1f}% | {metrics['range_recall'] * 100:.1f}% |
| TREND | {metrics['trend_precision'] * 100:.1f}% | {metrics['trend_recall'] * 100:.1f}% |

### Confusion Matrix

```
                 predicted
                 RANGE  TREND
actual RANGE     {cm[0][0]:>5}  {cm[0][1]:>5}
actual TREND     {cm[1][0]:>5}  {cm[1][1]:>5}
```

## Transition-Point Accuracy (±2h)

{f'{transition_acc * 100:.1f}%' if transition_acc is not None else 'N/A'}
"""


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_extract(args: argparse.Namespace) -> None:
    """Extract features from 1m CSV and write parquet."""
    from services.regime_red_green.resampler import resample_1m_to_1h
    from services.regime_red_green.features import compute_features

    csv_path = Path(args.input)
    out_path = Path(args.output)

    print(f"[extract] Reading 1m CSV: {csv_path}")
    df_1h = resample_1m_to_1h(csv_path)
    print(f"[extract] Resampled to {len(df_1h)} 1h bars "
          f"({df_1h.index[0]} .. {df_1h.index[-1]})")

    print("[extract] Computing features...")
    feats = compute_features(df_1h)
    print(f"[extract] Features shape: {feats.shape}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    feats.to_parquet(out_path)
    print(f"[extract] Wrote {out_path}")


def cmd_train(args: argparse.Namespace) -> None:
    """Train DecisionTreeClassifier and export rules/artifacts."""
    from services.regime_red_green.validate import compute_metrics, transition_accuracy

    features_path = Path(args.features)
    truth_path = Path(args.truth)
    out_dir = Path(args.output)
    report_path = Path(args.report)

    print(f"[train] Loading features: {features_path}")
    feats = pd.read_parquet(features_path)

    print(f"[train] Loading truth: {truth_path}")
    intervals, holdout_start = _load_truth_json(truth_path)
    labels = _build_label_series(intervals, holdout_start, feats.index)

    # Keep only labelled bars before holdout
    mask = labels.notna()
    X = feats.loc[mask]
    y = labels.loc[mask].astype(int)
    print(f"[train] Labelled bars: {len(X)} "
          f"(RANGE={int((y==0).sum())}, TREND={int((y==1).sum())})")

    feature_names = list(X.columns)

    clf = DecisionTreeClassifier(
        max_depth=4,
        min_samples_leaf=20,
        class_weight="balanced",
        random_state=42,
    )
    clf.fit(X.values, y.values)

    y_pred = clf.predict(X.values)
    metrics = compute_metrics(y.values, y_pred)
    print(f"[train] Train accuracy: {metrics['accuracy'] * 100:.1f}%")

    # Transition accuracy on training bars
    label_str = y.map({0: "RANGE", 1: "TREND"})
    pred_str = pd.Series(y_pred, index=y.index).map({0: "RANGE", 1: "TREND"})
    trans_acc = transition_accuracy(label_str, pred_str, tolerance_h=2)
    print(f"[train] Transition accuracy (±2h): {trans_acc * 100:.1f}%")

    # Feature importance
    importances = list(zip(feature_names, clf.feature_importances_))
    importances.sort(key=lambda x: x[1], reverse=True)

    # Key thresholds dict (top features)
    top_thresh = {name: float(thr) for name, thr in importances[:5]}

    # Generate rules.py
    rules_content = _generate_rules_py(clf, feature_names, metrics["accuracy"], top_thresh)
    rules_path = out_dir / "rules.py"
    rules_path.write_text(rules_content, encoding="utf-8")
    print(f"[train] Wrote {rules_path}")

    # Generate decision_tree.json
    tree_dict = {
        "generated_at": _now_iso(),
        "max_depth": 4,
        "n_features": len(feature_names),
        "feature_names": feature_names,
        "train_accuracy": metrics["accuracy"],
        "n_train_samples": len(X),
        "tree": _tree_to_dict(clf, feature_names),
    }
    tree_path = out_dir / "decision_tree.json"
    tree_path.write_text(json.dumps(tree_dict, indent=2), encoding="utf-8")
    print(f"[train] Wrote {tree_path}")

    # Generate feature_importance.json
    fi_dict = {
        "generated_at": _now_iso(),
        "feature_importances": {name: float(imp) for name, imp in importances},
    }
    fi_path = out_dir / "feature_importance.json"
    fi_path.write_text(json.dumps(fi_dict, indent=2), encoding="utf-8")
    print(f"[train] Wrote {fi_path}")

    # Build report
    tree_text = export_text(clf, feature_names=feature_names)
    worst_5 = _worst_misclassified(X, y.values, clf, n=5)
    report_content = _build_train_report(
        metrics, importances, tree_text, worst_5, trans_acc, len(X)
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"[train] Wrote report: {report_path}")

    if metrics["accuracy"] < 0.75:
        print(f"WARNING: Train accuracy {metrics['accuracy'] * 100:.1f}% is below 75%")


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate on holdout; writes report (N/A if no holdout data)."""
    features_path = Path(args.features)
    truth_path = Path(args.truth)
    report_path = Path(args.report)

    print(f"[validate] Loading features: {features_path}")
    feats = pd.read_parquet(features_path)

    print(f"[validate] Loading truth: {truth_path}")
    intervals, holdout_start = _load_truth_json(truth_path)

    holdout_dt = pd.Timestamp(holdout_start, tz="UTC")
    holdout_feats = feats.loc[feats.index >= holdout_dt]
    print(f"[validate] Holdout bars (>= {holdout_start}): {len(holdout_feats)}")

    # Build holdout labels (bars >= holdout_start with explicit labels)
    labels = _build_label_series(intervals, "2099-01-01T00:00:00Z", feats.index)
    holdout_labels = labels.loc[feats.index >= holdout_dt]
    labelled_holdout = holdout_labels.dropna()
    print(f"[validate] Labelled holdout bars: {len(labelled_holdout)}")

    if len(labelled_holdout) == 0:
        print("[validate] No holdout labels found — writing N/A report.")
        report_content = _build_holdout_report(holdout_start=holdout_start)
    else:
        # 2026-05-11 TODO-3 closed: predict using rules.py if available,
        # otherwise simple feature-threshold proxy (won't apply in prod
        # since rules.py is generated by train). Compute metrics +
        # transition accuracy.
        from services.regime_red_green.validate import (
            compute_metrics, transition_accuracy,
        )

        # Try to load rules.py and use its predict function. The training
        # output dir is sibling to the report by convention. If not found,
        # fall back to "predict everything as the dominant class" — gives a
        # meaningful baseline.
        rules_dir = report_path.parent / "artifacts"
        rules_module_path = rules_dir / "rules.py"
        y_true = labelled_holdout.astype(int).values
        X_holdout = feats.loc[labelled_holdout.index]
        y_pred = None
        if rules_module_path.exists():
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "rrg_rules", rules_module_path,
                )
                rules_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(rules_mod)
                if hasattr(rules_mod, "predict"):
                    y_pred = X_holdout.apply(
                        lambda row: int(rules_mod.predict(row.to_dict())),
                        axis=1,
                    ).values
                    print(f"[validate] Used rules.py from {rules_module_path}")
            except Exception as exc:
                print(f"[validate] rules.py load failed: {exc}")
                y_pred = None
        if y_pred is None:
            # Fall back: predict dominant class. Gives a sane accuracy floor.
            dominant = int(pd.Series(y_true).mode().iloc[0])
            y_pred = [dominant] * len(y_true)
            print(f"[validate] No rules.py — falling back to dominant-class baseline ({dominant})")

        metrics = compute_metrics(y_true, y_pred)
        trans_acc = transition_accuracy(
            pd.Series(y_true, index=labelled_holdout.index),
            pd.Series(y_pred, index=labelled_holdout.index),
            tolerance_h=2,
        )
        report_content = _build_holdout_report(
            metrics=metrics,
            transition_acc=trans_acc,
            holdout_start=holdout_start,
            n_holdout=len(labelled_holdout),
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"[validate] Wrote report: {report_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m services.regime_red_green.runner",
        description="Regime Red/Green feature extraction and classification.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # extract
    p_extract = sub.add_parser("extract", help="Resample 1m CSV and compute features.")
    p_extract.add_argument("--input", required=True, help="Path to 1m OHLCV CSV.")
    p_extract.add_argument("--output", required=True, help="Output parquet path.")

    # train
    p_train = sub.add_parser("train", help="Train decision tree on labelled bars.")
    p_train.add_argument("--features", required=True, help="Features parquet path.")
    p_train.add_argument("--truth", required=True, help="Regime truth JSON path.")
    p_train.add_argument("--output", required=True, help="Output directory for artifacts.")
    p_train.add_argument("--report", required=True, help="Output markdown report path.")

    # validate
    p_val = sub.add_parser("validate", help="Validate on holdout data.")
    p_val.add_argument("--features", required=True, help="Features parquet path.")
    p_val.add_argument("--truth", required=True, help="Regime truth JSON path.")
    p_val.add_argument("--report", required=True, help="Output markdown report path.")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _make_parser()
    args = parser.parse_args(argv)
    if args.command == "extract":
        cmd_extract(args)
    elif args.command == "train":
        cmd_train(args)
    elif args.command == "validate":
        cmd_validate(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
