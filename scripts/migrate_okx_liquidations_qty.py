"""One-shot migration: normalize OKX qty in market_live/liquidations.csv.

До 2026-05-12 market_collector писал OKX `sz` как есть (контракты), а
не BTC. Этот скрипт делит OKX-rows qty на 100 (1 contract = 0.01 BTC),
оставляя bybit/binance нетронутыми. Идемпотентный? **Нет** — повторный
запуск разделит ещё раз. Бэкап оригинала пишется рядом с .bak.

Запуск:
    python scripts/migrate_okx_liquidations_qty.py            # dry-run
    python scripts/migrate_okx_liquidations_qty.py --apply    # apply
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "market_live" / "liquidations.csv"
BAK_PATH = CSV_PATH.with_suffix(".csv.pre-okx-normalize.bak")

OKX_CONTRACT_SIZE_BTC = 0.01


def migrate(apply: bool) -> int:
    if not CSV_PATH.exists():
        print(f"no CSV at {CSV_PATH}")
        return 1
    rows: list[dict] = []
    headers: list[str] = []
    okx_count = 0
    okx_before_sum = 0.0
    okx_after_sum = 0.0
    other_count = 0
    skipped = 0

    with CSV_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        for row in reader:
            ex = (row.get("exchange") or "").strip().lower()
            qty_str = (row.get("qty") or "").strip()
            if ex == "okx" and qty_str:
                try:
                    qty = float(qty_str)
                    new_qty = qty * OKX_CONTRACT_SIZE_BTC
                    okx_count += 1
                    okx_before_sum += qty
                    okx_after_sum += new_qty
                    row["qty"] = f"{new_qty:.6f}"
                except ValueError:
                    skipped += 1
            elif qty_str:
                other_count += 1
            else:
                skipped += 1
            rows.append(row)

    print(f"OKX rows:    {okx_count}  (sum before={okx_before_sum:.1f}  sum after={okx_after_sum:.2f} BTC)")
    print(f"Other rows:  {other_count}  (unchanged)")
    print(f"Skipped:     {skipped}  (missing qty)")

    if not apply:
        print("\nDRY-RUN. Re-run with --apply to write.")
        return 0

    shutil.copy2(CSV_PATH, BAK_PATH)
    print(f"\nBackup: {BAK_PATH}")
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Wrote {len(rows)} rows.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sys.exit(migrate(apply=args.apply))
