"""Welcome / launcher screen shown when no image is loaded.

Layout (top to bottom):
  • Corner: discreet Preferences shortcut
  • Hero: brand + tagline
  • Primary row: three action cards (region / full / open)
  • Section: delayed capture (header + small chips)
  • Section: per-monitor capture (only if >1 monitor)
  • Footer: PrintScreen tip + "set up shortcut" link
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from yaz_settings import describe_screen


class Welcome(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName("welcome")
        self.setStyleSheet("""
            QWidget#welcome    { background: #15171c; }
            QLabel#brand       { color: #ffffff; font-size: 40pt; font-weight: 700; letter-spacing: 1px; }
            QLabel#amharic     { color: #ffd166; font-size: 36pt; font-weight: 700; }
            QLabel#tag         { color: #ffd166; font-size: 11pt; font-style: italic; }
            QLabel#sub         { color: #9aa0ad; font-size: 11pt; }
            QLabel#section     { color: #c8ccd6; font-size: 11pt; font-weight: 600; letter-spacing: 0.4px; }
            QLabel#footer      { color: #6a6f7d; font-size: 10pt; }

            /* "Card" buttons for primary actions */
            QPushButton.card {
                background: #232631;
                color: #ffffff;
                border: 1px solid #2e3240;
                border-radius: 10px;
                padding: 22px 14px;
                font-size: 12pt;
                text-align: center;
            }
            QPushButton.card:hover   { background: #2b2f3c; border-color: #3a86ff; }
            QPushButton.card-primary { background: #3a86ff; border: none; color: white; font-weight: bold; }
            QPushButton.card-primary:hover { background: #2c6fd9; }

            /* "Chip" buttons for secondary options */
            QPushButton.chip {
                background: #1e2129;
                color: #d4d8e1;
                border: 1px solid #2a2d38;
                border-radius: 16px;
                padding: 6px 14px;
                font-size: 10pt;
            }
            QPushButton.chip:hover { background: #2a2d38; color: #ffffff; }

            /* Plain link-style button (corner, footer) */
            QPushButton.link {
                background: transparent;
                color: #9aa0ad;
                border: none;
                padding: 4px 8px;
                font-size: 10pt;
            }
            QPushButton.link:hover { color: #ffffff; text-decoration: underline; }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(60, 24, 60, 32)
        outer.setSpacing(0)

        # ---------- top-right preferences shortcut ----------
        top_bar = QHBoxLayout()
        top_bar.addStretch(1)
        prefs_btn = QPushButton("⚙  Preferences")
        prefs_btn.setProperty("class", "link")
        prefs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        prefs_btn.clicked.connect(window.show_preferences)
        top_bar.addWidget(prefs_btn)
        shortcut_btn = QPushButton("⌨  Global shortcut…")
        shortcut_btn.setProperty("class", "link")
        shortcut_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        shortcut_btn.clicked.connect(window.setup_global_shortcut)
        top_bar.addWidget(shortcut_btn)
        outer.addLayout(top_bar)

        outer.addStretch(1)

        # ---------- hero ----------
        hero = QHBoxLayout()
        hero.setSpacing(14)
        hero.addStretch(1)
        brand = QLabel("Yaz")
        brand.setObjectName("brand")
        hero.addWidget(brand)
        dot = QLabel("·"); dot.setObjectName("brand")
        dot.setStyleSheet("color:#3a86ff;")
        hero.addWidget(dot)
        amh = QLabel("ያዝ"); amh.setObjectName("amharic")
        hero.addWidget(amh)
        hero.addStretch(1)
        outer.addLayout(hero)

        tag = QLabel('Amharic for "grab it"')
        tag.setObjectName("tag")
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(tag)
        outer.addSpacing(28)

        # ---------- primary cards ----------
        cards = QHBoxLayout()
        cards.setSpacing(14)
        cards.addStretch(1)

        def make_card(text: str, on_click, primary: bool = False):
            btn = QPushButton(text)
            btn.setProperty("class", "card-primary" if primary else "card")
            btn.setMinimumSize(220, 120)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(on_click)
            # Re-apply stylesheet so property-based selectors take effect.
            btn.setStyleSheet(self.styleSheet())
            return btn

        cards.addWidget(make_card(
            "📐\n\nCapture region\nDrag the area you want",
            window.capture_region, primary=True))
        cards.addWidget(make_card(
            "🖥\n\nCapture full screen\nEverything visible",
            window.capture_full_action))
        cards.addWidget(make_card(
            "📂\n\nOpen image\nAnnotate an existing file",
            window.open_image))
        cards.addStretch(1)
        outer.addLayout(cards)

        outer.addSpacing(28)

        # ---------- delayed capture section ----------
        delay_header = QLabel(
            "⏱  DELAYED CAPTURE  —  set up the hover state first")
        delay_header.setObjectName("section")
        delay_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(delay_header)
        outer.addSpacing(8)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        chips.addStretch(1)
        for sec in (3, 5, 10):
            c = QPushButton(f"Region · {sec}s")
            c.setProperty("class", "chip")
            c.setStyleSheet(self.styleSheet())
            c.setCursor(Qt.CursorShape.PointingHandCursor)
            c.clicked.connect(lambda _c=False, s=sec: window.capture_region_delayed(s))
            chips.addWidget(c)
        cfull = QPushButton("Full · 5s")
        cfull.setProperty("class", "chip")
        cfull.setStyleSheet(self.styleSheet())
        cfull.setCursor(Qt.CursorShape.PointingHandCursor)
        cfull.clicked.connect(lambda: window.capture_full_delayed(5))
        chips.addWidget(cfull)
        ccustom = QPushButton("Custom…")
        ccustom.setProperty("class", "chip")
        ccustom.setStyleSheet(self.styleSheet())
        ccustom.setCursor(Qt.CursorShape.PointingHandCursor)
        ccustom.clicked.connect(window.capture_region_custom_delay)
        chips.addWidget(ccustom)
        chips.addStretch(1)
        outer.addLayout(chips)

        # ---------- per-monitor section (only if >1) ----------
        screens = QGuiApplication.screens()
        if len(screens) > 1:
            outer.addSpacing(22)
            mon_header = QLabel("🖥  SPECIFIC MONITOR")
            mon_header.setObjectName("section")
            mon_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            outer.addWidget(mon_header)
            outer.addSpacing(8)

            primary = QGuiApplication.primaryScreen()
            # Order screens by their x coordinate so the button row mirrors
            # the physical layout left-to-right.
            ordered = sorted(screens, key=lambda s: (s.geometry().x(), s.geometry().y()))
            mon_row = QHBoxLayout()
            mon_row.setSpacing(8)
            mon_row.addStretch(1)
            for scr in ordered:
                label, tip = describe_screen(scr)
                if scr is primary:
                    label = "⭐ " + label + "  ·  Primary"
                btn = QPushButton(label)
                btn.setProperty("class", "chip")
                btn.setStyleSheet(self.styleSheet())
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setToolTip(tip)
                btn.clicked.connect(lambda _c=False, s=scr: window.capture_screen(s))
                mon_row.addWidget(btn)
            mon_row.addStretch(1)
            outer.addLayout(mon_row)

        outer.addStretch(2)

        # ---------- footer ----------
        footer = QHBoxLayout()
        footer.addStretch(1)
        tip = QLabel(
            "Tip — bind <b>PrintScreen</b> to <code>yaz --capture</code> "
            "for instant access."
        )
        tip.setTextFormat(Qt.TextFormat.RichText)
        tip.setObjectName("footer")
        footer.addWidget(tip)
        set_up = QPushButton("Set up now →")
        set_up.setProperty("class", "link")
        set_up.setStyleSheet(self.styleSheet())
        set_up.setCursor(Qt.CursorShape.PointingHandCursor)
        set_up.clicked.connect(window.setup_global_shortcut)
        footer.addWidget(set_up)
        footer.addStretch(1)
        outer.addLayout(footer)

        # Subtle credit line under the footer.
        credit = QLabel(
            "Built by <a href='https://www.linkedin.com/in/yetesfa-alemayehu' "
            "style='color:#6a6f7d;'>Yetesfa Alemayehu</a>"
        )
        credit.setTextFormat(Qt.TextFormat.RichText)
        credit.setObjectName("footer")
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setOpenExternalLinks(True)
        credit.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        outer.addWidget(credit)
