"""Persisted preferences and screen-description helpers.

Everything in here is pure Python — no Qt at module top. ``QScreen``
arguments to the screen helpers are duck-typed so the module stays
import-safe before Qt loads.
"""
from __future__ import annotations

import os
from pathlib import Path


DEFAULTS = {
    "save_dir": "",                                   # filled at runtime
    "filename_template": "Screenshot %Y-%m-%d %H-%M-%S",
    "format": "PNG",
    "jpg_quality": 92,
    "capture_delay": 0,
    "copy_after_save": False,
    "pick_region_after_capture": True,
    "color": "#e53935",
    "stroke": 4,
    "show_toolbar": True,
    "show_statusbar": True,
}


def _default_save_dir() -> str:
    for env in ("XDG_PICTURES_DIR",):
        v = os.environ.get(env)
        if v:
            return v
    cand = Path.home() / "Pictures"
    return str(cand if cand.exists() else Path.home())


def friendly_screen_name(scr) -> str:
    """Best-effort human name for a QScreen.

    Handles common cases:
      • Apple panels: "APP" + "Color LCD"      → "Built-in Display"
      • Laptop panels by output name (eDP-*, LVDS-*, DSI-*)
                                               → "Built-in Display"
      • Generic / numeric EDID model strings   → fall back to connector name
      • Useful model fields (HP / Samsung etc) → use the model verbatim
    """
    mfr = (scr.manufacturer() or "").strip()
    model = (scr.model() or "").strip()
    out = (scr.name() or "Display").strip()

    # Output-name first: a laptop's internal panel always uses eDP-*, LVDS-*
    # or DSI-* regardless of what its EDID says. This catches BOE / LG /
    # Samsung laptop panels with junk EDID model strings.
    low_out = out.lower()
    if low_out.startswith(("edp", "lvds", "dsi")):
        return "Built-in Display"

    # Apple-style builtin reporting.
    if mfr.upper() == "APP" and "LCD" in model.upper():
        return "Built-in Display"

    # Useful model? (Reject generic placeholders + hex-id-looking strings.)
    if model:
        low = model.lower()
        looks_generic = low in ("color lcd", "lcd", "display", "monitor", "")
        looks_hex = (model.startswith(("0x", "0X")) or
                     all(c in "0123456789abcdefABCDEF" for c in model))
        if not (looks_generic or looks_hex):
            return model

    # Final fallback: connector type makes it informative even without EDID.
    for prefix, label in (
        ("dp-", "DisplayPort"),
        ("hdmi-", "HDMI"),
        ("vga-", "VGA"),
        ("dvi-", "DVI"),
        ("usb-c-", "USB-C Display"),
    ):
        if low_out.startswith(prefix):
            # Append the connector index if present, e.g. "DisplayPort 3".
            tail = out.split("-", 1)[1] if "-" in out else ""
            return f"{label} {tail}".strip()
    return out


def describe_screen(scr) -> tuple[str, str]:
    """Return (label, tooltip) for a screen, including resolution and scale."""
    name = friendly_screen_name(scr)
    g = scr.geometry()
    dpr = scr.devicePixelRatio()
    size_main = f"{g.width()} × {g.height()}"
    if abs(dpr - 1.0) > 0.05:
        size_main += f"  @ {dpr:g}×"
    tooltip_lines = [
        f"Output: {scr.name() or '—'}",
        f"Manufacturer: {scr.manufacturer() or '—'}",
        f"Model: {scr.model() or '—'}",
        f"Logical size: {g.width()} × {g.height()} px",
        f"Position: ({g.x()}, {g.y()})",
        f"Device pixel ratio: {dpr:g}",
        f"Refresh rate: {scr.refreshRate():.0f} Hz",
    ]
    return f"{name}  ·  {size_main}", "\n".join(tooltip_lines)


def qt_chord_to_gsettings(text: str) -> str | None:
    """Convert a Qt PortableText keychord (e.g. "Ctrl+Shift+S") to GNOME's
    gsettings binding format (e.g. "<Primary><Shift>s"). Returns None if the
    chord has no key part."""
    if not text:
        return None
    parts = [p.strip() for p in text.split("+") if p.strip()]
    if not parts:
        return None
    *mod_parts, key = parts
    mod_map = {
        "ctrl": "<Primary>", "control": "<Primary>",
        "shift": "<Shift>",
        "alt": "<Alt>",
        "meta": "<Super>", "super": "<Super>",
    }
    mods = []
    for m in mod_parts:
        gs = mod_map.get(m.lower())
        if gs and gs not in mods:
            mods.append(gs)
    # Single letters use lowercase in gsettings convention; named keys
    # (Print, F1, Return, Space, Tab…) stay verbatim.
    if len(key) == 1 and key.isalpha():
        key = key.lower()
    return "".join(mods) + key
