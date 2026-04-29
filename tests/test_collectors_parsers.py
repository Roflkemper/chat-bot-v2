"""Smoke tests for collector parser functions — no real WS connections."""
from __future__ import annotations

import time

import pytest

from collectors.liquidations.binance import _parse as binance_liq_parse
from collectors.liquidations.bybit import _parse as bybit_liq_parse
from collectors.liquidations.hyperliquid import _parse as hl_liq_parse
from collectors.liquidations.bitmex import _parse as bitmex_liq_parse
from collectors.liquidations.okx import _parse as okx_liq_parse
from collectors.orderbook.binance import _parse as ob_parse
from collectors.trades.binance import _parse as trades_parse


# ── helpers ───────────────────────────────────────────────────────────────────

def _ts() -> int:
    return int(time.time() * 1000)


# ── Binance liquidations ──────────────────────────────────────────────────────

class TestBinanceLiqParser:
    def _msg(self, symbol="BTCUSDT", side="SELL", qty="0.5", price="30000"):
        return {"data": {"o": {"s": symbol, "S": side, "q": qty, "ap": price, "T": _ts()}}}

    def test_long_liquidation(self):
        rows = binance_liq_parse(self._msg(side="SELL"))
        assert rows and rows[0]["side"] == "long"

    def test_short_liquidation(self):
        rows = binance_liq_parse(self._msg(side="BUY"))
        assert rows and rows[0]["side"] == "short"

    def test_unknown_symbol_filtered(self):
        rows = binance_liq_parse(self._msg(symbol="DOGEUSDT"))
        assert rows is None

    def test_value_usd_computed(self):
        rows = binance_liq_parse(self._msg(qty="1.0", price="50000"))
        assert rows[0]["value_usd"] == pytest.approx(50000.0)

    def test_source_rate_limited_true(self):
        rows = binance_liq_parse(self._msg())
        assert rows[0]["source_rate_limited"] is True


# ── Bybit liquidations ────────────────────────────────────────────────────────

class TestBybitLiqParser:
    def _msg(self, symbol="BTCUSDT", side="Sell", size="0.1", price="30000"):
        return {
            "topic": f"allLiquidation.{symbol}",
            "data": [{"symbol": symbol, "side": side, "size": size,
                      "price": price, "updateTime": _ts()}],
        }

    def test_long_liquidation(self):
        rows = bybit_liq_parse(self._msg(side="Sell"))
        assert rows and rows[0]["side"] == "long"

    def test_short_liquidation(self):
        rows = bybit_liq_parse(self._msg(side="Buy"))
        assert rows and rows[0]["side"] == "short"

    def test_wrong_topic_ignored(self):
        msg = {"topic": "kline.BTCUSDT", "data": {}}
        assert bybit_liq_parse(msg) is None

    def test_source_rate_limited_false(self):
        rows = bybit_liq_parse(self._msg())
        assert rows[0]["source_rate_limited"] is False


# ── Hyperliquid liquidations ──────────────────────────────────────────────────

class TestHyperliquidLiqParser:
    def _msg(self, coin="BTC", side="A", sz="0.01", px="30000", with_liq=True):
        record = {"coin": coin, "side": side, "sz": sz, "px": px, "time": _ts()}
        if with_liq:
            record["liquidation"] = {"liquidatedNtlPos": 300.0, "markPx": px}
        return {"channel": "trades", "data": [record]}

    def test_long_liquidation(self):
        rows = hl_liq_parse(self._msg(side="A"))  # ask-side fill = long liq
        assert rows and rows[0]["side"] == "long"

    def test_short_liquidation(self):
        rows = hl_liq_parse(self._msg(side="B"))
        assert rows and rows[0]["side"] == "short"

    def test_regular_trade_ignored(self):
        rows = hl_liq_parse(self._msg(with_liq=False))
        assert not rows

    def test_unknown_coin_filtered(self):
        rows = hl_liq_parse(self._msg(coin="SOL"))
        assert not rows

    def test_symbol_normalized(self):
        rows = hl_liq_parse(self._msg(coin="XRP"))
        assert rows and rows[0]["symbol"] == "XRPUSDT"

    def test_source_rate_limited_false(self):
        rows = hl_liq_parse(self._msg())
        assert rows[0]["source_rate_limited"] is False


# ── BitMEX liquidations ───────────────────────────────────────────────────────

