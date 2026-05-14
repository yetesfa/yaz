# Yaz (ያዝ)

> Amharic for *"grab it"* — a Wayland-native screenshot and annotation tool
> for Linux. The screenshot tool that **actually works** on GNOME Wayland,
> with a clean editor on top.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Linux](https://img.shields.io/badge/Linux-Wayland%20%26%20X11-blue)]()
[![Python](https://img.shields.io/badge/Python-3.10+-blue)]()

## Install (Ubuntu / Debian / Pop!_OS)

```bash
git clone https://github.com/yetesfa/yaz.git
cd yaz
./install.sh
```

That's it. Run with `yaz` or click **Yaz** in your apps grid.

The installer:
- installs `python3-venv`, `python3-gi`, `gnome-screenshot`, `wl-clipboard` via apt (one password prompt)
- creates `.venv/` inside the repo with `PyQt6` (no system Python pollution)
- symlinks `yaz` to `~/.local/bin/yaz`
- registers a `.desktop` entry with quick-action menu items

To uninstall: delete the repo folder, `~/.local/bin/yaz`, and
`~/.local/share/applications/yaz.desktop`.

## Features

- **Capture**: interactive region picker (overlay, drag-to-select), full
  screen, specific monitor (multi-monitor aware), or delayed (3 / 5 / 10
  seconds — set up hover-state screenshots cleanly).
- **Annotation tools**: rectangle, ellipse, arrow, line, pen (freehand),
  highlighter, text, blur / pixelate.
- **Edit**: select / move / delete items, crop, color, stroke width, fill,
  bring-to-front / send-to-back, **undo / redo** for every change.
- **Live property editing**: change colour or width on an already-drawn
  shape by selecting it and tweaking the toolbar.
- **Output**: save as PNG / JPG, copy to clipboard (Qt + `wl-copy`).
- **Global hotkey**: built-in *File → Set Up Global Keyboard Shortcut…*
  wires `Ctrl+Shift+Print` (or your choice) to Yaz via `gsettings`.
- **Multi-monitor aware**: handles mixed DPRs and GNOME fractional scaling
  correctly — derives the screenshot scale empirically from
  `image_size ÷ virtual_geometry_size` (same approach Flameshot uses).
- **Wayland-first**: capture via `gnome-screenshot` (primary) →
  `grim` (wlroots) → `xdg-desktop-portal` (fallback).

## Run it

```bash
yaz                 # open the welcome screen
yaz --capture       # capture a region immediately
yaz --full          # capture full screen immediately
yaz --open IMAGE    # annotate an existing image
yaz --delay 5       # 5-second timer before capturing
```

## Keyboard shortcuts

| Key             | Action                |
|-----------------|-----------------------|
| `V`             | Select / move         |
| `C`             | Crop                  |
| `R`             | Rectangle             |
| `E`             | Ellipse               |
| `A`             | Arrow                 |
| `L`             | Line                  |
| `P`             | Pen (freehand)        |
| `H`             | Highlighter           |
| `T`             | Text                  |
| `B`             | Blur (pixelate)       |
| `Shift+F`       | Toggle fill           |
| `Ctrl+Z` / `Y`  | Undo / redo           |
| `Ctrl+S`        | Save                  |
| `Ctrl+Shift+S`  | Save As…              |
| `Ctrl+Shift+C`  | Copy to clipboard     |
| `Ctrl+N`        | New screenshot        |
| `Delete`        | Remove selected items |
| `Ctrl+Scroll`   | Zoom canvas           |

## Bind to PrintScreen (GNOME)

1. *Settings → Keyboard → View and Customize Shortcuts → Screenshots*
2. Disable or re-bind the default *"Take a screenshot interactively"*
3. *Custom Shortcuts → Add Shortcut*
   - Name: `Yaz`
   - Command: `/home/yetesfa/Documents/Yaz/yaz`
   - Shortcut: `Print` (or `Ctrl+Print`, `Super+S`, etc.)

## Requirements

- Linux with a Wayland (or X11) session that runs `xdg-desktop-portal`
- Python 3.10+, PyQt6, `python3-gi` (Gio), `wl-clipboard` (optional, for
  clipboard interop with non-Qt apps)

Ubuntu 24.04 install (from a fresh clone):

```bash
sudo apt install -y python3-venv python3-gi wl-clipboard
python3 -m venv --system-site-packages .venv
.venv/bin/pip install PyQt6
```

The included `yaz` shell launcher uses `./.venv/bin/python` automatically.

## Why a custom tool?

GNOME's Mutter compositor does not expose `wlr-screencopy`, so the wlroots
ecosystem (`grim`, `slurp`, `flameshot`, etc.) cannot capture on GNOME
Wayland. `org.gnome.Shell.Screenshot` is also locked down for unsandboxed
clients in recent versions. The only sanctioned path is
`org.freedesktop.portal.Screenshot` over D-Bus, which Yaz uses via `Gio`
(`python3-gi`).

## Roadmap

- Step-number stamps (1, 2, 3 …)
- Configurable default save directory
- AppImage / Flatpak packaging for one-line install
- `.deb` for Ubuntu/Debian

## Credits

Developed by **Yetesfa Alemayehu** — Addis Ababa, Ethiopia.
[LinkedIn — linkedin.com/in/yetesfa-alemayehu](https://www.linkedin.com/in/yetesfa-alemayehu)

If you ship a fork, improvement, or downstream package, attribution is
appreciated — a link back to the LinkedIn profile above or the project
repository is plenty.

## License

MIT — fork, ship, contribute. Made in Addis Ababa.
