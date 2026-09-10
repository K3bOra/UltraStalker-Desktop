import tempfile
import unittest
import requests
from unittest.mock import Mock, patch

from ultrastalker_desktop.core.adapters.m3u import M3UAdapter
from ultrastalker_desktop.core.adapters.stalker import StalkerAdapter, StalkerError
from ultrastalker_desktop.core.adapters.xtream import XtreamAdapter
from ultrastalker_desktop.core.adapters.base import SourceAdapter
from ultrastalker_desktop.core.tmdb import TMDbClient
from ultrastalker_desktop.core.models import MediaItem,Profile,profile_identity, media_snapshot, safe_artwork_url
from ultrastalker_desktop.storage.database import media_key


class CoreTests(unittest.TestCase):
    def test_stream_candidate_resolution_stops_after_rehydrate_cancellation(self):
        state = {'cancelled': False, 'resolved': False}
        class A(SourceAdapter):
            def connect(self): return True
            def categories(self, kind, cancelled=None): return []
            def items(self, kind, category_id='', cancelled=None): return []
            def rehydrate_item(self, item, cancelled=None):
                state['cancelled'] = True
                return item
            def resolve_stream(self, item, cancelled=None):
                state['resolved'] = True
                return 'https://should-not-run.test/stream'
        rows = A().stream_candidates(
            MediaItem('1', 'A', 'live'),
            cancelled=lambda: state['cancelled'],
        )
        self.assertEqual(rows, [])
        self.assertFalse(state['resolved'])

    def test_stalker_does_not_create_link_after_playback_cancellation(self):
        adapter = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        adapter.token = 'token'
        item = MediaItem('7', 'Channel', 'live', command='ffmpeg http://placeholder/live')
        calls = {'n': 0}
        def cancelled():
            calls['n'] += 1
            return calls['n'] >= 2
        adapter._get = Mock(return_value={'cmd': 'ffmpeg http://should-not-run.test/live'})
        self.assertEqual(adapter.resolve_stream(item, cancelled=cancelled), '')
        adapter._get.assert_not_called()

    def test_stalker_rehydrate_honors_playback_cancellation(self):
        adapter = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        adapter.token = 'token'
        cancelled = Mock(return_value=True)
        adapter.items = Mock()
        persisted = MediaItem('7', 'Channel', 'live')
        self.assertIs(adapter.rehydrate_item(persisted, cancelled=cancelled), persisted)
        adapter.items.assert_not_called()

    def test_fallback_normalizes_mag_commands_and_deduplicates(self):
        class A(SourceAdapter):
            def connect(self): return True
            def categories(self, kind, cancelled=None): return []
            def items(self, kind, category_id='', cancelled=None): return []
            def resolve_stream(self, item, cancelled=None): return 'ffmpeg http://x/primary.ts'

        item = MediaItem('1', 'A', 'live', raw={
            'sources': [
                'ffrt http://x/fallback.ts',
                {'cmd': 'auto http://x/fallback.ts'},
                {'url': 'https://x/second.ts'},
            ]
        })
        self.assertEqual(
            A().stream_candidates(item),
            ['http://x/primary.ts', 'http://x/fallback.ts', 'https://x/second.ts'],
        )

    def test_m3u_parse(self):
        a = M3UAdapter('x')
        a._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="News" tvg-logo="a.png",Channel One\n'
            'http://x/1\n'
            '#EXTINF:-1 group-title="Sport",Match\n'
            'http://x/2'
        )
        self.assertEqual([c.title for c in a.categories('live')], ['News', 'Sport'])
        self.assertEqual(a.items('live', 'News')[0].stream_url, 'http://x/1')

    def test_m3u_classifies_xtream_style_paths(self):
        a = M3UAdapter('x')
        a._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="Mixed",News\nhttps://iptv.test/live/u/p/1.ts\n'
            '#EXTINF:-1 group-title="Mixed",Movie A\nhttps://iptv.test/movie/u/p/2.mp4\n'
            '#EXTINF:-1 group-title="Mixed",Show S01E02\nhttps://iptv.test/series/u/p/3.mkv'
        )
        self.assertEqual([x.title for x in a.items('live')], ['News'])
        self.assertEqual([x.title for x in a.items('movies')], ['Movie A'])
        self.assertEqual([x.title for x in a.items('series')], ['Show'])
        series = a.items('series')[0]
        episodes = a.series_episodes(series)
        self.assertEqual([(x.season, x.episode) for x in episodes], [(1, 2)])
        self.assertEqual(episodes[0].stream_url, 'https://iptv.test/series/u/p/3.mkv')

    def test_m3u_group_title_fallback_classifies_movies_and_series(self):
        a = M3UAdapter('x')
        a._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="Arabic Movies",Film A\nhttps://cdn.test/a.mp4\n'
            '#EXTINF:-1 group-title="مسلسلات رمضان",Drama S02E03\nhttps://cdn.test/b.mkv\n'
            '#EXTINF:-1 group-title="News",Channel\nhttps://cdn.test/c.m3u8'
        )
        self.assertEqual([c.title for c in a.categories('movies')], ['Arabic Movies'])
        self.assertEqual([c.title for c in a.categories('series')], ['مسلسلات رمضان'])
        self.assertEqual([x.title for x in a.items('movies')], ['Film A'])
        self.assertEqual([x.title for x in a.items('series')], ['Drama'])
        self.assertEqual([x.title for x in a.items('live')], ['Channel'])

    def test_m3u_series_groups_and_sorts_episode_patterns(self):
        a = M3UAdapter('x')
        a._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="TV Shows",My Show S02E01 - Two\nhttps://cdn.test/2-1.mkv\n'
            '#EXTINF:-1 group-title="TV Shows",My Show 1x03\nhttps://cdn.test/1-3.mkv\n'
            '#EXTINF:-1 group-title="TV Shows",My Show Season 1 Episode 2\nhttps://cdn.test/1-2.mkv'
        )
        rows = a.items('series')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].title, 'My Show')
        episodes = a.series_episodes(rows[0])
        self.assertEqual([(x.season, x.episode) for x in episodes], [(1, 2), (1, 3), (2, 1)])
        self.assertTrue(all(x.series_id == rows[0].id for x in episodes))

    def test_m3u_movie_and_episode_rehydrate_rotating_url(self):
        old = M3UAdapter('x')
        old._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="movie-7" group-title="Movies",Film\nhttps://cdn.test/movie/7.mp4?token=old\n'
            '#EXTINF:-1 tvg-id="ep-7" group-title="Series",Show S01E01\nhttps://cdn.test/series/7.mkv?token=old'
        )
        movie_old = old.items('movies')[0]
        episode_old = old.series_episodes(old.items('series')[0])[0]

        fresh = M3UAdapter('x')
        fresh._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="movie-7" group-title="Movies",Film\nhttps://cdn.test/movie/7.mp4?token=new\n'
            '#EXTINF:-1 tvg-id="ep-7" group-title="Series",Show S01E01\nhttps://cdn.test/series/7.mkv?token=new'
        )
        persisted_movie = MediaItem(movie_old.id, movie_old.title, 'movies', movie_old.category_id)
        persisted_episode = MediaItem(
            episode_old.id, episode_old.title, 'episode', episode_old.category_id,
            series_id=episode_old.series_id, season=1, episode=1,
        )
        self.assertEqual(fresh.resolve_stream(persisted_movie), 'https://cdn.test/movie/7.mp4?token=new')
        self.assertEqual(fresh.resolve_stream(persisted_episode), 'https://cdn.test/series/7.mkv?token=new')

    def test_m3u_persisted_series_survives_group_rename_when_title_is_unique(self):
        old = M3UAdapter('x')
        old._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="Old Series",Show S01E01\nhttps://cdn.test/series/u/p/1.mkv?token=old'
        )
        persisted = media_snapshot(old.items('series')[0], keep_safe_artwork=False)
        saved = MediaItem(**persisted)

        fresh = M3UAdapter('x')
        fresh._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="Arabic Series",Show S01E01\nhttps://cdn.test/series/u/p/1.mkv?token=new'
        )
        episodes = fresh.series_episodes(saved)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0].stream_url, 'https://cdn.test/series/u/p/1.mkv?token=new')

    def test_m3u_persisted_playable_survives_group_rename_only_when_unambiguous(self):
        old = M3UAdapter('x')
        old._parse('#EXTM3U\n#EXTINF:-1 group-title="Old News",Channel A\nhttps://cdn.test/live/a?token=old')
        current = old.items('live')[0]
        saved = MediaItem(**media_snapshot(current, keep_safe_artwork=False))

        fresh = M3UAdapter('x')
        fresh._parse('#EXTM3U\n#EXTINF:-1 group-title="New News",Channel A\nhttps://cdn.test/live/a?token=new')
        self.assertEqual(fresh.resolve_stream(saved), 'https://cdn.test/live/a?token=new')

        duplicate = M3UAdapter('x')
        duplicate._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="One",Channel A\nhttps://cdn.test/live/a1\n'
            '#EXTINF:-1 group-title="Two",Channel A\nhttps://cdn.test/live/a2'
        )
        self.assertEqual(duplicate.resolve_stream(saved), '')

    def test_m3u_persisted_episode_survives_group_rename_with_episode_metadata(self):
        old = M3UAdapter('x')
        old._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="Old Series",Show S02E03\nhttps://cdn.test/series/u/p/23.mkv?token=old'
        )
        episode = old.series_episodes(old.items('series')[0])[0]
        saved = MediaItem(**media_snapshot(episode, keep_safe_artwork=False))

        fresh = M3UAdapter('x')
        fresh._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="New Series",Show S02E03\nhttps://cdn.test/series/u/p/23.mkv?token=new'
        )
        self.assertEqual(fresh.resolve_stream(saved), 'https://cdn.test/series/u/p/23.mkv?token=new')

    def test_m3u_ids_are_stable_when_playlist_order_changes(self):
        first = M3UAdapter('x')
        first._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="News",A\nhttp://x/a\n'
            '#EXTINF:-1 group-title="News",B\nhttp://x/b'
        )
        second = M3UAdapter('x')
        second._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="News",NEW\nhttp://x/new\n'
            '#EXTINF:-1 group-title="News",B\nhttp://x/b\n'
            '#EXTINF:-1 group-title="News",A\nhttp://x/a'
        )
        ids1 = {x.title: x.id for x in first.items('live')}
        ids2 = {x.title: x.id for x in second.items('live')}
        self.assertEqual(ids1['A'], ids2['A'])
        self.assertEqual(ids1['B'], ids2['B'])
        self.assertNotIn('http://', ids1['A'])

    def test_m3u_can_rehydrate_persisted_item_without_stream_url(self):
        a = M3UAdapter('x')
        a._parse('#EXTM3U\n#EXTINF:-1 tvg-id="news-1" group-title="News",A\nhttp://x/a?token=current')
        current = a.items('live')[0]
        persisted = MediaItem(current.id, current.title, 'live', current.category_id, stream_url='')
        self.assertEqual(a.resolve_stream(persisted), 'http://x/a?token=current')

    def test_m3u_id_survives_rotating_stream_token(self):
        a = M3UAdapter('x')
        a._parse('#EXTM3U\n#EXTINF:-1 tvg-id="news-1" group-title="News",A\nhttp://x/a?token=old')
        old_id = a.items('live')[0].id
        a._parse('#EXTM3U\n#EXTINF:-1 tvg-id="news-1" group-title="News",A\nhttp://x/a?token=new')
        self.assertEqual(old_id, a.items('live')[0].id)

    def test_duplicate_m3u_tvg_id_entries_become_one_logical_item_with_fallback(self):
        a = M3UAdapter('x')
        a._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="dup" group-title="News",Same\nhttp://x/a?token=old-a\n'
            '#EXTINF:-1 tvg-id="dup" group-title="News",Same\nhttp://x/b?token=old-b'
        )
        rows = a.items('live')
        self.assertEqual(len(rows), 1)
        first_id = rows[0].id
        self.assertEqual(
            a.stream_candidates(rows[0]),
            ['http://x/a?token=old-a', 'http://x/b?token=old-b'],
        )
        a._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="dup" group-title="News",Same\nhttp://x/a?token=new-a\n'
            '#EXTINF:-1 tvg-id="dup" group-title="News",Same\nhttp://x/b?token=new-b'
        )
        self.assertEqual(a.items('live')[0].id, first_id)
        self.assertEqual(
            a.stream_candidates(a.items('live')[0]),
            ['http://x/a?token=new-a', 'http://x/b?token=new-b'],
        )

    def test_duplicate_m3u_labels_without_tvg_id_keep_distinct_paths(self):
        a = M3UAdapter('x')
        a._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 group-title="News",Same\nhttp://x/a\n'
            '#EXTINF:-1 group-title="News",Same\nhttp://x/b'
        )
        rows = a.items('live')
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({x.id for x in rows}), 2)

    def test_persisted_m3u_item_rehydrates_current_mirror_urls(self):
        a = M3UAdapter('x')
        a._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="news" group-title="News",Channel\nhttp://x/a?token=old\n'
            '#EXTINF:-1 tvg-id="news" group-title="News",Channel\nhttp://x/b?token=old'
        )
        persisted = MediaItem(**media_snapshot(a.items('live')[0]))
        self.assertEqual(persisted.stream_url, '')
        self.assertNotIn('fallback_urls', persisted.raw)
        a._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="news" group-title="News",Channel\nhttp://x/a?token=new\n'
            '#EXTINF:-1 tvg-id="news" group-title="News",Channel\nhttp://x/b?token=new'
        )
        self.assertEqual(
            a.stream_candidates(persisted),
            ['http://x/a?token=new', 'http://x/b?token=new'],
        )

    def test_stalker_network_error_does_not_echo_portal_url(self):
        a = StalkerAdapter('http://portal.test/secret-path', '00:1A:79:00:00:01')

        class R:
            status_code = 500
            def raise_for_status(self):
                err = requests.HTTPError('500 for url http://portal.test/secret-path/portal.php?token=secret')
                err.response = self
                raise err
            def json(self):
                return {}

        a.http.get = lambda *args, **kwargs: R()
        with self.assertRaises(Exception) as cm:
            a.connect()
        text = str(cm.exception)
        self.assertIn('HTTP 500', text)
        self.assertNotIn('secret-path', text)
        self.assertNotIn('token=secret', text)

    def test_stalker_headers_include_portal_referer(self):
        a = StalkerAdapter('http://portal.test/stalker_portal/c/', '00:1A:79:00:00:01')
        headers = a._headers()
        self.assertEqual(headers['Referer'], 'http://portal.test/stalker_portal/c/')
        self.assertEqual(headers['Connection'], 'Keep-Alive')

    def test_stalker_falls_back_to_form_post_when_get_is_not_json(self):
        a = StalkerAdapter('http://portal.test/portal.php', '00:1A:79:00:00:01')

        class BadJsonResponse:
            status_code = 200
            def raise_for_status(self): return None
            def json(self): raise ValueError('not json')

        class GoodResponse:
            status_code = 200
            def raise_for_status(self): return None
            def json(self): return {'js': {'token': 'abc'}}

        a.http.get = Mock(return_value=BadJsonResponse())
        a.http.post = Mock(return_value=GoodResponse())
        data = a._get({'type':'stb','action':'handshake','JsHttpRequest':'1-xml'}, allow_unauth=True)
        self.assertEqual(data['token'], 'abc')
        a.http.post.assert_called_once()
        self.assertEqual(a.endpoint, 'http://portal.test/portal.php')

    def test_stalker_normalizes_direct_portal_endpoint(self):
        a = StalkerAdapter('http://portal.test/portal.php', '00:1A:79:00:00:01')
        self.assertEqual(a.endpoint, 'http://portal.test/portal.php')
        self.assertEqual(a.base, 'http://portal.test')
        self.assertEqual(a._candidates()[0], 'http://portal.test/portal.php')

    def test_stalker_normalizes_mag_c_portal_url(self):
        a = StalkerAdapter('http://portal.test/stalker_portal/c/', '00:1A:79:00:00:01')
        self.assertEqual(a.base, 'http://portal.test/stalker_portal')
        self.assertEqual(a._candidates()[0], 'http://portal.test/stalker_portal/server/load.php')

    def test_stalker_connection_failure_does_not_repeat_paths_on_dead_host(self):
        a = StalkerAdapter('http://portal.test', '00:1A:79:00:00:01')
        import requests
        a.http.get = Mock(side_effect=requests.ConnectionError('host unavailable'))
        a.http.post = Mock()
        with self.assertRaises(StalkerError):
            a._get({'type':'stb','action':'handshake'}, allow_unauth=True)
        a.http.get.assert_called_once()
        a.http.post.assert_not_called()

    def test_stalker_ssl_failure_does_not_repeat_paths_on_same_host(self):
        a = StalkerAdapter('https://portal.test', '00:1A:79:00:00:01')
        a.http.get = Mock(side_effect=requests.exceptions.SSLError('certificate failure'))
        with self.assertRaises(StalkerError):
            a._get({'type':'stb','action':'handshake'}, allow_unauth=True)
        a.http.get.assert_called_once()

    def test_stalker_post_transport_failure_after_reachable_get_tries_next_endpoint(self):
        a = StalkerAdapter('http://portal.test', '00:1A:79:00:00:01')
        class BadJsonResponse:
            status_code=200
            def raise_for_status(self): return None
            def json(self): raise ValueError('not json')
        class GoodResponse:
            status_code=200
            def raise_for_status(self): return None
            def json(self): return {'js': {'token':'ok'}}
        a.http.get = Mock(side_effect=[BadJsonResponse(), GoodResponse()])
        a.http.post = Mock(side_effect=requests.ConnectionError('post reset'))
        data=a._get({'type':'stb','action':'handshake'}, allow_unauth=True)
        self.assertEqual(data['token'],'ok')
        self.assertEqual(a.http.get.call_count,2)
        a.http.post.assert_called_once()

    def test_stalker_http_path_failure_still_tries_next_endpoint(self):
        a = StalkerAdapter('http://portal.test', '00:1A:79:00:00:01')
        class Response:
            def __init__(self,status,payload=None): self.status_code=status; self.payload=payload or {}
            def raise_for_status(self):
                if self.status_code >= 400:
                    import requests
                    raise requests.HTTPError(str(self.status_code))
            def json(self): return self.payload
        a.http.get = Mock(side_effect=[Response(404), Response(200, {'js': {'token':'ok'}})])
        data=a._get({'type':'stb','action':'handshake'}, allow_unauth=True)
        self.assertEqual(data['token'],'ok')
        self.assertEqual(a.http.get.call_count,2)
        self.assertTrue(a.endpoint.endswith('/server/load.php'))

    def test_stalker_create_link(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._get = Mock(return_value={'cmd': 'ffmpeg http://stream/live.ts'})
        x = MediaItem('1', 'A', 'live', command='ffmpeg http://placeholder')
        self.assertEqual(a.resolve_stream(x), 'http://stream/live.ts')

    def test_stalker_direct_url(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        x = MediaItem('1', 'A', 'live', stream_url='http://direct')
        self.assertEqual(a.resolve_stream(x), 'http://direct')

    def test_stalker_rehydrates_persisted_live_item_before_create_link(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        fresh = MediaItem('7', 'Channel', 'live', command='ffmpeg http://placeholder/7')
        a.items = Mock(return_value=[fresh])
        a._get = Mock(return_value={'cmd': 'ffmpeg http://stream/current.ts?token=fresh'})
        persisted = MediaItem('7', 'Channel', 'live', command='', stream_url='')
        self.assertEqual(a.resolve_stream(persisted), 'http://stream/current.ts?token=fresh')
        a.items.assert_called_once_with('live', '', cancelled=None)

    def test_stalker_rehydrates_persisted_episode_by_series_and_episode_id(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        fresh = MediaItem('22', 'Episode 2', 'episode', command='ffmpeg http://placeholder/e22', series_id='9', season=1, episode=2)
        a.series_episodes = Mock(return_value=[fresh])
        a._get = Mock(return_value={'cmd': 'ffmpeg http://stream/episode.ts'})
        persisted = MediaItem('22', 'Episode 2', 'episode', series_id='9', season=1, episode=2)
        self.assertEqual(a.resolve_stream(persisted), 'http://stream/episode.ts')
        self.assertEqual(a.series_episodes.call_args.args[0].series_id, '9')

    def test_stalker_rehydrates_numbered_episode_before_duplicate_provider_id(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        first = MediaItem('container-9', 'Episode 1', 'episode', command='cmd-one', series_id='9', season=1, episode=1)
        second = MediaItem('container-9', 'Episode 2', 'episode', command='cmd-two', series_id='9', season=1, episode=2)
        a.series_episodes = Mock(return_value=[first, second])
        a._get = Mock(return_value={'cmd': 'ffmpeg http://stream/episode-2.ts'})
        persisted = MediaItem('container-9', 'Episode 2', 'episode', series_id='9', season=1, episode=2)
        self.assertEqual(a.resolve_stream(persisted), 'http://stream/episode-2.ts')
        request = a._get.call_args.args[0]
        self.assertEqual(request['cmd'], 'cmd-two')
        self.assertEqual(request['series'], '2')

    def test_xtream_normalizes_direct_player_api_endpoint(self):
        a = XtreamAdapter('https://SERVER.test/sub/player_api.php', 'u', 'p')
        self.assertEqual(a.base, 'https://SERVER.test/sub')
        self.assertEqual(a.resolve_stream(MediaItem('1', 'A', 'live')), 'https://SERVER.test/sub/live/u/p/1.ts')

    def test_stalker_candidates_do_not_duplicate_stalker_portal_path(self):
        a = StalkerAdapter('https://portal.test/stalker_portal/c/', '00:1A:79:00:00:01')
        candidates = a._candidates()
        self.assertNotIn('https://portal.test/stalker_portal/stalker_portal/server/load.php', candidates)
        self.assertIn('https://portal.test/stalker_portal/server/load.php', candidates)


    def test_xtream_network_error_does_not_echo_credentials(self):
        a = XtreamAdapter('http://server', 'user', 'supersecret')

        class R:
            status_code = 401
            def raise_for_status(self):
                err = requests.HTTPError('401 for url http://server/player_api.php?username=user&password=supersecret')
                err.response = self
                raise err
            def json(self):
                return {}

        a.http.get = lambda *args, **kwargs: R()
        with self.assertRaises(RuntimeError) as cm:
            a.connect()
        text = str(cm.exception)
        self.assertIn('HTTP 401', text)
        self.assertNotIn('supersecret', text)
        self.assertNotIn('player_api.php', text)

    def test_xtream_stream_urls_encode_reserved_credentials(self):
        x = XtreamAdapter('http://example.test', 'user/name', 'p@ss word')
        live = MediaItem('10', 'Live', 'live', raw={'container_extension': 'ts'})
        self.assertEqual(
            x.resolve_stream(live),
            'http://example.test/live/user%2Fname/p%40ss%20word/10.ts',
        )

    def test_stalker_pagination(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._get = Mock(side_effect=[
            {'data': [{'id': '1', 'name': 'A'}, {'id': '2', 'name': 'B'}], 'total_items': 3},
            {'data': [{'id': '3', 'name': 'C'}], 'total_items': 3},
        ])
        rows = a._ordered_pages('itv')
        self.assertEqual([x['id'] for x in rows], ['1', '2', '3'])
        self.assertEqual([c.args[0]['p'] for c in a._get.call_args_list], ['0', '1'])

    def test_stalker_pagination_tolerates_zero_and_one_aliasing_first_page(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._get = Mock(side_effect=[
            {'data': [{'id': '1', 'name': 'A'}], 'total_items': 2},
            {'data': [{'id': '1', 'name': 'A'}], 'total_items': 2},
            {'data': [{'id': '2', 'name': 'B'}], 'total_items': 2},
        ])
        rows = a._ordered_pages('itv')
        self.assertEqual([x['id'] for x in rows], ['1', '2'])
        self.assertEqual([c.args[0]['p'] for c in a._get.call_args_list], ['0', '1', '2'])

    def test_stalker_pagination_falls_back_when_zero_page_is_rejected(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._get = Mock(side_effect=[
            RuntimeError('p=0 unsupported'),
            {'data': [{'id': '1', 'name': 'A'}], 'total_items': 1},
        ])
        rows = a._ordered_pages('itv')
        self.assertEqual([x['id'] for x in rows], ['1'])
        self.assertEqual([c.args[0]['p'] for c in a._get.call_args_list], ['0', '1'])

    def test_stalker_all_live_prefers_get_all_channels(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._get = Mock(return_value={'data':[
            {'id':'1','name':'One'}, {'id':'2','name':'Two'}
        ]})
        a._ordered_pages = Mock(side_effect=AssertionError('pagination should not run'))
        rows = a.items('live', '')
        self.assertEqual([x.id for x in rows], ['1','2'])
        self.assertEqual(a._get.call_args.args[0]['action'], 'get_all_channels')
        a._ordered_pages.assert_not_called()

    def test_stalker_all_live_falls_back_when_get_all_channels_is_missing(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._get = Mock(side_effect=RuntimeError('unsupported'))
        a._ordered_pages = Mock(return_value=[{'id':'1','name':'One'}])
        rows = a.items('live', '')
        self.assertEqual([x.id for x in rows], ['1'])
        a._ordered_pages.assert_called_once_with('itv', {}, cancelled=None)

    def test_stalker_uses_category_for_vod_and_genre_for_live(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        captured = []
        def fake_pages(typ, extra=None, **_kwargs):
            captured.append((typ, dict(extra or {})))
            return [{'id': '1', 'name': 'Item'}]
        a._ordered_pages = fake_pages
        a.items('live', '10')
        a.items('movies', '20')
        a.items('series', '30')
        self.assertEqual(captured, [
            ('itv', {'genre': '10'}),
            ('vod', {'category': '20'}),
            ('series', {'category': '30'}),
        ])

    def test_stalker_pagination_honors_cancellation_between_pages(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        calls = {'count': 0}

        def get(_params):
            calls['count'] += 1
            return {'data': [{'id': str(calls['count']), 'name': 'Item'}]}

        a._get = get
        rows = a._ordered_pages(
            'itv',
            max_pages=200,
            cancelled=lambda: calls['count'] >= 1,
        )
        self.assertEqual(calls['count'], 1)
        self.assertEqual(rows, [])

    def test_stalker_pagination_stops_on_repeat(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._get = Mock(side_effect=[
            {'data': [{'id': '1', 'name': 'A'}]},
            {'data': [{'id': '1', 'name': 'A'}]},
            {'data': [{'id': '1', 'name': 'A'}]},
        ])
        rows = a._ordered_pages('itv')
        self.assertEqual(len(rows), 1)
        self.assertEqual(a._get.call_count, 3)

    def test_xtream_urls(self):
        a = XtreamAdapter('http://server', 'u', 'p')
        x = MediaItem('12', 'A', 'live', raw={'container_extension': 'ts'})
        self.assertEqual(a.resolve_stream(x), 'http://server/live/u/p/12.ts')

    def test_media_keys_do_not_collide(self):
        live = MediaItem('12', 'Live', 'live')
        movie = MediaItem('12', 'Movie', 'movies')
        ep1 = MediaItem('1', 'Episode 1', 'episode', series_id='99')
        ep2 = MediaItem('1', 'Episode 1', 'episode', series_id='100')
        self.assertEqual(len({media_key(live), media_key(movie), media_key(ep1), media_key(ep2)}), 4)

    def test_profile_identity_changes_with_source_not_display_name(self):
        a = Profile('Home', 'xtream', 'http://one', '', 'user', 'secret-a', '')
        b = Profile('Home', 'xtream', 'http://two', '', 'user', 'secret-b', '')
        c = Profile('Renamed', 'xtream', 'http://one', '', 'user', 'different-secret', '')
        self.assertNotEqual(profile_identity(a), profile_identity(b))
        self.assertEqual(profile_identity(a), profile_identity(c))
        self.assertNotIn('secret', profile_identity(a))

    def test_profile_identity_normalizes_equivalent_stalker_entrypoints(self):
        mac = '00:1A:79:00:00:01'
        a = Profile('A', 'stalker', 'https://PORTAL.test/stalker_portal/c/', mac)
        b = Profile('B', 'stalker', 'https://portal.test/stalker_portal/portal.php', mac)
        c = Profile('C', 'stalker', 'https://portal.test/stalker_portal/server/load.php', mac)
        self.assertEqual(profile_identity(a), profile_identity(b))
        self.assertEqual(profile_identity(b), profile_identity(c))

    def test_profile_identity_m3u_ignores_rotating_secret_query_values(self):
        a = Profile('A', 'm3u', m3u_url='https://iptv.test/get.php?username=u&password=old&type=m3u_plus&token=one')
        b = Profile('B', 'm3u', m3u_url='https://iptv.test/get.php?token=two&type=m3u_plus&password=new&username=u')
        c = Profile('C', 'm3u', m3u_url='https://iptv.test/get.php?username=other&password=new&type=m3u_plus')
        self.assertEqual(profile_identity(a), profile_identity(b))
        self.assertNotEqual(profile_identity(a), profile_identity(c))

    def test_m3u_connect_rejects_non_playlist_response(self):
        a = M3UAdapter('https://example.test/list.m3u')
        response = Mock()
        response.raise_for_status.return_value = None
        response.text = '<html><body>Access denied</body></html>'
        a.http.get = Mock(return_value=response)
        with self.assertRaises(RuntimeError) as cm:
            a.connect()
        self.assertIn('no playable entries', str(cm.exception).lower())

    def test_m3u_supports_bare_url_playlist(self):
        a = M3UAdapter('x')
        a._parse('#EXTM3U\nhttps://stream.test/one.ts\nhttps://stream.test/two.ts')
        rows = a.items('live')
        self.assertEqual([x.title for x in rows], ['Stream 1', 'Stream 2'])
        self.assertEqual([x.category_id for x in rows], ['Other', 'Other'])

    def test_stalker_series_categories_fall_back_to_vod_categories(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        def fake_get(params, *args, **kwargs):
            if params.get('type') == 'series':
                raise RuntimeError('series api unsupported')
            return {'data': [{'id': '10', 'title': 'Drama'}]}
        a._get = Mock(side_effect=fake_get)
        rows = a.categories('series')
        self.assertEqual([(x.id, x.title, x.kind) for x in rows], [('10', 'Drama', 'series')])

    def test_stalker_empty_category_success_is_not_overridden_by_prior_error(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._get = Mock(side_effect=[RuntimeError('first action failed'), {'data': []}])
        self.assertEqual(a.categories('movies'), [])

    def test_stalker_series_items_fall_back_when_dedicated_api_raises(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        def fake_pages(typ, extra=None, **kwargs):
            if typ == 'series':
                raise RuntimeError('series api unsupported')
            return [
                {'id': 'movie-1', 'name': 'Movie', 'is_series': '0'},
                {'id': 'show-1', 'name': 'Show', 'is_series': '1'},
            ]
        a._ordered_pages = Mock(side_effect=fake_pages)
        rows = a.items('series')
        self.assertEqual([x.id for x in rows], ['show-1'])

    def test_stalker_series_falls_back_to_vod_is_series_rows(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        calls = []
        def fake_pages(typ, extra=None, **_kwargs):
            calls.append((typ, dict(extra or {})))
            if typ == 'series':
                return []
            return [
                {'id': 'movie-1', 'name': 'Movie', 'is_series': '0'},
                {'id': 'show-1', 'name': 'Show', 'is_series': '1'},
            ]
        a._ordered_pages = fake_pages
        rows = a.items('series', '')
        self.assertEqual([x.id for x in rows], ['show-1'])
        self.assertEqual(calls[0][0], 'series')
        self.assertEqual(calls[1][0], 'vod')

    def test_stalker_movies_exclude_vod_backed_series_rows(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._ordered_pages = Mock(return_value=[
            {'id': 'movie-1', 'name': 'Movie', 'is_series': '0'},
            {'id': 'show-1', 'name': 'Show', 'is_series': '1'},
            {'id': 'legacy-1', 'name': 'Legacy Movie'},
        ])
        rows = a.items('movies', '')
        self.assertEqual([x.id for x in rows], ['movie-1', 'legacy-1'])

    def test_stalker_episode_create_link_passes_episode_number_as_series(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._get = Mock(return_value={'cmd': 'ffmpeg http://stream/episode.ts'})
        ep = MediaItem('22', 'Episode 2', 'episode', command='/media/file_22.mpg', series_id='9', season=1, episode=2)
        self.assertEqual(a.resolve_stream(ep), 'http://stream/episode.ts')
        self.assertEqual(a._get.call_args.args[0]['series'], '2')
        self.assertEqual(a._get.call_args.args[0]['type'], 'vod')

    def test_stalker_embedded_series_episodes_do_not_hit_network(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        item = MediaItem('9', 'Show', 'series', series_id='9', raw={
            'series': [
                {'season_number': 1, 'episodes': [
                    {'id': 'e1', 'name': 'Pilot', 'cmd': '/media/e1', 'episode': 1},
                    {'id': 'e2', 'name': 'Second', 'cmd': '/media/e2', 'episode': 2},
                ]}
            ]
        })
        a._ordered_pages = Mock(side_effect=AssertionError('network should not be used'))
        rows = a.series_episodes(item)
        self.assertEqual([(x.id, x.season, x.episode) for x in rows], [('e1', 1, 1), ('e2', 1, 2)])
        a._ordered_pages.assert_not_called()

    def test_stalker_vod_backed_series_expands_season_shells(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        def pages(typ, extra=None, **_kwargs):
            extra=dict(extra or {})
            if typ == 'series': return []
            if extra == {'series_id':'9'}: return []
            if extra.get('movie_id') == '9' and extra.get('season_id') == '0':
                return [
                    {'id':'season-a','name':'Season 1','is_season':'1','season_number':'1'},
                    {'id':'season-b','name':'Season 2','is_season':'1','season_number':'2'},
                ]
            if extra.get('season_id') == 'season-a':
                return [{'id':'e1','name':'Episode 1','cmd':'/media/e1','series_number':'1'}]
            if extra.get('season_id') == 'season-b':
                return [{'id':'e2','name':'Episode 1','cmd':'/media/e2','series_number':'1'}]
            return []
        a._ordered_pages = Mock(side_effect=pages)
        rows = a.series_episodes(MediaItem('9','Show','series',series_id='9'))
        self.assertEqual([(x.id,x.season,x.episode) for x in rows], [('e1',1,1),('e2',2,1)])

    def test_stalker_series_raises_when_all_protocol_attempts_fail(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._ordered_pages = Mock(side_effect=RuntimeError('network unavailable'))
        with self.assertRaisesRegex(RuntimeError, 'network unavailable'):
            a.series_episodes(MediaItem('9', 'Show', 'series', series_id='9'))
        self.assertEqual(a._ordered_pages.call_count, 3)

    def test_stalker_series_empty_success_is_not_reported_as_network_failure(self):
        a = StalkerAdapter('http://portal', '00:1A:79:00:00:01')
        a.token = 't'
        a._ordered_pages = Mock(side_effect=[[], RuntimeError('fallback failed'), []])
        self.assertEqual(a.series_episodes(MediaItem('9', 'Show', 'series', series_id='9')), [])


    def test_stalker_refreshes_expired_token_once(self):
        a = StalkerAdapter('http://portal.test', '00:1A:79:00:00:01')
        a.endpoint = 'http://portal.test/portal.php'
        a.token = 'old'

        class R:
            def __init__(self, status, payload=None):
                self.status_code = status; self.payload = payload or {}
            def raise_for_status(self):
                if self.status_code >= 400:
                    import requests
                    raise requests.HTTPError(str(self.status_code))
            def json(self): return self.payload

        calls = [R(401), R(200, {'js': {'data': [{'id':'1'}]}})]
        a.http.get = lambda *args, **kwargs: calls.pop(0)
        def reconnect():
            a.token = 'new'
            return True
        a.connect = reconnect
        data = a._get({'type':'itv','action':'get_ordered_list'})
        self.assertEqual(data['data'][0]['id'], '1')
        self.assertEqual(a.token, 'new')


    def test_media_snapshot_removes_transport_and_signed_artwork(self):
        item = MediaItem(
            '7', 'Movie', 'movies',
            stream_url='http://user:pass@stream.test/movie/7?token=secret',
            command='ffmpeg http://stream.test/7?token=secret',
            poster='https://img.test/poster.jpg?token=secret',
            raw={
                'stream_id': 7,
                'container_extension': 'mp4',
                'cmd': 'ffmpeg http://stream.test/7?token=secret',
                'token': 'secret',
            },
            backdrop='https://img.test/backdrop.jpg',
        )
        snap = media_snapshot(item, keep_safe_artwork=True)
        self.assertEqual(snap['stream_url'], '')
        self.assertEqual(snap['command'], '')
        self.assertEqual(snap['poster'], '')
        self.assertEqual(snap['backdrop'], 'https://img.test/backdrop.jpg')
        self.assertEqual(snap['raw'], {'stream_id': 7, 'container_extension': 'mp4'})

    def test_safe_artwork_url_rejects_userinfo_and_query_secrets(self):
        self.assertEqual(safe_artwork_url('https://img.test/a.jpg'), 'https://img.test/a.jpg')
        self.assertEqual(safe_artwork_url('https://u:p@img.test/a.jpg'), '')
        self.assertEqual(safe_artwork_url('https://img.test/a.jpg?sig=abc'), '')
        self.assertEqual(safe_artwork_url('file:///tmp/a.jpg'), '')

    def test_xtream_skips_malformed_catalog_rows_without_losing_valid_items(self):
        x = XtreamAdapter('http://server', 'u', 'p')
        x._api = Mock(return_value=[
            None,
            {'name': 'Missing id'},
            {'stream_id': 7, 'name': ''},
            {'stream_id': 8, 'name': 'Valid', 'container_extension': 'ts'},
        ])
        rows = x.items('live')
        self.assertEqual([(row.id, row.title) for row in rows], [('8', 'Valid')])
        self.assertEqual(x.resolve_stream(rows[0]), 'http://server/live/u/p/8.ts')

    def test_xtream_skips_malformed_episode_rows_without_broken_urls(self):
        x = XtreamAdapter('http://server', 'u', 'p')
        x._api = Mock(return_value={
            'episodes': {
                '1': [
                    None,
                    {'title': 'Missing id'},
                    {'id': 11, 'episode_num': 1, 'title': 'Valid', 'container_extension': 'mkv'},
                ]
            }
        })
        show = MediaItem('5', 'Show', 'series', series_id='5')
        rows = x.series_episodes(show)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].id, '11')
        self.assertEqual(x.resolve_stream(rows[0]), 'http://server/series/u/p/11.mkv')

    def test_xtream_accepts_flat_episode_list_with_row_seasons(self):
        x = XtreamAdapter('http://server', 'u', 'p')
        x._api = Mock(return_value={
            'episodes': [
                {'id': 21, 'season': 2, 'episode_num': 3, 'title': 'Episode 3'},
                {'id': 22, 'season': '2', 'episode_num': 4, 'title': 'Episode 4', 'info': 'bad-info'},
            ]
        })
        show = MediaItem('5', 'Show', 'series', series_id='5')
        rows = x.series_episodes(show)
        self.assertEqual([(r.id, r.season, r.episode) for r in rows], [('21', 2, 3), ('22', 2, 4)])

    def test_xtream_catalog_loop_honors_cancellation(self):
        x = XtreamAdapter('http://server', 'u', 'p')
        x._api = Mock(return_value=[{'stream_id': 1, 'name': 'One'}, {'stream_id': 2, 'name': 'Two'}])
        calls = {'n': 0}
        def cancelled():
            calls['n'] += 1
            return calls['n'] >= 3
        self.assertEqual(x.items('live', cancelled=cancelled), [])

    def test_xtream_accepts_list_backdrop_metadata(self):
        x = __import__('ultrastalker_desktop.core.adapters.xtream', fromlist=['XtreamAdapter']).XtreamAdapter('http://server', 'u', 'p')
        x._api = __import__('unittest.mock', fromlist=['Mock']).Mock(return_value=[{
            'series_id': 55,
            'name': 'Show',
            'cover': 'https://img.test/poster.jpg',
            'backdrop_path': ['', 'https://img.test/backdrop.jpg'],
        }])
        item = x.items('series')[0]
        self.assertEqual(item.poster, 'https://img.test/poster.jpg')
        self.assertEqual(item.backdrop, 'https://img.test/backdrop.jpg')
    def test_source_fallback_uses_rehydrated_item_without_persisting_urls(self):
        class RehydratingAdapter(SourceAdapter):
            def connect(self): return True
            def categories(self, kind, cancelled=None): return []
            def items(self, kind, category_id='', cancelled=None): return []
            def resolve_stream(self, item, cancelled=None): return item.stream_url
            def rehydrate_item(self, item, cancelled=None):
                return MediaItem(
                    item.id, item.title, item.kind,
                    stream_url='https://primary.test/stream',
                    raw={'fallback_urls': [
                        'https://backup1.test/stream?token=fresh',
                        {'url': 'https://backup2.test/stream'},
                    ]},
                )

        persisted = MediaItem('42', 'Channel', 'live')
        urls = RehydratingAdapter().stream_candidates(persisted)
        self.assertEqual(urls, [
            'https://primary.test/stream',
            'https://backup1.test/stream?token=fresh',
            'https://backup2.test/stream',
        ])
        self.assertEqual(persisted.stream_url, '')
        self.assertEqual(persisted.raw, {})




class TMDbCacheTests(unittest.TestCase):
    def test_negative_result_is_cached_without_second_http_request(self):
        client = TMDbClient('test-key')
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {'results': []}
        client.http = Mock()
        client.http.get.return_value = response
        cache = {}
        with patch('ultrastalker_desktop.core.tmdb.cache_get', side_effect=lambda k: cache.get(k)), \
             patch('ultrastalker_desktop.core.tmdb.cache_set', side_effect=lambda k, v, ttl: cache.__setitem__(k, v)):
            self.assertIsNone(client.search('No Such Movie', 'movies', '2026'))
            self.assertIsNone(client.search('No Such Movie', 'movies', '2026'))
        client.http.get.assert_called_once()
        stored = next(iter(cache.values()))
        self.assertTrue(stored.get('_ultrastalker_tmdb_miss'))

    def test_positive_result_is_cached_and_reused(self):
        client = TMDbClient('test-key')
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {'results': [{
            'poster_path': '/p.jpg', 'backdrop_path': '/b.jpg',
            'vote_average': 8.1, 'overview': 'Desc', 'release_date': '2026-01-02',
        }]}
        client.http = Mock()
        client.http.get.return_value = response
        cache = {}
        with patch('ultrastalker_desktop.core.tmdb.cache_get', side_effect=lambda k: cache.get(k)), \
             patch('ultrastalker_desktop.core.tmdb.cache_set', side_effect=lambda k, v, ttl: cache.__setitem__(k, v)):
            first = client.search('Movie', 'movies', '2026')
            second = client.search('Movie', 'movies', '2026')
        self.assertEqual(first, second)
        self.assertEqual(first['year'], '2026')
        client.http.get.assert_called_once()

if __name__ == '__main__':
    unittest.main()
