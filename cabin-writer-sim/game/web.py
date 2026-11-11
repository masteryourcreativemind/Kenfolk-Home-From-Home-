"""Dependency-free, local browser host for the directly playable game."""

import json
import os
from pathlib import Path
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlsplit
import webbrowser

from .player import ActionError, GameOver, PlayerSim


ASSETS = Path(__file__).with_name("web")
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/play.css": ("play.css", "text/css; charset=utf-8"),
    "/play.js": ("play.js", "text/javascript; charset=utf-8"),
}


def forwarded_url(port):
    name = os.environ.get("CODESPACE_NAME")
    domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    return f"https://{name}-{port}.{domain}" if name and domain else None


class GameServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, game, save_path, seed=None):
        super().__init__(address, Handler)
        self.game = game
        self.save_path = save_path
        self.seed = seed
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(32)
        self.allowed_hosts = {"localhost", "127.0.0.1", "::1", address[0]}
        self.public_origin = forwarded_url(self.server_port)
        if self.public_origin:
            self.allowed_hosts.add(urlsplit(self.public_origin).hostname)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, message, *args):
        if len(args) > 1 and str(args[1]).isdigit() and int(args[1]) < 400:
            return
        super().log_message(message, *args)

    def _reply(self, status, body, content_type="application/json", filename=None):
        if isinstance(body, dict):
            body = json.dumps(body, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src 'self' data:; "
                         "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header("Content-Disposition",
                             "attachment; filename*=UTF-8''" + quote(filename))
        self.end_headers()
        self.wfile.write(body)

    def _valid_host(self):
        try:
            host = urlsplit("http://" + self.headers.get("Host", "")).hostname
        except ValueError:
            self._reply(400, {"error": "Invalid host."})
            return False
        if host not in self.server.allowed_hosts:
            self._reply(403, {"error": "This host is not allowed to access the local game."})
            return False
        return True

    def do_GET(self):
        if not self._valid_host():
            return
        path = urlsplit(self.path).path
        try:
            if path in STATIC:
                filename, mime = STATIC[path]
                self._reply(200, (ASSETS / filename).read_bytes(), mime)
            elif path == "/api/state":
                with self.server.lock:
                    self._reply(200, {"state": self.server.game.snapshot(),
                                      "token": self.server.token})
            elif path == "/api/save":
                with self.server.lock:
                    self.server.game.save(self.server.save_path)
                    self._reply(200, Path(self.server.save_path).read_bytes(),
                                "application/json", "player-save.json")
            elif path.startswith("/books/"):
                with self.server.lock:
                    available = {"/books/" + quote(Path(book["zip"]).name, safe=""): book["zip"]
                                 for book in self.server.game.finished_books}
                    if path not in available:
                        self._reply(404, {"error": "No published book with that filename."})
                        return
                    book_path = Path(available[path])
                    self._reply(200, book_path.read_bytes(), "application/zip", book_path.name)
            else:
                self._reply(404, {"error": "Not found."})
        except OSError as exc:
            print(f"[player] Could not read or save game data: {exc}", file=sys.stderr)
            self._reply(500, {"error": "Could not read or save game data. See the server log."})

    def do_POST(self):
        if not self._valid_host():
            return
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in ("http", "https") or (
                    parsed.netloc != self.headers.get("Host")
                    and origin != self.server.public_origin):
                self._reply(403, {"error": "Cross-origin game actions are not allowed."})
                return
        token = self.headers.get("X-Cabin-Token", "").encode("utf-8")
        if not secrets.compare_digest(token, self.server.token.encode("ascii")):
            self._reply(403, {"error": "Reload the game before sending actions."})
            return
        path = urlsplit(self.path).path
        if path not in ("/api/action", "/api/new"):
            self._reply(404, {"error": "Not found."})
            return
        if self.headers.get_content_type() != "application/json":
            self._reply(415, {"error": "Actions must use application/json."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._reply(400, {"error": "Invalid request length."})
            return
        if not 0 < size <= 8192:
            self._reply(413, {"error": "Action request must contain 1-8192 bytes."})
            return
        try:
            payload = json.loads(self.rfile.read(size))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._reply(400, {"error": "Invalid JSON action."})
            return
        if not isinstance(payload, dict):
            self._reply(400, {"error": "An action must be a JSON object."})
            return
        with self.server.lock:
            try:
                if path == "/api/new":
                    if payload != {"confirm": True}:
                        self._reply(400, {"error": "Confirm before replacing your saved life."})
                        return
                    game = PlayerSim(out_dir=self.server.game.out_dir,
                                     seed=self.server.seed, owner=self.server.game.owner)
                    game.save(self.server.save_path)
                    self.server.game = game
                    message = "A new life begins. Your previous life has been replaced."
                else:
                    action = payload.pop("action", None)
                    message = self.server.game.act(action, **payload)
                    self.server.game.save(self.server.save_path)
                self._reply(200, {"state": self.server.game.snapshot(), "message": message})
            except ActionError as exc:
                try:
                    self.server.game.save(self.server.save_path)
                except OSError as save_error:
                    print(f"[player] Save failed: {save_error}", file=sys.stderr)
                    self._reply(500, {"state": self.server.game.snapshot(),
                                      "error": "Your action could not be saved. See the server log."})
                    return
                self._reply(409 if isinstance(exc, GameOver) else 400,
                            {"state": self.server.game.snapshot(), "error": str(exc)})
            except OSError as exc:
                print(f"[player] Action/save failed: {exc}", file=sys.stderr)
                self._reply(500, {"state": self.server.game.snapshot(),
                                  "error": "Your action could not be saved. See the server log."})


def run(out_dir="output", host="127.0.0.1", port=8765, seed=None,
        owner="The Reader", load=None, open_browser=True):
    save_path = os.path.join(out_dir, "player-save.json")
    source = load or (save_path if os.path.exists(save_path) else None)
    game = (PlayerSim.load(source, out_dir=out_dir) if source else
            PlayerSim(out_dir=out_dir, seed=seed, owner=owner))
    server = GameServer((host, port), game, save_path, seed)
    try:
        game.save(save_path)
        local_host = "127.0.0.1" if host == "0.0.0.0" else host
        url = f"http://{local_host}:{server.server_port}"
        print(f"\nPINEWOOD - play your own life\nOpen {url}", flush=True)
        forwarded = forwarded_url(server.server_port)
        if forwarded:
            print(f"Codespaces: {forwarded} (keep the forwarded port private)", flush=True)
        print(f"WASD/arrows move; E interacts; M opens the map.\n"
              f"Actions autosave to {save_path}. Ctrl+C stops the server.\n", flush=True)
        if open_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSaving your life and stopping the game.", flush=True)
        server.game.save(save_path)
    finally:
        server.server_close()
    return 0
