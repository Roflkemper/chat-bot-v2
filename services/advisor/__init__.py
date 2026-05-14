"""Advisor — рыночный analyzer с trade setup-выводами.

v0.1: build_advisor_text — позиция-aware, deprecated by operator request.
v0.2: build_advisor_v2_text — чистый рынок + setups, decision-ready.
"""
from services.advisor.advisor import build_advisor_text  # legacy v0.1
from services.advisor.advisor_v2 import build_advisor_v2_text  # current

__all__ = ["build_advisor_text", "build_advisor_v2_text"]
