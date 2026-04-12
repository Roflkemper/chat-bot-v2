
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence


def _u(v: Any, default: str = "") -> str:
    try:
        if v is None:
            return default
        return str(v).strip().upper()
    except Exception:
        return default


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        if isinstance(v, str):
            v = v.replace(" ", "").replace(",", "")
        return float(v)
    except Exception:
        return default


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


@dataclass
class StrategyDecision:
    strategy_id: str
    action: str
    direction: str
    state: str
    score: float
    summary: str
    why: List[str] = field(default_factory=list)
    entry_hint: str = ""
    invalidation: str = ""
    setup_note: str = ""
    grid_bias: str = "WATCH"
    tags: List[str] = field(default_factory=list)
    priority: int = 50
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "action": self.action,
            "direction": self.direction,
            "state": self.state,
            "score": round(float(self.score or 0.0), 1),
            "summary": self.summary,
            "why": list(self.why or []),
            "entry_hint": self.entry_hint,
            "invalidation": self.invalidation,
            "setup_note": self.setup_note,
            "grid_bias": self.grid_bias,
            "tags": list(self.tags or []),
            "priority": int(self.priority or 0),
            "payload": dict(self.payload or {}),
        }


@dataclass
class StrategyContext:
    payload: Dict[str, Any]
    decision: Dict[str, Any]
    liquidity_decision: Dict[str, Any]
    liquidation_context: Dict[str, Any]
    liquidation_reaction: Dict[str, Any]
    liquidity_blocks: Dict[str, Any]
    impulse_character: Dict[str, Any]
    volume_confirmation: Dict[str, Any]
    reversal: Dict[str, Any]
    pattern_memory: Dict[str, Any]
    grid_strategy: Dict[str, Any]
    range_position: str
    direction_hint: str
    upper_block: Dict[str, Any]
    lower_block: Dict[str, Any]
    price: float


class StrategyPlugin(Protocol):
    strategy_id: str
    priority: int

    def evaluate(self, ctx: StrategyContext) -> Optional[StrategyDecision]:
        ...


def _block_zone(block: Dict[str, Any]) -> str:
    low = _f(block.get("low"), 0.0)
    high = _f(block.get("high"), 0.0)
    if low <= 0 and high <= 0:
        return "нет данных"
    if low > 0 and high > 0:
        lo, hi = min(low, high), max(low, high)
        return f"{lo:,.2f}-{hi:,.2f}".replace(",", " ")
    val = max(low, high)
    return f"{val:,.2f}".replace(",", " ")


def _edge_label(score: float) -> str:
    if score >= 72:
        return "STRONG"
    if score >= 56:
        return "WORKABLE"
    if score >= 38:
        return "WEAK"
    return "NO_EDGE"


def _norm_dir(v: Any) -> str:
    raw = _u(v, "NEUTRAL")
    if raw in {"LONG", "ЛОНГ", "UP", "BULL", "BULLISH", "ВВЕРХ"}:
        return "LONG"
    if raw in {"SHORT", "ШОРТ", "DOWN", "BEAR", "BEARISH", "ВНИЗ"}:
        return "SHORT"
    return "NEUTRAL"


def _range_edge_bias(range_position: str) -> str:
    pos = _u(range_position, "UNKNOWN")
    if "HIGH" in pos or "UPPER" in pos or "PREMIUM" in pos or "TOP" in pos:
        return "SHORT"
    if "LOW" in pos or "LOWER" in pos or "DISCOUNT" in pos or "BOTTOM" in pos:
        return "LONG"
    return "NEUTRAL"


