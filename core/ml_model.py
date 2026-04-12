from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from config import ENABLE_ML, ML_MODEL_PATH
from core.features import FEATURE_COLUMNS, prepare_features


class MLSignalModel:
    def __init__(self, model_path: str | Path = ML_MODEL_PATH):
        self.model_path = Path(model_path)
        self.model: Pipeline | None = None
        if self.model_path.exists():
            self.load()

    def load(self) -> None:
        self.model = joblib.load(self.model_path)

    def fit_if_possible(self, df: pd.DataFrame) -> None:
        if not ENABLE_ML:
            return
        feat = prepare_features(df).dropna().copy()
        if len(feat) < 120:
            return
        x = feat[FEATURE_COLUMNS]
        y = feat["target_up"]
        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, random_state=42)),
        ])
        pipeline.fit(x, y)
        self.model = pipeline
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipeline, self.model_path)

    def predict_proba_up(self, latest_x: pd.DataFrame) -> float:
        if not ENABLE_ML:
            return 50.0
        if self.model is None:
            return 50.0
        try:
            proba = self.model.predict_proba(latest_x[FEATURE_COLUMNS])[0][1]
            return float(proba * 100.0)
        except Exception:
            return 50.0
