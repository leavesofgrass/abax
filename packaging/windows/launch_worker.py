"""PyInstaller entry point for abax-worker.exe — the isolated code-execution
worker, and nothing else.

A dedicated console-subsystem exe (spawned with CREATE_NO_WINDOW, so it never
flashes a window) whose std handles always exist — the bridge prefers it over
re-launching the possibly-windowed abaxw.exe. Speaks the length-prefixed JSON
frame protocol on stdin/stdout (see abax.console_worker).
"""
from abax.console_worker import main

main()
