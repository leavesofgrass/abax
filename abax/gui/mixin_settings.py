"""SettingsMixin — composed from focused mixins (split 2026-06-29).

The command palette (Ctrl+Shift+P) is mandatory per spec §9: every action is
reachable from it. The former ~800-line grab-bag is split by concern across the
mixin_view / mixin_palette / mixin_calc / mixin_console / mixin_macros /
mixin_tools modules; this class simply composes them.
"""

from __future__ import annotations

from .mixin_calc import CalcMixin
from .mixin_console import ConsoleMixin
from .mixin_macros import MacroMixin
from .mixin_palette import PaletteMixin
from .mixin_tools import ToolsMixin
from .mixin_view import ViewMixin


class SettingsMixin(ViewMixin, PaletteMixin, CalcMixin, ConsoleMixin, MacroMixin, ToolsMixin):
    """All settings/tools behaviour, composed from focused mixins."""
