"""TZ-CALIBRATE-VS-GINAREA: Calibrate bt-engine against GinArea native backtest.

Computes calibration factor K for:
  - (SHORT, USDT-M): 6 runs, TD in [0.19, 0.21, 0.25, 0.30, 0.35, 0.45]
  - (LONG, COIN-M):  3 runs, TD in [0.25, 0.30, 0.45]

Usage (from c:\\bot7):
    python tools/calibrate_ginarea.py
    python tools/calibrate_ginarea.py --out docs/calibration/CALIBRATION_VS_GINAREA_2026-04-30.md
"""
from __future__ import annotations

import csv
import io
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
CODEX_SRC = Path(r"C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src")
OHLCV_PATH = ROOT / "backtests" / "frozen" / "BTCUSDT_1m_2y.csv"
DEFAULT_OUT = ROOT / "docs" / "calibration" / "CALIBRATION_VS_GINAREA_2026-04-30.md"

if str(CODEX_SRC) not in sys.path:
    sys.path.insert(0, str(CODEX_SRC))

# ---------------------------------------------------------------------------
# GinArea ground truth — 9 backtests, 2025-05-01..2026-04-30
# ---------------------------------------------------------------------------
# Common SHORT params
# boundaries: wide open (GinArea calibration runs have no border restriction)
# indicator_period/threshold: GinArea default (30 bars / 0.3%)
_SHORT_PARAMS = dict(
    side="SHORT", contract="LINEAR",
    grid_step=0.03, order_count=800, order_size=0.003,
    instop=0.03, min_stop=0.01, max_stop=0.04,
    dsblin=False,
    boundaries_lower=10_000.0, boundaries_upper=999_999.0,
    indicator_period=30, indicator_threshold_pct=0.3,
)
# Common LONG params
_LONG_PARAMS = dict(
    side="LONG", contract="INVERSE",
    grid_step=0.03, order_count=800, order_size=200.0,
    instop=0.018, min_stop=0.01, max_stop=0.30,
    dsblin=False,
    boundaries_lower=10_000.0, boundaries_upper=999_999.0,
    indicator_period=30, indicator_threshold_pct=0.3,
)

GINAREA_GROUND_TRUTH = [
    # SHORT USDT-M
    dict(bot_id="5181061252", **_SHORT_PARAMS, td=0.19,
         ga_realized=31746.86, ga_unrealized=-14447.90, ga_volume=52666201, ga_triggers=589),
    dict(bot_id="5658350391", **_SHORT_PARAMS, td=0.21,
         ga_realized=34791.83, ga_unrealized=-13414.06, ga_volume=48937853, ga_triggers=559),
    dict(bot_id="4714585329", **_SHORT_PARAMS, td=0.25,
         ga_realized=38909.93, ga_unrealized=-14045.53, ga_volume=42780857, ga_triggers=582),
    dict(bot_id="5360096295", **_SHORT_PARAMS, td=0.30,
         ga_realized=42616.75, ga_unrealized=-14384.17, ga_volume=37010264, ga_triggers=598),
    dict(bot_id="5380108649", **_SHORT_PARAMS, td=0.35,
         ga_realized=46166.43, ga_unrealized=-15198.05, ga_volume=33000181, ga_triggers=614),
    dict(bot_id="4929609976", **_SHORT_PARAMS, td=0.45,
         ga_realized=49782.51, ga_unrealized=-15352.82, ga_volume=26676981, ga_triggers=617),
    # LONG COIN-M
    dict(bot_id="4373073010", **_LONG_PARAMS, td=0.25,
         ga_realized=0.12486136, ga_unrealized=-0.62173048, ga_volume=14211200, ga_triggers=None),
    dict(bot_id="5602603251", **_LONG_PARAMS, td=0.30,
         ga_realized=0.13355682, ga_unrealized=-0.62634603, ga_volume=12207600, ga_triggers=None),
    dict(bot_id="5975887092", **_LONG_PARAMS, td=0.45,
         ga_realized=0.15423005, ga_unrealized=-0.63096202, ga_volume=8344000,  ga_triggers=None),
]

