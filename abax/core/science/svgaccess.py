"""Accessible SVG: give any standalone SVG a title and description that
assistive technology announces. Pure stdlib.

:func:`make_accessible` adds ``role="img"`` and ``aria-labelledby`` to the root
``<svg>`` element and inserts ``<title>`` and ``<desc>`` as its first children,
which is the pattern screen readers support most consistently for inline and
standalone SVG. The ids are derived from the text, so two charts embedded in
one HTML page do not collide.
"""

from __future__ import annotations

import hashlib
import re

_SVG_OPEN = re.compile(r"<svg\b([^>]*)>", re.IGNORECASE)


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def make_accessible(svg: str, title: str, desc: str = "") -> str:
    """Return ``svg`` with an accessible name (``title``) and description.

    Raises ValueError if ``svg`` has no ``<svg>`` element or ``title`` is empty.
    An element that already declares ``role`` is left as it is apart from the
    added ``<title>`` / ``<desc>``.
    """
    if not title.strip():
        raise ValueError("an accessible SVG needs a non-empty title")
    m = _SVG_OPEN.search(svg)
    if m is None:
        raise ValueError("no <svg> element found")
    uid = hashlib.sha1(f"{title}\n{desc}".encode()).hexdigest()[:10]
    t_id, d_id = f"t-{uid}", f"d-{uid}"
    attrs = m.group(1)
    self_closing = attrs.rstrip().endswith("/")
    if self_closing:
        attrs = attrs.rstrip()[:-1]
    labelled = f"{t_id} {d_id}" if desc else t_id
    if "role=" not in attrs:
        attrs += ' role="img"'
    attrs += f' aria-labelledby="{labelled}"'
    children = f'<title id="{t_id}">{_esc(title)}</title>'
    if desc:
        children += f'<desc id="{d_id}">{_esc(desc)}</desc>'
    if self_closing:
        replacement = f"<svg{attrs}>{children}</svg>"
    else:
        replacement = f"<svg{attrs}>\n{children}"
    return svg[: m.start()] + replacement + svg[m.end():]
