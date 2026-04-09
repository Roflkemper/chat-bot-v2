from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterable, Optional

import requests

BASE_URL = os.getenv('COINGLASS_BASE_URL', 'https://open-api-v4.coinglass.com').rstrip('/')
API_KEY = os.getenv('COINGLASS_API_KEY', '').strip()
TIMEOUT = float(os.getenv('COINGLASS_TIMEOUT_SEC', '6'))
CACHE_TTL_SEC = int(os.getenv('COINGLASS_CACHE_TTL_SEC', '90'))

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _headers() -> Dict[str, str]:
    headers = {'Accept': 'application/json'}
    if API_KEY:
        # CoinGlass auth docs require an API key header; different client examples in the wild
        # use slightly different header casing, so we send the common variants defensively.
        headers['CG-API-KEY'] = API_KEY
        headers['coinglassSecret'] = API_KEY
    return headers


def _cache_key(path: str, params: Optional[Dict[str, Any]]) -> str:
    items = '&'.join(f'{k}={params[k]}' for k in sorted(params or {}))
    return f'{path}?{items}'


def _request(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    key = _cache_key(path, params)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] <= CACHE_TTL_SEC:
        return dict(cached[1])
    url = f'{BASE_URL}{path}'
    resp = requests.get(url, headers=_headers(), params=params or {}, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        _CACHE[key] = (now, dict(data))
        return data
    return {'data': data}


def _find_numeric(node: Any, keys: Iterable[str]) -> Optional[float]:
    want = {str(k).lower() for k in keys}
    if isinstance(node, dict):
        for k, v in node.items():
            if str(k).lower() in want:
                try:
                    return float(v)
                except Exception:
                    pass
        for v in node.values():
            found = _find_numeric(v, keys)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in reversed(node):
            found = _find_numeric(item, keys)
            if found is not None:
                return found
    return None


def _find_heatmap_levels(node: Any, price: float) -> dict[str, float]:
    levels: list[tuple[float, float]] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            p = None
            s = None
            for pk in ('price', 'p', 'level', 'liqPrice'):
                if pk in x:
                    try:
                        p = float(x[pk])
                        break
                    except Exception:
                        pass
            for sk in ('value', 'strength', 'liq', 'amount', 'v'):
                if sk in x:
                    try:
                        s = float(x[sk])
                        break
                    except Exception:
                        pass
            if p is not None and s is not None:
                levels.append((p, s))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(node)
    above = sorted((lv for lv in levels if lv[0] > price), key=lambda t: abs(t[0] - price), reverse=False)
    below = sorted((lv for lv in levels if lv[0] < price), key=lambda t: abs(t[0] - price), reverse=False)
    out = {}
    if above:
        out['nearest_above_price'] = above[0][0]
        out['nearest_above_strength'] = above[0][1]
    if below:
        out['nearest_below_price'] = below[0][0]
        out['nearest_below_strength'] = below[0][1]
    return out


def fetch_coin_context(coin: str = 'BTC', interval: str = '1h', price: float = 0.0) -> Dict[str, Any]:
    if not API_KEY:
        return {'ok': False, 'reason': 'missing_api_key'}

    out: Dict[str, Any] = {'ok': True, 'coin': coin, 'interval': interval, 'source': 'coinglass_v4'}
    errors: list[str] = []

    try:
        oi = _request('/api/futures/open-interest/aggregated-history', {'symbol': coin, 'interval': interval, 'limit': 3})
        out['oi_close'] = _find_numeric(oi, ['close', 'c', 'oi'])
        out['oi_prev_close'] = _find_numeric(oi.get('data', [])[:-1] if isinstance(oi.get('data'), list) else oi, ['close', 'c', 'oi'])
    except Exception as e:
        errors.append(f'oi:{type(e).__name__}')

    try:
        fr = _request('/api/futures/funding-rate/oi-weight-history', {'symbol': coin, 'interval': interval, 'limit': 3})
        out['funding_rate'] = _find_numeric(fr, ['close', 'c', 'fundingRate', 'rate'])
        out['funding_prev'] = _find_numeric(fr.get('data', [])[:-1] if isinstance(fr.get('data'), list) else fr, ['close', 'c', 'fundingRate', 'rate'])
    except Exception as e:
        errors.append(f'funding:{type(e).__name__}')

    try:
        heat = _request('/api/futures/liquidation/heatmap/model1', {'symbol': coin, 'exchange': 'Binance'})
        out.update(_find_heatmap_levels(heat, price))
    except Exception:
        try:
            heat = _request('/api/futures/liquidation/aggregate-heatmap', {'symbol': coin})
            out.update(_find_heatmap_levels(heat, price))
        except Exception as e:
            errors.append(f'heatmap:{type(e).__name__}')

    try:
        liq = _request('/api/futures/liquidation/order', {'symbol': coin})
        out['liquidation_last'] = _find_numeric(liq, ['amount', 'value', 'liq'])
    except Exception as e:
        errors.append(f'liq_order:{type(e).__name__}')

    if errors:
        out['errors'] = errors
    return out