class LiquidityTrapStrategy:
    strategy_id = "liquidity_trap"
    priority = 95

    def evaluate(self, ctx: StrategyContext) -> Optional[StrategyDecision]:
        reaction = _u(ctx.liquidation_reaction.get("acceptance"), "NONE")
        impulse = _u(ctx.impulse_character.get("state"), "NO_CLEAR_IMPULSE")
        volume_state = _u(ctx.volume_confirmation.get("state"), "NEUTRAL")
        strength = _f(ctx.liquidation_reaction.get("reaction_strength"), 0.0)
        block = ctx.upper_block if reaction == "REJECTED_ABOVE" else ctx.lower_block
        zone = _block_zone(block)

        if reaction == "REJECTED_ABOVE":
            score = 60.0 + strength * 0.18
            if impulse in {"TRAP_CANDIDATE_UP", "EXHAUSTION_UP"}:
                score += 10.0
            if volume_state in {"CONFIRMED", "SELLER_CONFIRMED", "BEAR_CONFIRMED"}:
                score += 6.0
            return StrategyDecision(
                strategy_id=self.strategy_id,
                action="ARM_SHORT" if score < 74 else "EXECUTE_PROBE_SHORT",
                direction="SHORT",
                state="TRAP_SHORT",
                score=min(score, 92.0),
                summary="верхний блок вынесли и рынок не принял цену выше: приоритет short after fake up",
                why=[
                    "есть rejection выше верхнего блока",
                    f"реакция по блоку: {ctx.liquidation_reaction.get('summary') or 'ложный вынос вверх'}",
                    f"характер движения: {ctx.impulse_character.get('comment') or 'вынос выглядит уставшим'}",
                ],
                entry_hint=f"ждать возврат под верхний блок {zone} и локальный bearish confirm",
                invalidation=f"закрепление выше верхнего блока {zone}",
                setup_note="контртренд только после confirm, не шортить первую свечу выноса",
                grid_bias="ARM_SHORT",
                tags=["trap", "rejected_above", "countertrend"],
            )

        if reaction == "REJECTED_BELOW":
            score = 60.0 + strength * 0.18
            if impulse in {"TRAP_CANDIDATE_DOWN", "EXHAUSTION_DOWN"}:
                score += 10.0
            if volume_state in {"CONFIRMED", "BUYER_CONFIRMED", "BULL_CONFIRMED"}:
                score += 6.0
            return StrategyDecision(
                strategy_id=self.strategy_id,
                action="ARM_LONG" if score < 74 else "EXECUTE_PROBE_LONG",
                direction="LONG",
                state="TRAP_LONG",
                score=min(score, 92.0),
                summary="нижний блок вынесли и рынок быстро вернул цену назад: приоритет long after fake down",
                why=[
                    "есть rejection ниже нижнего блока",
                    f"реакция по блоку: {ctx.liquidation_reaction.get('summary') or 'ложный пролив вниз'}",
                    f"характер движения: {ctx.impulse_character.get('comment') or 'пролив выглядит уставшим'}",
                ],
                entry_hint=f"ждать возврат выше нижнего блока {zone} и локальный bullish confirm",
                invalidation=f"закрепление ниже нижнего блока {zone}",
                setup_note="контртренд только после confirm, не ловить нож на первой свече",
                grid_bias="ARM_LONG",
                tags=["trap", "rejected_below", "countertrend"],
            )
        return None


class AcceptedContinuationStrategy:
    strategy_id = "accepted_continuation"
    priority = 90

    def evaluate(self, ctx: StrategyContext) -> Optional[StrategyDecision]:
        reaction = _u(ctx.liquidation_reaction.get("acceptance"), "NONE")
        impulse = _u(ctx.impulse_character.get("state"), "NO_CLEAR_IMPULSE")
        liq_pressure = _u(ctx.liquidity_decision.get("liq_side_pressure"), "NEUTRAL")
        vol_state = _u(ctx.volume_confirmation.get("state"), "NEUTRAL")

        if reaction == "ACCEPTED_ABOVE" and impulse == "CONTINUATION_UP":
            score = 64.0
            if liq_pressure == "UP":
                score += 8.0
            if vol_state in {"CONFIRMED", "BUYER_CONFIRMED", "BULL_CONFIRMED"}:
                score += 6.0
            zone = _block_zone(ctx.upper_block)
            return StrategyDecision(
                strategy_id=self.strategy_id,
                action="EXECUTE_LONG" if score >= 76 else "ARM_LONG",
                direction="LONG",
                state="CONTINUATION_LONG",
                score=min(score, 90.0),
                summary="рынок принял цену выше верхнего блока, движение вверх пока рабочее",
                why=[
                    "цена удерживается выше верхнего блока",
                    f"характер движения: {ctx.impulse_character.get('comment') or 'импульс вверх чистый'}",
                    f"ликвидность: {ctx.liquidity_decision.get('summary') or 'давление вверх'}",
                ],
                entry_hint=f"не chase; ждать retest верхнего блока {zone} и удержание выше",
                invalidation=f"возврат обратно под верхний блок {zone}",
                setup_note="вход по тренду только через retest/reclaim, без догонки в середине импульса",
                grid_bias="REDUCE_SHORT",
                tags=["accepted_above", "trend"],
            )

        if reaction == "ACCEPTED_BELOW" and impulse == "CONTINUATION_DOWN":
            score = 64.0
            if liq_pressure == "DOWN":
                score += 8.0
            if vol_state in {"CONFIRMED", "SELLER_CONFIRMED", "BEAR_CONFIRMED"}:
                score += 6.0
            zone = _block_zone(ctx.lower_block)
            return StrategyDecision(
                strategy_id=self.strategy_id,
                action="EXECUTE_SHORT" if score >= 76 else "ARM_SHORT",
                direction="SHORT",
                state="CONTINUATION_SHORT",
                score=min(score, 90.0),
                summary="рынок принял цену ниже нижнего блока, движение вниз пока рабочее",
                why=[
                    "цена удерживается ниже нижнего блока",
                    f"характер движения: {ctx.impulse_character.get('comment') or 'импульс вниз чистый'}",
                    f"ликвидность: {ctx.liquidity_decision.get('summary') or 'давление вниз'}",
                ],
                entry_hint=f"не chase; ждать retest нижнего блока {zone} и удержание ниже",
                invalidation=f"возврат обратно выше нижнего блока {zone}",
                setup_note="вход по тренду только через retest/reclaim, без догонки в конце свечи",
                grid_bias="REDUCE_LONG",
                tags=["accepted_below", "trend"],
            )
        return None


