"""Preferences dialog backed by QSettings.

Every persisted preference is listed in :data:`yaz_settings.DEFAULTS` and
exposed here. The dialog writes through to QSettings and asks MainWindow
to refresh its in-memory mirror via ``apply_settings()``.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QVBoxLayout,
)

from yaz_settings import DEFAULTS, _default_save_dir


class PreferencesDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window_ref = window
        self.settings = window.qsettings
        self.setWindowTitle("Yaz — Preferences")
        self.resize(520, 0)

        form = QFormLayout()

        # Save directory
        dir_row = QHBoxLayout()
        self.save_dir_edit = QLineEdit(
            self.settings.value("save_dir", _default_save_dir()))
        dir_btn = QPushButton("Browse…")
        dir_btn.clicked.connect(self._pick_dir)
        dir_row.addWidget(self.save_dir_edit)
        dir_row.addWidget(dir_btn)
        form.addRow("Default save folder:", dir_row)

        self.tmpl_edit = QLineEdit(self.settings.value(
            "filename_template", DEFAULTS["filename_template"]))
        form.addRow("Filename template:", self.tmpl_edit)
        hint = QLabel("Uses strftime codes — %Y year, %m month, "
                      "%d day, %H %M %S time.")
        hint.setStyleSheet("color: #888; font-size: 9pt;")
        form.addRow("", hint)

        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "JPG"])
        self.format_combo.setCurrentText(
            self.settings.value("format", DEFAULTS["format"]))
        form.addRow("Default format:", self.format_combo)

        self.jpg_spin = QSpinBox()
        self.jpg_spin.setRange(10, 100)
        self.jpg_spin.setValue(
            int(self.settings.value("jpg_quality", DEFAULTS["jpg_quality"])))
        self.jpg_spin.setSuffix(" %")
        form.addRow("JPG quality:", self.jpg_spin)

        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 30)
        self.delay_spin.setValue(
            int(self.settings.value("capture_delay",
                                    DEFAULTS["capture_delay"])))
        self.delay_spin.setSuffix(" s")
        form.addRow("Capture delay:", self.delay_spin)

        self.copy_check = QCheckBox("Copy image to clipboard when saved")
        self.copy_check.setChecked(self._b("copy_after_save"))
        form.addRow("", self.copy_check)

        self.region_check = QCheckBox(
            "Show region picker after capture (uncheck = edit full screen)")
        self.region_check.setChecked(self._b("pick_region_after_capture"))
        form.addRow("", self.region_check)

        self.color_btn = QPushButton()
        self._color = QColor(
            self.settings.value("color", DEFAULTS["color"]))
        self._refresh_color_btn()
        self.color_btn.clicked.connect(self._pick_color)
        form.addRow("Default annotation color:", self.color_btn)

        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(1, 64)
        self.stroke_spin.setValue(
            int(self.settings.value("stroke", DEFAULTS["stroke"])))
        form.addRow("Default stroke width:", self.stroke_spin)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        btns.accepted.connect(self._save_and_close)
        btns.rejected.connect(self.reject)
        btns.button(
            QDialogButtonBox.StandardButton.RestoreDefaults
        ).clicked.connect(self._restore_defaults)

        outer = QVBoxLayout(self)
        outer.addLayout(form)
        outer.addWidget(btns)

    def _b(self, key):
        v = self.settings.value(key, DEFAULTS[key])
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("true", "1", "yes")

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Default save folder", self.save_dir_edit.text())
        if d:
            self.save_dir_edit.setText(d)

    def _refresh_color_btn(self):
        self.color_btn.setText(self._color.name())
        self.color_btn.setStyleSheet(
            f"QPushButton {{ background:{self._color.name()}; "
            f"color:white; padding:6px 10px; }}"
        )

    def _pick_color(self):
        c = QColorDialog.getColor(self._color, self,
                                  "Default annotation color")
        if c.isValid():
            self._color = c
            self._refresh_color_btn()

    def _restore_defaults(self):
        self.save_dir_edit.setText(_default_save_dir())
        self.tmpl_edit.setText(DEFAULTS["filename_template"])
        self.format_combo.setCurrentText(DEFAULTS["format"])
        self.jpg_spin.setValue(DEFAULTS["jpg_quality"])
        self.delay_spin.setValue(DEFAULTS["capture_delay"])
        self.copy_check.setChecked(DEFAULTS["copy_after_save"])
        self.region_check.setChecked(DEFAULTS["pick_region_after_capture"])
        self._color = QColor(DEFAULTS["color"])
        self._refresh_color_btn()
        self.stroke_spin.setValue(DEFAULTS["stroke"])

    def _save_and_close(self):
        s = self.settings
        s.setValue("save_dir", self.save_dir_edit.text())
        s.setValue("filename_template", self.tmpl_edit.text())
        s.setValue("format", self.format_combo.currentText())
        s.setValue("jpg_quality", self.jpg_spin.value())
        s.setValue("capture_delay", self.delay_spin.value())
        s.setValue("copy_after_save", self.copy_check.isChecked())
        s.setValue("pick_region_after_capture", self.region_check.isChecked())
        s.setValue("color", self._color.name())
        s.setValue("stroke", self.stroke_spin.value())
        s.sync()
        self.window_ref.apply_settings()
        self.accept()
