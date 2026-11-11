import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from game.player import PlayerSim
from game.web import GameServer


class BrowserHostTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cabin-web-test-")
        game = PlayerSim(out_dir=self.directory.name, seed=7)
        save = str(Path(self.directory.name) / "player-save.json")
        self.server = GameServer(("127.0.0.1", 0), game, save, seed=7)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.directory.cleanup()

    def request(self, path, payload=None, headers=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.url + path, data=data, headers=headers or {})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def action(self, payload, headers=None):
        return self.request("/api/action", payload, {
            "Content-Type": "application/json",
            "X-Cabin-Token": self.server.token, **(headers or {}),
        })

    def test_browser_bootstrap_and_actions_persist_the_played_state(self):
        status, headers, raw = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b'id="game-canvas"', raw)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        status, _, raw = self.request("/api/state")
        state = json.loads(raw)
        self.assertEqual(state["state"]["player"]["hp"], 1000)
        self.assertEqual(state["token"], self.server.token)
        status, _, raw = self.action({"action": "move", "dx": 0, "dy": 1})
        self.assertEqual(status, 200)
        played = json.loads(raw)["state"]
        saved = json.loads(Path(self.server.save_path).read_text())
        self.assertEqual(played["player"]["y"], 6)
        self.assertEqual(saved["body"]["y"], 6)
        self.assertEqual(saved["mode"], "player")
        status, _, raw = self.request("/api/save")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["body"]["physiology"]["organs"]["heart"], 160)

    def test_cross_origin_or_uncredentialed_requests_cannot_control_the_player(self):
        clock = self.server.game.clock
        payload = {"action": "wait", "minutes": 60}
        for headers in ({"X-Cabin-Token": ""}, {"Origin": "https://unrelated.example"},
                        {"Host": "unrelated.example"}):
            with self.subTest(headers=headers):
                status, _, _ = self.action(payload, headers)
                self.assertEqual(status, 403)
        self.assertEqual(self.server.game.clock, clock)

    def test_bad_action_shapes_return_explicit_errors_not_success(self):
        start = self.server.game.clock
        for payload in (["move"], {"action": "move", "dx": True, "dy": 0},
                        {"action": "buy", "item": []}, {"action": "unknown"},
                        {"action": "wait", "minutes": 99999}):
            with self.subTest(payload=payload):
                status, _, raw = self.action(payload)
                self.assertEqual(status, 400)
                self.assertIn("error", json.loads(raw))
        self.assertEqual(self.server.game.clock, start)

    def test_private_forwarded_origin_works_when_the_proxy_rewrites_host(self):
        self.server.public_origin = "https://trusted-cabin.app.github.dev"
        status, _, _ = self.action(
            {"action": "wait", "minutes": 1},
            {"Origin": self.server.public_origin})
        self.assertEqual(status, 200)
        status, _, _ = self.action(
            {"action": "wait", "minutes": 1},
            {"Origin": "https://unrelated-cabin.app.github.dev"})
        self.assertEqual(status, 403)

    def test_new_life_requires_confirmation_and_downloads_are_allowlisted(self):
        self.server.game.body.physiology.hurt("heart", 10)
        headers = {"Content-Type": "application/json", "X-Cabin-Token": self.server.token}
        status, _, _ = self.request("/api/new", {"confirm": False}, headers)
        self.assertEqual(status, 400)
        self.assertEqual(self.server.game.body.physiology.hp, 990)
        status, _, raw = self.request("/api/new", {"confirm": True}, headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["state"]["player"]["hp"], 1000)
        for path in ("/game/player.py", "/books/../game/player.py", "/books/missing.zip"):
            self.assertEqual(self.request(path)[0], 404)

    def test_a_vital_failure_is_returned_as_game_over_not_a_successful_action(self):
        self.server.game.body.physiology.hurt("brain", 120)
        status, _, raw = self.action({"action": "rest"})
        result = json.loads(raw)
        self.assertEqual(status, 409)
        self.assertFalse(result["state"]["player"]["alive"])
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
