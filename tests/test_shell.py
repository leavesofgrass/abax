"""System-shell passthrough (line-oriented in-app terminal core)."""

from __future__ import annotations

import os
import sys

from abax.core.shell import Result, ShellSession, run


def test_run_captures_stdout_and_returncode_zero():
    result = run(f'{sys.executable} -c "print(7*6)"')
    assert result.returncode == 0
    assert result.stdout.strip() == "42"
    assert result.stderr == ""


def test_run_failing_command_returns_exit_code():
    result = run(f'{sys.executable} -c "import sys; sys.exit(3)"')
    assert result.returncode == 3


def test_run_captures_stderr():
    result = run(f'{sys.executable} -c "import sys; sys.stderr.write(\'boom\')"')
    assert "boom" in result.stderr


def test_run_timeout_does_not_raise():
    result = run(f'{sys.executable} -c "import time; time.sleep(5)"', timeout=0.2)
    assert result.returncode != 0
    assert "timed out" in result.stderr.lower()


def test_session_default_cwd_is_process_cwd():
    session = ShellSession()
    assert session.cwd == os.path.abspath(os.getcwd())


def test_session_cd_changes_cwd_for_subsequent_commands(tmp_path):
    session = ShellSession()
    cd_result = session.execute(f"cd {tmp_path}")
    assert cd_result.returncode == 0
    assert os.path.samefile(session.cwd, tmp_path)

    result = session.execute(f'{sys.executable} -c "import os; print(os.getcwd())"')
    assert result.returncode == 0
    assert os.path.samefile(result.stdout.strip(), tmp_path)


def test_session_cd_relative(tmp_path):
    sub = tmp_path / "child"
    sub.mkdir()
    session = ShellSession(cwd=str(tmp_path))
    session.execute("cd child")
    assert os.path.samefile(session.cwd, sub)


def test_session_cd_nonexistent_returns_nonzero_without_raising(tmp_path):
    session = ShellSession(cwd=str(tmp_path))
    before = session.cwd
    result = session.execute("cd no_such_dir_here")
    assert result.returncode != 0
    assert result.stderr
    assert session.cwd == before  # unchanged on failure


def test_session_bare_cd_goes_home():
    session = ShellSession()
    result = session.execute("cd")
    assert result.returncode == 0
    assert os.path.samefile(session.cwd, os.path.expanduser("~"))


def test_session_pwd_reports_tracked_cwd(tmp_path):
    session = ShellSession(cwd=str(tmp_path))
    result = session.execute("pwd")
    assert result.returncode == 0
    assert os.path.samefile(result.stdout.strip(), tmp_path)


def test_prompt_contains_cwd(tmp_path):
    session = ShellSession(cwd=str(tmp_path))
    assert str(tmp_path) in session.prompt()


def test_result_is_dataclass():
    r = Result(stdout="a", stderr="b", returncode=0)
    assert (r.stdout, r.stderr, r.returncode) == ("a", "b", 0)
