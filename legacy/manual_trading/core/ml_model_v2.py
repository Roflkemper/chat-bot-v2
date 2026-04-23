from __future__ import annotations

from dataclasses import dataclass
from math import exp
from pathlib import Path
from typing import Iterable, Dict, Any

import joblib
import numpy as np

try:
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover
    XGBClassifier = None

STATE_DIR = Path('models')


@dataclass
class _RuleModel:
    setup_type: str

    def predict_proba(self, X):
        x = np.asarray(X, dtype=float).reshape(1, -1)[0]
        # FEATURE_COLUMNS order:
        # ret1, ret5, ret10, vol_ratio, trend_strength, distance_ema20_atr,
        # distance_ema50_atr, rsi14, hl_range, body_to_range
        values = list(x) + [0.0] * max(0, 10 - len(x))
        ret1, ret5, ret10, vol_ratio, trend_strength, dist20, dist50, rsi, hl_range, body_to_range = values[:10]
        if self.setup_type == 'trend':
            logit = (
                0.70 * ret5 + 0.30 * ret1 + 0.20 * ret10 + 0.30 * trend_strength
                + 0.12 * body_to_range + 0.10 * max(0.0, vol_ratio - 1.0)
                - 0.10 * abs(dist20)
            )
        elif self.setup_type == 'range':
            logit = (
                -0.35 * ret1 - 0.20 * ret5 - 0.15 * trend_strength
                + 0.25 * max(0.0, 1.0 - abs(dist20)) + 0.18 * (55.0 - abs(rsi - 50.0)) / 10.0
                + 0.08 * hl_range
            )
        else:  # countertrend
            logit = (
                -0.60 * ret1 - 0.30 * ret5 - 0.15 * ret10 - 0.15 * trend_strength
                + 0.16 * abs(dist20) + 0.14 * (rsi - 50.0) / 10.0 - 0.08 * body_to_range
            )
        logit = max(-4.0, min(4.0, logit))
        p = 1.0 / (1.0 + exp(-logit))
        return np.array([[1.0 - p, p]], dtype=float)


class SetupModels:
    def __init__(self):
        self.models: Dict[str, Any] = {}
        self.meta: Dict[str, Dict[str, Any]] = {}
        for setup_type in ('trend', 'countertrend', 'range'):
            self.models[setup_type] = self._load_or_stub(setup_type)

    def _load_or_stub(self, setup_type: str):
        model_path = STATE_DIR / f'xgb_{setup_type}.joblib'
        if model_path.exists():
            try:
                model = joblib.load(model_path)
                self.meta[setup_type] = {'status': 'trained', 'model_path': str(model_path)}
                return model
            except Exception as exc:
                self.meta[setup_type] = {'status': 'broken_model', 'model_path': str(model_path), 'error': str(exc)}
        if XGBClassifier is not None:
            _ = XGBClassifier(
                n_estimators=120,
                max_depth=3,
                learning_rate=0.06,
                subsample=0.9,
                colsample_bytree=0.9,
                eval_metric='logloss',
                random_state=42,
            )
        self.meta[setup_type] = {'status': 'rule_fallback', 'model_path': None}
        return _RuleModel(setup_type)

    def describe(self, setup_type: str) -> Dict[str, Any]:
        return dict(self.meta.get(setup_type) or {'status': 'unknown', 'model_path': None})

    def predict(self, X: Iterable[float], setup_type: str):
        model = self.models.get(setup_type) or self.models['countertrend']
        arr = np.asarray(list(X), dtype=float).reshape(1, -1)
        try:
            prob = float(model.predict_proba(arr)[0][1])
        except Exception:
            prob = 0.5
        return max(0.01, min(0.99, prob))

    def predict_bundle(self, X: Iterable[float], setup_type: str) -> Dict[str, Any]:
        features = [float(v or 0.0) for v in list(X)]
        prob = self.predict(features, setup_type)
        edge = abs(prob - 0.5) * 2.0
        meta = self.describe(setup_type)
        status = str(meta.get('status') or 'unknown')
        source = 'xgboost_v2' if status == 'trained' else 'ml_rule_fallback'
        confidence = min(0.98, 0.50 + edge * (0.42 if status == 'trained' else 0.28))
        follow_through = prob if setup_type == 'trend' else max(0.01, min(0.99, 0.45 + (prob - 0.5) * 0.60))
        reversal = max(0.01, min(0.99, 1.0 - prob if setup_type == 'countertrend' else 0.35 + (0.5 - prob) * 0.50))
        setup_quality = max(0.01, min(0.99, 0.42 + edge * (0.45 if status == 'trained' else 0.25)))
        return {
            'setup_type': setup_type,
            'probability': round(prob, 4),
            'edge_strength': round(edge, 4),
            'confidence': round(confidence, 4),
            'follow_through_probability': round(follow_through, 4),
            'reversal_probability': round(reversal, 4),
            'setup_quality_probability': round(setup_quality, 4),
            'features_used': len(features),
            'source': source,
            'model_status': status,
            'model_path': meta.get('model_path'),
        }
