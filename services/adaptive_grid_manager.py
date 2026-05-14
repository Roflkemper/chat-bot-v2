"""Adaptive grid manager — авто-затягивание параметров шорт-ботов в просадке.

Логика:
- Каждые 5 минут читает snapshots.csv (current_profit = unrealized USD) и params.csv.
- Тригерует «затянуть» (target×0.60, gs×0.67) когда бот в просадке ≥4ч с unreal < -$200.
- Отпускает к original_params когда unreal > -$50.
- State персистируется в state/adaptive_grid_state.json (переживает рестарт).
- dry_run: пишет в JSONL вместо PUT /params.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CFG = _ROOT / "config" / "adaptive_grid.yaml"
_STATE_PATH = _ROOT / "state" / "adaptive_grid_state.json"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BotSnapshot:
    bot_id: str
    alias: str
    unrealized_usd: float   # current_profit from snapshots.csv
    gap_tog: float          # gap.tog from params.csv
    gs: float               # gs from params.csv


@dataclass
class BotGridState:
    """Persisted per-bot state."""
    mode: str = "original"               # "original" | "tightened"
    original_gap_tog: float = 0.0
    original_gs: float = 0.0
    drawdown_start_epoch: float | None = None   # when unreal crossed below release threshold
    last_release_epoch: float | None = None
    tightenings_24h: list[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure helpers (testable)
# ---------------------------------------------------------------------------

def read_short_bots_snapshot(
    params_csv: Path,
    snapshots_csv: Path,
    *,
    target_min: float = 0.18,
    target_max: float = 0.30,
) -> list[BotSnapshot]:
    """Return latest snapshot for eligible SHORT bots.

    Eligible: side==2 (SHORT), gap.tog in [target_min, target_max].
    """
    if not params_csv.exists() or not snapshots_csv.exists():
        return []

    # Latest params per bot
    params: dict[str, dict] = {}
    try:
        with params_csv.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                bid = row.get("bot_id", "").strip()
                if bid:
                    params[bid] = row
    except Exception:
        logger.exception("adaptive_grid.params_read_failed")
        return []

    # Latest snapshot per bot
    snaps: dict[str, dict] = {}
    try:
        with snapshots_csv.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                bid = row.get("bot_id", "").strip()
                if bid:
                    snaps[bid] = row
    except Exception:
        logger.exception("adaptive_grid.snapshots_read_failed")
        return []

    result: list[BotSnapshot] = []
    for bid, prow in params.items():
        srow = snaps.get(bid)
        if srow is None:
            continue

        try:
            raw = json.loads(prow.get("raw_params_json", "{}") or "{}")
        except json.JSONDecodeError:
            continue

        if raw.get("side") != 2:
            continue

        gap_tog = float((raw.get("gap") or {}).get("tog") or 0)
        if not (target_min <= gap_tog <= target_max):
            continue

        gs = float(raw.get("gs") or 0)
        if gs <= 0:
            continue

        try:
            unrealized = float(srow.get("current_profit") or 0)
        except (TypeError, ValueError):
            unrealized = 0.0

        alias = srow.get("alias") or prow.get("bot_name", bid)[:20].strip()

        result.append(BotSnapshot(
            bot_id=bid,
            alias=alias,
            unrealized_usd=unrealized,
            gap_tog=gap_tog,
            gs=gs,
        ))

    return result


def simulate_episode(
    events: list[dict],  # [{ts, bot_id, alias, unrealized_usd}]
    *,
    tighten_usd: float = -200.0,
    dwell_h: float = 4.0,
    release_usd: float = -50.0,
    target_factor: float = 0.60,
    gs_factor: float = 0.67,
    cooldown_after_release_h: float = 2.0,
    max_tightenings_per_24h: int = 3,
    original_gap_tog: float = 0.25,
    original_gs: float = 0.03,
) -> list[dict]:
    """Simulate adaptive grid logic over a time series of snapshots.

    Each event: {ts (ISO), bot_id, alias, unrealized_usd}.
    Returns list of action dicts: {ts, bot_id, alias, action, ...}.
    """
    # Per-bot state
    mode: dict[str, str] = {}
    drawdown_start: dict[str, float | None] = {}
    last_release: dict[str, float | None] = {}
    tightenings_24h: dict[str, list[float]] = {}
    actions: list[dict] = []

    for ev in events:
        ts_str = ev["ts"]
        bid = ev["bot_id"]
        alias = ev.get("alias", bid)
        unreal = float(ev["unrealized_usd"])

        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            epoch = dt.timestamp()
        except ValueError:
            continue

        # Init state for new bot
        if bid not in mode:
            mode[bid] = "original"
            drawdown_start[bid] = None
            last_release[bid] = None
            tightenings_24h[bid] = []

        cur_mode = mode[bid]
        gap_tog = original_gap_tog if cur_mode == "original" else round(original_gap_tog * target_factor, 4)
        gs = original_gs if cur_mode == "original" else round(original_gs * gs_factor, 4)

        # Track drawdown start (when dropped below release threshold)
        if unreal < release_usd:
            if drawdown_start[bid] is None:
                drawdown_start[bid] = epoch
        else:
            drawdown_start[bid] = None  # recovered

        # Release trigger
        if cur_mode == "tightened" and unreal >= release_usd:
            mode[bid] = "original"
            last_release[bid] = epoch
            drawdown_start[bid] = None
            actions.append({
                "ts": ts_str, "bot_id": bid, "alias": alias, "action": "release",
                "unrealized_usd": unreal,
                "new_gap_tog": original_gap_tog, "new_gs": original_gs,
            })
            continue

        # Tighten trigger
        if cur_mode == "original" and unreal < tighten_usd:
            # Dwell check
            ds = drawdown_start[bid]
            if ds is None or (epoch - ds) / 3600 < dwell_h:
                continue

            # Cooldown after release
            lr = last_release[bid]
            if lr is not None and (epoch - lr) / 3600 < cooldown_after_release_h:
                continue

            # Max tightenings/24h
            tightenings_24h[bid] = [t for t in tightenings_24h[bid] if t > epoch - 86400]
            if len(tightenings_24h[bid]) >= max_tightenings_per_24h:
                continue

            new_tog = round(original_gap_tog * target_factor, 4)
            new_gs = round(original_gs * gs_factor, 4)
            mode[bid] = "tightened"
            tightenings_24h[bid].append(epoch)
            actions.append({
                "ts": ts_str, "bot_id": bid, "alias": alias, "action": "tighten",
                "unrealized_usd": unreal,
                "new_gap_tog": new_tog, "new_gs": new_gs,
                "original_gap_tog": original_gap_tog, "original_gs": original_gs,
                "dwell_h": round((epoch - ds) / 3600, 2),  # type: ignore[operator]
            })

    return actions


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class AdaptiveGridManager:
    """Adaptive grid manager — singleton, тик каждые 5 минут."""

    _instance: "AdaptiveGridManager | None" = None

    def __init__(self, cfg_path: Path = _DEFAULT_CFG) -> None:
        raw: dict[str, Any] = {}
        try:
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            logger.exception("adaptive_grid.cfg_load_failed path=%s", cfg_path)

        cfg = raw.get("adaptive_grid", raw)  # support both top-level and nested
        self._enabled: bool = bool(cfg.get("enabled", True))
        self._dry_run: bool = cfg.get("mode", "dry_run") != "live"

        appl = cfg.get("applicability", {})
        self._target_min: float = float(appl.get("target_min", 0.18))
        self._target_max: float = float(appl.get("target_max", 0.30))

        trig = cfg.get("tighten_trigger", {})
        self._tighten_usd: float = float(trig.get("unrealized_usd", -200.0))
        self._dwell_h: float = float(trig.get("dwell_h", 4.0))

        rel = cfg.get("release_trigger", {})
        self._release_usd: float = float(rel.get("unrealized_usd", -50.0))

        tp = cfg.get("tightened_params", {})
        self._target_factor: float = float(tp.get("target_factor", 0.60))
        self._gs_factor: float = float(tp.get("gs_factor", 0.67))

        guard = cfg.get("guard", {})
        self._cooldown_release_h: float = float(guard.get("cooldown_after_release_h", 2.0))
        self._max_tighten_24h: int = int(guard.get("max_tightenings_per_24h", 3))

        log_file: str = cfg.get("log_file", "logs/adaptive_grid_events.jsonl")
        lp = Path(log_file)
        self._log_path: Path = lp if lp.is_absolute() else _ROOT / log_file
        self._state_path: Path = _STATE_PATH

        self._params_csv: Path = _ROOT / "ginarea_tracker" / "ginarea_live" / "params.csv"
        self._snapshots_csv: Path = _ROOT / "ginarea_tracker" / "ginarea_live" / "snapshots.csv"

        # Runtime state — loaded from disk then kept in memory
        self._state: dict[str, BotGridState] = self._load_state()

    # ------------------------------------------------------------------
    # Singleton

    @classmethod
    def instance(cls, cfg_path: Path = _DEFAULT_CFG) -> "AdaptiveGridManager":
        if cls._instance is None:
            cls._instance = cls(cfg_path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ------------------------------------------------------------------
    # Tick

    async def tick(self) -> None:
        if not self._enabled:
            return
        try:
            await self._run_tick()
        except Exception:
            logger.exception("adaptive_grid.tick_failed")

    async def _run_tick(self) -> None:
        bots = read_short_bots_snapshot(
            self._params_csv,
            self._snapshots_csv,
            target_min=self._target_min,
            target_max=self._target_max,
        )
        if not bots:
            return

        now = time.time()
        changed = False

        for bot in bots:
            bid = bot.bot_id

            # Init state for new bot
            if bid not in self._state:
                self._state[bid] = BotGridState(
                    original_gap_tog=bot.gap_tog,
                    original_gs=bot.gs,
                )
                changed = True

            st = self._state[bid]

            # If tightened and we see original params from API — restore original in state
            # (handles case where someone manually reset params)
            if st.mode == "original" and st.original_gap_tog == 0.0:
                st.original_gap_tog = bot.gap_tog
                st.original_gs = bot.gs
                changed = True

            unreal = bot.unrealized_usd

            # Drawdown tracking (when did we cross below release threshold)
            if unreal < self._release_usd:
                if st.drawdown_start_epoch is None:
                    st.drawdown_start_epoch = now
                    changed = True
            else:
                if st.drawdown_start_epoch is not None:
                    st.drawdown_start_epoch = None
                    changed = True

            # Release trigger
            if st.mode == "tightened" and unreal >= self._release_usd:
                await self._release(bot, st, now)
                changed = True
                continue

            # Tighten trigger
            if st.mode == "original" and unreal < self._tighten_usd:
                # Dwell check
                ds = st.drawdown_start_epoch
                if ds is None or (now - ds) / 3600 < self._dwell_h:
                    continue

                # Cooldown after release
                lr = st.last_release_epoch
                if lr is not None and (now - lr) / 3600 < self._cooldown_release_h:
                    logger.info(
                        "adaptive_grid.tighten_cooldown bot=%s release_h_ago=%.1f",
                        bot.alias, (now - lr) / 3600,
                    )
                    continue

                # Max tightenings per 24h
                st.tightenings_24h = [t for t in st.tightenings_24h if t > now - 86400]
                if len(st.tightenings_24h) >= self._max_tighten_24h:
                    logger.warning(
                        "adaptive_grid.daily_limit_reached bot=%s limit=%d",
                        bot.alias, self._max_tighten_24h,
                    )
                    await self._notify(
                        f"⚠️ ADAPTIVE GRID: {bot.alias} достиг лимита {self._max_tighten_24h} затяжек/24ч"
                    )
                    continue

                await self._tighten(bot, st, now)
                changed = True

        if changed:
            self._save_state()

    # ------------------------------------------------------------------
    # Actions

    async def _tighten(self, bot: BotSnapshot, st: BotGridState, now: float) -> None:
        new_tog = round(st.original_gap_tog * self._target_factor, 4)
        new_gs = round(st.original_gs * self._gs_factor, 4)
        ts_now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        dwell_h = round((now - (st.drawdown_start_epoch or now)) / 3600, 1)

        if self._dry_run:
            logger.info(
                "adaptive_grid.DRY_RUN tighten bot=%s gap_tog=%s→%s gs=%s→%s unreal=%.0f dwell_h=%.1f",
                bot.alias, st.original_gap_tog, new_tog, st.original_gs, new_gs,
                bot.unrealized_usd, dwell_h,
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
                client.update_bot_grid_params(bot.bot_id, new_tog, new_gs)
                logger.info(
                    "adaptive_grid.LIVE tighten bot=%s gap_tog=%s→%s gs=%s→%s",
                    bot.alias, st.original_gap_tog, new_tog, st.original_gs, new_gs,
                )
            except Exception:
                logger.exception("adaptive_grid.api_tighten_failed bot=%s — skipping", bot.alias)
                await self._notify(f"❌ ADAPTIVE GRID API ERROR: {bot.alias} tighten — проверьте логи")
                return

        # Update state
        st.mode = "tightened"
        st.tightenings_24h.append(now)

        entry = {
            "ts": ts_now, "bot_id": bot.bot_id, "alias": bot.alias,
            "action": "tighten",
            "unrealized_usd": bot.unrealized_usd,
            "dwell_h": dwell_h,
            "original_gap_tog": st.original_gap_tog,
            "original_gs": st.original_gs,
            "new_gap_tog": new_tog,
            "new_gs": new_gs,
            "dry_run": self._dry_run,
        }
        self._log_event(entry)

        mode_tag = "[DRY-RUN] " if self._dry_run else ""
        text = (
            f"📉 {mode_tag}ADAPTIVE GRID TIGHTEN: {bot.alias}\n"
            f"gap.tog {st.original_gap_tog}→{new_tog} | gs {st.original_gs}→{new_gs}\n"
            f"unreal=${bot.unrealized_usd:.0f} | dwell={dwell_h}h"
        )
        await self._notify(text)

    async def _release(self, bot: BotSnapshot, st: BotGridState, now: float) -> None:
        ts_now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if self._dry_run:
            logger.info(
                "adaptive_grid.DRY_RUN release bot=%s gap_tog→%s gs→%s unreal=%.0f",
                bot.alias, st.original_gap_tog, st.original_gs, bot.unrealized_usd,
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
                client.update_bot_gap_and_gs(bot.bot_id, st.original_gap_tog, st.original_gs)
                logger.info(
                    "adaptive_grid.LIVE release bot=%s gap_tog→%s gs→%s",
                    bot.alias, st.original_gap_tog, st.original_gs,
                )
            except Exception:
                logger.exception("adaptive_grid.api_release_failed bot=%s — skipping", bot.alias)
                await self._notify(f"❌ ADAPTIVE GRID API ERROR: {bot.alias} release — проверьте логи")
                return

        # Update state
        st.mode = "original"
        st.last_release_epoch = now
        st.drawdown_start_epoch = None

        entry = {
            "ts": ts_now, "bot_id": bot.bot_id, "alias": bot.alias,
            "action": "release",
            "unrealized_usd": bot.unrealized_usd,
            "restored_gap_tog": st.original_gap_tog,
            "restored_gs": st.original_gs,
            "dry_run": self._dry_run,
        }
        self._log_event(entry)

        mode_tag = "[DRY-RUN] " if self._dry_run else ""
        text = (
            f"📈 {mode_tag}ADAPTIVE GRID RELEASE: {bot.alias}\n"
            f"gap.tog→{st.original_gap_tog} | gs→{st.original_gs}\n"
            f"unreal=${bot.unrealized_usd:.0f}"
        )
        await self._notify(text)

    # ------------------------------------------------------------------
    # Public control

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        logger.info("adaptive_grid.set_enabled enabled=%s", enabled)

    def status_text(self) -> str:
        mode_tag = "DRY-RUN" if self._dry_run else "LIVE"
        state_tag = "✅ ON" if self._enabled else "⏸ OFF"
        lines = [
            f"📊 Adaptive Grid: {state_tag} | {mode_tag}",
            f"tighten: unreal<${self._tighten_usd:.0f} + dwell≥{self._dwell_h}h",
            f"release: unreal>${self._release_usd:.0f}",
            f"factors: target×{self._target_factor} gs×{self._gs_factor}",
            f"guards: cooldown={self._cooldown_release_h}h after release, max {self._max_tighten_24h}/24h",
            "",
        ]

        if not self._state:
            lines.append("Ботов не обнаружено")
            return "\n".join(lines)

        for bid, st in sorted(self._state.items()):
            mode_emoji = "🔴" if st.mode == "tightened" else "🟢"
            t24 = len([t for t in st.tightenings_24h if t > time.time() - 86400])
            line = f"{mode_emoji} {bid[:12]} [{st.mode}] tighten24h={t24}"
            if st.mode == "tightened":
                line += f" | orig_tog={st.original_gap_tog} orig_gs={st.original_gs}"
            lines.append(line)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # State persistence

    def _load_state(self) -> dict[str, BotGridState]:
        if not self._state_path.exists():
            return {}
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            result: dict[str, BotGridState] = {}
            for bid, d in raw.items():
                result[bid] = BotGridState(
                    mode=d.get("mode", "original"),
                    original_gap_tog=float(d.get("original_gap_tog", 0)),
                    original_gs=float(d.get("original_gs", 0)),
                    drawdown_start_epoch=d.get("drawdown_start_epoch"),
                    last_release_epoch=d.get("last_release_epoch"),
                    tightenings_24h=list(d.get("tightenings_24h", [])),
                )
            logger.info("adaptive_grid.state_loaded bots=%d", len(result))
            return result
        except Exception:
            logger.exception("adaptive_grid.state_load_failed — starting fresh")
            return {}

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {bid: asdict(st) for bid, st in self._state.items()}
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._state_path)
        except Exception:
            logger.exception("adaptive_grid.state_save_failed")

    # ------------------------------------------------------------------
    # Helpers

    def _log_event(self, event: dict[str, Any]) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
                fh.flush()
        except Exception:
            logger.exception("adaptive_grid.log_failed")

    async def _notify(self, text: str) -> None:
        from services.telegram_alert_service import send_telegram_alert
        await send_telegram_alert(text)
