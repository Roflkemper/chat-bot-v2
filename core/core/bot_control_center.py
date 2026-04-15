from __future__ import annotations

from typing import Any, Dict, List


LONG_KEYS = {"ct_long", "range_long"}
SHORT_KEYS = {"ct_short", "range_short"}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _norm_status(card: Dict[str, Any]) -> str:
    status = str(card.get("activation_state") or card.get("status") or "OFF").upper()
    plan = str(card.get("plan_state") or "WAIT").upper()
    action = str(card.get("management_action") or "WAIT").upper()
    score = _f(card.get("ranking_score") or card.get("score"))
    if action in {"CANCEL SCENARIO", "EXIT", "CAUTIOUS EXIT"}:
        return "CANCEL" if action == "CANCEL SCENARIO" else "REDUCE"
    if score >= 0.82 and status in {"READY", "ARMED"}:
        return "ACTIVE"
    if status in {"SOFT_READY", "WATCH"} and bool(card.get("small_entry_only")):
        return "START SMALL"
    if plan in {"ARM", "ATTACK", "READY"} or status in {"READY", "ARMED"}:
        return "PREPARE"
    if status in {"SOFT_READY", "WATCH"}:
        return "WATCH"
    if score >= 0.45:
        return "WATCH"
    return "OFF"


def _pick(cards: List[Dict[str, Any]], side: str) -> List[Dict[str, Any]]:
    keys = LONG_KEYS if side == "LONG" else SHORT_KEYS
    picked = [c for c in cards if str(c.get("bot_key") or "") in keys]
    picked.sort(key=lambda c: (_f(c.get("ranking_score") or c.get("score")), _f(c.get("score"))), reverse=True)
    return picked


def _layer_reason(card: Dict[str, Any], status: str, side: str, layer_kind: str, score: float) -> str:
    note = str(card.get("note") or card.get("execution_hint") or "").strip()
    if note:
        return note
    if status == "ACTIVE":
        return f"есть рабочий edge по стороне {side.lower()}"
    if status == "PREPARE":
        return "сетап почти готов, лучше ждать зону/триггер"
    if status == "START SMALL":
        return "разрешён только маленький старт без агрессии"
    if status == "REDUCE":
        return "слой лучше сокращать, а не наращивать"
    if status == "CANCEL":
        return "сценарий лучше отменить до новой структуры"
    if status == "WATCH":
        if score >= 0.45:
            return "есть наблюдаемый перевес, но подтверждение слабое"
        return f"пока без чистого edge для {layer_kind}"
    return "чистого edge пока нет"


def _layer_permission(status: str, score: float, layer_kind: str) -> str:
    if status == "ACTIVE":
        return "ALLOW"
    if status in {"PREPARE", "WATCH"}:
        return "WAIT"
    if status == "START SMALL":
        return "SMALL ONLY"
    if status == "REDUCE":
        return "NO ADDS"
    if status == "CANCEL":
        return "BLOCK"
    return "WAIT"


def _layer_from_card(card: Dict[str, Any], asset: str, side: str, layer_num: int, layer_kind: str) -> Dict[str, Any]:
    label = f"{asset} {side} {layer_num}"
    score = _f(card.get("ranking_score") or card.get("score"))
    status = _norm_status(card)
    permission = _layer_permission(status, score, layer_kind)
    return {
        "bot_label": label,
        "layer_kind": layer_kind,
        "source_bot": str(card.get("bot_label") or card.get("bot_key") or "bot"),
        "status": status,
        "score": round(score, 3),
        "action": str(card.get("management_action") or "WAIT"),
        "entry": str(card.get("entry_instruction") or ""),
        "exit": str(card.get("exit_instruction") or ""),
        "zone": str(card.get("zone") or ""),
        "invalidation": str(card.get("invalidation") or ""),
        "note": str(card.get("note") or card.get("execution_hint") or "").strip(),
        "permission": permission,
        "reason": _layer_reason(card, status, side, layer_kind, score),
        "no_adds": permission in {"NO ADDS", "BLOCK"},
    }


