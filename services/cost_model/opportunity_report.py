from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from services.cost_model.integration import load_funding_rate_pct
from services.cost_model.fees import compute_fee
from services.cost_model.slippage import estimate_slippage
from services.cost_model.funding import compute_funding_pnl

RECOVERED_RESULTS = Path("_recovery/restored/whatif_results")
OUTPUT_REPORT = Path("reports/opportunity_map_with_costs_2026-05-01.md")

PLAY_META: dict[str, dict[str, object]] = {
    "P-1": {"side": "short", "venue": "ginarea_inverse", "kind": "grid"},
    "P-2": {"side": "short", "venue": "ginarea_inverse", "kind": "grid"},
    "P-3": {"side": "long", "venue": "ginarea_linear", "kind": "directional"},
    "P-4": {"side": "short", "venue": "ginarea_inverse", "kind": "stop"},
    "P-5": {"side": "short", "venue": "ginarea_inverse", "kind": "close"},
    "P-6": {"side": "short", "venue": "ginarea_inverse", "kind": "grid"},
    "P-7": {"side": "long", "venue": "ginarea_linear", "kind": "directional"},
    "P-8": {"side": "short", "venue": "ginarea_inverse", "kind": "restart"},
    "P-9": {"side": "long", "venue": "ginarea_linear", "kind": "close"},
    "P-10": {"side": "short", "venue": "ginarea_inverse", "kind": "restart"},
    "P-11": {"side": "short", "venue": "ginarea_inverse", "kind": "grid"},
    "P-12": {"side": "short", "venue": "ginarea_inverse", "kind": "grid"},
    "P-13": {"side": "long", "venue": "ginarea_linear", "kind": "grid"},
    "P-14": {"side": "long", "venue": "ginarea_linear", "kind": "restart"},
}


def _default_notional(play_id: str, params: dict[str, object]) -> float:
    if "size_btc" in params:
        return abs(float(params["size_btc"])) * 80_000.0
    if play_id in {"P-3", "P-7", "P-9"}:
        return 0.05 * 80_000.0
    if play_id in {"P-5", "P-8", "P-10", "P-14"}:
        return 0.18 * 80_000.0
    return 0.10 * 80_000.0


def _row_costs(play_id: str, row: pd.Series) -> tuple[float, float, float, float]:
    meta = PLAY_META[play_id]
    params = json.loads(str(row["param_values"]))
    side = str(meta["side"])
    venue = str(meta["venue"])
    kind = str(meta["kind"])
    maker_volume = float(row.get("volume_traded_usd", 0.0) or 0.0)
    duration_h = float(row.get("duration_min", 0.0) or 0.0) / 60.0
    base_notional = _default_notional(play_id, params)

    fees = 0.0
    slippage = 0.0
    funding = 0.0

    if maker_volume > 0:
        fees += compute_fee(venue, side, maker_volume, is_maker=True)

    if kind in {"directional", "close", "restart", "stop"}:
        fees += compute_fee(venue, side, base_notional, is_maker=False)
        order_type = "taker_stop" if kind == "stop" else "taker_market"
        slippage += estimate_slippage(order_type, base_notional, atr_1h=500.0)

    if kind == "directional":
        fees += compute_fee(venue, side, base_notional, is_maker=True)

    funding_rate_pct = load_funding_rate_pct(
        pd.Timestamp(str(row["ts_start"])),
        "BTCUSDT",
        bias_hint=1.0 if side == "short" else 0.5,
    )
    contract_type = "inverse" if "inverse" in venue else "linear"
    funding += compute_funding_pnl(base_notional, side, contract_type, funding_rate_pct, duration_h)
    net_pnl = float(row["pnl_usd"]) - fees - slippage + funding
    return fees, slippage, funding, net_pnl


def build_report(results_dir: Path = RECOVERED_RESULTS, output_path: Path = OUTPUT_REPORT) -> Path:
    play_rows: list[dict[str, object]] = []
    for agg_path in sorted(results_dir.glob("P-[0-9]*_*.parquet")):
        if agg_path.name.endswith("_raw.parquet"):
            continue
        play_id = agg_path.stem.split("_", 1)[0]
        raw_path = results_dir / f"{agg_path.stem}_raw.parquet"
        if play_id not in PLAY_META or not raw_path.exists():
            continue
        raw_df = pd.read_parquet(raw_path)
        if raw_df.empty:
            continue
        fees = []
        slips = []
        fundings = []
        nets = []
        for _, row in raw_df.iterrows():
            fee, slip, funding, net = _row_costs(play_id, row)
            fees.append(fee)
            slips.append(slip)
            fundings.append(funding)
            nets.append(net)
        raw_df = raw_df.copy()
        raw_df["fees_usd"] = fees
        raw_df["slippage_usd"] = slips
        raw_df["funding_usd"] = fundings
        raw_df["net_pnl_usd"] = nets

        gross_mean = float(raw_df["pnl_usd"].mean())
        net_mean = float(raw_df["net_pnl_usd"].mean())
        delta = net_mean - gross_mean
        if delta > 1.0:
            verdict = "improved"
        elif delta < -1.0:
            verdict = "worsened"
        else:
            verdict = "flat"
        play_rows.append(
            {
                "play_id": play_id,
                "gross_pnl_usd": gross_mean,
                "net_pnl_usd": net_mean,
                "delta_usd": delta,
                "fees_usd": float(raw_df["fees_usd"].mean()),
                "slippage_usd": float(raw_df["slippage_usd"].mean()),
                "funding_usd": float(raw_df["funding_usd"].mean()),
                "verdict": verdict,
            }
        )

    table_df = pd.DataFrame(play_rows).sort_values("play_id")
    improved = table_df[table_df["verdict"] == "improved"]["play_id"].tolist()
    worsened = table_df[table_df["verdict"] == "worsened"]["play_id"].tolist()
    flat = table_df[table_df["verdict"] == "flat"]["play_id"].tolist()

    lines = [
        "# Opportunity Map With Costs",
        "",
        "Comparison uses recovered What-If raw parquet from `_recovery/restored/whatif_results` and applies the explicit cost model post-hoc.",
        "",
        "| Play | Gross PnL USD | Net PnL USD | Delta USD | Fees USD | Slippage USD | Funding USD | Verdict |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for _, row in table_df.iterrows():
        lines.append(
            f"| {row['play_id']} | {row['gross_pnl_usd']:.2f} | {row['net_pnl_usd']:.2f} | {row['delta_usd']:.2f} | "
            f"{row['fees_usd']:.2f} | {row['slippage_usd']:.2f} | {row['funding_usd']:.2f} | {row['verdict']} |"
        )
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Improved: {', '.join(improved) if improved else 'none'}",
            f"- Worsened: {', '.join(worsened) if worsened else 'none'}",
            f"- Unchanged: {', '.join(flat) if flat else 'none'}",
            "",
            "## Verdict",
            "",
            "- Re-evaluate maker-heavy short stack plays where rebate and positive short funding lift net PnL.",
            "- Re-evaluate stop / restart / forced-close plays where taker fee and taker slippage drag net PnL lower.",
            "- Keep `OPPORTUNITY_MAP_v1.md` unchanged in this TZ; this file is comparison-only input for a later v2 update.",
            "",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


if __name__ == "__main__":
    path = build_report()
    print(path)
