"""MainWindow mixin: GNOME global keyboard shortcut wizard + preferences.

Lets the user pick (or record) a system-wide chord and binds it to one
of the capture commands via the GNOME ``custom-keybindings`` schema. We
shell out to ``gsettings`` rather than touching dconf directly so the
change is visible in Settings → Keyboard.

Mixin only — combine with QMainWindow + the other mw mixins.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QInputDialog, QKeySequenceEdit, QLabel,
    QMessageBox, QVBoxLayout,
)

from yaz_preferences import PreferencesDialog
from yaz_settings import qt_chord_to_gsettings


class ShortcutsMixin:
    # ---- preferences ----
    def show_preferences(self):
        dlg = PreferencesDialog(self)
        dlg.exec()

    # ---- global keyboard shortcut ----
    def setup_global_shortcut(self):
        """Register a GNOME system-wide shortcut so Yaz works from any app."""
        # Sentinel value triggers the custom-chord recorder below.
        CUSTOM = object()
        options = {
            "Shift+Print  (GNOME area-screenshot key)": "<Shift>Print",
            "Ctrl+Shift+Print": "<Primary><Shift>Print",
            "Super+Shift+S": "<Super><Shift>s",
            "Ctrl+Alt+S": "<Primary><Alt>s",
            "Ctrl+Print": "<Primary>Print",
            "Custom…  (record your own keys)": CUSTOM,
        }
        choice, ok = QInputDialog.getItem(
            self, "Yaz — Global shortcut",
            "Pick a system-wide shortcut that triggers Yaz from any app "
            "(including browsers).\n\n"
            "Avoid Ctrl+Shift+R (browser hard-reload).",
            list(options.keys()), 0, False,
        )
        if not ok:
            return
        binding = options[choice]
        if binding is CUSTOM:
            custom = self._prompt_custom_binding()
            if not custom:
                return
            pretty, binding = custom
            choice = pretty
        mode_choice, ok2 = QInputDialog.getItem(
            self, "Yaz — Global shortcut action",
            "What should the shortcut do?",
            ["Capture Region", "Capture Region (3s delay)",
             "Capture Region (5s delay)", "Capture Full Screen"], 0, False,
        )
        if not ok2:
            return
        cmd_args = {
            "Capture Region": "--capture",
            "Capture Region (3s delay)": "--capture --delay 3",
            "Capture Region (5s delay)": "--capture --delay 5",
            "Capture Full Screen": "--full",
        }[mode_choice]
        # The wrapper script sits next to yaz.py (and now the yaz_*.py modules)
        # — same directory regardless of installed vs. source-tree layout.
        launcher = str(Path(__file__).resolve().parent / "yaz")
        command = f"{launcher} {cmd_args}"

        try:
            self._install_gnome_shortcut(binding, command)
        except Exception as ex:  # noqa: BLE001
            QMessageBox.warning(
                self, "Yaz",
                f"Could not register shortcut automatically:\n\n{ex}\n\n"
                "You can set it manually in Settings → Keyboard → "
                "Custom Shortcuts.\n"
                f"Command: {command}"
            )
            return
        mbox = QMessageBox(self)
        mbox.setIcon(QMessageBox.Icon.Information)
        mbox.setWindowTitle("Yaz")
        mbox.setTextFormat(Qt.TextFormat.RichText)
        mbox.setText(
            "<h3 style='margin:0'>Shortcut set!</h3>"
            f"<p>Press <b>{choice}</b> from any app to trigger "
            f"<i>{mode_choice}</i>.</p>"
        )
        mbox.exec()

    def _prompt_custom_binding(self):
        """Open a key-capture dialog and return ``(pretty, gsettings)`` or
        ``None`` if the user cancels or doesn't enter a usable chord.

        The pretty string is shown back to the user (e.g. "Ctrl+Shift+P");
        the gsettings string is what we hand to ``gsettings set …
        binding`` (e.g. "<Primary><Shift>p")."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Yaz — Custom shortcut")
        dlg.resize(420, 0)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(
            "Press the key combination you want to use as the "
            "system-wide shortcut, then click OK."
        ))
        edit = QKeySequenceEdit(dlg)
        layout.addWidget(edit)
        hint = QLabel(
            "Tip: include at least one modifier (Ctrl / Shift / Alt / "
            "Super) so it doesn't fire while you're typing."
        )
        hint.setStyleSheet("color: #888; font-size: 9pt;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        seq = edit.keySequence()
        if seq.isEmpty():
            return None
        pretty = seq.toString(QKeySequence.SequenceFormat.NativeText)
        portable = seq.toString(QKeySequence.SequenceFormat.PortableText)
        gs = qt_chord_to_gsettings(portable)
        if not gs:
            QMessageBox.warning(
                self, "Yaz",
                "That key combination couldn't be converted to a "
                "system shortcut. Try a different one."
            )
            return None
        return pretty, gs

    def _install_gnome_shortcut(self, binding: str, command: str):
        base = "org.gnome.settings-daemon.plugins.media-keys"
        kb_id = "yaz"
        kb_path = (
            "/org/gnome/settings-daemon/plugins/media-keys/"
            f"custom-keybindings/{kb_id}/"
        )

        res = subprocess.run(
            ["gsettings", "get", base, "custom-keybindings"],
            capture_output=True, text=True, check=True,
        )
        current = res.stdout.strip()
        if current in ("@as []", "[]"):
            paths: list[str] = []
        else:
            # Existing list is "['/.../a/', '/.../b/']"
            paths = [
                p.strip().strip("'\"")
                for p in current.strip("[]").split(",")
                if p.strip()
            ]
        if kb_path not in paths:
            paths.append(kb_path)
        new = "[" + ", ".join(f"'{p}'" for p in paths) + "]"
        subprocess.run(
            ["gsettings", "set", base, "custom-keybindings", new],
            check=True,
        )

        schema = f"{base}.custom-keybinding:{kb_path}"
        for key, value in (
            ("name", "Yaz"),
            ("command", command),
            ("binding", binding),
        ):
            subprocess.run(
                ["gsettings", "set", schema, key, value],
                check=True,
            )
