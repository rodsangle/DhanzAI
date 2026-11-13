"""Branch, archive and share conversations (ChatGPT-parity features).

Self-contained: its own tables and routes, switched on by ``install(app)``. The live server's
API image has patched core files, so this package never edits existing routes or tables.
"""


def install(app) -> None:
    from app.conversation_extras.routes import install as _install

    _install(app)
