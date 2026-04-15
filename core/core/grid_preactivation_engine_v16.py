
from __future__ import annotations

def _f(x, d=0.0):
    try:
        return float(x)
    except:
        return d

def _u(x, d=""):
    return str(x).upper() if x is not None else d

def build_grid_preactivation(payload: dict) -> dict:
    blocks = payload.get("liquidity_blocks", {})
    liq_reaction = payload.get("liquidation_reaction", {})
    liq_ctx = payload.get("liquidation_context", {})
    impulse = payload.get("impulse_character", {})
    volume = payload.get("volume_confirmation", {})
    grid = payload.get("grid_strategy", {})

    price = _f(payload.get("price"))

    upper = blocks.get("upper_block", {})
    lower = blocks.get("lower_block", {})

    def dist_to_block(block):
        low = _f(block.get("low"))
        high = _f(block.get("high"))
        if low == 0 and high == 0:
            return 999
        mid = (low + high) / 2
        return abs(price - mid) / max(mid, 1) * 100

    d_upper = dist_to_block(upper)
    d_lower = dist_to_block(lower)

    # direction
    direction = "NEUTRAL"
    if _u(liq_reaction.get("acceptance")) == "REJECTED_ABOVE":
        direction = "SHORT"
    elif _u(liq_reaction.get("acceptance")) == "REJECTED_BELOW":
        direction = "LONG"
    elif d_upper < 0.4:
        direction = "SHORT"
    elif d_lower < 0.4:
        direction = "LONG"
    elif grid.get("contrarian_side"):
        direction = _u(grid.get("contrarian_side"))

    score = 0

    # location
    if d_upper < 0.3 or d_lower < 0.3:
        score += 20
    elif d_upper < 0.6 or d_lower < 0.6:
        score += 10

    # block strength
    if _f(blocks.get("upper_block_strength")) > 0.7 or _f(blocks.get("lower_block_strength")) > 0.7:
        score += 10

    # reaction
    acc = _u(liq_reaction.get("acceptance"))
    if "REJECTED" in acc:
        score += 20
    elif acc == "NONE":
        score += 5

    # impulse
    imp = _u(impulse.get("state"))
    if "EXHAUSTION" in imp:
        score += 15
    elif "TRAP" in imp:
        score += 12
    elif "CHOP" in imp:
        score += 5
    elif "CONTINUATION" in imp:
        score -= 10

    # volume
    if "weak" in _u(volume.get("summary")):
        score += 5

    # liquidity
    if _u(liq_ctx.get("magnet_side")) != direction:
        score += 10

    # stage
    if score < 35:
        stage = "WATCH"
    elif score < 50:
        stage = "PREPARE_REDUCED"
    elif score < 65:
        stage = "PREPARE"
    elif score < 80:
        stage = "ARM"
    elif score < 90:
        stage = "ENABLE_SMALL"
    else:
        stage = "ENABLE"

    return {
        "grid_direction": direction,
        "preactivation_score": round(score, 1),
        "stage": stage,
        "grid_action": stage,
        "size_mode": "SMALL" if stage == "PREPARE_REDUCED" else "NORMAL" if stage=="PREPARE" else "FULL",
        "reason": f"score={score} near block / impulse={imp}",
        "allow_adds": stage in ["ARM","ENABLE_SMALL","ENABLE"]
    }
