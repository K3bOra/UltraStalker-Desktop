from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from ultrastalker_desktop.core.adapters.m3u import M3UAdapter
from ultrastalker_desktop.core.adapters.stalker import StalkerAdapter
from ultrastalker_desktop.core.adapters.xtream import XtreamAdapter


class _IPTVHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests_seen: list[dict] = []
    handshake_count = 0
    force_401_once = False

    def log_message(self, _format, *_args):
        return

    def _record(self, method: str, params: dict[str, list[str]]):
        type(self).requests_seen.append({
            "method": method,
            "path": urlsplit(self.path).path,
            "params": params,
            "authorization": self.headers.get("Authorization", ""),
            "cookie": self.headers.get("Cookie", ""),
            "referer": self.headers.get("Referer", ""),
        })

    def _send_json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, text: str, content_type="text/plain; charset=utf-8"):
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlsplit(self.path)
        params = parse_qs(parsed.query, keep_blank_values=True)
        self._record("GET", params)

        if parsed.path == "/portal.php":
            action = (params.get("action") or [""])[0]
            typ = (params.get("type") or [""])[0]
            if action == "handshake":
                type(self).handshake_count += 1
                token = "local-stalker-token" if type(self).handshake_count == 1 else "refreshed-stalker-token"
                self._send_json({"js": {"token": token}})
                return
            if action == "get_profile":
                self._send_json({"js": {"id": "profile-1"}})
                return
            if action in {"get_genres", "get_categories"} and typ == "itv":
                if type(self).force_401_once and self.headers.get("Authorization") == "Bearer local-stalker-token":
                    type(self).force_401_once = False
                    self._send_json({"error": "expired"}, status=401)
                    return
                self._send_json({"js": [{"id": "10", "title": "News"}]})
                return
            if action in {"get_genres", "get_categories"} and typ == "series":
                # Simulate a Ministra deployment that does not expose a
                # dedicated series shelf. The adapter must fall back to VOD.
                self._send_json({"js": []})
                return
            if action in {"get_genres", "get_categories"} and typ == "vod":
                self._send_json({"js": [
                    {"id": "20", "title": "Movies"},
                    {"id": "30", "title": "Shows"},
                ]})
                return
            if action == "get_all_channels" and typ == "itv":
                self._send_json({"js": {"data": [
                    {"id": "501", "name": "Local News", "cmd": "ffmpeg http://provider.invalid/live/501"},
                    {"id": "502", "name": "Local Sports", "cmd": "ffmpeg http://provider.invalid/live/502"},
                ]}})
                return
            if action == "get_ordered_list" and typ == "itv":
                page = (params.get("p") or [""])[0]
                if page == "0":
                    self._send_json({
                        "js": {
                            "data": [{"id": "501", "name": "Local News", "cmd": "ffmpeg http://provider.invalid/live/501"}],
                            "total_items": "1",
                        }
                    })
                else:
                    self._send_json({"js": {"data": [], "total_items": "1"}})
                return
            if action == "get_ordered_list" and typ == "series":
                self._send_json({"js": {"data": [], "total_items": "0"}})
                return
            if action == "get_ordered_list" and typ == "vod":
                category = (params.get("category") or params.get("genre") or [""])[0]
                movie_id = (params.get("movie_id") or [""])[0]
                season_id = (params.get("season_id") or [""])[0]
                series_id = (params.get("series_id") or [""])[0]
                if series_id == "700":
                    # This deployment ignores the simpler VOD series_id shape
                    # and requires lazy movie_id/season_id expansion instead.
                    self._send_json({"js": {"data": [], "total_items": "0"}})
                    return
                if movie_id == "700" and season_id == "0":
                    self._send_json({"js": {"data": [
                        {"id": "701", "name": "Season 1", "is_season": "1", "season_number": "1"}
                    ], "total_items": "1"}})
                    return
                if movie_id == "700" and season_id == "701":
                    self._send_json({"js": {"data": [
                        {"id": "702", "name": "Episode 1", "episode_num": "1", "season": "1",
                         "cmd": "ffmpeg http://provider.invalid/vod/series/702"}
                    ], "total_items": "1"}})
                    return
                rows = []
                if category in ("", "20"):
                    rows.append({"id": "601", "name": "Local Movie", "cmd": "ffmpeg http://provider.invalid/vod/601", "is_series": "0"})
                if category in ("", "30"):
                    rows.append({"id": "700", "name": "Local Show", "cmd": "", "is_series": "1", "series_id": "700"})
                self._send_json({"js": {"data": rows, "total_items": str(len(rows))}})
                return
            if action == "create_link":
                series = (params.get("series") or ["0"])[0]
                cmd = (params.get("cmd") or [""])[0]
                if "702" in cmd:
                    self._send_json({"js": {"cmd": f"ffmpeg http://127.0.0.1/episode-{series}.mkv"}})
                elif "/vod/" in cmd:
                    self._send_json({"js": {"cmd": "ffmpeg http://127.0.0.1/final-movie.mkv"}})
                else:
                    self._send_json({"js": {"cmd": "ffmpeg http://127.0.0.1/final-stream.ts"}})
                return
            self._send_json({"js": {}})
            return

        if parsed.path == "/player_api.php":
            action = (params.get("action") or [""])[0]
            username = (params.get("username") or [""])[0]
            password = (params.get("password") or [""])[0]
            if username != "user name" or password != "p@ss/word":
                self._send_json({"user_info": {"auth": 0}}, status=403)
                return
            if not action:
                self._send_json({"user_info": {"auth": 1}})
                return
            if action == "get_live_categories":
                self._send_json([{"category_id": "1", "category_name": "Local"}])
                return
            if action == "get_live_streams":
                self._send_json([{"stream_id": 77, "name": "Local Channel", "container_extension": "ts"}])
                return
            if action == "get_series_categories":
                self._send_json([{"category_id": "9", "category_name": "Shows"}])
                return
            if action == "get_series":
                self._send_json([{"series_id": 300, "name": "Local Series", "year": "2026"}])
                return
            if action == "get_series_info":
                self._send_json({
                    "episodes": {
                        "1": [
                            {
                                "id": 301,
                                "episode_num": 1,
                                "title": "Pilot",
                                "container_extension": "mkv",
                                "info": {"plot": "Local episode"},
                            }
                        ]
                    }
                })
                return
            self._send_json([])
            return

        if parsed.path == "/playlist.m3u":
            self._send_text(
                '#EXTM3U\n'
                '#EXTINF:-1 tvg-id="local" group-title="News",Local M3U\n'
                'http://127.0.0.1/live/user/pass/900.ts\n',
                "audio/x-mpegurl; charset=utf-8",
            )
            return

        self._send_text("not found")


class NetworkIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _IPTVHandler.requests_seen = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _IPTVHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        _IPTVHandler.requests_seen.clear()
        _IPTVHandler.handshake_count = 0
        _IPTVHandler.force_401_once = False

    def test_stalker_real_http_handshake_catalog_and_create_link(self):
        adapter = StalkerAdapter(self.base, "00:1A:79:AA:BB:CC", timeout=2)
        self.assertTrue(adapter.connect())
        categories = adapter.categories("live")
        self.assertEqual([(x.id, x.title) for x in categories], [("10", "News")])
        items = adapter.items("live", "10")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Local News")
        self.assertEqual(adapter.resolve_stream(items[0]), "http://127.0.0.1/final-stream.ts")

        handshake = next(x for x in _IPTVHandler.requests_seen if x["params"].get("action") == ["handshake"])
        self.assertIn("mac=00%3A1A%3A79%3AAA%3ABB%3ACC", handshake["cookie"])
        profile = next(x for x in _IPTVHandler.requests_seen if x["params"].get("action") == ["get_profile"])
        self.assertEqual(profile["authorization"], "Bearer local-stalker-token")
        self.assertEqual(profile["referer"], self.base + "/c/")
        ordered = next(x for x in _IPTVHandler.requests_seen if x["params"].get("action") == ["get_ordered_list"])
        self.assertEqual(ordered["params"].get("genre"), ["10"])
        create = next(x for x in _IPTVHandler.requests_seen if x["params"].get("action") == ["create_link"])
        self.assertEqual(create["params"].get("cmd"), ["ffmpeg http://provider.invalid/live/501"])


    def test_stalker_real_http_all_live_prefers_get_all_channels(self):
        adapter = StalkerAdapter(self.base, "00:1A:79:AA:BB:CC", timeout=2)
        self.assertTrue(adapter.connect())
        items = adapter.items("live", "")
        self.assertEqual([x.id for x in items], ["501", "502"])
        actions = [
            (x["params"].get("action") or [""])[0]
            for x in _IPTVHandler.requests_seen
            if x["path"] == "/portal.php"
        ]
        self.assertIn("get_all_channels", actions)
        self.assertNotIn("get_ordered_list", actions)

    def test_stalker_real_http_movie_flow_uses_vod_category_and_create_link(self):
        adapter = StalkerAdapter(self.base, "00:1A:79:AA:BB:CC", timeout=2)
        self.assertTrue(adapter.connect())
        categories = adapter.categories("movies")
        self.assertIn(("20", "Movies"), [(x.id, x.title) for x in categories])
        items = adapter.items("movies", "20")
        self.assertEqual([(x.id, x.title) for x in items], [("601", "Local Movie")])
        self.assertEqual(adapter.resolve_stream(items[0]), "http://127.0.0.1/final-movie.mkv")
        ordered = next(
            x for x in _IPTVHandler.requests_seen
            if x["params"].get("action") == ["get_ordered_list"] and x["params"].get("type") == ["vod"]
        )
        self.assertEqual(ordered["params"].get("category"), ["20"])
        self.assertNotIn("genre", ordered["params"])

    def test_stalker_real_http_vod_backed_series_and_episode_flow(self):
        adapter = StalkerAdapter(self.base, "00:1A:79:AA:BB:CC", timeout=2)
        self.assertTrue(adapter.connect())
        categories = adapter.categories("series")
        self.assertIn(("30", "Shows"), [(x.id, x.title) for x in categories])
        shows = adapter.items("series", "30")
        self.assertEqual([(x.id, x.title) for x in shows], [("700", "Local Show")])
        episodes = adapter.series_episodes(shows[0])
        self.assertEqual(len(episodes), 1)
        self.assertEqual((episodes[0].id, episodes[0].season, episodes[0].episode), ("702", 1, 1))
        self.assertEqual(adapter.resolve_stream(episodes[0]), "http://127.0.0.1/episode-1.mkv")
        create = [
            x for x in _IPTVHandler.requests_seen
            if x["params"].get("action") == ["create_link"]
        ][-1]
        self.assertEqual(create["params"].get("type"), ["vod"])
        self.assertEqual(create["params"].get("series"), ["1"])

    def test_xtream_real_http_auth_catalog_and_encoded_stream_url(self):
        adapter = XtreamAdapter(self.base, "user name", "p@ss/word", timeout=2)
        self.assertTrue(adapter.connect())
        categories = adapter.categories("live")
        self.assertEqual(categories[0].title, "Local")
        items = adapter.items("live", "1")
        self.assertEqual(items[0].id, "77")
        url = adapter.resolve_stream(items[0])
        self.assertEqual(url, self.base + "/live/user%20name/p%40ss%2Fword/77.ts")

        actions = [
            (x["params"].get("action") or [""])[0]
            for x in _IPTVHandler.requests_seen
            if x["path"] == "/player_api.php"
        ]
        self.assertEqual(actions, ["", "get_live_categories", "get_live_streams"])

    def test_stalker_real_http_refreshes_expired_token_once(self):
        adapter = StalkerAdapter(self.base, "00:1A:79:AA:BB:CC", timeout=2)
        self.assertTrue(adapter.connect())
        _IPTVHandler.force_401_once = True
        categories = adapter.categories("live")
        self.assertEqual(categories[0].title, "News")
        self.assertEqual(_IPTVHandler.handshake_count, 2)
        authorized = [
            x["authorization"] for x in _IPTVHandler.requests_seen
            if x["params"].get("action") == ["get_genres"]
        ]
        self.assertIn("Bearer local-stalker-token", authorized)
        self.assertIn("Bearer refreshed-stalker-token", authorized)

    def test_xtream_real_http_series_episode_flow(self):
        adapter = XtreamAdapter(self.base, "user name", "p@ss/word", timeout=2)
        self.assertTrue(adapter.connect())
        categories = adapter.categories("series")
        self.assertEqual([(x.id, x.title) for x in categories], [("9", "Shows")])
        shows = adapter.items("series", "9")
        self.assertEqual(len(shows), 1)
        self.assertEqual(shows[0].id, "300")
        episodes = adapter.series_episodes(shows[0])
        self.assertEqual(len(episodes), 1)
        self.assertEqual((episodes[0].season, episodes[0].episode), (1, 1))
        self.assertEqual(
            adapter.resolve_stream(episodes[0]),
            self.base + "/series/user%20name/p%40ss%2Fword/301.mkv",
        )

    def test_m3u_real_http_fetch_and_parse(self):
        adapter = M3UAdapter(self.base + "/playlist.m3u", timeout=2)
        self.assertTrue(adapter.connect())
        categories = adapter.categories("live")
        self.assertEqual(categories[0].title, "News")
        items = adapter.items("live", "News")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Local M3U")
        self.assertEqual(items[0].stream_url, "http://127.0.0.1/live/user/pass/900.ts")


if __name__ == "__main__":
    unittest.main()
