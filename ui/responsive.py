"""Small PySide6 helpers for responsive layouts.

Qt layouts already reflow automatically; this module only exposes a compact
breakpoint helper for future optional UI adjustments.
"""
from __future__ import annotations


def layout_mode(width: int) -> str:
    if width >= 1420:
        return "wide"
    if width >= 1100:
        return "medium"
    return "compact"
