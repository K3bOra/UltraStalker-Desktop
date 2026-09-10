from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ultrastalker_desktop.core.adapters.cached import CachedAdapter
from ultrastalker_desktop.core.adapters.m3u import M3UAdapter
from ultrastalker_desktop.core.adapters.stalker import StalkerAdapter
from ultrastalker_desktop.core.adapters.xtream import XtreamAdapter
from ultrastalker_desktop.core.adapters.base import SourceAdapter
from ultrastalker_desktop.core.models import MediaItem
import ultrastalker_desktop.storage.database as db


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_app, self.old_db = db.APP_DIR, db.DB
        db.APP_DIR, db.DB = self.root, self.root / 'flow.db'

    def tearDown(self):
        db.APP_DIR, db.DB = self.old_app, self.old_db
        self.tmp.cleanup()

    def test_stalker_live_flow_categories_items_create_link(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        responses = [
            {'token': 'abc'},
            {'id': 'profile'},
            [{'id': '10', 'title': 'News'}],
            {'data': [{'id': '100', 'name': 'Channel', 'cmd': 'ffmpeg http://placeholder'}], 'total_items': 1},
            {'cmd': 'ffmpeg http://stream.example/live.ts'},
        ]
        a._get = Mock(side_effect=responses)
        self.assertTrue(a.connect())
        cats = a.categories('live')
        self.assertEqual(cats[0].title, 'News')
        items = a.items('live', cats[0].id)
        self.assertEqual(items[0].title, 'Channel')
        self.assertEqual(a.resolve_stream(items[0]), 'http://stream.example/live.ts')

    def test_xtream_series_episode_flow(self):
        a = XtreamAdapter('http://server', 'u', 'p')
        a._api = Mock(side_effect=[
            {'user_info': {'auth': 1}},
            [{'category_id': '7', 'category_name': 'Drama'}],
            [{'series_id': 55, 'name': 'Show'}],
            {'episodes': {'1': [{'id': 901, 'episode_num': 1, 'title': 'Pilot', 'container_extension': 'mkv'}]}},
        ])
        self.assertTrue(a.connect())
        cat = a.categories('series')[0]
        series = a.items('series', cat.id)[0]
        episode = a.series_episodes(series)[0]
        self.assertEqual(episode.season, 1)
        self.assertEqual(episode.episode, 1)
        self.assertEqual(a.resolve_stream(episode), 'http://server/series/u/p/901.mkv')

    def test_m3u_movies_series_cache_and_episode_flow(self):
        inner = M3UAdapter('x')
        inner._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="Movies",Film\nhttps://cdn.test/movie/u/p/7.mp4?token=one\n'
            '#EXTINF:-1 group-title="TV Shows",Show S01E02\nhttps://cdn.test/series/u/p/8.mkv?token=one'
        )
        a = CachedAdapter(inner, 'm3u-profile')
        movies = a.items('movies')
        series = a.items('series')
        self.assertEqual([x.title for x in movies], ['Film'])
        self.assertEqual([x.title for x in series], ['Show'])
        episodes = a.series_episodes(series[0])
        self.assertEqual([(x.season, x.episode) for x in episodes], [(1, 2)])
        self.assertEqual(a.resolve_stream(episodes[0]), 'https://cdn.test/series/u/p/8.mkv?token=one')

    def test_persisted_m3u_favorite_series_reopens_with_rotating_episode_url(self):
        old = M3UAdapter('x')
        old._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="ep-1" group-title="Series",Show S01E01\n'
            'https://cdn.test/series/u/p/1.mkv?token=old'
        )
        show = old.items('series')[0]
        db.toggle_favorite('P', show)
        persisted_show = db.favorites('P')[0]
        self.assertEqual(persisted_show.stream_url, '')
        self.assertEqual(persisted_show.command, '')

        fresh = M3UAdapter('x')
        fresh._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="ep-1" group-title="Series",Show S01E01\n'
            'https://cdn.test/series/u/p/1.mkv?token=new'
        )
        episode = fresh.series_episodes(persisted_show)[0]
        db.add_history('P', episode, 30, 1200)
        persisted_episode = db.history('P')[0][0]
        self.assertEqual(persisted_episode.stream_url, '')
        self.assertEqual(
            fresh.stream_candidates(persisted_episode),
            ['https://cdn.test/series/u/p/1.mkv?token=new'],
        )

    def test_persisted_m3u_mirrors_rehydrate_after_sqlite_round_trip(self):
        old = M3UAdapter('x')
        old._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="news-1" group-title="News",News\n'
            'https://one.test/live/news.ts?token=old-a\n'
            '#EXTINF:-1 tvg-id="news-1" group-title="News",News\n'
            'https://two.test/live/news.ts?token=old-b'
        )
        item = old.items('live')[0]
        self.assertEqual(len(item.raw.get('fallback_urls', [])), 1)
        db.toggle_favorite('P', item)

        persisted = db.favorites('P')[0]
        self.assertEqual(persisted.stream_url, '')
        self.assertNotIn('fallback_urls', persisted.raw or {})

        fresh = M3UAdapter('x')
        fresh._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="news-1" group-title="News",News\n'
            'https://one.test/live/news.ts?token=new-a\n'
            '#EXTINF:-1 tvg-id="news-1" group-title="News",News\n'
            'https://two.test/live/news.ts?token=new-b'
        )
        self.assertEqual(
            fresh.stream_candidates(persisted),
            [
                'https://one.test/live/news.ts?token=new-a',
                'https://two.test/live/news.ts?token=new-b',
            ],
        )

    def test_persisted_xtream_movie_and_episode_rebuild_current_stream_urls(self):
        adapter = XtreamAdapter('https://server.test/base', 'user name', 'p@ss/word')
        movie = MediaItem(
            '77', 'Film', 'movies', raw={'container_extension': 'mkv'}
        )
        episode = MediaItem(
            '88', 'Episode', 'episode', series_id='9', season=1, episode=2,
            raw={'container_extension': 'ts'},
        )
        db.toggle_favorite('P', movie)
        db.add_history('P', episode, 90, 1800)
        persisted_movie = db.favorites('P')[0]
        persisted_episode = db.history('P')[0][0]
        self.assertEqual(
            adapter.stream_candidates(persisted_movie),
            ['https://server.test/base/movie/user%20name/p%40ss%2Fword/77.mkv'],
        )
        self.assertEqual(
            adapter.stream_candidates(persisted_episode),
            ['https://server.test/base/series/user%20name/p%40ss%2Fword/88.ts'],
        )

    def test_persisted_stalker_live_and_movie_get_fresh_commands(self):
        adapter = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        adapter.token = 'token'
        old_live = MediaItem('7', 'Channel', 'live', command='ffmpeg http://old/live')
        old_movie = MediaItem('8', 'Film', 'movies', command='ffmpeg http://old/movie')
        db.toggle_favorite('P', old_live)
        db.toggle_favorite('P', old_movie)
        persisted = {item.kind: item for item in db.favorites('P')}
        self.assertTrue(all(not item.command for item in persisted.values()))

        fresh_live = MediaItem('7', 'Channel', 'live', command='ffmpeg http://placeholder/live')
        fresh_movie = MediaItem('8', 'Film', 'movies', command='ffmpeg http://placeholder/movie')
        adapter.items = Mock(side_effect=lambda kind, category_id='', cancelled=None: [fresh_live] if kind == 'live' else [fresh_movie])
        adapter._get = Mock(side_effect=[
            {'cmd': 'ffmpeg http://stream.test/live.ts?token=new'},
            {'cmd': 'ffmpeg http://stream.test/movie.mkv?token=new'},
        ])
        self.assertEqual(
            adapter.stream_candidates(persisted['live']),
            ['http://stream.test/live.ts?token=new'],
        )
        self.assertEqual(
            adapter.stream_candidates(persisted['movies']),
            ['http://stream.test/movie.mkv?token=new'],
        )

    def test_persisted_stalker_episode_rehydrates_from_series_before_create_link(self):
        adapter = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        adapter.token = 'token'
        old = MediaItem(
            '22', 'Episode 2', 'episode', command='ffmpeg http://old/episode',
            series_id='9', season=1, episode=2,
        )
        db.add_history('P', old, 120, 1800)
        persisted = db.history('P')[0][0]
        self.assertEqual(persisted.command, '')
        fresh = MediaItem(
            '22', 'Episode 2', 'episode', command='ffmpeg http://placeholder/episode',
            series_id='9', season=1, episode=2,
        )
        adapter.series_episodes = Mock(return_value=[fresh])
        adapter._get = Mock(return_value={'cmd': 'ffmpeg http://stream.test/e22.ts?token=fresh'})
        self.assertEqual(
            adapter.stream_candidates(persisted),
            ['http://stream.test/e22.ts?token=fresh'],
        )
        parent = adapter.series_episodes.call_args.args[0]
        self.assertEqual(parent.series_id, '9')

    def test_cache_round_trip_avoids_second_catalog_call(self):
        inner = Mock()
        inner.categories.return_value = []
        a = CachedAdapter(inner, 'profile')
        self.assertEqual(a.categories('live'), [])
        self.assertEqual(a.categories('live'), [])
        self.assertEqual(inner.categories.call_count, 1)


    def test_concurrent_cache_miss_coalesces_same_catalog_request(self):
        started = threading.Event()
        release = threading.Event()

        class Inner(SourceAdapter):
            def __init__(self):
                self.calls = 0
                self.guard = threading.Lock()
            def categories(self, kind, cancelled=None):
                with self.guard:
                    self.calls += 1
                started.set()
                self.assert_not_cancelled(cancelled)
                release.wait(2)
                return []
            def connect(self): return True
            def items(self, kind, category_id='', cancelled=None): return []
            def resolve_stream(self, item, cancelled=None): return ''
            @staticmethod
            def assert_not_cancelled(cancelled):
                if cancelled:
                    assert not cancelled()

        inner = Inner()
        adapter = CachedAdapter(inner, 'single-flight')
        results = []
        t1 = threading.Thread(target=lambda: results.append(adapter.categories('live')))
        t2 = threading.Thread(target=lambda: results.append(adapter.categories('live')))
        t1.start()
        self.assertTrue(started.wait(1))
        t2.start()
        time.sleep(0.08)
        self.assertEqual(inner.calls, 1)
        release.set()
        t1.join(2)
        t2.join(2)
        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())
        self.assertEqual(inner.calls, 1)
        self.assertEqual(results, [[], []])

    def test_cancelled_waiter_does_not_duplicate_inflight_catalog_request(self):
        started = threading.Event()
        release = threading.Event()
        cancelled = threading.Event()

        class Inner(SourceAdapter):
            def __init__(self): self.calls = 0
            def connect(self): return True
            def categories(self, kind, cancelled=None): return []
            def items(self, kind, category_id='', cancelled=None):
                self.calls += 1
                started.set()
                release.wait(2)
                return [MediaItem('1', 'One', kind)]
            def resolve_stream(self, item, cancelled=None): return ''

        inner = Inner()
        adapter = CachedAdapter(inner, 'cancel-flight')
        first = []
        second = []
        t1 = threading.Thread(target=lambda: first.extend(adapter.items('movies')))
        t1.start()
        self.assertTrue(started.wait(1))
        t2 = threading.Thread(
            target=lambda: second.extend(adapter.items('movies', cancelled=cancelled.is_set))
        )
        t2.start()
        time.sleep(0.08)
        cancelled.set()
        t2.join(1)
        self.assertFalse(t2.is_alive())
        self.assertEqual(second, [])
        self.assertEqual(inner.calls, 1)
        release.set()
        t1.join(2)
        self.assertFalse(t1.is_alive())

    def test_reconnect_during_inflight_fetch_cannot_repopulate_stale_cache(self):
        started = threading.Event()
        release = threading.Event()

        class Inner(SourceAdapter):
            def __init__(self):
                self.calls = 0
                self.connects = 0
            def connect(self):
                self.connects += 1
                return True
            def categories(self, kind, cancelled=None): return []
            def items(self, kind, category_id='', cancelled=None):
                self.calls += 1
                call = self.calls
                if call == 1:
                    started.set()
                    release.wait(2)
                return [MediaItem(str(call), f'Item {call}', kind)]
            def resolve_stream(self, item, cancelled=None): return ''

        inner = Inner()
        adapter = CachedAdapter(inner, 'generation')
        old_rows = []
        worker = threading.Thread(target=lambda: old_rows.extend(adapter.items('live')))
        worker.start()
        self.assertTrue(started.wait(1))
        adapter.connect()
        release.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(old_rows, [])
        self.assertIsNone(db.cache_get('generation:items:live:'))

        fresh = adapter.items('live')
        self.assertEqual([x.id for x in fresh], ['2'])
        self.assertEqual(inner.calls, 2)
        self.assertEqual(db.cache_get('generation:items:live:')[0]['id'], '2')

    def test_different_cache_keys_do_not_block_each_other(self):
        both_started = threading.Event()
        seen = set()
        guard = threading.Lock()
        release = threading.Event()

        class Inner(SourceAdapter):
            def connect(self): return True
            def categories(self, kind, cancelled=None):
                with guard:
                    seen.add(kind)
                    if len(seen) == 2:
                        both_started.set()
                release.wait(2)
                return []
            def items(self, kind, category_id='', cancelled=None): return []
            def resolve_stream(self, item, cancelled=None): return ''

        adapter = CachedAdapter(Inner(), 'parallel-keys')
        t1 = threading.Thread(target=lambda: adapter.categories('live'))
        t2 = threading.Thread(target=lambda: adapter.categories('movies'))
        t1.start(); t2.start()
        self.assertTrue(both_started.wait(1))
        release.set()
        t1.join(2); t2.join(2)
        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())


    def test_new_adapter_connect_invalidates_old_instance_inflight_cache_write(self):
        started = threading.Event()
        release = threading.Event()

        class Inner(SourceAdapter):
            def __init__(self, label):
                self.label = label
                self.calls = 0
            def connect(self): return True
            def categories(self, kind, cancelled=None): return []
            def items(self, kind, category_id='', cancelled=None):
                self.calls += 1
                if self.label == 'old':
                    started.set()
                    release.wait(2)
                return [MediaItem(self.label, self.label.title(), kind)]
            def resolve_stream(self, item, cancelled=None): return ''

        old_inner = Inner('old')
        new_inner = Inner('new')
        old = CachedAdapter(old_inner, 'shared-profile')
        old.connect()
        old_rows = []
        worker = threading.Thread(target=lambda: old_rows.extend(old.items('movies')))
        worker.start()
        self.assertTrue(started.wait(1))

        new = CachedAdapter(new_inner, 'shared-profile')
        new.connect()
        release.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(old_rows, [])
        self.assertIsNone(db.cache_get('shared-profile:items:movies:'))

        fresh = new.items('movies')
        self.assertEqual([x.id for x in fresh], ['new'])
        cached = db.cache_get('shared-profile:items:movies:')
        self.assertEqual(cached[0]['id'], 'new')

    def test_obsolete_adapter_started_after_new_connect_cannot_write_shared_cache(self):
        class Inner(SourceAdapter):
            def __init__(self, label): self.label = label
            def connect(self): return True
            def categories(self, kind, cancelled=None): return []
            def items(self, kind, category_id='', cancelled=None):
                return [MediaItem(self.label, self.label.title(), kind)]
            def resolve_stream(self, item, cancelled=None): return ''

        old = CachedAdapter(Inner('old'), 'shared-after')
        old.connect()
        new = CachedAdapter(Inner('new'), 'shared-after')
        new.connect()

        self.assertEqual(old.items('live'), [])
        self.assertIsNone(db.cache_get('shared-after:items:live:'))
        self.assertEqual([x.id for x in new.items('live')], ['new'])
        self.assertEqual(db.cache_get('shared-after:items:live:')[0]['id'], 'new')


    def test_cached_schema_mismatch_is_deleted_and_refetched(self):
        inner = Mock()
        inner.items.return_value = [MediaItem('fresh', 'Fresh', 'movies')]
        key = 'schema-cache:items:movies:'
        db.cache_set(key, [{'id': 'old', 'title': 'Old', 'kind': 'movies', 'future_field': 123}], 300)
        adapter = CachedAdapter(inner, 'schema-cache')

        rows = adapter.items('movies')
        self.assertEqual([x.id for x in rows], ['fresh'])
        self.assertEqual(inner.items.call_count, 1)
        self.assertEqual(db.cache_get(key)[0]['id'], 'fresh')

    def test_invalid_json_cache_row_is_removed_then_refetched(self):
        key = 'broken-json:categories:live'
        c = db.conn()
        c.execute('insert or replace into cache values(?,?,?)', (key, '{not-json', time.time() + 300))
        c.commit(); c.close()
        inner = Mock()
        inner.categories.return_value = []
        adapter = CachedAdapter(inner, 'broken-json')

        self.assertEqual(adapter.categories('live'), [])
        self.assertEqual(inner.categories.call_count, 1)
        self.assertEqual(db.cache_get(key), [])


    def test_episode_catalog_is_cached_without_transport_secrets(self):
        inner = Mock()
        inner.series_episodes.return_value = [MediaItem(
            'ep1', 'Episode 1', 'episode',
            stream_url='https://stream.test/ep1?token=secret',
            command='ffmpeg https://stream.test/ep1?token=secret',
            poster='https://img.test/e.jpg?token=secret',
            backdrop='https://img.test/safe.jpg',
            series_id='show1', season=1, episode=1,
            raw={'container_extension': 'mkv', 'token': 'secret'},
        )]
        adapter = CachedAdapter(inner, 'episode-cache')
        show = MediaItem('show1', 'Show', 'series', series_id='show1')

        first = adapter.series_episodes(show)
        second = adapter.series_episodes(show)
        self.assertEqual(first[0].id, 'ep1')
        self.assertEqual(second[0].id, 'ep1')
        self.assertEqual(inner.series_episodes.call_count, 1)

        cached = db.cache_get('episode-cache:episodes:show1')[0]
        self.assertEqual(cached['stream_url'], '')
        self.assertEqual(cached['command'], '')
        self.assertEqual(cached['poster'], '')
        self.assertEqual(cached['backdrop'], 'https://img.test/safe.jpg')
        self.assertEqual(cached['raw'], {'container_extension': 'mkv'})

    def test_concurrent_episode_cache_miss_is_single_flight(self):
        started = threading.Event()
        release = threading.Event()

        class Inner(SourceAdapter):
            def __init__(self): self.calls = 0
            def connect(self): return True
            def categories(self, kind, cancelled=None): return []
            def items(self, kind, category_id='', cancelled=None): return []
            def series_episodes(self, item, cancelled=None):
                self.calls += 1
                started.set()
                release.wait(2)
                return [MediaItem('e1', 'Episode', 'episode', series_id=item.id)]
            def resolve_stream(self, item, cancelled=None): return ''

        inner = Inner()
        adapter = CachedAdapter(inner, 'episode-flight')
        show = MediaItem('s1', 'Show', 'series', series_id='s1')
        out = []
        t1 = threading.Thread(target=lambda: out.append(adapter.series_episodes(show)))
        t2 = threading.Thread(target=lambda: out.append(adapter.series_episodes(show)))
        t1.start(); self.assertTrue(started.wait(1)); t2.start()
        time.sleep(0.08)
        self.assertEqual(inner.calls, 1)
        release.set(); t1.join(2); t2.join(2)
        self.assertEqual(inner.calls, 1)
        self.assertEqual([[x.id for x in rows] for rows in out], [['e1'], ['e1']])

    def test_history_resume_flow(self):
        item = MediaItem('33', 'Movie', 'movies')
        db.add_history('Profile', item, 0, 0)
        db.update_progress('Profile', item, 125, 1000)
        self.assertEqual(db.resume_point('Profile', item), (125.0, 1000.0))
        hist = db.history('Profile')
        self.assertEqual(hist[0][0].title, 'Movie')


    def test_reconnect_invalidates_profile_catalog_cache(self):
        class Inner(SourceAdapter):
            def __init__(self): self.calls=0; self.connects=0
            def connect(self): self.connects+=1; return True
            def categories(self,kind,cancelled=None): return []
            def items(self,kind,category_id='',cancelled=None):
                self.calls+=1
                return [MediaItem(str(self.calls), 'Item', kind)]
            def resolve_stream(self,item,cancelled=None): return ''

        inner=Inner();adapter=CachedAdapter(inner,'P')
        adapter.connect()
        self.assertEqual(adapter.items('live')[0].id,'1')
        self.assertEqual(adapter.items('live')[0].id,'1')
        self.assertEqual(inner.calls,1)
        adapter.connect()
        self.assertEqual(adapter.items('live')[0].id,'2')
        self.assertEqual(inner.calls,2)



    def test_catalog_cache_never_persists_stream_commands_or_signed_artwork(self):
        inner = Mock()
        inner.items.return_value = [MediaItem(
            '9', 'Cached', 'movies',
            stream_url='https://stream.test/9?token=secret',
            command='ffmpeg https://stream.test/9?token=secret',
            poster='https://img.test/p.jpg?token=secret',
            backdrop='https://img.test/b.jpg',
            raw={
                'stream_id': '9',
                'container_extension': 'mp4',
                'cmd': 'ffmpeg https://stream.test/9?token=secret',
                'token': 'secret',
            },
        )]
        a = CachedAdapter(inner, 'secure-cache')
        rows = a.items('movies')
        self.assertEqual(rows[0].title, 'Cached')
        cached = db.cache_get('secure-cache:items:movies:')[0]
        self.assertEqual(cached['stream_url'], '')
        self.assertEqual(cached['command'], '')
        self.assertEqual(cached['poster'], '')
        self.assertEqual(cached['backdrop'], 'https://img.test/b.jpg')
        self.assertNotIn('cmd', cached['raw'])
        self.assertNotIn('token', cached['raw'])
        self.assertEqual(cached['raw']['container_extension'], 'mp4')

if __name__ == '__main__':
    unittest.main()
