#!/usr/bin/env bash
# Heavy step: rasterize the icon and build the raw AppImage with python-appimage
# (a relocatable manylinux Python with abax[all] pip-installed into it). Tries the
# full [all]; if PyNEC's SWIG/C++ compile fails, falls back to all-except-nec and
# drops a /build/NONEC marker. Leaves the result at /build/raw.AppImage.
set -euo pipefail
export APPIMAGE_EXTRACT_AND_RUN=1
PY=/opt/python/cp311-cp311/bin/python
VERSION="${ABAX_VERSION:-0.1.7}"
cd /build

echo "== Rasterize icon (SVG -> 256px PNG) =="
rsvg-convert -w 256 -h 256 abax.svg -o abax.png
file abax.png

build_recipe() {
  local reqs="$1"
  rm -rf recipe; mkdir -p recipe
  cp entrypoint.desktop abax.png recipe/
  printf '%s\n' "$reqs" > recipe/requirements.txt
  echo "   requirements: $reqs"
  rm -f abax*.AppImage
  "$PY" -m python_appimage build app -l manylinux_2_28_x86_64 -p 3.11 recipe
}

# Install abax from a CI-provided local wheel if one was dropped in wheelhouse/
# (extras still resolve from PyPI); otherwise install abax[all] from PyPI. This
# lets CI build the AppImage from the freshly-built wheel before it's on PyPI.
NONEC_EXTRAS="thin,parquet,science,jupyter,bayes,stats-io,database,hdf5,satellite,tts,restricted"
WHEEL=$(ls /build/wheelhouse/abax-*.whl 2>/dev/null | head -1 || true)
if [ -n "$WHEEL" ]; then
  echo "== installing abax from local wheel: $WHEEL =="
  ALL_SPEC="${WHEEL}[all]"
  NONEC_SPEC="${WHEEL}[${NONEC_EXTRAS}]"
else
  echo "== installing abax[all]==${VERSION} from PyPI =="
  ALL_SPEC="abax[all]==${VERSION}"
  NONEC_SPEC="abax[${NONEC_EXTRAS}]==${VERSION}"
fi

rm -f /build/NONEC
echo "== python-appimage build (attempting full abax[all]) =="
if build_recipe "$ALL_SPEC"; then
  echo "   full abax[all] build succeeded (PyNEC included)."
else
  echo "!! Full [all] build failed (most likely PyNEC's SWIG/C++ compile)."
  echo "!! Falling back to all-except-nec (the built-in MoM solver still works)."
  touch /build/NONEC
  build_recipe "$NONEC_SPEC"
fi

APP=$(ls -t abax*.AppImage 2>/dev/null | grep -iv appimagetool | head -1)
[ -n "$APP" ] || { echo "ERROR: no AppImage produced"; exit 1; }
mv -f "$APP" /build/raw.AppImage
echo "== raw AppImage -> /build/raw.AppImage =="
ls -lh /build/raw.AppImage
