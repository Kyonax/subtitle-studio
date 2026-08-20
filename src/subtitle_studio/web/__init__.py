"""The browser front end: a local HTTP API plus the built Vue app.

Same stage functions as the CLI and the TUI — this package only exposes them
over HTTP so a page can drive them and show a live preview of every change.
Nothing here talks to the network: the server binds to localhost by default.
"""

from subtitle_studio.web.server import serve

__all__ = ["serve"]
