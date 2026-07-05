# AppImage builder for abax[all].
#
# Base: manylinux_2_28 (AlmaLinux 8, glibc 2.28). Building here means the finished
# AppImage links against glibc 2.28, so it runs on any distro from ~2019 on
# (Ubuntu 18.10+/Debian 10+/RHEL 8+/Fedora 29+) rather than only on the very
# newest. It also carries the gcc/g++/swig toolchain that PyNEC (the one
# source-only dep in [all]) needs to compile.
#
# Usage (from the repo root):
#   docker build -t abax-appimage -f packaging/appimage/Dockerfile packaging/appimage
#   docker run --rm -v "$PWD/dist:/out" abax-appimage    # copies the .AppImage to ./dist
#
# Override the version with --build-arg ABAX_VERSION=0.1.7 (installs abax[all]==<v>).
FROM quay.io/pypa/manylinux_2_28_x86_64

ARG ABAX_VERSION=0.1.7
ENV ABAX_VERSION=${ABAX_VERSION}
# AppImage tooling uses FUSE to mount; containers rarely have /dev/fuse, so force
# the extract-and-run path everywhere.
ENV APPIMAGE_EXTRACT_AND_RUN=1

# Qt runtime system libraries (PySide6 bundles Qt itself, but Qt links these
# X11/XCB/GL/xkbcommon/font/dbus libs at run time — 02-finalize.sh copies them
# into the bundle so it starts on a bare desktop). Plus swig + gcc-c++ for PyNEC,
# and librsvg2-tools (rsvg-convert) to rasterize the icon.
RUN dnf -y install --allowerasing \
      libX11 libXext libXrender libXi libXtst libxcb \
      xcb-util xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
      libxkbcommon libxkbcommon-x11 \
      mesa-libGL mesa-libEGL libglvnd-glx libglvnd-egl \
      fontconfig freetype dbus-libs libSM libICE \
      swig gcc-c++ make \
      librsvg2-tools file desktop-file-utils wget which findutils \
 && dnf clean all
RUN dnf -y install epel-release || true; dnf -y install xcb-util-cursor || true; dnf clean all || true

RUN /opt/python/cp311-cp311/bin/python -m pip install --no-cache-dir python-appimage

WORKDIR /build
# Heavy layer: pip-install abax[all] into a relocatable Python and build the raw
# AppImage. Cached across rebuilds; the pip cache mount avoids re-downloading the
# ~0.84 GB of wheels when it does re-run.
#
# wheelhouse/ is empty for local builds (→ 01-build-raw.sh installs abax[all] from
# PyPI). CI drops the freshly-built abax wheel here so the AppImage installs abax
# from it (extras still resolve from PyPI) — decoupling the AppImage from the PyPI
# publish, so it can build in parallel on a tag.
COPY entrypoint.desktop abax.svg 01-build-raw.sh ./
COPY wheelhouse/ ./wheelhouse/
RUN --mount=type=cache,target=/root/.cache/pip \
    chmod +x 01-build-raw.sh && ./01-build-raw.sh

# Fast layer: bundle Qt system libs, write the AppRun, repack, smoke-test.
# Editing 02 re-runs only this step, not the heavy install above.
COPY 02-finalize.sh ./
RUN chmod +x 02-finalize.sh && ./02-finalize.sh

# `docker run` with /out mounted drops the finished AppImage (+ any NOTE) on the host.
CMD ["sh", "-c", "cp -v /build/dist/*.AppImage /build/dist/NOTE-* /out/ 2>/dev/null; ls -lh /build/dist"]
