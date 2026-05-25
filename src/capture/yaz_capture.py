"""Screenshot capture backends.

Backends are tried in this deliberate order:
    1. gnome-screenshot  (most reliable on Ubuntu GNOME — Wayland + X11)
    2. grim              (wlroots-based Wayland: Sway, Hyprland)
    3. xdg-desktop-portal  (last resort; limited on GNOME 46 unsandboxed)

Each backend returns a ``Path`` to a temp PNG. Callers own deletion.
Failures raise ``RuntimeError`` with a user-readable message; user cancel
raises ``CaptureCancelled``.
"""
from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse


class CaptureCancelled(Exception):
    """User dismissed the capture UI — not an error."""


class PortalCancelled(CaptureCancelled):
    """Portal-specific cancel (response code 1)."""


def capture_full_screen() -> Path:
    """Capture full virtual screen via the first working backend."""
    last_error: Exception | None = None

    if shutil.which("gnome-screenshot"):
        try:
            return _capture_with_gnome_screenshot()
        except Exception as ex:  # noqa: BLE001
            last_error = ex

    if shutil.which("grim"):
        try:
            return _capture_with_grim()
        except Exception as ex:  # noqa: BLE001
            last_error = ex

    try:
        return capture_via_portal(interactive=False)
    except Exception as ex:  # noqa: BLE001
        last_error = ex

    raise RuntimeError(
        "No working screenshot backend.\n\n"
        "Install gnome-screenshot for reliable capture:\n"
        "    sudo apt install gnome-screenshot\n\n"
        f"(Last backend error: {last_error})"
    )


def _capture_with_gnome_screenshot() -> Path:
    fd, name = tempfile.mkstemp(prefix="yaz-", suffix=".png")
    os.close(fd)
    out = Path(name)
    res = subprocess.run(
        ["gnome-screenshot", "-f", str(out)],
        capture_output=True, timeout=30, text=True,
    )
    if res.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(
            f"gnome-screenshot failed (rc={res.returncode}): {res.stderr.strip()}"
        )
    return out


def _capture_with_grim() -> Path:
    fd, name = tempfile.mkstemp(prefix="yaz-", suffix=".png")
    os.close(fd)
    out = Path(name)
    res = subprocess.run(
        ["grim", str(out)],
        capture_output=True, timeout=30, text=True,
    )
    if res.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"grim failed (rc={res.returncode}): {res.stderr.strip()}")
    return out


def capture_via_portal(interactive: bool = True) -> Path:
    """Call org.freedesktop.portal.Screenshot via Gio/D-Bus."""
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    token = "yaz_" + secrets.token_hex(8)
    sender = bus.get_unique_name()[1:].replace(".", "_")
    request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    state: dict = {}
    loop = GLib.MainLoop()

    def on_response(_conn, _sender, _obj, _iface, _signal, params):
        code, results = params.unpack()
        state["code"] = code
        state["results"] = results
        loop.quit()

    sub_id = bus.signal_subscribe(
        "org.freedesktop.portal.Desktop",
        "org.freedesktop.portal.Request",
        "Response",
        request_path,
        None,
        Gio.DBusSignalFlags.NONE,
        on_response,
    )

    options = {
        "handle_token": GLib.Variant("s", token),
        "interactive": GLib.Variant("b", interactive),
        "modal": GLib.Variant("b", True),
    }

    bus.call_sync(
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Screenshot",
        "Screenshot",
        GLib.Variant("(sa{sv})", ("", options)),
        GLib.VariantType("(o)"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )

    GLib.timeout_add_seconds(90, lambda: (state.setdefault("code", 2), loop.quit())[1])
    loop.run()
    bus.signal_unsubscribe(sub_id)

    code = state.get("code")
    if code == 1:
        raise PortalCancelled()
    if code != 0:
        raise RuntimeError(
            f"Portal returned code {code}. Install gnome-screenshot for a "
            "more reliable backend on GNOME 46:\n    sudo apt install gnome-screenshot"
        )
    uri = (state.get("results") or {}).get("uri")
    if not uri:
        raise RuntimeError("Portal returned no image URI.")
    return Path(unquote(urlparse(uri).path))


def capture_region_native() -> Path:
    """Interactive region capture using the OS-native area selector.

    Unlike ``capture_full_screen()`` + the in-app picker, this lets the user
    drag a selection on the *live* screen before any capture is taken — the
    standard behaviour most screenshot apps offer. Returns the path to the
    already-cropped PNG. Raises :class:`CaptureCancelled` if the user
    dismisses the selector, or :class:`RuntimeError` if no native backend is
    available."""
    last_error: Exception | None = None

    if shutil.which("gnome-screenshot"):
        try:
            return _capture_region_with_gnome_screenshot()
        except CaptureCancelled:
            raise
        except Exception as ex:  # noqa: BLE001
            last_error = ex

    if shutil.which("slurp") and shutil.which("grim"):
        try:
            return _capture_region_with_grim_slurp()
        except CaptureCancelled:
            raise
        except Exception as ex:  # noqa: BLE001
            last_error = ex

    raise RuntimeError(
        "No interactive region backend available. Install gnome-screenshot:\n"
        "    sudo apt install gnome-screenshot\n"
        f"(Last backend error: {last_error})"
    )


def _capture_region_with_gnome_screenshot() -> Path:
    """``gnome-screenshot -a`` opens a live drag-to-select overlay and saves
    only the selected region."""
    fd, name = tempfile.mkstemp(prefix="yaz-region-", suffix=".png")
    os.close(fd)
    out = Path(name)
    # Long timeout — the user is framing the shot and may take their time.
    res = subprocess.run(
        ["gnome-screenshot", "-a", "-f", str(out)],
        capture_output=True, timeout=600, text=True,
    )
    if res.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(
            f"gnome-screenshot -a failed (rc={res.returncode}): "
            f"{res.stderr.strip()}"
        )
    # gnome-screenshot exits 0 even when the user cancels — detect that by
    # the absent / empty output file.
    if not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise CaptureCancelled()
    return out


def _capture_region_with_grim_slurp() -> Path:
    """``slurp`` prints a region geometry; ``grim`` then captures just that."""
    slurp = subprocess.run(
        ["slurp"], capture_output=True, timeout=600, text=True,
    )
    geom = slurp.stdout.strip()
    if slurp.returncode != 0 or not geom:
        raise CaptureCancelled()
    fd, name = tempfile.mkstemp(prefix="yaz-region-", suffix=".png")
    os.close(fd)
    out = Path(name)
    res = subprocess.run(
        ["grim", "-g", geom, str(out)],
        capture_output=True, timeout=30, text=True,
    )
    if res.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(
            f"grim region failed (rc={res.returncode}): {res.stderr.strip()}"
        )
    return out