SIM_START = "2025-05-01T00:00:00+00:00"
SIM_END   = "2026-04-29T23:59:59+00:00"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class SimResult:
    bot_id: str
    side: str
    contract: str
    td: float
    sim_trades: int
    sim_realized: float
    sim_volume: float
    sim_unrealized: float


@dataclass
class CalibRow:
    bot_id: str
    side: str
    contract: str
    td: float
    sim_trades: int
    ga_triggers: Optional[int]
    k_trades: Optional[float]
    sim_realized: float
    ga_realized: float
    k_realized: float
    sim_volume: float
    ga_volume: float
    k_volume: float
    normalized_sim_realized: float  # sim_realized * mean_K_realized for group


# ---------------------------------------------------------------------------
# OHLCV loader
# ---------------------------------------------------------------------------
def load_ohlcv(start_iso: str, end_iso: str) -> list:
    from backtest_lab.engine_v2.bot import OHLCBar

    start_ms = int(datetime.fromisoformat(start_iso).timestamp() * 1000)
    end_ms   = int(datetime.fromisoformat(end_iso).timestamp()   * 1000)

    bars = []
    with open(OHLCV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_ms = int(float(row["ts"]))
            if ts_ms < start_ms:
                continue
            if ts_ms > end_ms:
                break
            dt = datetime.utcfromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            bars.append(OHLCBar(
                ts=dt,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume") or 0),
            ))
    return bars


# ---------------------------------------------------------------------------
# Run one simulation
# ---------------------------------------------------------------------------
def run_one_sim(cfg: dict, bars: list) -> SimResult:
    from backtest_lab.engine_v2.bot import BotConfig, GinareaBot
    from backtest_lab.engine_v2.contracts import LINEAR, INVERSE, Side

    side = Side.SHORT if cfg["side"] == "SHORT" else Side.LONG
    contract = LINEAR if cfg["contract"] == "LINEAR" else INVERSE

    bot_cfg = BotConfig(
        bot_id=cfg["bot_id"],
        alias=cfg["bot_id"],
        side=side,
        contract=contract,
        order_size=cfg["order_size"],
        order_count=cfg["order_count"],
        grid_step_pct=cfg["grid_step"],
        target_profit_pct=cfg["td"],
        min_stop_pct=cfg["min_stop"],
        max_stop_pct=cfg["max_stop"],
        instop_pct=cfg["instop"],
        boundaries_lower=cfg.get("boundaries_lower", 10_000.0),
        boundaries_upper=cfg.get("boundaries_upper", 999_999.0),
        indicator_period=cfg.get("indicator_period", 30),
        indicator_threshold_pct=cfg.get("indicator_threshold_pct", 0.3),
        dsblin=cfg.get("dsblin", False),
        leverage=100,
    )

    bot = GinareaBot(bot_cfg)
    for i, bar in enumerate(bars):
        bot.step(bar, i)

    last_price = bars[-1].close if bars else 0.0
    return SimResult(
        bot_id=cfg["bot_id"],
        side=cfg["side"],
        contract=cfg["contract"],
        td=cfg["td"],
        sim_trades=len(bot.closed_orders),
        sim_realized=bot.realized_pnl,
        sim_volume=bot.in_qty_notional + bot.out_qty_notional,
        sim_unrealized=bot.unrealized_pnl(last_price),
    )


# ---------------------------------------------------------------------------
# Calibration math
# ---------------------------------------------------------------------------
def safe_k(numerator: float, denominator: float) -> Optional[float]:
    if denominator == 0 or math.isnan(denominator) or math.isnan(numerator):
        return None
    return numerator / denominator


def group_stats(ks: list[float]) -> dict:
    if not ks:
        return dict(mean=None, std=None, cv=None, min=None, max=None, n=0)
    mean = statistics.mean(ks)
    std = statistics.stdev(ks) if len(ks) > 1 else 0.0
    cv = (std / mean * 100) if mean != 0 else float("inf")
    return dict(mean=mean, std=std, cv=cv, min=min(ks), max=max(ks), n=len(ks))


def verdict(cv: Optional[float]) -> str:
    if cv is None:
        return "UNKNOWN"
    if cv < 15:
        return "STABLE"
    if cv < 35:
        return "TD-DEPENDENT"
    return "FRACTURED"


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------
def write_report(rows: list[CalibRow], groups: dict, out_path: Path) -> None:
    buf = io.StringIO()
    ts_now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    buf.write(f"# Calibration vs GinArea — {ts_now}\n\n")
    buf.write("**Period:** 2025-05-01 → 2026-04-29 (frozen BTCUSDT 1m)  \n")
    buf.write("**Engine:** backtest_lab engine_v2  \n")
    buf.write("**Resolution gap:** 1m bars vs GinArea tick-level  \n\n")
    buf.write("---\n\n")

    # Main table
    buf.write("## Per-run calibration table\n\n")
    hdr = ("| ID | Dir | Ctr | TD"
           " | sim_trades | ga_trig | K_trades"
           " | sim_realized | ga_realized | K_realized"
           " | sim_volume | ga_volume | K_volume |\n")
    sep = ("|---|---|---|---"
           "|---:|---:|---:"
           "|---:|---:|---:"
           "|---:|---:|---:|\n")
    buf.write(hdr)
    buf.write(sep)

    for r in rows:
        k_tr  = f"{r.k_trades:.2f}"  if r.k_trades  is not None else "N/A"
        k_re  = f"{r.k_realized:.2f}"
        k_vo  = f"{r.k_volume:.2f}"
        ga_tr = str(r.ga_triggers) if r.ga_triggers is not None else "N/A"
        buf.write(
            f"| {r.bot_id} | {r.side} | {r.contract} | {r.td:.2f}"
            f" | {r.sim_trades:,} | {ga_tr} | {k_tr}"
            f" | {r.sim_realized:,.4f} | {r.ga_realized:,.4f} | {k_re}"
            f" | {r.sim_volume:,.0f} | {r.ga_volume:,.0f} | {k_vo} |\n"
        )

    buf.write("\n---\n\n")

    # Per-group summary
    buf.write("## Per-group summary\n\n")
    for gname, gdata in groups.items():
        st_re = gdata["k_realized"]
        st_vo = gdata["k_volume"]
        st_tr = gdata.get("k_trades", {})

        buf.write(f"### {gname}\n\n")

        buf.write("| Metric | mean K | std | CV% | min | max | Verdict |\n")
        buf.write("|---|---:|---:|---:|---:|---:|---|\n")

        def row_line(name, st):
            if st["mean"] is None:
                return f"| {name} | N/A | N/A | N/A | N/A | N/A | UNKNOWN |\n"
            return (f"| {name} | {st['mean']:.3f} | {st['std']:.3f} | {st['cv']:.1f}%"
                    f" | {st['min']:.3f} | {st['max']:.3f} | **{verdict(st['cv'])}** |\n")

        buf.write(row_line("K_trades",   st_tr  if st_tr  else dict(mean=None,std=None,cv=None,min=None,max=None)))
        buf.write(row_line("K_realized", st_re))
        buf.write(row_line("K_volume",   st_vo))
        buf.write("\n")

        # Normalized comparison
        k_mean = st_re["mean"]
        if k_mean:
            buf.write("**Normalized sim_realized vs ga_realized** (sim × mean K_realized):\n\n")
            buf.write("| ID | TD | norm_sim_realized | ga_realized | err% |\n")
            buf.write("|---|---|---:|---:|---:|\n")
            for r in gdata["rows"]:
                norm = r.sim_realized * k_mean
                err_pct = (norm - r.ga_realized) / abs(r.ga_realized) * 100 if r.ga_realized else float("nan")
                buf.write(f"| {r.bot_id} | {r.td:.2f} | {norm:,.4f} | {r.ga_realized:,.4f} | {err_pct:+.1f}% |\n")
            buf.write("\n")

    buf.write("---\n\n")
    buf.write("## Conclusions\n\n")
    for gname, gdata in groups.items():
        st_re = gdata["k_realized"]
        v = verdict(st_re["cv"])
        k_mean = st_re["mean"]
        buf.write(f"**{gname}:** K_realized = {k_mean:.3f} ± {st_re['std']:.3f}"
                  f" (CV={st_re['cv']:.1f}%) → **{v}**  \n")
        if v == "STABLE":
            buf.write(f"  → Use K = {k_mean:.3f} as fixed calibration multiplier.  \n")
        elif v == "TD-DEPENDENT":
            buf.write(f"  → K varies with TD. Fit linear regression K(TD) before applying.  \n")
        else:
            buf.write(f"  → K is unstable. Do not use single multiplier; needs per-TD lookup.  \n")
    buf.write("\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(buf.getvalue(), encoding="utf-8")
    print(f"[calibrate] Report written: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(out_path: Path = DEFAULT_OUT) -> list[CalibRow]:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(out_path))
    args, _ = parser.parse_known_args()
    out_path = Path(args.out)

    # Verify OHLCV
    if not OHLCV_PATH.exists():
        print(f"[calibrate] STOP: OHLCV not found at {OHLCV_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"[calibrate] Loading OHLCV {SIM_START} → {SIM_END} ...")
    bars = load_ohlcv(SIM_START, SIM_END)
    print(f"[calibrate] Loaded {len(bars):,} bars")
    if len(bars) < 100_000:
        print("[calibrate] STOP: too few bars (<100k), data may be incomplete", file=sys.stderr)
        sys.exit(1)

    # Run all 9 sims
    rows: list[CalibRow] = []
    for i, cfg in enumerate(GINAREA_GROUND_TRUTH):
        print(f"[calibrate] [{i+1}/9] Simulating {cfg['bot_id']} side={cfg['side']} TD={cfg['td']} ...")
        sim = run_one_sim(cfg, bars)

        k_tr = safe_k(cfg["ga_triggers"], sim.sim_trades) if cfg["ga_triggers"] else None
        k_re = safe_k(cfg["ga_realized"], sim.sim_realized)
        k_vo = safe_k(cfg["ga_volume"],   sim.sim_volume)

        rows.append(CalibRow(
            bot_id=cfg["bot_id"],
            side=cfg["side"],
            contract=cfg["contract"],
            td=cfg["td"],
            sim_trades=sim.sim_trades,
            ga_triggers=cfg["ga_triggers"],
            k_trades=k_tr,
            sim_realized=sim.sim_realized,
            ga_realized=cfg["ga_realized"],
            k_realized=k_re if k_re is not None else float("nan"),
            sim_volume=sim.sim_volume,
            ga_volume=cfg["ga_volume"],
            k_volume=k_vo if k_vo is not None else float("nan"),
            normalized_sim_realized=0.0,  # filled below
        ))

    # Group stats
    groups: dict = {}

    def make_group(name: str, row_filter):
        grp_rows = [r for r in rows if row_filter(r)]
        k_re_vals = [r.k_realized for r in grp_rows if not math.isnan(r.k_realized)]
        k_vo_vals = [r.k_volume   for r in grp_rows if not math.isnan(r.k_volume)]
        k_tr_vals = [r.k_trades   for r in grp_rows if r.k_trades is not None]
        return dict(
            rows=grp_rows,
            k_realized=group_stats(k_re_vals),
            k_volume=group_stats(k_vo_vals),
            k_trades=group_stats(k_tr_vals),
        )

    groups["SHORT / USDT-M (LINEAR)"] = make_group("short", lambda r: r.side == "SHORT")
    groups["LONG / COIN-M (INVERSE)"] = make_group("long",  lambda r: r.side == "LONG")

    # Print summary to stdout
    for gname, gdata in groups.items():
        st = gdata["k_realized"]
        print(f"\n[calibrate] {gname}")
        print(f"  K_realized: mean={st['mean']:.3f} std={st['std']:.3f} "
              f"CV={st['cv']:.1f}% min={st['min']:.3f} max={st['max']:.3f} → {verdict(st['cv'])}")
        st = gdata["k_volume"]
        print(f"  K_volume:   mean={st['mean']:.3f} std={st['std']:.3f} "
              f"CV={st['cv']:.1f}% min={st['min']:.3f} max={st['max']:.3f} → {verdict(st['cv'])}")

    write_report(rows, groups, out_path)
    return rows


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
