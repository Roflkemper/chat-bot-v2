"""Loads project context for Claude system prompt."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CONTEXT_DIR = _ROOT / "docs" / "CONTEXT"
_STATE_CURRENT = _CONTEXT_DIR / "STATE_CURRENT.md"
_PROJECT_CONTEXT = _CONTEXT_DIR / "PROJECT_CONTEXT.md"


def _latest_handoff() -> Path | None:
    files = sorted(_CONTEXT_DIR.glob("HANDOFF_*.md"), reverse=True)
    return files[0] if files else None


def load_system_prompt() -> str:
    """Build system prompt from latest HANDOFF or fallback to STATE_CURRENT."""
    handoff = _latest_handoff()
    if handoff and handoff.exists():
        text = handoff.read_text(encoding="utf-8")
        # Trim to ~40k chars to stay within API limits
        if len(text) > 40_000:
            text = text[:40_000] + "\n\n[...truncated for context window...]"
        return (
            "You are Claude, an AI assistant embedded in the bot7 grid trading project.\n"
            "The following is the project HANDOFF document — read it carefully before answering.\n\n"
            f"{text}\n\n"
            "---\n"
            "Rules:\n"
            "- Respond in the same language the operator uses (RU or EN).\n"
            "- When the operator provides a TZ (task specification), acknowledge it and confirm you logged it.\n"
            "- Be concise. This is an operational channel, not a tutorial.\n"
            "- If you lack context for a decision, say so and ask for the specific detail.\n"
        )

    # Fallback: minimal context
    state = _STATE_CURRENT.read_text(encoding="utf-8") if _STATE_CURRENT.exists() else ""
    return (
        "You are Claude, an AI assistant for the bot7 grid trading project.\n"
        f"Current state:\n{state}\n"
        "Respond in the same language the operator uses."
    )


def reload_prompt() -> str:
    """Re-read from disk (called after /reload)."""
    return load_system_prompt()
