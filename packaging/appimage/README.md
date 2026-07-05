# abax AppImage (Linux, portable)

Builds a single-file, portable Linux binary of **`abax[all]`** — the GUI plus the
full optional stack (numpy/pandas/scipy, PySide6, Jupyter, pymc, HDF5, SGP4, TTS,
the SQL drivers, …) — with **Docker**, so you can build it from any host (Windows,
macOS, Linux) that has a Linux Docker engine.

The build runs inside `manylinux_2_28` (glibc 2.28), so the resulting AppImage
runs on any reasonably modern distro (Ubuntu 18.10+/Debian 10+/RHEL 8+/Fedora 29+),
not just the one you built on.

## Build

From the **repo root**:

```sh
# 1. Build the image (this does the whole AppImage build inside it).
docker build -t abax-appimage -f packaging/appimage/Dockerfile packaging/appimage

# 2. Copy the finished .AppImage out to ./dist on the host.
docker run --rm -v "$PWD/dist:/out" abax-appimage
```

Package a different version with `--build-arg ABAX_VERSION=0.1.7` (it installs
`abax[all]==<version>` from PyPI).

## Run (on a Linux desktop)

```sh
chmod +x dist/abax-0.1.7-x86_64.AppImage
./dist/abax-0.1.7-x86_64.AppImage            # launches the GUI
./dist/abax-0.1.7-x86_64.AppImage --version  # or any CLI subcommand: tui, doctor, view …
```

## Notes

- **PyNEC is best-effort.** It's the only `[all]` dependency without a prebuilt
  wheel (a SWIG/C++ extension). The builder compiles it in-container; if that
  fails, it falls back to everything *except* `nec` and names the artifact
  `…-nonec-x86_64.AppImage` (the built-in Method-of-Moments solver still works —
  only the reference-grade PyNEC path is dropped). A `dist/NOTE-nonec.txt` records it.
- **Qt portability.** PySide6 bundles Qt itself; the builder additionally copies
  the X11/XCB/GL/xkbcommon system libraries Qt links at runtime (including
  `libxcb-cursor`, which Qt 6.5+ requires and many hosts lack) into the AppImage,
  and points `AppRun` at them. A desktop session (X11, or XWayland on Wayland) is
  still required to show a window.
- **Text-to-speech** (`speak_on_move`) needs the host's `espeak`/speech engine;
  it degrades to a silent no-op inside the AppImage if none is present.
- The builder runs a headless (`QT_QPA_PLATFORM=offscreen`) `--version` + `doctor`
  smoke test at the end so a broken bundle fails the build.
