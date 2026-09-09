"""A warm process that answers the same commands over HTTP.

Starting Python, importing Pillow and opening the Win32 libraries costs about 400ms,
which is several times what most actions actually take. An agent driving a desktop pays
that on every click. Holding one process open and talking to it over loopback turns a
click into a few milliseconds.

The endpoints mirror the command line exactly: the query string is turned back into an
argument list and handed to the same parser and the same functions, so the two surfaces
cannot drift apart.

This server can click anything the user can click, so it is deliberately hard to reach:
it binds to the loopback address only, demands a secret that lives in a file only the
user can read, refuses any request carrying browser headers, and refuses any request
whose Host is not loopback, which is what stops a DNS rebinding attack from a web page.
"""

from __future__ import annotations

import hmac
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from doppelhand import __version__, session
from doppelhand.cli import ACTIONS, cached_parser
from doppelhand.errors import DoppelhandError, UsageError

TOKEN_HEADER = "X-Doppelhand-Token"

#: Which query parameters are positional arguments on the command line, in order.
POSITIONALS = {
    "shot": ("out",), "screen": (), "cursor": (),
    "click": ("at",), "move": ("at",), "drag": ("start", "end"),
    "scroll": ("direction", "amount"), "type": ("text",),
    "key": ("combo",), "hold": ("combo", "seconds"), "wait": ("seconds",),
}
BOOLEAN = {"no-cursor", "fast"}
READ_ONLY = {"health", "screen", "cursor", "shot"}


def state_file():
    return session.state_dir() / "serve.json"


def to_argv(action: str, query: dict[str, list[str]]) -> list[str]:
    """Rebuild the command line a caller would have typed."""
    values = {key: items[-1] for key, items in query.items()}
    argv = [action]
    for name in POSITIONALS.get(action, ()):
        if name not in values:
            break  # a later positional without an earlier one is argparse's to reject
        argv.append(values.pop(name))
    for key, value in values.items():
        flag = f"--{key.replace('_', '-')}"
        if key.replace("_", "-") in BOOLEAN:
            if value.lower() not in ("0", "false", "no"):
                argv.append(flag)
        else:
            argv.extend([flag, value])
    return argv


class Handler(BaseHTTPRequestHandler):
    server_version = f"doppelhand/{__version__}"
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def _handle(self, method: str):
        from doppelhand import screen

        route = urlparse(self.path)
        action = route.path.strip("/").lower()
        refusal = self._refuse()
        if refusal:
            status, reason = refusal
            return self._reply(status, {"ok": False, "error": reason})

        # Requests arrive on worker threads and the desktop attachment is per thread,
        # so every thread makes the call. It happens after the checks above, because an
        # unauthenticated caller should not reach any of the machine's state.
        screen.attach_input_desktop()

        if action == "health":
            return self._reply(200, {"ok": True, "version": __version__})
        if action == "stop":
            # Taking the lock first means no action is part way through the shared
            # capture objects when they are released during shutdown.
            with self.server.busy:
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            return self._reply(200, {"ok": True, "stopping": True})
        if action not in ACTIONS:
            return self._reply(404, {"ok": False, "error": f"no such action: {action}",
                                     "actions": sorted(ACTIONS) + ["health", "stop"]})
        if method == "GET" and action not in READ_ONLY:
            return self._reply(405, {"ok": False,
                                     "error": f"{action} changes the screen, use POST"})

        argv = to_argv(action, parse_qs(route.query, keep_blank_values=True))
        try:
            with self.server.busy:
                args = cached_parser().parse_args(argv)
                payload = ACTIONS[action](args, self.server.build_executor(args))
        except UsageError as exc:
            return self._reply(400, {"ok": False, "error": str(exc), "usage": exc.usage})
        except DoppelhandError as exc:
            return self._reply(400, {"ok": False, "error": str(exc)})
        except OSError as exc:
            return self._reply(500, {"ok": False,
                                     "error": f"{type(exc).__name__}: {exc}"})
        except Exception as exc:  # noqa: BLE001 - the contract is a JSON answer, always
            # Without this a caller gets a dropped connection instead of an answer, and
            # has no way to tell a crash from a hang.
            return self._reply(500, {"ok": False,
                                     "error": f"{type(exc).__name__}: {exc}"})
        return self._reply(200, {"ok": True, **payload})

    def _refuse(self) -> tuple[int, str] | None:
        """Every reason to turn a request away, before it can touch the desktop."""
        host = (self.headers.get("Host") or "").lower()
        allowed = {f"127.0.0.1:{self.server.server_address[1]}",
                   f"localhost:{self.server.server_address[1]}"}
        if host not in allowed:
            return 403, "Host must be loopback"
        if self.headers.get("Origin"):
            return 403, "browsers may not drive doppelhand"
        site = self.headers.get("Sec-Fetch-Site")
        if site and site != "none":
            return 403, "browsers may not drive doppelhand"
        sent = self.headers.get(TOKEN_HEADER) or ""
        if not hmac.compare_digest(sent, self.server.token):
            return 401, f"send the shared secret in the {TOKEN_HEADER} header"
        return None

    def _reply(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *fmt_args):
        if not self.server.quiet:
            super().log_message(fmt, *fmt_args)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, port: int, token: str, quiet: bool, frames=None):
        super().__init__(("127.0.0.1", port), Handler)
        self.token = token
        self.quiet = quiet
        self.frames = frames
        # One pointer, one keyboard: actions run one at a time whatever arrives.
        self.busy = threading.Lock()

    def build_executor(self, args):
        from doppelhand.cli import _executor

        executor = _executor(args)
        executor.frames = self.frames
        return executor

    def server_close(self):
        # Shutting down only stops new connections; a request already inside the lock
        # may still be using the capture objects this is about to release.
        with self.busy:
            if self.frames is not None:
                self.frames.close()
                self.frames = None
        super().server_close()


def serve(port: int = 0, token: str | None = None, quiet: bool = False) -> int:
    from doppelhand import screen
    from doppelhand.duplication import FrameSource

    token = token or secrets.token_urlsafe(32)
    # Duplication is refused to a thread that is not on the interactive desktop, which
    # is where a process launched by an agent often starts.
    screen.attach_input_desktop()
    server = Server(port, token, quiet, frames=FrameSource())
    chosen = server.server_address[1]

    note = state_file()
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(json.dumps({"port": chosen, "token": token,
                                "version": __version__}), encoding="utf-8")
    if not quiet:
        print(f"doppelhand {__version__} listening on http://127.0.0.1:{chosen}")
        print(f"token written to {note}")
        print(f'  curl -sH "{TOKEN_HEADER}: {token}" '
              f'http://127.0.0.1:{chosen}/shot?fast=1')
        print(f'  curl -sXPOST -H "{TOKEN_HEADER}: {token}" '
              f'"http://127.0.0.1:{chosen}/click?at=640,360"')
        print("stop with ctrl+c")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        note.unlink(missing_ok=True)
    return 0
