"""Telegram delivery utilities.

dedup_layer: state-change + cooldown + cluster-collapse wrapper for emitters.
See docs/STATE/TELEGRAM_EMITTERS_INVENTORY.md and Finding 1 (cooldown ≠ dedup).
"""
from .dedup_layer import DedupLayer, DedupConfig, DedupDecision

__all__ = ["DedupLayer", "DedupConfig", "DedupDecision"]
