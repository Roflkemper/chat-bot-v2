"""Trade proposal flow — operator-confirmed virtual entries.

When a high-conviction setup fires (PRIORITY type + confidence >= threshold),
the bot builds a 'proposal' with a unique token and sends it to Telegram.
The operator has TTL minutes to /confirm <token> or /reject <token>.

Flow states (state/proposals.jsonl):
  PENDING    — proposal created, awaiting operator
  CONFIRMED  — operator approved within TTL (paper trade marked op-confirmed)
  REJECTED   — operator declined
  EXPIRED    — TTL exceeded without operator action

This is the half-step before real-exchange execution. No real money moves —
confirmed proposals open VIRTUAL paper trades (services/paper_trader). The
'operator_confirmed' flag in the paper journal lets us measure operator
discretion vs raw detector output (do confirmed trades win more?).

Future: services/setup_detector/proposal_executor.py will also place an
order on the exchange when ENABLE_LIVE_EXECUTION env var is set. Not in
this commit.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

PROPOSALS_PATH = Path("state/proposals.jsonl")
PROPOSAL_TTL_MINUTES = 10

# Detector types we propose for. Restrict to high-PF detectors to avoid
# spamming the operator with confirm-prompts for low-quality signals.
PROPOSE_FOR_TYPES = frozenset({
    "long_div_bos_confirmed",       # PF=4.49 hold_1h
    "long_div_bos_15m",              # PF=5.01 hold_4h
    "short_div_bos_15m",             # PF=3.85 hold_1h
    "long_multi_asset_confluence",   # PF=3.88 hold_1h, BTC+ETH
})
PROPOSE_MIN_CONFIDENCE = 75.0

# In-process lock for proposals.jsonl writes (multiple async tasks).
_FILE_LOCK = threading.Lock()


@dataclass
class Proposal:
    token: str               # short hex (8 chars), used in /confirm/<token>
    setup_id: str
    setup_type: str
    side: str                # "long" | "short"
    pair: str
    entry: float
    sl: float
    tp1: float
    tp2: Optional[float]
    rr: Optional[float]
    confidence: float
    strength: int
    proposed_at: str         # iso utc
    expires_at: str          # iso utc
    status: str = "PENDING"  # PENDING/CONFIRMED/REJECTED/EXPIRED
    decided_at: Optional[str] = None
    decided_by: Optional[int] = None  # chat_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _generate_token() -> str:
    return secrets.token_hex(4)   # 8 hex chars


def _append(record: dict[str, Any]) -> None:
    with _FILE_LOCK:
        PROPOSALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PROPOSALS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")


def _read_all() -> list[dict[str, Any]]:
    if not PROPOSALS_PATH.exists():
        return []
    out = []
    try:
        for line in PROPOSALS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except OSError:
        return []
    return out


def find_pending(token: str) -> Optional[dict[str, Any]]:
    """Return latest record for token if status is PENDING and not expired."""
    now = datetime.now(timezone.utc)
    matches = [r for r in _read_all() if r.get("token") == token]
    if not matches:
        return None
    # Walk from most recent backwards — we want the latest status.
    latest = matches[-1]
    if latest.get("status") != "PENDING":
        return None
    try:
        exp = datetime.fromisoformat(latest["expires_at"].replace("Z", "+00:00"))
        if now > exp:
            return None
    except Exception:
        return None
    return latest


def list_pending(now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Return all currently-PENDING (not expired) proposals."""
    now = now or datetime.now(timezone.utc)
    by_token: dict[str, dict] = {}
    for r in _read_all():
        by_token[r.get("token")] = r   # latest wins
    out: list[dict[str, Any]] = []
    for r in by_token.values():
        if r.get("status") != "PENDING":
            continue
        try:
            exp = datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if now > exp:
            continue
        out.append(r)
    out.sort(key=lambda r: r.get("proposed_at", ""))
    return out


def should_propose(setup) -> bool:
    """Filter: only propose for backtest-validated PRIORITY types with high conf."""
    stype = getattr(setup, "setup_type", None)
    stype_str = stype.value if hasattr(stype, "value") else str(stype or "")
    if stype_str not in PROPOSE_FOR_TYPES:
        return False
    conf = float(getattr(setup, "confidence_pct", 0))
    return conf >= PROPOSE_MIN_CONFIDENCE


