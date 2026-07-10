#!/usr/bin/env bash
#
# Generate packaging/macos/abax.icns from the shared SVG, for the PyInstaller
# BUNDLE step. Rasterize the source SVG to 1024px, downscale to every size the
# .iconset needs with sips, add the @2x retina variants iconutil expects, then
# pack the .icns. Best-effort throughout (|| true): a missing icon must not fail
# the build — the app just ships without a custom icon. Run from the repo root.
#
# Shared by the arm64 and Intel macOS build jobs in .github/workflows/release.yml
# so the two stay identical.
set -e

ICONSET=packaging/macos/abax.iconset
mkdir -p "$ICONSET"

# Rasterize the source SVG to the largest size, then downscale with sips.
qlmanage -t -s 1024 -o packaging/macos packaging/appimage/abax.svg || true
BASE=packaging/macos/abax.svg.png
if [ ! -f "$BASE" ]; then
  # Fallback: let sips read the SVG directly at 1024px.
  sips -s format png packaging/appimage/abax.svg --out "$BASE" -Z 1024 || true
fi

if [ -f "$BASE" ]; then
  for s in 16 32 64 128 256 512 1024; do
    sips -z $s $s "$BASE" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  done
  # Retina @2x variants iconutil expects.
  cp "$ICONSET/icon_32x32.png"     "$ICONSET/icon_16x16@2x.png"
  cp "$ICONSET/icon_64x64.png"     "$ICONSET/icon_32x32@2x.png"
  cp "$ICONSET/icon_256x256.png"   "$ICONSET/icon_128x128@2x.png"
  cp "$ICONSET/icon_512x512.png"   "$ICONSET/icon_256x256@2x.png"
  cp "$ICONSET/icon_1024x1024.png" "$ICONSET/icon_512x512@2x.png"
  iconutil -c icns "$ICONSET" -o packaging/macos/abax.icns || true
fi

echo "icns present: $([ -f packaging/macos/abax.icns ] && echo yes || echo no)"
