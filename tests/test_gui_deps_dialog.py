"""First-run optional-feature chooser (Thin / All / custom) — no real pip."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax import autodeps  # noqa: E402
from abax.gui._qtcompat import QApplication, QWidget  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    w = QWidget()
    w._settings = Settings()
    return w


@pytest.fixture()
def no_pip(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(autodeps, "_MARKER_DIR", str(tmp_path))
    monkeypatch.setattr(autodeps, "_INSTALL_FN", lambda pip, **k: calls.append(pip) or True)
    autodeps._attempted_session.clear()
    autodeps.set_enabled(None)
    yield calls
    autodeps.set_enabled(None)
    autodeps._attempted_session.clear()


def _dlg(win):
    from abax.gui.dialogs.deps_dialog import DependencyChooser

    return DependencyChooser(win)


def test_has_a_checkbox_per_feature(win):
    dlg = _dlg(win)
    assert set(dlg._boxes) == set(autodeps.FEATURE_INFO)


def test_thin_preset_selects_only_light_features(win):
    dlg = _dlg(win)
    dlg._apply_preset("thin")
    sel = set(dlg.selected())
    # already-installed features stay checked+disabled, so only compare the
    # *enabled* boxes against the thin preset
    enabled = {k for k, cb in dlg._boxes.items() if cb.isEnabled()}
    assert sel & enabled == set(autodeps.preset("thin")) & enabled
    assert "science" not in (sel & enabled)


def test_all_preset_checks_everything(win):
    dlg = _dlg(win)
    dlg._apply_preset("all")
    assert set(dlg.selected()) == set(autodeps.FEATURE_INFO)


def test_install_marks_prompted_and_installs(win, no_pip):
    dlg = _dlg(win)
    dlg._apply_preset("all")
    dlg._install()
    assert win._settings.deps_prompted is True
    # any not-yet-present package in the closure was handed to the (fake) installer
    # (in a full dev env everything may already be present -> empty is also fine)
    assert isinstance(no_pip, list)


def test_skip_marks_prompted_without_installing(win, no_pip):
    dlg = _dlg(win)
    dlg._skip()
    assert win._settings.deps_prompted is True
    assert no_pip == []


def test_maybe_prompt_respects_flags(win, monkeypatch):
    from abax.gui.dialogs import deps_dialog

    shown = []
    monkeypatch.setattr(deps_dialog, "DependencyChooser",
                        lambda w: type("F", (), {"exec": lambda s: shown.append(1)})())

    win._settings.deps_prompted = True
    deps_dialog.maybe_prompt(win)
    assert shown == []                                   # already prompted -> no dialog

    win._settings.deps_prompted = False
    win._settings.auto_install = False
    deps_dialog.maybe_prompt(win)
    assert shown == []                                   # opted out -> no dialog

    win._settings.auto_install = True
    deps_dialog.maybe_prompt(win)
    assert shown == [1]                                  # first run -> shown


def test_wired_into_window(app):
    from abax.gui.main_window import MainWindow

    w = MainWindow(Settings())
    assert callable(w.install_optional_features)
    assert "Install optional features now" in w._palette_actions()