def create_proposal(setup) -> Proposal:
    """Build a Proposal object from a Setup, append PENDING record. No send."""
    now = datetime.now(timezone.utc)
    token = _generate_token()
    stype = setup.setup_type.value if hasattr(setup.setup_type, "value") else str(setup.setup_type)
    side = "long" if stype.startswith("long_") else "short" if stype.startswith("short_") else "?"
    p = Proposal(
        token=token,
        setup_id=getattr(setup, "setup_id", "") or "",
        setup_type=stype,
        side=side,
        pair=getattr(setup, "pair", "BTCUSDT"),
        entry=float(getattr(setup, "entry_price", 0) or 0),
        sl=float(getattr(setup, "stop_price", 0) or 0),
        tp1=float(getattr(setup, "tp1_price", 0) or 0),
        tp2=float(getattr(setup, "tp2_price", 0) or 0) or None,
        rr=getattr(setup, "risk_reward", None),
        confidence=float(getattr(setup, "confidence_pct", 0) or 0),
        strength=int(getattr(setup, "strength", 0) or 0),
        proposed_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=PROPOSAL_TTL_MINUTES)).isoformat(),
        status="PENDING",
    )
    _append(p.to_dict())
    return p


def format_proposal_card(p: Proposal) -> str:
    """Operator-friendly Telegram card with confirm/reject instructions."""
    side_word = "🟢 LONG" if p.side == "long" else "🔴 SHORT"
    rr_str = f" RR {p.rr}" if p.rr else ""
    tp2_str = f" | TP2 {p.tp2:.0f}" if p.tp2 else ""
    lines = [
        f"⚡ TRADE PROPOSAL — {p.setup_type}",
        f"{side_word} @ {p.entry:.0f}",
        f"SL {p.sl:.0f} | TP1 {p.tp1:.0f}{tp2_str}{rr_str}",
        f"Conf {p.confidence:.0f}% | Strength {p.strength}/10",
        "",
        f"Token: {p.token}  ({PROPOSAL_TTL_MINUTES}min TTL)",
        f"  /confirm {p.token}  — открыть paper trade",
        f"  /reject {p.token}   — отклонить",
        "",
        "Если не ответить за 10 мин — auto-EXPIRE, paper-trade откроется без операторской подписи.",
    ]
    return "\n".join(lines)


def confirm_proposal(token: str, chat_id: int) -> tuple[bool, str, Optional[Proposal]]:
    """Mark proposal CONFIRMED and return Proposal data for paper-trade open.

    Returns: (success, message_for_operator, proposal_dict_if_success)
    """
    pending = find_pending(token)
    if pending is None:
        return False, f"❌ Token `{token}` не найден или уже истёк.", None
    confirmed = dict(pending)
    confirmed["status"] = "CONFIRMED"
    confirmed["decided_at"] = datetime.now(timezone.utc).isoformat()
    confirmed["decided_by"] = chat_id
    _append(confirmed)
    p = Proposal(**{k: v for k, v in confirmed.items() if k in Proposal.__dataclass_fields__})
    return True, f"✅ Confirmed `{token}` — открываю paper trade.", p


def reject_proposal(token: str, chat_id: int) -> tuple[bool, str]:
    """Mark proposal REJECTED."""
    pending = find_pending(token)
    if pending is None:
        return False, f"❌ Token `{token}` не найден или уже истёк."
    rejected = dict(pending)
    rejected["status"] = "REJECTED"
    rejected["decided_at"] = datetime.now(timezone.utc).isoformat()
    rejected["decided_by"] = chat_id
    _append(rejected)
    return True, f"❎ Rejected `{token}`."


def expire_stale() -> int:
    """Mark all PENDING records past expires_at as EXPIRED. Returns count."""
    now = datetime.now(timezone.utc)
    count = 0
    by_token: dict[str, dict] = {}
    for r in _read_all():
        by_token[r.get("token")] = r
    for r in by_token.values():
        if r.get("status") != "PENDING":
            continue
        try:
            exp = datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if now > exp:
            expired = dict(r)
            expired["status"] = "EXPIRED"
            expired["decided_at"] = now.isoformat()
            _append(expired)
            count += 1
    return count
