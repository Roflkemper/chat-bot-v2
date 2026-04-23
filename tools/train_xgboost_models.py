from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import joblib
import pandas as pd

from core.features import FEATURE_COLUMNS

try:
    from xgboost import XGBClassifier
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"xgboost import failed: {exc}")


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == '.jsonl':
        rows = []
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
    except Exception:
        return []
    return []


def _flatten_features(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for col in FEATURE_COLUMNS:
        if col in row:
            out[col] = row.get(col)
    feat = row.get('features') if isinstance(row.get('features'), dict) else {}
    for col in FEATURE_COLUMNS:
        if col in feat and col not in out:
            out[col] = feat.get(col)
    decision = row.get('decision_snapshot') if isinstance(row.get('decision_snapshot'), dict) else {}
    for col in FEATURE_COLUMNS:
        if col in decision and col not in out:
            out[col] = decision.get(col)
    return out


def _extract_label(row: dict[str, Any]) -> int | None:
    for key in ('target_up', 'label', 'result_label', 'y'):
        if key in row:
            try:
                return int(row.get(key))
            except Exception:
                pass
    result_pct = row.get('result_pct')
    if result_pct is not None:
        try:
            return 1 if float(result_pct) > 0 else 0
        except Exception:
            return None
    return None


def _extract_setup_type(row: dict[str, Any]) -> str:
    for key in ('setup_type', 'regime_bucket', 'strategy_type'):
        val = str(row.get(key) or '').strip().lower()
        if val in {'trend', 'countertrend', 'range'}:
            return val
    return 'countertrend'


def build_dataset(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    out_rows = []
    for row in rows:
        feat = _flatten_features(row)
        label = _extract_label(row)
        if label is None:
            continue
        payload = {col: float(feat.get(col) or 0.0) for col in FEATURE_COLUMNS}
        payload['target_up'] = int(label)
        payload['setup_type'] = _extract_setup_type(row)
        out_rows.append(payload)
    return pd.DataFrame(out_rows)


def train_one(df: pd.DataFrame, setup_type: str, out_dir: Path, min_rows: int = 50) -> str:
    subset = df[df['setup_type'] == setup_type].copy()
    if len(subset) < min_rows:
        return f"{setup_type}: мало данных ({len(subset)})"
    X = subset[FEATURE_COLUMNS].fillna(0.0)
    y = subset['target_up'].astype(int)
    model = XGBClassifier(
        n_estimators=180,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric='logloss',
        random_state=42,
    )
    model.fit(X, y)
    out_path = out_dir / f'xgb_{setup_type}.joblib'
    joblib.dump(model, out_path)
    return f"{setup_type}: OK ({len(subset)} rows) -> {out_path}"


def main() -> None:
    ap = argparse.ArgumentParser(description='Train XGBoost setup models from journal-style data.')
    ap.add_argument('--input', default='state/trade_journal.jsonl')
    ap.add_argument('--output-dir', default='models')
    ap.add_argument('--min-rows', type=int, default=50)
    args = ap.parse_args()

    rows = _read_rows(Path(args.input))
    df = build_dataset(rows)
    if df.empty:
        raise SystemExit('dataset is empty; add journal rows with features + labels/result_pct')

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    notes = [f'dataset rows: {len(df)}']
    for setup_type in ('trend', 'countertrend', 'range'):
        notes.append(train_one(df, setup_type, out_dir, min_rows=args.min_rows))
    report = out_dir / 'xgb_train_report.txt'
    report.write_text("\n".join(notes), encoding='utf-8')
    (out_dir / 'xgb_train_report.json').write_text(json.dumps({'dataset_rows': int(len(df)), 'notes': notes}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(report.read_text(encoding='utf-8'))


if __name__ == '__main__':
    main()