class RangeReentryStrategy:
    strategy_id = "range_reentry"
    priority = 80

    def evaluate(self, ctx: StrategyContext) -> Optional[StrategyDecision]:
        pos = _u(ctx.range_position, "UNKNOWN")
        edge_bias = _range_edge_bias(pos)
        reaction = _u(ctx.liquidation_reaction.get("acceptance"), "NONE")
        impulse = _u(ctx.impulse_character.get("state"), "NO_CLEAR_IMPULSE")
        pattern_bias = _norm_dir(ctx.pattern_memory.get("pattern_bias") or ctx.pattern_memory.get("direction"))

        if reaction not in {"NONE", "UNKNOWN"}:
            return None

        if edge_bias == "SHORT" and impulse in {"EXHAUSTION_UP", "TRAP_CANDIDATE_UP", "CHOP"}:
            score = 48.0
            if pattern_bias == "SHORT":
                score += 6.0
            return StrategyDecision(
                strategy_id=self.strategy_id,
                action="ARM_SHORT",
                direction="SHORT",
                state="RANGE_SHORT_SETUP",
                score=score,
                summary="цена у верхней части диапазона, продолжение не подтверждено: можно готовить short reaction",
                why=[
                    "локация ближе к верхнему краю диапазона",
                    "движение не даёт clean continuation",
                ],
                entry_hint=f"смотреть rejection в верхнем блоке {_block_zone(ctx.upper_block)}",
                invalidation=f"принятие цены выше {_block_zone(ctx.upper_block)}",
                setup_note="мягкий сценарий от range edge, только small/probe после confirm",
                grid_bias="ARM_SHORT",
                tags=["range", "edge", "soft"],
                priority=78,
            )

        if edge_bias == "LONG" and impulse in {"EXHAUSTION_DOWN", "TRAP_CANDIDATE_DOWN", "CHOP"}:
            score = 48.0
            if pattern_bias == "LONG":
                score += 6.0
            return StrategyDecision(
                strategy_id=self.strategy_id,
                action="ARM_LONG",
                direction="LONG",
                state="RANGE_LONG_SETUP",
                score=score,
                summary="цена у нижней части диапазона, продолжение не подтверждено: можно готовить long reaction",
                why=[
                    "локация ближе к нижнему краю диапазона",
                    "движение не даёт clean continuation",
                ],
                entry_hint=f"смотреть reclaim в нижнем блоке {_block_zone(ctx.lower_block)}",
                invalidation=f"принятие цены ниже {_block_zone(ctx.lower_block)}",
                setup_note="мягкий сценарий от range edge, только small/probe после confirm",
                grid_bias="ARM_LONG",
                tags=["range", "edge", "soft"],
                priority=78,
            )
        return None


