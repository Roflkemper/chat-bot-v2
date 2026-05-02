"""Claude-powered Telegram bot for operator communication.

Usage:
    python -m services.claude_bot.bot

Env vars required:
    CLAUDE_BOT_TOKEN   — Telegram bot token (from @BotFather)
    ANTHROPIC_API_KEY  — Anthropic API key (from console.anthropic.com)

Optional:
    CLAUDE_BOT_ALLOWED_CHAT_ID  — restrict to one chat ID (recommended)
    CLAUDE_BOT_MODEL            — Claude model ID (default: claude-sonnet-4-6)
    CLAUDE_BOT_MAX_TOKENS       — max tokens per response (default: 2048)
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Allow running from project root
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import telebot
from telebot.types import Message

from services.claude_bot.context_loader import load_system_prompt, reload_prompt
from services.claude_bot.queue_writer import append_if_tz

log = logging.getLogger("claude_bot")


def _get_env(key: str, required: bool = True) -> str:
    val = os.getenv(key, "").strip()
    if required and not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


# ── config ────────────────────────────────────────────────────────────────────

CLAUDE_BOT_TOKEN = _get_env("CLAUDE_BOT_TOKEN")
ANTHROPIC_API_KEY = _get_env("ANTHROPIC_API_KEY")
MODEL = os.getenv("CLAUDE_BOT_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("CLAUDE_BOT_MAX_TOKENS", "2048"))
ALLOWED_CHAT_ID = os.getenv("CLAUDE_BOT_ALLOWED_CHAT_ID", "").strip()

# Per-chat conversation history: {chat_id: [{"role": ..., "content": ...}]}
_histories: dict[int, list[dict]] = {}
_MAX_HISTORY = 20  # messages to keep per chat


# ── Anthropic client ──────────────────────────────────────────────────────────

def _call_claude(chat_id: int, user_text: str, system_prompt: str) -> str:
    try:
        import anthropic
    except ImportError:
        return "ERROR: `anthropic` package not installed. Run: pip install anthropic"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    history = _histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})

    # Keep history bounded
    if len(history) > _MAX_HISTORY:
        history[:] = history[-_MAX_HISTORY:]

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=history,
        )
        reply = response.content[0].text
        history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        log.error("Anthropic API error: %s", e)
        return f"API error: {e}"


# ── Telegram bot ──────────────────────────────────────────────────────────────

bot = telebot.TeleBot(CLAUDE_BOT_TOKEN, parse_mode=None)
_system_prompt: list[str] = []  # mutable container so we can reload


def _get_system_prompt() -> str:
    if not _system_prompt:
        _system_prompt.append(load_system_prompt())
    return _system_prompt[0]


def _is_allowed(message: Message) -> bool:
    if not ALLOWED_CHAT_ID:
        return True
    return str(message.chat.id) == ALLOWED_CHAT_ID


def _send(message: Message, text: str) -> None:
    # Telegram max message = 4096 chars; split if needed
    for chunk in _split(text, 4000):
        bot.send_message(message.chat.id, chunk)


def _split(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks


@bot.message_handler(commands=["start", "help"])
def handle_help(message: Message) -> None:
    if not _is_allowed(message):
        return
    bot.reply_to(message, (
        "Claude Grid Assistant\n\n"
        "Просто пиши — отвечу как Claude с полным контекстом проекта.\n\n"
        "Команды:\n"
        "/reload  — перезагрузить контекст из HANDOFF\n"
        "/clear   — очистить историю разговора\n"
        "/queue   — показать последние TZ в очереди\n"
        "/model   — показать текущую модель\n"
        "/help    — эта справка"
    ))


@bot.message_handler(commands=["reload"])
def handle_reload(message: Message) -> None:
    if not _is_allowed(message):
        return
    _system_prompt.clear()
    _system_prompt.append(reload_prompt())
    bot.reply_to(message, "Context reloaded from latest HANDOFF.")


@bot.message_handler(commands=["clear"])
def handle_clear(message: Message) -> None:
    if not _is_allowed(message):
        return
    _histories.pop(message.chat.id, None)
    bot.reply_to(message, "Conversation history cleared.")


@bot.message_handler(commands=["model"])
def handle_model(message: Message) -> None:
    if not _is_allowed(message):
        return
    bot.reply_to(message, f"Model: {MODEL}\nMax tokens: {MAX_TOKENS}")


@bot.message_handler(commands=["queue"])
def handle_queue(message: Message) -> None:
    if not _is_allowed(message):
        return
    queue_path = _ROOT / "docs" / "CONTEXT" / "QUEUE.md"
    if not queue_path.exists():
        bot.reply_to(message, "QUEUE.md does not exist yet.")
        return
    text = queue_path.read_text(encoding="utf-8")
    # Show last 3000 chars
    if len(text) > 3000:
        text = "...(truncated)\n\n" + text[-3000:]
    bot.reply_to(message, text or "(empty)")


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message: Message) -> None:
    if not _is_allowed(message):
        log.warning("Rejected message from chat %s", message.chat.id)
        return

    user_text = message.text or ""
    if not user_text.strip():
        return

    # Log TZs to queue
    tz_logged = append_if_tz(user_text, message.chat.id)

    # Show typing indicator
    bot.send_chat_action(message.chat.id, "typing")

    reply = _call_claude(message.chat.id, user_text, _get_system_prompt())

    if tz_logged:
        reply = "[TZ logged to QUEUE.md]\n\n" + reply

    _send(message, reply)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log.info("Starting Claude bot (model=%s)", MODEL)
    if ALLOWED_CHAT_ID:
        log.info("Restricted to chat_id=%s", ALLOWED_CHAT_ID)

    # Pre-load context
    _get_system_prompt()
    log.info("Context loaded (%d chars)", len(_system_prompt[0]))

    bot.infinity_polling(timeout=30, long_polling_timeout=20)


if __name__ == "__main__":
    main()
