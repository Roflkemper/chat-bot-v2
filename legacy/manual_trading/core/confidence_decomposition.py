from __future__ import annotations


def build_confidence_decomposition(signal: str, regime: str, setup_grade: str, execution_grade: str, winrate: float) -> dict:
    env = 60.0 if regime in {"trend", "range"} else 48.0
    structure = 62.0 if signal != "NO TRADE" else 40.0
    execution = {"A": 82.0, "B": 64.0, "C": 42.0}.get(execution_grade, 50.0)
    management = min(85.0, 45.0 + winrate * 0.5)
    total = round(env * 0.25 + structure * 0.30 + execution * 0.25 + management * 0.20, 2)
    return {
        "confidence": total,
        "confidence_decomposition": {
            "env": round(env, 2),
            "structure": round(structure, 2),
            "execution": round(execution, 2),
            "management": round(management, 2),
            "setup_grade": setup_grade,
            "execution_grade": execution_grade,
        },
    }
