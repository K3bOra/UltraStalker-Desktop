import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication

from ultrastalker_desktop.core.models import Category, MediaItem, Profile
import ultrastalker_desktop.ui.bridge as bridge_mod


class FakeAdapter:
    def __init__(self):
        self.connected = False

    def connect(self):
        self.connected = True
        return True

    def categories(self, kind, cancelled=None):
        return [Category("1", "News", kind)]

    def items(self, kind, category_id="", cancelled=None):
        return [MediaItem("7", "EN| The Show (2020)", kind, category_id,
                          stream_url="http://secret.example/u/p/7.ts", command="ffmpeg http://secret.example/x",
                          poster="http://img.example/p.jpg", rating="75", raw={"number": "4", "token": "abc"})]

    def series_episodes(self, item, cancelled=None):
        return [MediaItem(f"e{s}{e}", f"Ep {e}", "episode", series_id=item.id, season=s, episode=e)
                for s in (2, 1) for e in (2, 1)]

    def short_epg(self, item, cancelled=None):
        return []

    def stream_candidates(self, item, cancelled=None):
        return ["http://secret.example/u/p/7.ts"]


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        patches = [
            patch.object(bridge_mod, "load_settings", return_value={}),
            patch.object(bridge_mod, "save_settings"),
            patch.object(bridge_mod, "load_profiles", return_value=[Profile("Home", "stalker", "http://p.example/c/", "00:1A:79:00:00:01")]),
            patch.object(bridge_mod, "save_profile"),
            patch.object(bridge_mod.db, "next_episode", return_value=set()),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.bridge = bridge_mod.Bridge(adapter_factory=lambda p: FakeAdapter(), workers=1)
        self.addCleanup(self.bridge.shutdown)

    def test_items_never_expose_stream_links_or_raw_provider_data(self):
        self.bridge.api_connect("Home")
        rows = self.bridge.api_items("movies", "1")
        text = json.dumps(rows)
        self.assertNotIn("secret.example", text)
        self.assertNotIn("token", text)
        self.assertEqual(rows[0]["rating"], "7.5")
        self.assertEqual(rows[0]["poster"], "http://img.example/p.jpg")
        self.assertIn("ref", rows[0])

    def test_profile_listing_masks_mac(self):
        rows = self.bridge.api_profiles()
        self.assertEqual(rows[0]["host"], "p.example")
        self.assertNotIn("00:01", rows[0]["mac"][:8] + rows[0]["mac"][9:14])
        self.assertTrue(rows[0]["mac"].endswith("01"))

    def test_profile_validation_messages(self):
        with self.assertRaises(bridge_mod.BridgeError):
            self.bridge._profile_from({"type": "stalker", "url": "http://x", "mac": "bad"})
        with self.assertRaises(bridge_mod.BridgeError):
            self.bridge._profile_from({"type": "xtream", "url": "http://x", "username": "u"})
        p = self.bridge._profile_from({"type": "m3u", "url": "http://x/list.m3u"})
        self.assertEqual(p.m3u_url, "http://x/list.m3u")

    def test_episodes_are_grouped_and_sorted(self):
        self.bridge.api_connect("Home")
        series = self.bridge.api_items("series", "1")[0]
        data = self.bridge.api_episodes(series["ref"])
        self.assertEqual([s["season"] for s in data["seasons"]], [1, 2])
        self.assertEqual([e["episode"] for e in data["seasons"][0]["episodes"]], [1, 2])
        self.assertEqual(data["next"], data["seasons"][0]["episodes"][0]["ref"])

    def test_unknown_ref_is_a_friendly_error(self):
        with self.assertRaises(bridge_mod.BridgeError):
            self.bridge.item("nope")

    def test_actions_require_a_connection(self):
        with self.assertRaises(bridge_mod.BridgeError):
            self.bridge.api_categories("live")

    def test_call_rejects_unknown_methods(self):
        out = []
        self.bridge.reply.connect(out.append)
        self.bridge.call(json.dumps({"id": 1, "method": "__init__", "args": []}))
        self.app.processEvents()
        self.assertTrue(out and json.loads(out[0])["ok"] is False)


if __name__ == "__main__":
    unittest.main()