class TestBitmexLiqParser:
    def _msg(self, symbol="XBTUSD", side="Buy", price=30000, leaves_qty=1000):
        return {
            "table": "liquidation",
            "action": "insert",
            "data": [{"orderID": "abc", "symbol": symbol, "side": side,
                      "price": price, "leavesQty": leaves_qty}],
        }

    def test_short_liquidation(self):
        # Buy order closes a short → short was liquidated
        rows = bitmex_liq_parse(self._msg(side="Buy"))
        assert rows and rows[0]["side"] == "short"

    def test_long_liquidation(self):
        rows = bitmex_liq_parse(self._msg(side="Sell"))
        assert rows and rows[0]["side"] == "long"

    def test_xbtusd_mapped_to_btcusdt(self):
        rows = bitmex_liq_parse(self._msg())
        assert rows and rows[0]["symbol"] == "BTCUSDT"

    def test_value_usd_equals_leaves_qty(self):
        rows = bitmex_liq_parse(self._msg(leaves_qty=2500, price=50000))
        # inverse contract: USD value = leavesQty contracts
        assert rows[0]["value_usd"] == pytest.approx(2500.0)

    def test_qty_is_btc_not_usd(self):
        rows = bitmex_liq_parse(self._msg(leaves_qty=2500, price=50000))
        # qty must be in BTC = leavesQty / price, consistent with linear exchanges
        assert rows[0]["qty"] == pytest.approx(2500 / 50000)

    def test_unknown_symbol_ignored(self):
        rows = bitmex_liq_parse(self._msg(symbol="ETHUSD"))
        assert not rows

    def test_wrong_action_ignored(self):
        msg = {"table": "liquidation", "action": "partial", "data": []}
        assert bitmex_liq_parse(msg) is None

    def test_source_rate_limited_false(self):
        rows = bitmex_liq_parse(self._msg())
        assert rows[0]["source_rate_limited"] is False


# ── OKX liquidations ──────────────────────────────────────────────────────────

class TestOkxLiqParser:
    def _msg(self, inst_id="BTC-USDT-SWAP", side="buy", sz="0.1", bk_px="30000"):
        return {
            "arg": {"channel": "liquidation-orders", "instType": "SWAP"},
            "data": [{
                "instId": inst_id,
                "details": [{"side": side, "sz": sz, "bkPx": bk_px, "ts": str(_ts())}],
            }],
        }

    def test_short_liquidation(self):
        # buy = forced buy to close short → short liquidated
        rows = okx_liq_parse(self._msg(side="buy"))
        assert rows and rows[0]["side"] == "short"

    def test_long_liquidation(self):
        rows = okx_liq_parse(self._msg(side="sell"))
        assert rows and rows[0]["side"] == "long"

    def test_unknown_instrument_filtered(self):
        rows = okx_liq_parse(self._msg(inst_id="SOL-USDT-SWAP"))
        assert not rows

    def test_symbol_normalized(self):
        rows = okx_liq_parse(self._msg(inst_id="ETH-USDT-SWAP"))
        assert rows and rows[0]["symbol"] == "ETHUSDT"

    def test_wrong_channel_ignored(self):
        msg = {"arg": {"channel": "tickers"}, "data": []}
        assert okx_liq_parse(msg) is None

    def test_source_rate_limited_false(self):
        rows = okx_liq_parse(self._msg())
        assert rows[0]["source_rate_limited"] is False


# ── Binance orderbook ─────────────────────────────────────────────────────────

class TestBinanceObParser:
    def _msg(self):
        return {"data": {"T": _ts(), "b": [["30000", "1.5"], ["29999", "2.0"]],
                         "a": [["30001", "0.5"]]}}

    def test_returns_bid_and_ask_rows(self):
        rows = ob_parse("BTCUSDT", self._msg())
        sides = {r["side"] for r in rows}
        assert "bid" in sides and "ask" in sides

    def test_level_starts_at_1(self):
        rows = ob_parse("BTCUSDT", self._msg())
        bid_rows = [r for r in rows if r["side"] == "bid"]
        assert bid_rows[0]["level"] == 1

    def test_price_is_float(self):
        rows = ob_parse("BTCUSDT", self._msg())
        assert isinstance(rows[0]["price"], float)


# ── Binance trades ────────────────────────────────────────────────────────────

class TestBinanceTradesParser:
    def _msg(self, maker=True, symbol="BTCUSDT"):
        return {"data": {"e": "aggTrade", "s": symbol, "m": maker,
                         "q": "0.5", "p": "30000", "T": _ts()}}

    def test_maker_true_is_sell(self):
        row = trades_parse(self._msg(maker=True))
        assert row and row["side"] == "sell"

    def test_maker_false_is_buy(self):
        row = trades_parse(self._msg(maker=False))
        assert row and row["side"] == "buy"

    def test_is_liquidation_false(self):
        row = trades_parse(self._msg())
        assert row["is_liquidation"] is False

    def test_wrong_event_ignored(self):
        msg = {"data": {"e": "kline", "s": "BTCUSDT"}}
        assert trades_parse(msg) is None
