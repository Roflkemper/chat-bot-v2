"""Boundary expand manager — авто-расширение border_top шорт-ботов.

Триггер: цена >= border_top * (1 + gap_pct/100) дольше dwell_min минут.
Действие (dry_run): log JSONL.
Действие (live): PUT /bots/{id}/params с новым border.top.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CFG = _ROOT / "config" / "boundary_expand.yaml"


# ---------------------------------------------------------------------------
# Data helpers (pure functions — testable)
# ---------------------------------------------------------------------------

@dataclass
class BotSpec:
    bot_id: str
    alias: str
    border_top: float
    target: float       # gap.tog value


@dataclass
class ExpansionEvent:
    ts: str
    bot_id: str
    alias: str
    old_top: float
    new_top: float
    current_price: float
    high_5m: float
    dry_run: bool


def read_eligible_bots(
    params_csv: Path,
    *,
    target_min: float = 0.18,
    target_max: float = 0.30,
    aliases: dict[str, str] | None = None,
) -> list[BotSpec]:
    """Read latest params per bot, return eligible SHORT bots.

    Eligible: side==2 (SHORT), border.top > 0, target_min <= gap.tog <= target_max.
    """
    if not params_csv.exists():
        return []

    latest: dict[str, dict] = {}
    try:
        with params_csv.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                bid = row.get("bot_id", "").strip()
                if bid:
                    latest[bid] = row
    except Exception:
        logger.exception("boundary_expand.params_read_failed path=%s", params_csv)
        return []

    result: list[BotSpec] = []
    for bid, row in latest.items():
        try:
            raw = json.loads(row.get("raw_params_json", "{}") or "{}")
        except json.JSONDecodeError:
            continue

        if raw.get("side") != 2:
            continue

        border_top = float((raw.get("border") or {}).get("top") or 0)
        if border_top <= 0:
            continue

        target = float((raw.get("gap") or {}).get("tog") or 0)
        if not (target_min <= target <= target_max):
            continue

        alias = (aliases or {}).get(bid, row.get("bot_name", bid)[:20].strip())
        result.append(BotSpec(bot_id=bid, alias=alias, border_top=border_top, target=target))

    return result


def read_ohlcv_tail(market_1m_csv: Path, n: int = 5) -> tuple[float, float]:
    """Return (last_close, max_high_of_last_n_bars)."""
    if not market_1m_csv.exists():
        return 0.0, 0.0
    bars: list[tuple[float, float]] = []
    try:
        with market_1m_csv.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    bars.append((float(row["close"]), float(row["high"])))
                except (KeyError, ValueError):
                    pass
    except Exception:
        logger.exception("boundary_expand.ohlcv_read_failed")
        return 0.0, 0.0

    tail = bars[-n:] if len(bars) >= n else bars
    if not tail:
        return 0.0, 0.0
    last_close = tail[-1][0]
    max_high = max(c[1] for c in tail)
    return last_close, max_high


# ---------------------------------------------------------------------------
# Simulation helper (pure — for acceptance test)
# ---------------------------------------------------------------------------

def simulate_episode(
    bots: list[BotSpec],
    bars: list[dict],   # list of {ts, close, high}
    *,
    gap_pct: float = 0.50,
    dwell_min: int = 30,
    offset_pct: float = 0.50,
    cooldown_min: int = 60,
    max_expansions_per_24h: int = 4,
    max_total_offset_pct: float = 5.0,
) -> list[ExpansionEvent]:
    """Run boundary-expand logic over a list of synthetic 1m bars.

    Bars must be in chronological order. Each bar: {ts, close, high}.
    Returns list of ExpansionEvents that would fire.
    """
    above_since: dict[str, str | None] = {b.bot_id: None for b in bots}
    cooldown_until: dict[str, float] = {}
    expansions_24h: dict[str, list[float]] = {b.bot_id: [] for b in bots}
    original_top: dict[str, float] = {b.bot_id: b.border_top for b in bots}
    current_top: dict[str, float] = {b.bot_id: b.border_top for b in bots}
    events: list[ExpansionEvent] = []

    # Build 5-bar rolling window per bar index
    for bar_idx, bar in enumerate(bars):
        bar_ts = bar["ts"]
        try:
            bar_dt = datetime.fromisoformat(bar_ts.replace("Z", "+00:00"))
            bar_epoch = bar_dt.timestamp()
        except ValueError:
            continue

        price = float(bar["close"])
        high_5m = max(float(b["high"]) for b in bars[max(0, bar_idx - 4): bar_idx + 1])

        for bot in bots:
            bid = bot.bot_id
            c_top = current_top[bid]
            gap = (price - c_top) / c_top * 100

            if gap >= gap_pct:
                if above_since[bid] is None:
                    above_since[bid] = bar_ts

                # Compute dwell
                try:
                    since_dt = datetime.fromisoformat(above_since[bid].replace("Z", "+00:00"))  # type: ignore[arg-type]
                    dwell = (bar_epoch - since_dt.timestamp()) / 60
                except Exception:
                    dwell = 0.0

                if dwell < dwell_min:
                    continue

                # Guards
                if bar_epoch < cooldown_until.get(bid, 0):
                    continue
                now24 = [t for t in expansions_24h[bid] if t > bar_epoch - 86400]
                if len(now24) >= max_expansions_per_24h:
                    continue
                orig = original_top[bid]
                total_drift = (c_top - orig) / orig * 100
                if total_drift >= max_total_offset_pct:
                    continue

                # Fire expansion
                new_top = round(high_5m * (1 + offset_pct / 100), 2)
                events.append(ExpansionEvent(
                    ts=bar_ts,
                    bot_id=bid,
                    alias=bot.alias,
                    old_top=c_top,
                    new_top=new_top,
                    current_price=price,
                    high_5m=high_5m,
                    dry_run=True,
                ))
                current_top[bid] = new_top
                cooldown_until[bid] = bar_epoch + cooldown_min * 60
                expansions_24h[bid].append(bar_epoch)
                above_since[bid] = None  # reset dwell after expansion
            else:
                above_since[bid] = None  # price returned below threshold

    return events


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class BoundaryExpandManager:
    """Авто-расширение border_top шорт-ботов. Вызывать tick() каждые 60с.

    Singleton через instance() для использования из Telegram-хэндлеров.
    """
    _instance: "BoundaryExpandManager | None" = None

    def __init__(self, cfg_path: Path = _DEFAULT_CFG) -> None:
        raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        self._enabled: bool = bool(raw.get("enabled", True))
        self._dry_run: bool = raw.get("mode", "dry_run") != "live"

        appl = raw.get("applicability", {})
        self._target_min: float = float(appl.get("target_min", 0.18))
        self._target_max: float = float(appl.get("target_max", 0.30))

        trig = raw.get("trigger", {})
        self._gap_pct: float = float(trig.get("gap_pct", 0.50))
        self._dwell_min: int = int(trig.get("dwell_min", 30))

        act = raw.get("action", {})
        self._offset_pct: float = float(act.get("offset_pct", 0.50))
        self._cooldown_min: int = int(act.get("cooldown_min", 60))

        guard = raw.get("guard", {})
        self._max_exp_24h: int = int(guard.get("max_expansions_per_24h", 4))
        self._max_offset_pct: float = float(guard.get("max_total_offset_pct", 5.0))

        log_file: str = raw.get("log_file", "logs/boundary_expand_events.jsonl")
        log_path = Path(log_file)
        self._log_path: Path = log_path if log_path.is_absolute() else _ROOT / log_file

        self._params_csv: Path = _ROOT / "ginarea_tracker" / "ginarea_live" / "params.csv"
        self._market_1m_csv: Path = _ROOT / "market_live" / "market_1m.csv"
        self._aliases_path: Path = _ROOT / "ginarea_tracker" / "bot_aliases.json"

        # Per-bot runtime state
        self._above_since: dict[str, float | None] = {}   # epoch when gap first opened
        self._cooldown_until: dict[str, float] = {}
        self._expansions_24h: dict[str, list[float]] = {}
        self._original_top: dict[str, float] = {}         # locked on first sighting
        self._current_top: dict[str, float] = {}          # updated after each expand
        self._last_expansion_ts: dict[str, str] = {}      # for status display

    # ------------------------------------------------------------------

    @classmethod
    def instance(cls, cfg_path: Path = _DEFAULT_CFG) -> "BoundaryExpandManager":
        if cls._instance is None:
            cls._instance = cls(cfg_path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ------------------------------------------------------------------

    async def tick(self) -> None:
        if not self._enabled:
            return
        try:
            await self._run_tick()
        except Exception:
            logger.exception("boundary_expand.tick_failed")

    async def _run_tick(self) -> None:
        aliases = self._load_aliases()
        bots = read_eligible_bots(
            self._params_csv,
            target_min=self._target_min,
            target_max=self._target_max,
            aliases=aliases,
        )
        if not bots:
            return

        price, high_5m = read_ohlcv_tail(self._market_1m_csv, n=5)
        if price <= 0:
            return

        now = time.time()
        for bot in bots:
            bid = bot.bot_id
            # Use tracked current_top if we expanded (in dry-run params.csv won't reflect it)
            c_top = self._current_top.get(bid, bot.border_top)
            if bid not in self._original_top:
                self._original_top[bid] = bot.border_top
            if bid not in self._expansions_24h:
                self._expansions_24h[bid] = []

            gap = (price - c_top) / c_top * 100

            if gap >= self._gap_pct:
                if self._above_since.get(bid) is None:
                    self._above_since[bid] = now
                    logger.debug("boundary_expand.above_start bot=%s gap=%.2f%%", bid, gap)

                dwell = (now - self._above_since[bid]) / 60  # type: ignore[operator]

                if dwell < self._dwell_min:
                    continue

                # Guard: cooldown
                if now < self._cooldown_until.get(bid, 0):
                    continue

                # Guard: max expansions per 24h
                self._expansions_24h[bid] = [t for t in self._expansions_24h[bid] if t > now - 86400]
                if len(self._expansions_24h[bid]) >= self._max_exp_24h:
                    logger.warning("boundary_expand.daily_limit_reached bot=%s", bid)
                    await self._notify(
                        f"⚠️ BOUNDARY EXPAND: {bot.alias} достиг лимита {self._max_exp_24h} расширений/24ч"
                    )
                    self._above_since[bid] = None
                    continue

                # Guard: max total offset
                orig = self._original_top[bid]
                total_drift = (c_top - orig) / orig * 100
                if total_drift >= self._max_offset_pct:
                    logger.warning("boundary_expand.max_offset_reached bot=%s drift=%.2f%%", bid, total_drift)
                    await self._notify(
                        f"⚠️ BOUNDARY EXPAND: {bot.alias} достиг лимита +{self._max_offset_pct}% от исходного"
                    )
                    self._above_since[bid] = None
                    continue

                await self._expand(bot, c_top, high_5m, price, now)
            else:
                self._above_since[bid] = None  # вернулся под порог

    async def _expand(
        self,
        bot: BotSpec,
        old_top: float,
        high_5m: float,
        price: float,
        now: float,
    ) -> None:
        new_top = round(high_5m * (1 + self._offset_pct / 100), 2)
        ts_now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if self._dry_run:
            logger.info(
                "boundary_expand.DRY_RUN bot=%s %s→%s price=%.2f",
                bot.alias, old_top, new_top, price,
            )
        else:
            try:
                from ginarea_tracker.ginarea_client import GinAreaClient
                import os
                client = GinAreaClient(
                    api_url=os.environ["GINAREA_API_URL"],
                    email=os.environ["GINAREA_EMAIL"],
                    password=os.environ["GINAREA_PASSWORD"],
                    totp_secret=os.environ["GINAREA_TOTP_SECRET"],
                )
                client.login()
                client.update_bot_border_top(bot.bot_id, new_top)
                logger.info(
                    "boundary_expand.LIVE bot=%s %s→%s",
                    bot.alias, old_top, new_top,
                )
            except Exception:
                logger.exception(
                    "boundary_expand.api_failed bot=%s — STOPPING expand for this bot",
                    bot.alias,
                )
                await self._notify(
                    f"❌ BOUNDARY EXPAND API ERROR: {bot.alias} — expand прерван, проверьте логи"
                )
                return

        # Update state
        self._current_top[bot.bot_id] = new_top
        self._cooldown_until[bot.bot_id] = now + self._cooldown_min * 60
        self._expansions_24h[bot.bot_id].append(now)
        self._above_since[bot.bot_id] = None
        self._last_expansion_ts[bot.bot_id] = ts_now

        # Log
        entry = {
            "ts": ts_now,
            "bot_id": bot.bot_id,
            "alias": bot.alias,
            "old_top": old_top,
            "new_top": new_top,
            "current_price": price,
            "high_5m": high_5m,
            "dry_run": self._dry_run,
        }
        self._log_event(entry)

        # Notify
        mode_tag = "[DRY-RUN] " if self._dry_run else ""
        text = (
            f"🔼 {mode_tag}BOUNDARY EXPAND: {bot.alias}\n"
            f"{old_top:,.0f} → {new_top:,.0f} (price={price:,.0f})"
        )
        await self._notify(text)

    # ------------------------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        logger.info("boundary_expand.set_enabled enabled=%s", enabled)

    def status_text(self) -> str:
        mode = "DRY-RUN" if self._dry_run else "LIVE"
        state = "✅ ON" if self._enabled else "⏸ OFF"
        lines = [
            f"🔼 Boundary Expand: {state} | {mode}",
            f"trigger: gap≥{self._gap_pct}% + dwell≥{self._dwell_min}мин",
            f"action: offset={self._offset_pct}%, cooldown={self._cooldown_min}мин",
            f"guards: max {self._max_exp_24h}/24ч, max+{self._max_offset_pct}% total",
        ]

        if self._last_expansion_ts:
            lines.append("")
            lines.append("Последние расширения:")
            for bid, ts in sorted(self._last_expansion_ts.items(), key=lambda x: x[1], reverse=True)[:6]:
                c_top = self._current_top.get(bid, "?")
                lines.append(f"  {bid[:12]}: {ts[11:16]} UTC → top={c_top:,.0f}" if isinstance(c_top, float) else f"  {bid[:12]}: {ts[11:16]} UTC")

        active = [bid for bid, since in self._above_since.items() if since is not None]
        if active:
            lines.append("")
            lines.append(f"Сейчас выше порога: {', '.join(active[:5])}")

        return "\n".join(lines)

    # ------------------------------------------------------------------

    def _load_aliases(self) -> dict[str, str]:
        if not self._aliases_path.exists():
            return {}
        try:
            return json.loads(self._aliases_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _log_event(self, event: dict[str, Any]) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
                fh.flush()
        except Exception:
            logger.exception("boundary_expand.log_failed")

    async def _notify(self, text: str) -> None:
        from services.telegram_alert_service import send_telegram_alert
        await send_telegram_alert(text)