class GridPreactivationStrategy:
    strategy_id = "grid_preactivation"
    priority = 70

    def evaluate(self, ctx: StrategyContext) -> Optional[StrategyDecision]:
        gs = ctx.grid_strategy
        if not gs:
            return None
        active = list(gs.get("active_bots") or [])
        strongest = str(gs.get("strongest_bot") or "NONE")
        side = _norm_dir(gs.get("contrarian_side"))
        deviation = _f(gs.get("deviation_abs_pct"), 0.0)
        if active:
            return StrategyDecision(
                strategy_id=self.strategy_id,
                action="ARM_LONG" if side == "LONG" else "ARM_SHORT" if side == "SHORT" else "WATCH",
                direction=side,
                state="GRID_PREACTIVE",
                score=min(35.0 + deviation * 10.0, 62.0),
                summary=f"3-bot grid engine уже видит рабочее отклонение: активны {', '.join(active)}",
                why=[
                    f"отклонение: {deviation:.2f}%",
                    f"strongest bot: {strongest}",
                    f"summary: {gs.get('summary') or 'grid logic active'}",
                ],
                entry_hint="для сетки допускается ранняя активация только по стороне рабочего отклонения",
                invalidation="если реакция на блок не подтверждится, сетки держать в reduced/watch",
                setup_note="это не market-entry, а grid-arming по отклонению",
                grid_bias="ARM_LONG" if side == "LONG" else "ARM_SHORT" if side == "SHORT" else "WATCH",
                tags=["grid", "deviation", "preactivation"],
            )
        return None


