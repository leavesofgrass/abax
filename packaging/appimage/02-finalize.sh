#!/usr/bin/env bash
# Fast step: take /build/raw.AppImage, bundle the Qt runtime system libs for
# portability, write a clean AppRun that execs `python -m abax`, repack with
# appimagetool, and run a headless smoke test.
set -euo pipefail
export APPIMAGE_EXTRACT_AND_RUN=1
PY=/opt/python/cp311-cp311/bin/python
ARCH=x86_64
APPNAME=abax
VERSION="${ABAX_VERSION:-0.1.7}"
cd /build

echo "== Extract raw AppImage =="
rm -rf squashfs-root
./raw.AppImage --appimage-extract >/dev/null
ROOT=/build/squashfs-root

# Bundled interpreter (python-appimage lays it under opt/pythonX.Y/bin), relative to ROOT.
PYBIN=$(cd "$ROOT" && ls opt/python*/bin/python3.1* 2>/dev/null | grep -vE 'config|m$' | head -1)
[ -n "$PYBIN" ] || PYBIN=$(cd "$ROOT" && ls opt/python*/bin/python3* 2>/dev/null | head -1)
[ -n "$PYBIN" ] || { echo "ERROR: no bundled python found under $ROOT/opt"; exit 1; }
echo "== bundled python: $PYBIN =="

echo "== Locate + inject Qt runtime system libs =="
QTCORE=$(find "$ROOT" -name 'libQt6Core.so*' | head -1 || true)
QT_REL=""; PLUG_PARENT_REL=""
if [ -n "$QTCORE" ]; then
  QTLIBDIR=$(dirname "$QTCORE"); QT_REL=${QTLIBDIR#"$ROOT"/}
  PLUGDIR=$(find "$ROOT" -type d -name platforms -path '*plugins*' | head -1 || true)
  [ -n "$PLUGDIR" ] && PLUG_PARENT_REL=$(dirname "${PLUGDIR#"$ROOT"/}")
  echo "   Qt libs: $QT_REL   plugins parent: ${PLUG_PARENT_REL:-<none>}"
  mkdir -p "$ROOT/usr/lib"
  inject() {
    ldd "$1" 2>/dev/null | awk '/=> \// {print $3}' | while read -r so; do
      case "$so" in *squashfs-root*|*/opt/python/*) continue;; esac
      b=$(basename "$so")
      case "$b" in libc.so*|libm.so*|libdl.so*|libpthread.so*|librt.so*|ld-linux*|libresolv.so*|libgcc_s.so*|libstdc++.so*) continue;; esac
      [ -e "$ROOT/usr/lib/$b" ] || cp -Lv "$so" "$ROOT/usr/lib/" 2>/dev/null || true
    done
  }
  [ -n "$PLUGDIR" ] && for f in "$PLUGDIR"/*.so; do [ -e "$f" ] && inject "$f"; done
  for f in "$QTLIBDIR"/libQt6*.so*; do [ -e "$f" ] && inject "$f"; done
  for want in libxcb-cursor.so.0 libxkbcommon-x11.so.0 libxkbcommon.so.0 libxcb-util.so.1; do
    src=$(ldconfig -p 2>/dev/null | awk -v n="$want" '$1==n {print $NF; exit}')
    [ -n "${src:-}" ] && [ ! -e "$ROOT/usr/lib/$want" ] && cp -Lv "$src" "$ROOT/usr/lib/" 2>/dev/null || true
  done
  echo "   usr/lib now carries $(ls "$ROOT/usr/lib" 2>/dev/null | wc -l) libs"
else
  echo "!! libQt6Core not found — Qt injection skipped."
fi

echo "== Write a clean AppRun (exec: python -m abax) =="
SSL_REL=$(cd "$ROOT" && ls opt/_internal/certs.pem 2>/dev/null | head -1 || true)
QT_REL="$QT_REL" PLUG="$PLUG_PARENT_REL" SSL="$SSL_REL" PYBIN="$PYBIN" \
  "$PY" - "$ROOT/AppRun" <<'PYEOF'
import os, sys
apprun = sys.argv[1]
qt   = os.environ.get("QT_REL", "")
plug = os.environ.get("PLUG", "")
ssl  = os.environ.get("SSL", "")
pybin = os.environ["PYBIN"]
L = ['#!/bin/bash',
     '# abax AppImage launcher — self-locating, execs `python -m abax`.',
     'HERE="$(dirname "$(readlink -f "$0")")"',
     'export APPDIR="${APPDIR:-$HERE}"']
ld = '"$APPDIR/usr/lib'
if qt:
    ld += ':$APPDIR/%s' % qt
ld += ':${LD_LIBRARY_PATH}"'
L.append('export LD_LIBRARY_PATH=%s' % ld)
if plug:
    L.append('export QT_QPA_PLATFORM_PLUGIN_PATH="$APPDIR/%s"' % plug)
if ssl:
    L.append('export SSL_CERT_FILE="$APPDIR/%s"' % ssl)
L.append('export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"')
L.append('exec "$APPDIR/%s" -m abax "$@"' % pybin)
open(apprun, "w", encoding="utf-8").write("\n".join(L) + "\n")
os.chmod(apprun, 0o755)
PYEOF
echo "---- AppRun ----"; cat "$ROOT/AppRun"; echo "----------------"

echo "== Repack with appimagetool =="
[ -x /tmp/appimagetool ] || { wget -q "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" -O /tmp/appimagetool; chmod +x /tmp/appimagetool; }
mkdir -p dist
SUFFIX=""; [ -f /build/NONEC ] && SUFFIX="-nonec"
OUT="dist/${APPNAME}-${VERSION}${SUFFIX}-${ARCH}.AppImage"
ARCH=$ARCH /tmp/appimagetool "$ROOT" "$OUT"
[ -f /build/NONEC ] && echo "Built WITHOUT PyNEC (nec): the SWIG/C++ compile failed; the built-in Method-of-Moments solver still works." > dist/NOTE-nonec.txt

echo "== Headless smoke test (offscreen Qt) =="
rm -rf /tmp/s && mkdir -p /tmp/s && cd /tmp/s
"/build/$OUT" --appimage-extract >/dev/null
echo "-- abax --version --"
QT_QPA_PLATFORM=offscreen ./squashfs-root/AppRun --version
echo "-- abax doctor (optional-dependency matrix) --"
QT_QPA_PLATFORM=offscreen ./squashfs-root/AppRun doctor || true
cd /build && rm -rf /tmp/s

echo "==================================================================="
ls -lh "/build/$OUT"
echo " DONE -> /build/$OUT"
echo "==================================================================="
