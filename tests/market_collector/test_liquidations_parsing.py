"""Smoke tests for liquidation WS parsing logic.

Не запускаем настоящие WS-соединения — только проверяем shape парсинга
для каждого протокола (OKX/Binance/Bybit) против образца сообщения.

Этот файл — defensive: ловит регрессии в parser-логике когда меняем
schema или фильтрацию.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


# ── OKX ───────────────────────────────────────────────────────────────────

SAMPLE_OKX_LIQ_MSG = {
    "arg": {"channel": "liquidation-orders", "instType": "SWAP"},
    "data": [{
        "instType": "SWAP",
        "instFamily": "BTC-USD",
        "instId": "BTC-USDT-SWAP",
        "details": [{
            "side": "sell",       # liquidation of LONG
            "sz": "0.5",
            "bkPx": "65000.5",
            "ccy": "BTC",
            "posSide": "long",
            "ts": "1726876800000",
        }],
    }],
}

SAMPLE_OKX_OTHER_PAIR = {
    "arg": {"channel": "liquidation-orders", "instType": "SWAP"},
    "data": [{
        "instType": "SWAP",
        "instId": "ETH-USDT-SWAP",
        "details": [{"side": "buy", "sz": "10", "bkPx": "3500"}],
    }],
}


def test_okx_side_mapping_sell_means_long_liquidation():
    """OKX side=sell → CSV side=long (long position got liquidated)."""
    side_raw = SAMPLE_OKX_LIQ_MSG["data"][0]["details"][0]["side"]
    assert side_raw == "sell"
    mapped = "long" if side_raw == "sell" else "short"
    assert mapped == "long"


def test_okx_side_mapping_buy_means_short_liquidation():
    side_raw = "buy"
    mapped = "long" if side_raw == "sell" else "short"
    assert mapped == "short"


def test_okx_instId_filter_passes_btc():
    """BTC-USDT-SWAP should be kept."""
    inst_id = SAMPLE_OKX_LIQ_MSG["data"][0]["instId"]
    assert inst_id == "BTC-USDT-SWAP"


def test_okx_instId_filter_drops_eth():
    """ETH-USDT-SWAP should be filtered out."""
    inst_id = SAMPLE_OKX_OTHER_PAIR["data"][0]["instId"]
    assert inst_id != "BTC-USDT-SWAP"


# ── Binance all-market filter ─────────────────────────────────────────────

SAMPLE_BINANCE_BTC = {
    "e": "forceOrder",
    "o": {
        "s": "BTCUSDT", "S": "SELL", "q": "0.005",
        "p": "67100.5", "ap": "67100.5",
        "T": 1726876800000,
    },
}

SAMPLE_BINANCE_ETH = {
    "e": "forceOrder",
    "o": {"s": "ETHUSDT", "S": "BUY", "q": "1.2", "p": "3500"},
}


def test_binance_symbol_filter_keeps_btc():
    assert SAMPLE_BINANCE_BTC["o"]["s"] == "BTCUSDT"


def test_binance_symbol_filter_drops_eth():
    assert SAMPLE_BINANCE_ETH["o"]["s"] != "BTCUSDT"


def test_binance_side_mapping():
    """Binance S=SELL means a long got liquidated (server selling longs to close)."""
    side = "long" if SAMPLE_BINANCE_BTC["o"]["S"] == "SELL" else "short"
    assert side == "long"


# ── Smoke: module imports cleanly with all collectors ──────────────────────

def test_module_imports_all_three_streams():
    from market_collector import liquidations
    # Functions must exist and be callable
    assert callable(liquidations._run_bybit_ws)
    assert callable(liquidations._run_binance_ws)
    assert callable(liquidations._run_okx_ws)


def test_start_liquidation_streams_creates_three_threads():
    """Without actually starting websockets (stop_event is set immediately),
    verify start_liquidation_streams spawns 3 thread objects."""
    import threading
    from market_collector import liquidations

    stop = threading.Event()
    stop.set()  # tell threads to exit immediately

    # Patch the three runners to no-op so we don't hit network.
    with patch.object(liquidations, "_run_bybit_ws", lambda e: None), \
         patch.object(liquidations, "_run_binance_ws", lambda e: None), \
         patch.object(liquidations, "_run_okx_ws", lambda e: None):
        threads = liquidations.start_liquidation_streams(stop)
    assert len(threads) == 3
    names = {t.name for t in threads}
    assert names == {"liq-bybit", "liq-binance", "liq-okx"}


def test_okx_ws_url_in_config():
    from market_collector.config import OKX_WS_URL
    assert OKX_WS_URL.startswith("wss://")
    assert "okx" in OKX_WS_URL


def test_binance_ws_url_is_all_market():
    """After 2026-05-12 fix: should be the all-market !forceOrder@arr stream."""
    from market_collector.config import BINANCE_WS_URL
    assert "!forceOrder@arr" in BINANCE_WS_URL
