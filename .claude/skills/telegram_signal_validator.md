# telegram_signal_validator
Trigger: any change to Telegram output, advise generation, signal rendering.

Validate before Telegram send:
- No duplicate action blocks within message.
- Russian formatting (no English mixed in unless trader uses tickers).
- Action-first: command before analysis paragraph.
- PREPARE state only with confirmed trigger (not speculative).
- Length: live signal ≤500 chars, analysis ≤2000 chars.

On violation:
TG SIGNAL INVALID: [issue]. NOT SENT.

Renderer ≠ decision maker. Decision is upstream.
