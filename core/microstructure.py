
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class OrderBookLevel:
    price: float
    size: float


@dataclass
class MicroSnapshot:
    bids: Optional[List[OrderBookLevel]] = None
    asks: Optional[List[OrderBookLevel]] = None
    aggressive_buy_ratio: float = 0.5
    aggressive_sell_ratio: float = 0.5
    recent_spread_bps: float = 2.0


def build_microstructure_context(snapshot: Optional[MicroSnapshot] = None, df=None) -> Dict:
    snapshot = snapshot or MicroSnapshot()
    if df is None or getattr(df, 'empty', True):
        return {'micro_bias':'NEUTRAL','confidence':50.0,'absorption_side':'NONE','compression':'UNKNOWN','last_swing':'UNKNOWN','summary':'micro_bias=NEUTRAL, imbalance=0.50, spread_bps=2.0, absorption=NONE'}

    close = df['close'].astype(float)
    open_ = df['open'].astype(float)
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    volume = df['volume'].astype(float) if 'volume' in df.columns else close * 0 + 1.0
    n = len(df)
    recent = min(12, n)
    c_now = float(close.iloc[-1])
    c_prev = float(close.iloc[-2]) if n >= 2 else c_now
    body = (close - open_).abs()
    ranges = (high - low).clip(lower=1e-9)
    body_ratio = (body / ranges).tail(recent)
    up_closes = int((close.diff().tail(recent) > 0).sum())
    down_closes = int((close.diff().tail(recent) < 0).sum())
    buy_proxy = float((((close > open_).astype(float) * volume).tail(recent)).sum())
    sell_proxy = float((((close < open_).astype(float) * volume).tail(recent)).sum())
    total = max(buy_proxy + sell_proxy, 1e-9)
    buy_ratio = buy_proxy / total
    sell_ratio = sell_proxy / total
    spread_bps = float((ranges.tail(recent).mean() / max(c_now, 1e-9)) * 10000.0)

    compression = 'YES' if float(ranges.tail(5).mean()) < float(ranges.tail(min(20, n)).mean()) * 0.82 else 'NO'
    hh = int((high.diff().tail(recent) > 0).sum())
    ll = int((low.diff().tail(recent) < 0).sum())
    last_swing = 'NEUTRAL'
    if hh >= recent * 0.55 and up_closes >= down_closes + 2:
        last_swing = 'BULLISH'
    elif ll >= recent * 0.55 and down_closes >= up_closes + 2:
        last_swing = 'BEARISH'

    absorption_side = 'NONE'
    upper_wick = (high - close.where(close >= open_, open_)).tail(4).mean()
    lower_wick = (close.where(close <= open_, open_) - low).tail(4).mean()
    avg_body = body.tail(4).mean()
    if upper_wick > avg_body * 1.25:
        absorption_side = 'SELLER_AT_HIGH'
    elif lower_wick > avg_body * 1.25:
        absorption_side = 'BUYER_AT_LOW'

    micro_bias = 'NEUTRAL'
    if sell_ratio >= 0.56 and last_swing == 'BEARISH':
        micro_bias = 'SHORT'
    elif buy_ratio >= 0.56 and last_swing == 'BULLISH':
        micro_bias = 'LONG'
    elif absorption_side == 'SELLER_AT_HIGH':
        micro_bias = 'SHORT'
    elif absorption_side == 'BUYER_AT_LOW':
        micro_bias = 'LONG'

    confidence = 50.0
    confidence += abs(buy_ratio - sell_ratio) * 70.0
    confidence += 8.0 if compression == 'YES' else 0.0
    confidence += 6.0 if last_swing in {'BULLISH', 'BEARISH'} else 0.0
    confidence = max(35.0, min(84.0, confidence))

    structure = 'MIXED'
    if last_swing == 'BULLISH' and micro_bias == 'LONG':
        structure = 'HH/HL FORMING'
    elif last_swing == 'BEARISH' and micro_bias == 'SHORT':
        structure = 'LH/LL FORMING'
    elif compression == 'YES':
        structure = 'COMPRESSION'

    summary = (
        f"micro_bias={micro_bias}, buy_ratio={buy_ratio:.2f}, sell_ratio={sell_ratio:.2f}, "
        f"spread_bps={spread_bps:.1f}, absorption={absorption_side}, structure={structure}"
    )
    return {
        'micro_bias': micro_bias,
        'confidence': round(confidence, 1),
        'absorption_side': absorption_side,
        'compression': compression,
        'last_swing': last_swing,
        'structure': structure,
        'buy_ratio': round(buy_ratio, 3),
        'sell_ratio': round(sell_ratio, 3),
        'spread_bps': round(spread_bps, 1),
        'summary': summary,
    }
