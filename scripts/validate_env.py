"""Validate .env.local against known/expected env-var keys.

Warns about:
  - Unknown keys (likely typos)
  - Required keys that are missing or empty
  - Keys with deprecated values

Run manually or via cron. Output to stdout + (optional) TG via done.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_LOCAL = ROOT / ".env.local"
ENV_EXAMPLE = ROOT / ".env.example"


# Known env-var keys grouped by purpose.
KNOWN_KEYS: set[str] = {
    # Telegram
    "BOT_TOKEN", "ALLOWED_CHAT_IDS", "ENABLE_TELEGRAM",
    # Anthropic / Claude
    "ANTHROPIC_API_KEY", "CLAUDE_BOT_MODEL", "CLAUDE_BOT_MAX_TOKENS",
    "CLAUDE_BOT_ALLOWED_CHAT_ID",
    # BitMEX
    "BITMEX_API_KEY", "BITMEX_API_SECRET",
    # Ginarea
    "GINAREA_API_URL", "GINAREA_EMAIL", "GINAREA_PASSWORD", "GINAREA_TOTP_SECRET",
    # Coinglass
    "COINGLASS_API_KEY",
    # Advisor v2
    "ADVISOR_DEPO_TOTAL",
    # Cascade
    "CASCADE_AUTO_OPEN",
    # Telegram filters
    "TELEGRAM_REGULATION_FILTER_ENABLED",
    "TELEGRAM_FILTER_CRITICAL_LEVELS_USD",
    "TELEGRAM_FILTER_CRITICAL_PROXIMITY_USD",
    "DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE",
    "DEDUP_LAYER_ENABLED_FOR_PNL",
    "DEDUP_LAYER_ENABLED_FOR_LEVEL",
    "DEDUP_LAYER_ENABLED_FOR_REGIME",
    # Setup detector kill switch + GC
    "DISABLED_DETECTORS", "GC_SHADOW_MODE",
    # Legacy
    "ENABLE_ML", "LOOP_SECONDS",
    "AUTO_EDGE_ALERTS_ENABLED", "AUTO_EDGE_ALERTS_INTERVAL_SEC",
    "AUTO_EDGE_ALERTS_COOLDOWN_SEC", "AUTO_EDGE_ALERTS_TIMEFRAMES",
    # Misc env that may appear
    "CHAT_ID",  # used by some scripts as singular
}

# Keys that must be resolvable via config (env OR config.py defaults).
# Note: .env.local only stores LOCAL secrets — BOT_TOKEN etc may come from
# the global config.py or system env, so we check the resolved config, not
# just the file.
REQUIRED_VIA_CONFIG: set[str] = {
    "BOT_TOKEN",
    "CHAT_ID",
}


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            out[key.strip()] = val.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def main() -> int:
    if not ENV_LOCAL.exists():
        print(f"[validate-env] {ENV_LOCAL} missing")
        return 1

    env = _parse_env(ENV_LOCAL)
    print(f"[validate-env] read {len(env)} keys from {ENV_LOCAL}")

    issues: list[str] = []

    # Unknown keys (likely typos)
    for k in env:
        if k not in KNOWN_KEYS:
            similar = [known for known in KNOWN_KEYS
                       if known.startswith(k[:5]) or k.startswith(known[:5])]
            hint = f"  (did you mean {similar[0]}?)" if similar else ""
            issues.append(f"[UNKNOWN] {k}{hint}")

    # Missing required (resolved via config, not just .env.local)
    try:
        sys.path.insert(0, str(ROOT))
        import config as cfg
        for k in REQUIRED_VIA_CONFIG:
            val = getattr(cfg, k, None)
            if not val:
                issues.append(f"[MISSING] {k} required but empty (config)")
    except Exception as exc:
        issues.append(f"[ERROR] config import failed: {exc}")

    # Deprecated value patterns
    if env.get("DISABLED_DETECTORS"):
        toks = [t.strip() for t in env["DISABLED_DETECTORS"].split(",") if t.strip()]
        for t in toks:
            print(f"  detector kill switch active: '{t}'")

    if env.get("GC_SHADOW_MODE") in ("1", "true", "yes"):
        print("  GC shadow mode ENABLED — decisions recorded but not applied")

    if not issues:
        print("[validate-env] OK")
        return 0

    print(f"\n[validate-env] {len(issues)} issue(s):")
    for i in issues:
        print(f"  {i}")
    return 1 if any(i.startswith("[MISSING]") for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
