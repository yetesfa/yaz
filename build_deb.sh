#!/usr/bin/env bash
# Build a Debian package (.deb) for Yaz.
#
# Output: yaz_<VERSION>_all.deb in the project root.
# Install with:    sudo apt install ./yaz_<VERSION>_all.deb
#         or:     sudo dpkg -i yaz_<VERSION>_all.deb && sudo apt -f install
set -euo pipefail

VERSION="${1:-0.1.0}"
ARCH="all"
PKG="yaz_${VERSION}_${ARCH}"
ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
BUILD="$(mktemp -d)/$PKG"

echo "▶  Building $PKG.deb"
mkdir -p \
    "$BUILD/DEBIAN" \
    "$BUILD/usr/lib/yaz" \
    "$BUILD/usr/bin" \
    "$BUILD/usr/share/applications" \
    "$BUILD/usr/share/doc/yaz" \
    "$BUILD/usr/share/metainfo"

# --- payload ---
# yaz.py is the entry; yaz_*.py modules live under src/ (grouped by role)
# but get flattened into /usr/lib/yaz/ at install time so the sibling
# imports work without the dev-only sys.path bootstrap.
install -m 0644 "$ROOT/yaz.py" "$BUILD/usr/lib/yaz/yaz.py"
for mod in "$ROOT"/src/yaz_*.py "$ROOT"/src/*/yaz_*.py; do
    install -m 0644 "$mod" "$BUILD/usr/lib/yaz/$(basename "$mod")"
done
cat > "$BUILD/usr/bin/yaz" <<'EOF'
#!/usr/bin/env bash
exec /usr/bin/python3 /usr/lib/yaz/yaz.py "$@"
EOF
chmod 0755 "$BUILD/usr/bin/yaz"

# Desktop entry — system-wide /usr layout, no @PREFIX@ substitution needed.
sed 's|@PREFIX@/yaz|/usr/bin/yaz|g' "$ROOT/yaz.desktop.in" \
    > "$BUILD/usr/share/applications/yaz.desktop"

# Docs.
install -m 0644 "$ROOT/README.md"  "$BUILD/usr/share/doc/yaz/"
install -m 0644 "$ROOT/LICENSE"    "$BUILD/usr/share/doc/yaz/copyright"

# Compute installed-size in KiB (apt shows this).
INSTALLED_SIZE=$(du -sk "$BUILD/usr" | cut -f1)

# --- control metadata ---
cat > "$BUILD/DEBIAN/control" <<EOF
Package: yaz
Version: $VERSION
Section: graphics
Priority: optional
Architecture: $ARCH
Installed-Size: $INSTALLED_SIZE
Depends: python3 (>= 3.10), python3-pyqt6, python3-gi, gnome-screenshot, wl-clipboard
Recommends: grim, slurp
Maintainer: Yetesfa Alemayehu <noreply@example.com>
Homepage: https://github.com/yetesfa/yaz
Description: Wayland-native screenshot and annotation tool
 Yaz captures and annotates screenshots on Linux. Designed for GNOME
 Wayland (Ubuntu 24.04+) where Flameshot, grim and other wlroots-only
 tools don't work.
 .
 Features region/full-screen/per-monitor capture, delayed capture (for
 hover screenshots), arrow/rectangle/ellipse/pen/highlight/text/blur
 annotations, undo/redo, crop, and a global keyboard-shortcut wizard.
 .
 "Yaz" is Amharic for "grab it". Built by Yetesfa Alemayehu.
EOF

# --- AppStream metadata (lets the package appear in GNOME Software too) ---
cat > "$BUILD/usr/share/metainfo/io.github.yetesfa.yaz.metainfo.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>io.github.yetesfa.yaz</id>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>MIT</project_license>
  <name>Yaz</name>
  <summary>Wayland-native screenshot and annotation tool</summary>
  <description>
    <p>
      Yaz is a screenshot capture and annotation tool for Linux,
      designed to work reliably on GNOME Wayland where many other
      tools fail.
    </p>
    <p>"Yaz" is Amharic for "grab it".</p>
    <ul>
      <li>Region, full-screen, and per-monitor capture</li>
      <li>Delayed capture for hover-state screenshots</li>
      <li>Arrows, rectangles, ellipses, pen, highlighter, text, blur</li>
      <li>Full undo/redo</li>
      <li>Global keyboard-shortcut wizard</li>
    </ul>
  </description>
  <launchable type="desktop-id">yaz.desktop</launchable>
  <url type="homepage">https://github.com/yetesfa/yaz</url>
  <url type="bugtracker">https://github.com/yetesfa/yaz/issues</url>
  <developer_name>Yetesfa Alemayehu</developer_name>
  <provides>
    <binary>yaz</binary>
  </provides>
  <content_rating type="oars-1.1"/>
  <releases>
    <release version="$VERSION" date="$(date +%Y-%m-%d)"/>
  </releases>
</component>
EOF

# --- postinst: refresh desktop / icon caches ---
cat > "$BUILD/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF
chmod 0755 "$BUILD/DEBIAN/postinst"

# --- build ---
dpkg-deb --root-owner-group --build "$BUILD" "$ROOT/$PKG.deb" >/dev/null
echo "✓ $ROOT/$PKG.deb"
echo
echo "Install locally with:"
echo "    sudo apt install $ROOT/$PKG.deb"
echo
echo "Or attach $PKG.deb to a GitHub Release for users to download."
