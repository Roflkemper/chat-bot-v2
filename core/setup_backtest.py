from __future__ import annotations


def evaluate_trade(df, entry_idx, horizon=10):
    entry = float(df['close'].iloc[entry_idx])
    future = df.iloc[entry_idx:entry_idx + horizon]
    if len(future) < 2 or entry == 0:
        return None
    max_price = float(future['high'].max())
    min_price = float(future['low'].min())
    mfe = (max_price - entry) / entry * 100
    mae = (entry - min_price) / entry * 100
    return {'mfe': round(mfe,4), 'mae': round(mae,4)}
