"""abax.gui — Qt front-end. No Qt imports leak outside this package.

The top of the three-layer seam. Binding-specific code is confined to
``_qtcompat.py``; everything else imports Qt symbols from there.
"""
