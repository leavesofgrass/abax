"""PyInstaller entry point for abax-worker — the isolated code-execution worker.

A sibling executable placed in Contents/MacOS beside the main `abax` binary; the
console/macros/scripts bridge finds it via os.path.dirname(sys.executable) and
prefers it over re-launching the app. Speaks the length-prefixed JSON frame
protocol on stdin/stdout (see abax.console_worker).
"""
from abax.console_worker import main

main()