def _build_asset_side(cards: List[Dict[str, Any]], asset: str, side: str) -> List[Dict[str, Any]]:
    picked = _pick(cards, side)
    primary = picked[0] if picked else {}
    secondary = picked[1] if len(picked) > 1 else primary
    layers = [
        _layer_from_card(primary, asset, side, 1, "volume-layer"),
        _layer_from_card(primary, asset, side, 2, "profit-layer"),
        _layer_from_card(secondary, asset, side, 3, "panic-layer"),
    ]
    if not picked:
        for layer in layers:
            layer.update({
                "status": "OFF",
                "action": "WAIT",
                "note": "нет чистого edge",
                "entry": "",
                "exit": "",
                "zone": "",
                "permission": "WAIT",
                "reason": "нет чистого edge",
                "no_adds": False,
            })
    else:
        if layers[0]["status"] == "ACTIVE":
            layers[1]["status"] = "PREPARE"
            layers[1]["permission"] = "WAIT"
            layers[1]["reason"] = "profit-layer лучше включать только после живого подтверждения"
        if layers[2]["status"] == "ACTIVE":
            layers[2]["status"] = "REDUCE"
            layers[2]["permission"] = "NO ADDS"
            layers[2]["reason"] = "panic-layer уже опасен для новых добавлений"
            layers[2]["no_adds"] = True
    return layers


def _side_snapshot(layers: List[Dict[str, Any]], side: str) -> Dict[str, Any]:
    best = layers[0] if layers else {}
    active = [x for x in layers if x.get("status") in {"ACTIVE", "PREPARE", "START SMALL"}]
    blocked = [x for x in layers if x.get("permission") in {"NO ADDS", "BLOCK"}]
    pressure = max((_f(x.get("score")) for x in layers), default=0.0)
    return {
        "side": side,
        "leader": best.get("bot_label") or f"{side} 1",
        "leader_status": best.get("status") or "OFF",
        "pressure": round(pressure, 3),
        "active_count": len(active),
        "blocked_count": len(blocked),
        "allow_new": bool(active) and best.get("permission") in {"ALLOW", "SMALL ONLY"},
        "mode": "ATTACK" if best.get("status") == "ACTIVE" else ("PREPARE" if active else "WATCH"),
    }


def _asset_precision(asset: str, long_layers: List[Dict[str, Any]], short_layers: List[Dict[str, Any]]) -> Dict[str, Any]:
    long_view = _side_snapshot(long_layers, "LONG")
    short_view = _side_snapshot(short_layers, "SHORT")
    if long_view["pressure"] >= short_view["pressure"] + 0.08:
        dominant_side = "LONG"
    elif short_view["pressure"] >= long_view["pressure"] + 0.08:
        dominant_side = "SHORT"
    else:
        dominant_side = "MIXED"

    if dominant_side == "LONG":
        lead = long_layers[0] if long_layers else {}
        side_risk = "SHORT TRAP" if short_view["pressure"] >= 0.55 else "LONG OVERCHASE"
        summary = f"{asset}: приоритет LONG, главный слой {lead.get('bot_label', asset + ' LONG 1')}"
    elif dominant_side == "SHORT":
        lead = short_layers[0] if short_layers else {}
        side_risk = "LONG TRAP" if long_view["pressure"] >= 0.55 else "SHORT OVERCHASE"
        summary = f"{asset}: приоритет SHORT, главный слой {lead.get('bot_label', asset + ' SHORT 1')}"
    else:
        lead = {}
        side_risk = "MIXED CHOP"
        summary = f"{asset}: mixed control — брать только лучший слой и без перегруза"

    if lead:
        top_permission = lead.get("permission") or "WAIT"
        top_reason = lead.get("reason") or ""
    else:
        top_permission = "WAIT"
        top_reason = "нет чистого ведущего слоя"

    return {
        "dominant_side": dominant_side,
        "side_risk": side_risk,
        "top_permission": top_permission,
        "top_reason": top_reason,
        "long_view": long_view,
        "short_view": short_view,
        "summary": summary,
    }


def build_bot_control_center(bot_cards: List[Dict[str, Any]], market_mode: str = "MIXED") -> Dict[str, Any]:
    assets: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    precision: Dict[str, Dict[str, Any]] = {}
    summary: List[str] = []
    for asset in ("BTC",):
        long_layers = _build_asset_side(bot_cards, asset, "LONG")
        short_layers = _build_asset_side(bot_cards, asset, "SHORT")
        assets[asset] = {"long": long_layers, "short": short_layers}
        precision[asset] = _asset_precision(asset, long_layers, short_layers)
        summary.append(precision[asset]["summary"])
    return {
        "market_mode": market_mode,
        "assets": assets,
        "precision": precision,
        "summary": summary,
    }
