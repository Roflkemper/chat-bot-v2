"""Historical liquidation ingest from exchange public REST APIs.

Exchange availability (tested 2026-04-29):
  OKX  — /api/v5/public/liquidation-orders: PUBLIC, ~24h window per call, pageable
  Binance — /fapi/v1/forceOrders: REQUIRES AUTH (401 on unauthenticated calls)
  BitMEX  — /api/v1/liquidation XBTUSD: 0 rows (symbol deprecated, no activity)

Schema matches the live collector (collectors/liquidations/):
    ts_ms            int64     Unix timestamp ms
    exchange         str       'okx'
    symbol           str       'BTCUSDT' | 'ETHUSDT' | 'XRPUSDT'
    side             str       'long' | 'short'  (position that was liquidated)
    qty              float64   Position size in base currency
    price            float64   Bankruptcy price
    value_usd        float64   Notional USD value
    source_rate_limited bool   False for OKX (tick-level delivery)

Usage:
    python scripts/liq_ingest_historical.py
    python scripts/liq_ingest_historical.py --max-pages 50
    python scripts/liq_ingest_historical.py --dry-run

Output:
    market_data/liquidations_historical/okx_<symbol>_live.parquet
    docs/STATE/LIQ_INGESTION_REPORT_<ts>.md
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "buffer") and sys.stdout.encoding and \
        sys.stdout.encoding.lower().replace("-", "") not in ("utf8", "utf8bom"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "market_data" / "liquidations_historical"
REPORT_DIR = ROOT / "docs" / "STATE"

log = logging.getLogger(__name__)

_SLEEP_S = 0.3   # between paginated requests (~3 req/s)

SCHEMA = pa.schema([
    pa.field("ts_ms", pa.int64()),
    pa.field("exchange", pa.string()),
    pa.field("symbol", pa.string()),
    pa.field("side", pa.string()),
    pa.field("qty", pa.float64()),
    pa.field("price", pa.float64()),
    pa.field("value_usd", pa.float64()),
    pa.field("source_rate_limited", pa.bool_()),
])

# OKX underlying → normalized symbol
_OKX_ULY_MAP = {
    "BTC-USDT": "BTCUSDT",
    "ETH-USDT": "ETHUSDT",
    "XRP-USDT": "XRPUSDT",
}

_OKX_BASE = "https://www.okx.com/api/v5/public/liquidation-orders"
_OKX_LIMIT = 100   # outer group limit per call


# ── helpers ───────────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def _ms_to_dt(ms: int) -> str:
    return datetime.utcfromtimestamp(ms / 1000).replace(tzinfo=timezone.utc).isoformat()


def _fetch(url: str, retries: int = 4) -> dict | list:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bot7-liq-ingest/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as exc:
            if attempt == retries - 1:
                raise RuntimeError(f"fetch failed {url}: {exc}") from exc
            wait = min(2 ** attempt * 0.5, 15)
            log.warning("retry %d/%d: %s — sleeping %.1fs", attempt + 1, retries, exc, wait)
            time.sleep(wait)
    return {}  # unreachable


def _save(rows: list[dict], tag: str, dry_run: bool) -> Path:
    out_path = OUT_DIR / f"{tag}.parquet"
    if not rows:
        log.warning("%s: no rows to save", tag)
        return out_path

    df = pd.DataFrame(rows).sort_values("ts_ms").drop_duplicates(subset=["ts_ms", "exchange", "symbol", "side", "qty"])
    for col in ["qty", "price", "value_usd"]:
        df[col] = df[col].astype(float)
    df["source_rate_limited"] = df["source_rate_limited"].astype(bool)

    table = pa.Table.from_pandas(df, schema=SCHEMA, preserve_index=False)
    if not dry_run:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, out_path, compression="zstd", compression_level=3)
    return out_path


# ── OKX ───────────────────────────────────────────────────────────────────────

def _fetch_okx_uly(uly: str, symbol: str, start_ms: int, max_pages: int) -> list[dict]:
    """Paginate OKX liquidation-orders backward from now until start_ms or max_pages."""
    rows: list[dict] = []
    after_cursor = ""   # oldest ts seen, passed as `after` for next (older) page

    for page in range(max_pages):
        url = f"{_OKX_BASE}?instType=SWAP&uly={uly}&state=filled&limit={_OKX_LIMIT}"
        if after_cursor:
            url += f"&after={after_cursor}"

        data = _fetch(url)
        if not isinstance(data, dict) or data.get("code") != "0":
            log.warning("okx %s: bad response code=%s msg=%s",
                        uly, data.get("code"), data.get("msg"))
            break

        groups = data.get("data", [])
        if not groups:
            log.debug("okx %s page=%d: empty — done", uly, page)
            break

        batch_rows: list[dict] = []
        batch_ts: list[int] = []

        for group in groups:
            for detail in group.get("details", []):
                ts_ms = int(detail.get("ts", 0))
                if ts_ms == 0:
                    continue
                batch_ts.append(ts_ms)
                if ts_ms < start_ms:
                    continue   # outside our window, but keep collecting from this page
                pos_side = detail.get("posSide", "")   # "long" | "short" (direct from OKX)
                side = pos_side if pos_side in ("long", "short") else (
                    "long" if detail.get("side", "") == "sell" else "short"
                )
                qty = float(detail.get("sz", 0) or 0)
                price = float(detail.get("bkPx", 0) or 0)
                batch_rows.append({
                    "ts_ms": ts_ms,
                    "exchange": "okx",
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "price": price,
                    "value_usd": qty * price,
                    "source_rate_limited": False,
                })

        rows.extend(batch_rows)
        log.debug("okx %s page=%d: %d groups → %d rows (total=%d)",
                  uly, page, len(groups), len(batch_rows), len(rows))

        if not batch_ts:
            break

        oldest_in_page = min(batch_ts)
        if oldest_in_page < start_ms:
            log.info("okx %s: reached start_ms at page=%d, stopping", uly, page)
            break

        # Use oldest ts from this page as the `after` cursor for next (older) page
        after_cursor = str(oldest_in_page)
        time.sleep(_SLEEP_S)

    return rows


def fetch_okx(start_ms: int, max_pages: int) -> list[dict]:
    all_rows: list[dict] = []
    for uly, symbol in _OKX_ULY_MAP.items():
        log.info("okx %s (%s): fetching from %s (max_pages=%d)...",
                 uly, symbol, _ms_to_dt(start_ms)[:10], max_pages)
        try:
            rows = _fetch_okx_uly(uly, symbol, start_ms, max_pages)
            first = _ms_to_dt(min(r["ts_ms"] for r in rows))[:16] if rows else "—"
            last = _ms_to_dt(max(r["ts_ms"] for r in rows))[:16] if rows else "—"
            log.info("okx %s: %d rows [%s → %s]", symbol, len(rows), first, last)
            all_rows.extend(rows)
        except Exception as exc:
            log.error("okx %s failed: %s", uly, exc)
    return all_rows


# ── main ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--max-pages", type=int, default=20,
                   help="Max pagination pages per symbol (default 20; each page ≈24h)")
    p.add_argument("--dry-run", action="store_true",
                   help="Fetch and count but do not write files")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    now_ms = _now_ms()
    # OKX only supports ~30d history; Binance needs auth; BitMEX XBTUSD deprecated
    start_ms = now_ms - 30 * 86_400_000

    log.info("liq_ingest: OKX historical liquidations start=%s max_pages=%d dry_run=%s",
             _ms_to_dt(start_ms)[:10], args.max_pages, args.dry_run)
    log.info("NOTE: Binance /fapi/v1/forceOrders requires API key (401); skipped")
    log.info("NOTE: BitMEX XBTUSD has no recent liquidations (symbol deprecated); skipped")

    results: list[dict] = []

    # OKX — only working public exchange
    okx_rows = fetch_okx(start_ms, args.max_pages)

    # Split by symbol and save
    for symbol in ["BTCUSDT", "ETHUSDT", "XRPUSDT"]:
        sym_rows = [r for r in okx_rows if r["symbol"] == symbol]
        tag = f"okx_{symbol}_live"
        out = _save(sym_rows, tag, args.dry_run)
        first = _ms_to_dt(min(r["ts_ms"] for r in sym_rows))[:16] if sym_rows else "—"
        last = _ms_to_dt(max(r["ts_ms"] for r in sym_rows))[:16] if sym_rows else "—"
        results.append({
            "exchange": "okx", "symbol": symbol,
            "rows": len(sym_rows), "first_ts": first, "last_ts": last,
            "path": str(out), "status": "ok" if sym_rows else "empty",
        })

    # Validation
    errors: list[str] = []
    for r in results:
        if r.get("rows", 0) < 10 and r["status"] == "ok":
            errors.append(f"{r['exchange']} {r['symbol']}: only {r['rows']} rows")
    for r in results:
        log.info("  %s %s: %d rows  status=%s", r["exchange"], r["symbol"],
                 r.get("rows", 0), r["status"])
    for e in errors:
        log.warning("VALIDATION: %s", e)

    # Report
    ts_str = datetime.utcnow().strftime("%Y-%m-%dT%H%M%SZ")
    report_path = REPORT_DIR / f"LIQ_INGESTION_REPORT_{ts_str}.md"
    total_rows = sum(r.get("rows", 0) for r in results)

    lines = [
        f"# LIQ INGESTION REPORT {ts_str}",
        "",
        f"**Max pages (OKX):** {args.max_pages}  ",
        f"**Start:** {_ms_to_dt(start_ms)[:10]}  ",
        f"**Total rows:** {total_rows}  ",
        f"**Dry run:** {args.dry_run}  ",
        "",
        "## Exchange status",
        "",
        "| Exchange | Status | Reason |",
        "|----------|--------|--------|",
        "| OKX | ✅ active | Public API, ~30d history, pageable |",
        "| Binance | ⛔ auth_required | `/fapi/v1/forceOrders` requires API key |",
        "| BitMEX | ⛔ deprecated | XBTUSD symbol has no recent liquidations |",
        "",
        "## Results",
        "",
        "| Exchange | Symbol | Rows | First | Last | Status |",
        "|----------|--------|------|-------|------|--------|",
    ]
    for r in results:
        lines.append(
            f"| {r['exchange']} | {r['symbol']} | {r.get('rows',0)} "
            f"| {r.get('first_ts','—')} | {r.get('last_ts','—')} | {r['status']} |"
        )
    if errors:
        lines += ["", "## Validation warnings", ""]
        for e in errors:
            lines.append(f"- {e}")
    lines += ["", "## Output files", "", f"- Directory: `{OUT_DIR}`"]
    for r in results:
        if "path" in r and not args.dry_run and r["rows"] > 0:
            lines.append(f"- `{r['path']}`")

    report_text = "\n".join(lines) + "\n"
    if not args.dry_run:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_text, encoding="utf-8")
        log.info("report → %s", report_path)
    else:
        print(report_text)

    log.info("done. total_rows=%d", total_rows)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