class ActionEngineV16:
    def __init__(self, strategies: Optional[Sequence[StrategyPlugin]] = None) -> None:
        self._strategies: List[StrategyPlugin] = sorted(
            list(strategies or [
                LiquidityTrapStrategy(),
                AcceptedContinuationStrategy(),
                RangeReentryStrategy(),
                GridPreactivationStrategy(),
            ]),
            key=lambda s: int(getattr(s, "priority", 50)),
            reverse=True,
        )

    def register_strategy(self, strategy: StrategyPlugin) -> None:
        self._strategies.append(strategy)
        self._strategies.sort(key=lambda s: int(getattr(s, "priority", 50)), reverse=True)

    def build_context(self, payload: Dict[str, Any]) -> StrategyContext:
        decision = _safe_dict(payload.get("decision"))
        blocks = _safe_dict(payload.get("liquidity_blocks"))
        pattern = _safe_dict(payload.get("pattern_memory_v2"))
        return StrategyContext(
            payload=payload,
            decision=decision,
            liquidity_decision=_safe_dict(payload.get("liquidity_decision")),
            liquidation_context=_safe_dict(payload.get("liquidation_context")),
            liquidation_reaction=_safe_dict(payload.get("liquidation_reaction")),
            liquidity_blocks=blocks,
            impulse_character=_safe_dict(payload.get("impulse_character")),
            volume_confirmation=_safe_dict(payload.get("volume_confirmation")),
            reversal=_safe_dict(payload.get("reversal_v15")),
            pattern_memory=pattern,
            grid_strategy=_safe_dict(payload.get("grid_strategy")),
            range_position=str(payload.get("range_position") or decision.get("range_position") or "UNKNOWN"),
            direction_hint=_norm_dir(payload.get("forecast_direction") or decision.get("direction")),
            upper_block=_safe_dict(blocks.get("upper_block")),
            lower_block=_safe_dict(blocks.get("lower_block")),
            price=_f(payload.get("price"), 0.0),
        )

    def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ctx = self.build_context(payload)
        candidates: List[StrategyDecision] = []
        for strategy in self._strategies:
            try:
                decision = strategy.evaluate(ctx)
            except Exception as exc:
                candidates.append(
                    StrategyDecision(
                        strategy_id=getattr(strategy, "strategy_id", "unknown_strategy"),
                        action="WATCH",
                        direction="NEUTRAL",
                        state="STRATEGY_ERROR",
                        score=0.0,
                        summary=f"strategy error: {type(exc).__name__}",
                        why=[str(exc)],
                        priority=0,
                    )
                )
                continue
            if decision is not None:
                candidates.append(decision)

        # fallback: always produce action
        if not candidates:
            gs_side = _norm_dir(ctx.grid_strategy.get("contrarian_side"))
            gs_active = list(ctx.grid_strategy.get("active_bots") or [])
            fallback_action = "WATCH"
            fallback_dir = ctx.direction_hint if ctx.direction_hint != "NEUTRAL" else _range_edge_bias(ctx.range_position)
            fallback_state = "WATCH_ZONE"
            fallback_summary = "край диапазона ещё не подтверждён; продолжаем смотреть реакцию"
            fallback_score = 24.0
            if gs_active and gs_side in {"LONG", "SHORT"}:
                fallback_action = "ARM_LONG" if gs_side == "LONG" else "ARM_SHORT"
                fallback_dir = gs_side
                fallback_state = "GRID_PREPARE"
                fallback_summary = f"отклонение уже есть; можно готовить {gs_side.lower()}-сценарий под сетку"
                fallback_score = 34.0
            candidates.append(
                StrategyDecision(
                    strategy_id="fallback_watch",
                    action=fallback_action,
                    direction=fallback_dir,
                    state=fallback_state,
                    score=fallback_score,
                    summary=fallback_summary,
                    why=[
                        "нет подтверждённого acceptance/reclaim по блоку",
                        f"характер движения: {ctx.impulse_character.get('comment') or 'пока без clean move'}",
                        f"ликвидность: {ctx.liquidity_decision.get('summary') or 'явного преимущества нет'}",
                    ],
                    entry_hint="ждать касание блока + возврат / удержание",
                    invalidation="без активной стороны нет рабочей invalidation-зоны",
                    setup_note="есть мягкий сценарий, но execution пока не разрешён",
                    grid_bias="WATCH",
                    tags=["fallback", "watch"],
                    priority=1,
                )
            )

        # choose best, favor stronger score then priority
        best = sorted(candidates, key=lambda c: (float(c.score), int(c.priority)), reverse=True)[0]

        direction = _norm_dir(best.direction)
        edge_score = max(0.0, min(100.0, float(best.score or 0.0)))
        edge_label = _edge_label(edge_score)
        trade_authorized = _u(best.action).startswith("EXECUTE_")
        setup_valid = trade_authorized or _u(best.action).startswith("ARM_")

        grid_map = {
            "ARM_LONG": {"status": "ARM_LONG", "long_grid": "ARM", "short_grid": "HOLD"},
            "ARM_SHORT": {"status": "ARM_SHORT", "long_grid": "HOLD", "short_grid": "ARM"},
            "EXECUTE_PROBE_LONG": {"status": "ENABLE_SMALL", "long_grid": "ENABLE_SMALL", "short_grid": "HOLD"},
            "EXECUTE_PROBE_SHORT": {"status": "ENABLE_SMALL", "long_grid": "HOLD", "short_grid": "ENABLE_SMALL"},
            "EXECUTE_LONG": {"status": "TREND_UP", "long_grid": "HOLD", "short_grid": "REDUCE"},
            "EXECUTE_SHORT": {"status": "TREND_DOWN", "long_grid": "REDUCE", "short_grid": "HOLD"},
            "WATCH": {"status": "WATCH", "long_grid": "HOLD", "short_grid": "HOLD"},
        }.get(_u(best.action), {"status": "WATCH", "long_grid": "HOLD", "short_grid": "HOLD"})

        return {
            "direction": direction,
            "action": _u(best.action, "WATCH"),
            "state": best.state,
            "summary": best.summary,
            "setup_note": best.setup_note or best.summary,
            "entry_hint": best.entry_hint,
            "invalidation": best.invalidation,
            "why": list(best.why or []),
            "edge_score": round(edge_score, 1),
            "edge_label": edge_label,
            "trade_authorized": trade_authorized,
            "setup_valid": setup_valid,
            "manager_action": "MANAGE" if trade_authorized else _u(best.action, "WATCH"),
            "manager_action_text": "ВЕСТИ ПОЗИЦИЮ" if trade_authorized else _u(best.action, "WATCH"),
            "best_strategy_id": best.strategy_id,
            "best_strategy_tags": list(best.tags or []),
            "strategy_candidates": [c.to_dict() for c in sorted(candidates, key=lambda c: (float(c.score), int(c.priority)), reverse=True)],
            "grid_action": grid_map["status"],
            "grid_execution": {
                **grid_map,
                "reason": best.summary,
            },
            "action_output": {
                "title": "⚡ ЧТО ДЕЛАТЬ",
                "summary_lines": [
                    f"сейчас: {best.summary}",
                    f"стратегия: {best.strategy_id}",
                    f"edge: {edge_label} ({edge_score:.1f}/100)",
                ],
                "launch_lines": [best.entry_hint] if best.entry_hint else [],
                "invalidation_lines": [best.invalidation] if best.invalidation else [],
            },
        }


_ENGINE = ActionEngineV16()


def build_action_engine_v16_context(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return _ENGINE.evaluate(payload or {})


__all__ = [
    "StrategyDecision",
    "StrategyContext",
    "ActionEngineV16",
    "build_action_engine_v16_context",
]
