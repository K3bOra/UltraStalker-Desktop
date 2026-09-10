from __future__ import annotations

import tempfile
import time
import threading
import unittest
from pathlib import Path

from ultrastalker_desktop.core.artwork import ArtworkCache


PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64


class FakeResponse:
    def __init__(self, data=PNG, content_type="image/png", status=200):
        self.data = data
        self.headers = {"Content-Type": content_type}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http failure")

    def iter_content(self, size):
        for i in range(0, len(self.data), size):
            yield self.data[i:i + size]


class FakeHttp:
    def __init__(self, response=None):
        self.response = response or FakeResponse()
        self.calls = 0
        self.urls = []

    def get(self, url, **kwargs):
        self.calls += 1
        self.urls.append(url)
        return self.response


class ArtworkCacheTests(unittest.TestCase):
    def test_fetch_caches_by_hash_without_writing_url(self):
        with tempfile.TemporaryDirectory() as td:
            http = FakeHttp()
            cache = ArtworkCache(Path(td), http=http)
            secret_url = "https://img.test/poster.jpg?token=super-secret"
            self.assertEqual(cache.fetch(secret_url), PNG)
            self.assertEqual(cache.fetch(secret_url), PNG)
            self.assertEqual(http.calls, 1)
            names = [p.name for p in Path(td).glob("*.img")]
            self.assertEqual(len(names), 1)
            self.assertNotIn("token", names[0])
            self.assertNotIn("super-secret", names[0])

    def test_rejects_non_image_and_non_http_urls(self):
        with tempfile.TemporaryDirectory() as td:
            http = FakeHttp(FakeResponse(b"<html>nope</html>", "text/html"))
            cache = ArtworkCache(Path(td), http=http)
            self.assertIsNone(cache.fetch("file:///tmp/a.png"))
            self.assertIsNone(cache.fetch("https://img.test/a.png"))
            self.assertEqual(http.calls, 1)
            self.assertEqual(list(Path(td).glob("*.img")), [])

    def test_rejects_oversized_download(self):
        with tempfile.TemporaryDirectory() as td:
            # Constructor enforces a 256 KiB floor; exceed it deliberately.
            huge = b"\x89PNG\r\n\x1a\n" + b"x" * (300 * 1024)
            cache = ArtworkCache(Path(td), http=FakeHttp(FakeResponse(huge)), max_download_bytes=256 * 1024)
            self.assertIsNone(cache.fetch("https://img.test/huge.png"))
            self.assertEqual(list(Path(td).glob("*.img")), [])

    def test_prune_enforces_total_byte_budget_and_removes_stale_temp(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = ArtworkCache(
                root, http=FakeHttp(), max_download_bytes=256 * 1024,
                max_total_bytes=300 * 1024, max_files=50, ttl=3600,
            )
            root.mkdir(parents=True, exist_ok=True)
            now = time.time()
            for i in range(3):
                path = root / f"{i}.img"
                path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * (140 * 1024))
                __import__('os').utime(path, (now - 30 + i, now - 30 + i))
            tmp = root / 'orphan.tmp'
            tmp.write_bytes(b'x')
            __import__('os').utime(tmp, (now - 7200, now - 7200))

            cache._prune()
            remaining = list(root.glob('*.img'))
            self.assertEqual(len(remaining), 2)
            self.assertLessEqual(sum(x.stat().st_size for x in remaining), cache.max_total_bytes)
            self.assertFalse(tmp.exists())

    def test_expired_entry_refetches(self):
        with tempfile.TemporaryDirectory() as td:
            http = FakeHttp()
            cache = ArtworkCache(Path(td), http=http, ttl=60)
            url = "https://img.test/a.png"
            self.assertEqual(cache.fetch(url), PNG)
            path = next(Path(td).glob("*.img"))
            old = time.time() - 120
            __import__('os').utime(path, (old, old))
            self.assertEqual(cache.fetch(url), PNG)
            self.assertEqual(http.calls, 2)

    def test_different_urls_do_not_block_each_other_during_download(self):
        with tempfile.TemporaryDirectory() as td:
            first_started = threading.Event()
            release_first = threading.Event()
            second_started = threading.Event()

            class ParallelHttp:
                def get(self, url, **kwargs):
                    if url.endswith('one.png'):
                        first_started.set()
                        release_first.wait(1.0)
                    else:
                        second_started.set()
                    return FakeResponse()

            cache = ArtworkCache(Path(td), http=ParallelHttp())
            # Pick two URLs that map to different lock stripes.
            first = 'https://img.test/one.png'
            second = 'https://img.test/two.png'
            if cache._url_lock(first) is cache._url_lock(second):
                second = 'https://img.test/three.png'
            self.assertIsNot(cache._url_lock(first), cache._url_lock(second))

            results = {}
            t1 = threading.Thread(target=lambda: results.setdefault('one', cache.fetch(first)))
            t2 = threading.Thread(target=lambda: results.setdefault('two', cache.fetch(second)))
            t1.start()
            self.assertTrue(first_started.wait(0.5))
            t2.start()
            self.assertTrue(second_started.wait(0.5), 'second artwork was blocked by unrelated first download')
            release_first.set()
            t1.join(1.0); t2.join(1.0)
            self.assertEqual(results.get('one'), PNG)
            self.assertEqual(results.get('two'), PNG)

    def test_same_url_download_is_deduplicated_across_threads(self):
        with tempfile.TemporaryDirectory() as td:
            entered = threading.Event()
            release = threading.Event()
            calls = {'n': 0}

            class SlowHttp:
                def get(self, url, **kwargs):
                    calls['n'] += 1
                    entered.set()
                    release.wait(1.0)
                    return FakeResponse()

            cache = ArtworkCache(Path(td), http=SlowHttp())
            url = 'https://img.test/shared.png'
            out = []
            t1 = threading.Thread(target=lambda: out.append(cache.fetch(url)))
            t2 = threading.Thread(target=lambda: out.append(cache.fetch(url)))
            t1.start(); self.assertTrue(entered.wait(0.5)); t2.start()
            time.sleep(0.05)
            self.assertEqual(calls['n'], 1)
            release.set(); t1.join(1.0); t2.join(1.0)
            self.assertEqual(calls['n'], 1)
            self.assertEqual(out, [PNG, PNG])


if __name__ == "__main__":
    unittest.main()
