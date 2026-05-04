"""Migrate / seed bot_registry.json from BOT_INVENTORY.md + ginarea_live/snapshots.csv.

Usage:
    python scripts/migrate_bot_ids.py --dry-run     # print proposed registry
    python scripts/migrate_bot_ids.py --apply       # write data/bot_registry.json

Idempotent: re-running --apply preserves existing UIDs and only appends new bots.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.bot_registry.resolver import REGISTRY_PATH, _invalidate_cache

SNAPSHOTS_PATH = ROOT / "ginarea_live" / "snapshots.csv"


# Heuristic: classify side from name. Operator can edit registry post-apply.
def _infer_side(name: str) -> str:
    n = name.lower()
    if "spot" in n:
        return "spot"
    if "test" in n:
        return "test"
    if "short" in n or "шорт" in n:
        return "short"
    if "long" in n or "лонг" in n:
        return "long"
    if "hedge" in n or "хедж" in n:
        return "hedge"
    return "long"  # default fallback


def _infer_symbol(name: str) -> str:
    n = name.lower()
    if "xrp" in n:
        return "xrpusdt"
    return "btcusdt"


def _scan_snapshots() -> dict[str, dict]:
    """Return dict of {ginarea_id: {display_name, status, alias_short}} from CSV."""
    if not SNAPSHOTS_PATH.exists():
        return {}
    out: dict[str, dict] = {}
    with SNAPSHOTS_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gid = str(row.get("bot_id", "")).strip().rstrip(".0")
            if not gid:
                continue
            name = (row.get("bot_name") or "").strip()
            alias = (row.get("alias") or "").strip()
            status_code = (row.get("status") or "").strip()
            status = {"2": "running", "12": "paused", "0": "off"}.get(status_code, "unknown")
            # latest record wins (CSV is append-only, last row is latest)
            out[gid] = {
                "ginarea_id": gid,
                "display_name": name,
                "alias_short": alias if alias else None,
                "status": status,
            }
    return out


def _next_seq(existing: dict, platform: str, side: str, symbol: str) -> int:
    """Smallest seq number not yet used for the (platform, side, symbol) tuple."""
    used: set[int] = set()
    prefix = f"{platform}:{side}:{symbol}:"
    for uid in existing.get("bots", {}).keys():
        if uid.startswith(prefix):
            try:
                used.add(int(uid.split(":")[-1]))
            except ValueError:
                pass
    seq = 1
    while seq in used:
        seq += 1
    return seq


def build_proposed_registry(existing: dict | None = None) -> dict:
    """Combine existing registry (for stable UIDs) with current scan."""
    existing = existing or {"version": "v0.1", "bots": {}}
    snap = _scan_snapshots()
    # Map ginarea_id → uid in existing registry for stable mapping
    gid_to_uid = {
        str(info.get("ginarea_id", "")): uid
        for uid, info in existing.get("bots", {}).items()
    }
    bots: dict[str, dict] = dict(existing.get("bots", {}))
    now = datetime.now(timezone.utc).isoformat()

    for gid, info in snap.items():
        if gid in gid_to_uid:
            uid = gid_to_uid[gid]
            # Update mutable fields (status, display_name, alias) but not UID/ginarea_id
            bots[uid] = {
                **bots[uid],
                "display_name": info["display_name"] or bots[uid].get("display_name", ""),
                "alias_short": info["alias_short"] or bots[uid].get("alias_short"),
                "status": info["status"],
            }
            continue
        # New bot — derive a UID
        platform = "binance"
        side = _infer_side(info["display_name"])
        symbol = _infer_symbol(info["display_name"])
        seq = _next_seq({"bots": bots}, platform, side, symbol)
        uid = f"{platform}:{side}:{symbol}:{seq:03d}"
        bots[uid] = {
            "ginarea_id": gid,
            "display_name": info["display_name"],
            "alias_short": info["alias_short"],
            "platform": platform,
            "side": side,
            "symbol": symbol.upper(),
            "first_seen": now,
            "status": info["status"],
            "notes": "",
        }
    return {"version": "v0.1", "updated_at": now, "bots": bots}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--registry", default=str(REGISTRY_PATH))
    args = ap.parse_args(argv)

    registry_path = Path(args.registry)
    existing = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else None
    proposed = build_proposed_registry(existing)

    if args.dry_run:
        sys.stdout.buffer.write(json.dumps(proposed, indent=2, ensure_ascii=False).encode("utf-8", "replace"))
        sys.stdout.buffer.write(b"\n")
        sys.stdout.buffer.write(f"\n# {len(proposed['bots'])} bots in proposed registry\n".encode("utf-8"))
        return 0

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(proposed, indent=2, ensure_ascii=False), encoding="utf-8")
    _invalidate_cache()
    print(f"Wrote {registry_path} with {len(proposed['bots'])} bots.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
