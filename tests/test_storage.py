from __future__ import annotations
import time

import hashlib
import json
import sqlite3
import tempfile
import unittest
import sys
import types
from pathlib import Path
from unittest.mock import patch

from ultrastalker_desktop.core.models import MediaItem, Profile, profile_identity
import ultrastalker_desktop.storage.database as db

# Unit tests do not depend on the host OS credential backend.
if 'keyring' not in sys.modules:
    _fake_store = {}
    fake_keyring = types.SimpleNamespace(
        get_password=lambda service, user: _fake_store.get((service, user)),
        set_password=lambda service, user, value: _fake_store.__setitem__((service, user), value),
        delete_password=lambda service, user: _fake_store.pop((service, user), None),
    )
    sys.modules['keyring'] = fake_keyring
import ultrastalker_desktop.storage.profiles as profiles
import ultrastalker_desktop.storage.settings as settings


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_app = db.APP_DIR
        self.old_db = db.DB
        db.APP_DIR = self.root
        db.DB = self.root / 'test.db'

    def tearDown(self):
        db.APP_DIR = self.old_app
        db.DB = self.old_db
        self.tmp.cleanup()

    def test_resume_and_completion_threshold(self):
        ep = MediaItem('7', 'Episode 7', 'episode', series_id='series-1', season=1, episode=7)
        db.add_history('P', ep, 10, 1000)
        self.assertNotIn(db.episode_tracking_key(ep), db.watched_episodes('P', 'series-1'))
        db.update_progress('P', ep, 900, 1000)
        self.assertIn(db.episode_tracking_key(ep), db.watched_episodes('P', 'series-1'))
        self.assertEqual(db.resume_point('P', ep), (900.0, 1000.0))

    def test_favorites_keep_different_kinds_with_same_id(self):
        live = MediaItem('1', 'Channel', 'live')
        movie = MediaItem('1', 'Movie', 'movies')
        db.toggle_favorite('P', live)
        db.toggle_favorite('P', movie)
        rows = db.favorites('P')
        self.assertEqual({x.kind for x in rows}, {'live', 'movies'})

    def test_corrupt_stored_payload_recovers_provider_identity_from_media_key(self):
        c = db.conn()
        try:
            c.execute(
                'insert into favorites values(?,?,?,?,?)',
                ('P', 'movies:movie-42', 'Recovered Movie', 'movies', '{broken'),
            )
            c.execute(
                'insert into history values(?,?,?,?,?,?,?,?)',
                ('P', 'episode:show-7:se:2:4', 'Episode 4', 'episode', 'bad', 'nan', 1.0, '{broken'),
            )
            c.commit()
        finally:
            c.close()

        movie = db.favorites('P')[0]
        self.assertEqual((movie.kind, movie.id), ('movies', 'movie-42'))
        episode, position, duration = db.history('P')[0]
        self.assertEqual(episode.kind, 'episode')
        self.assertEqual(episode.id, '')
        self.assertEqual((episode.series_id, episode.season, episode.episode), ('show-7', 2, 4))
        self.assertEqual((position, duration), (0.0, 0.0))

    def test_corrupt_unnumbered_episode_payload_recovers_provider_id(self):
        c = db.conn()
        try:
            c.execute(
                'insert into favorites values(?,?,?,?,?)',
                ('P', 'episode:show-8:id:provider-99', 'Special', 'episode', '{broken'),
            )
            c.commit()
        finally:
            c.close()
        item = db.favorites('P')[0]
        self.assertEqual((item.id, item.series_id), ('provider-99', 'show-8'))

    def test_unknown_corrupt_storage_key_never_becomes_provider_id(self):
        c = db.conn()
        try:
            c.execute(
                'insert into favorites values(?,?,?,?,?)',
                ('P', 'opaque-garbage-key', 'Broken', 'movies', '{broken'),
            )
            c.commit()
        finally:
            c.close()
        item = db.favorites('P')[0]
        self.assertEqual(item.id, '')
        self.assertNotEqual(item.id, 'opaque-garbage-key')

    def test_history_payload_does_not_persist_resolved_stream_credentials(self):
        item = MediaItem(
            '10', 'Episode', 'episode',
            stream_url='http://server/series/user/supersecret/10.mp4',
            command='ffmpeg http://portal/ch/10?token=cmd-secret',
            poster='http://images/poster.jpg?token=poster-secret',
            series_id='5',
            raw={
                'container_extension': 'mp4',
                'url': 'http://server/?token=secret-token',
                'cmd': 'ffmpeg http://portal/ch/10?token=raw-cmd-secret',
                'opaque_account': 'do-not-persist',
            },
        )
        db.add_history('P', item, 1, 10)
        c = db.conn()
        payload = c.execute('select payload from history where source=?', ('P',)).fetchone()['payload']
        c.close()
        for secret in ('supersecret', 'secret-token', 'cmd-secret', 'poster-secret', 'raw-cmd-secret', 'do-not-persist'):
            self.assertNotIn(secret, payload)
        restored = db.history('P')[0][0]
        self.assertEqual(restored.stream_url, '')
        self.assertEqual(restored.command, '')
        self.assertEqual(restored.poster, '')
        self.assertEqual(restored.raw.get('container_extension'), 'mp4')
        self.assertNotIn('cmd', restored.raw)

    def test_database_sets_baseline_schema_version(self):
        c = db.conn()
        try:
            version = c.execute("PRAGMA user_version").fetchone()[0]
        finally:
            c.close()
        self.assertEqual(version, db.SCHEMA_VERSION)

    def test_database_refuses_newer_schema_version_on_downgrade(self):
        raw = sqlite3.connect(db.DB)
        raw.execute(f"PRAGMA user_version={db.SCHEMA_VERSION + 1}")
        raw.commit(); raw.close()
        identity = db._database_identity()
        with db._SCHEMA_LOCK:
            db._INITIALIZED_DBS.discard(identity)
        with self.assertRaises(sqlite3.DatabaseError) as cm:
            db.conn()
        self.assertIn("newer than supported", str(cm.exception))
        self.assertNotIn(identity, db._INITIALIZED_DBS)

    def test_database_creates_long_lived_query_indexes(self):
        c = db.conn()
        names = {row[1] for row in c.execute("PRAGMA index_list('history')").fetchall()}
        cache_names = {row[1] for row in c.execute("PRAGMA index_list('cache')").fetchall()}
        c.close()
        self.assertIn('idx_history_source_watched', names)
        self.assertIn('idx_cache_expires', cache_names)

    def test_database_initialization_prunes_expired_cache_rows(self):
        c = db.conn()
        c.execute('insert or replace into cache values(?,?,?)', ('expired', '{}', 1.0))
        c.execute('insert or replace into cache values(?,?,?)', ('fresh', '{}', time.time() + 3600))
        c.commit()
        c.close()

        identity = db._database_identity()
        with db._SCHEMA_LOCK:
            db._INITIALIZED_DBS.discard(identity)
        c = db.conn()
        keys = {row[0] for row in c.execute('select key from cache').fetchall()}
        c.close()
        self.assertNotIn('expired', keys)
        self.assertIn('fresh', keys)

    def test_failed_database_initialization_is_not_marked_initialized(self):
        identity = db._database_identity()
        with db._SCHEMA_LOCK:
            db._INITIALIZED_DBS.discard(identity)
        original = db._SCHEMA_SQL
        db._SCHEMA_SQL = 'THIS IS NOT VALID SQL'
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                db.conn()
            self.assertNotIn(identity, db._INITIALIZED_DBS)
        finally:
            db._SCHEMA_SQL = original
        c = db.conn()
        try:
            tables = {row[0] for row in c.execute("select name from sqlite_master where type='table'").fetchall()}
        finally:
            c.close()
        self.assertTrue({'favorites', 'history', 'cache'}.issubset(tables))
        self.assertIn(identity, db._INITIALIZED_DBS)

    def test_database_schema_initialization_is_not_repeated_on_hot_connections(self):
        c = db.conn(); c.close()
        original = db._SCHEMA_SQL
        db._SCHEMA_SQL = 'THIS IS NOT VALID SQL'
        try:
            # Same database path was already initialized, so hot reads/writes must
            # not execute schema DDL again.
            c = db.conn(); c.close()
        finally:
            db._SCHEMA_SQL = original

    def test_read_connection_closes_when_query_raises(self):
        class BrokenConnection:
            def __init__(self):
                self.closed = False
            def execute(self, *args, **kwargs):
                raise sqlite3.OperationalError("forced read failure")
            def close(self):
                self.closed = True

        broken = BrokenConnection()
        with patch.object(db, "conn", return_value=broken):
            with self.assertRaises(sqlite3.OperationalError):
                db.favorites("P")
        self.assertTrue(broken.closed)

    def test_write_connection_closes_when_query_raises(self):
        class BrokenConnection:
            def __init__(self):
                self.closed = False
            def execute(self, *args, **kwargs):
                raise sqlite3.OperationalError("forced write failure")
            def commit(self):
                raise AssertionError("commit should not run after execute failure")
            def close(self):
                self.closed = True

        broken = BrokenConnection()
        item = MediaItem("1", "Movie", "movies")
        with patch.object(db, "conn", return_value=broken):
            with self.assertRaises(sqlite3.OperationalError):
                db.add_history("P", item)
        self.assertTrue(broken.closed)

    def test_database_reinitializes_if_file_is_recreated_at_same_path(self):
        c = db.conn(); c.close()
        db.DB.unlink()
        c = db.conn()
        try:
            tables = {row[0] for row in c.execute("select name from sqlite_master where type='table'").fetchall()}
        finally:
            c.close()
        self.assertTrue({'favorites', 'history', 'cache'}.issubset(tables))


    def test_cache_delete_prefix_treats_percent_and_underscore_literally(self):
        db.cache_set('a_b%:one', {'v': 1}, 300)
        db.cache_set('axbX:two', {'v': 2}, 300)
        db.cache_set('a_b%:three', {'v': 3}, 300)
        db.cache_delete_prefix('a_b%:')
        self.assertIsNone(db.cache_get('a_b%:one'))
        self.assertIsNone(db.cache_get('a_b%:three'))
        self.assertEqual(db.cache_get('axbX:two'), {'v': 2})

    def test_cache_expiration(self):
        db.cache_set('x', {'a': 1}, ttl=60)
        self.assertEqual(db.cache_get('x'), {'a': 1})
        db.cache_set('dead', {'a': 2}, ttl=-1)
        self.assertIsNone(db.cache_get('dead'))

    def test_unnumbered_episodes_track_by_id_not_none_tuple(self):
        a = MediaItem('ep-a', 'Episode A', 'episode', series_id='show')
        b = MediaItem('ep-b', 'Episode B', 'episode', series_id='show')
        db.add_history('P', a, 1000, 1000)
        watched = db.watched_episodes('P', 'show')
        self.assertIn(db.episode_tracking_key(a), watched)
        self.assertNotIn(db.episode_tracking_key(b), watched)
        self.assertNotEqual(db.episode_tracking_key(a), db.episode_tracking_key(b))

    def test_history_progress_label_matches_completion_rule(self):
        self.assertEqual(db.history_progress_label(0, 1000), 'Started')
        self.assertEqual(db.history_progress_label(370, 1000), 'Continue • 37% • 6:10 / 16:40')
        self.assertEqual(db.history_progress_label(900, 1000), 'Watched • 90%')
        self.assertEqual(db.history_progress_label(125, 0), 'Continue • 2:05')
        self.assertTrue(db.is_completed(900, 1000))
        self.assertFalse(db.is_completed(370, 1000))

    def test_numbered_episode_tracking_prefers_season_episode(self):
        a = MediaItem('provider-a', 'Episode 2', 'episode', series_id='show', season=1, episode=2)
        same = MediaItem('provider-b', 'Renumbered ID', 'episode', series_id='show', season=1, episode=2)
        self.assertEqual(db.episode_tracking_key(a), db.episode_tracking_key(same))

    def test_numbered_episode_history_keys_do_not_collide_when_provider_reuses_id(self):
        first = MediaItem('container-9', 'Episode 1', 'episode', series_id='show', season=1, episode=1)
        second = MediaItem('container-9', 'Episode 2', 'episode', series_id='show', season=1, episode=2)
        self.assertNotEqual(db.media_key(first), db.media_key(second))
        db.add_history('P', first, 100, 1000)
        db.add_history('P', second, 200, 1000)
        rows = db.history('P')
        self.assertEqual(len(rows), 2)
        self.assertEqual({row[0].episode for row in rows}, {1, 2})

    def test_unnumbered_episode_history_still_uses_provider_id(self):
        first = MediaItem('ep-a', 'Special A', 'episode', series_id='show')
        second = MediaItem('ep-b', 'Special B', 'episode', series_id='show')
        self.assertNotEqual(db.media_key(first), db.media_key(second))

    def test_legacy_episode_history_key_is_read_and_migrated_on_update(self):
        ep = MediaItem('container-9', 'Episode 2', 'episode', series_id='show', season=1, episode=2)
        legacy = 'episode:show:container-9'
        current = db.media_key(ep)
        c = db.conn()
        c.execute(
            'insert into history values(?,?,?,?,?,?,?,?)',
            ('P', legacy, ep.title, ep.kind, 321.0, 1000.0, 1.0, db._payload(ep)),
        )
        c.commit(); c.close()
        self.assertEqual(db.resume_point('P', ep), (321.0, 1000.0))
        db.update_progress('P', ep, 400, 1000)
        c = db.conn()
        try:
            keys = {row[0] for row in c.execute('select item_id from history where source=?', ('P',)).fetchall()}
        finally:
            c.close()
        self.assertIn(current, keys)
        self.assertNotIn(legacy, keys)
        self.assertEqual(db.resume_point('P', ep), (400.0, 1000.0))

    def test_legacy_episode_favorite_key_migrates_before_toggle(self):
        ep = MediaItem('container-9', 'Episode 2', 'episode', series_id='show', season=1, episode=2)
        legacy = 'episode:show:container-9'
        c = db.conn()
        c.execute('insert into favorites values(?,?,?,?,?)', ('P', legacy, ep.title, ep.kind, db._payload(ep)))
        c.commit(); c.close()
        # Existing legacy favorite is recognized as the same numbered episode and
        # toggled off instead of creating a duplicate under the new key.
        self.assertFalse(db.toggle_favorite('P', ep))
        self.assertEqual(db.favorites('P'), [])


class ProfileSecurityTests(unittest.TestCase):
    def setUp(self):
        _fake_store.clear()

    def test_profile_atomic_write_fsyncs_before_replace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                with patch.object(profiles.os, 'fsync') as fsync:
                    profiles._write_atomic([{'name': 'P'}])
                fsync.assert_called_once()
                self.assertEqual(json.loads(profiles.FILE.read_text(encoding='utf-8'))[0]['name'], 'P')
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_profile_atomic_write_failure_leaves_original_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                original = b'[{"name":"old"}]'
                profiles.FILE.write_bytes(original)
                with patch.object(profiles.os, 'fsync', side_effect=OSError('disk flush failed')):
                    with self.assertRaises(OSError):
                        profiles._write_atomic([{'name': 'new'}])
                self.assertEqual(profiles.FILE.read_bytes(), original)
                self.assertFalse(profiles.FILE.with_suffix('.json.tmp').exists())
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_corrupt_profile_file_is_not_overwritten_by_save(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                original = b'{broken-json-with-legacy-secret: supersecret'
                profiles.FILE.write_bytes(original)
                p = Profile('X', 'xtream', 'https://server.test', username='u', password='new-secret')
                with self.assertRaises(profiles.ProfileMetadataCorruptError):
                    profiles.save_profile(p)
                self.assertEqual(profiles.FILE.read_bytes(), original)
                marker = root / 'profiles_corruption.json'
                self.assertTrue(marker.is_file())
                marker_text = marker.read_text(encoding='utf-8')
                self.assertNotIn('supersecret', marker_text)
                self.assertIn(hashlib.sha256(original).hexdigest(), marker_text)
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_corrupt_profile_file_does_not_prevent_app_profile_list_loading(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                profiles.FILE.write_text('{broken', encoding='utf-8')
                self.assertEqual(profiles.load_profiles(), [])
                self.assertEqual(profiles.FILE.read_text(encoding='utf-8'), '{broken')
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_delete_refuses_to_overwrite_corrupt_profile_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                original = b'not-json'
                profiles.FILE.write_bytes(original)
                with self.assertRaises(profiles.ProfileMetadataCorruptError):
                    profiles.delete_profile('Home')
                self.assertEqual(profiles.FILE.read_bytes(), original)
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_stalker_mac_not_written_plaintext(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                mac = '00:1A:79:12:34:56'
                p = Profile('S', 'stalker', 'http://portal.example/stalker_portal/c/', mac, '', '', '')
                profiles.save_profile(p)
                text = profiles.FILE.read_text(encoding='utf-8')
                self.assertNotIn(mac, text)
                self.assertEqual(_fake_store[(profiles.SERVICE, profiles._mac_key(p))], mac)
                loaded = profiles.load_profiles()[0]
                self.assertEqual(loaded.mac, mac)
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_xtream_password_not_written_plaintext(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                with patch.object(profiles, 'load_profiles', return_value=[]):
                    p = Profile('X', 'xtream', 'http://server', '', 'user', 'supersecret', '')
                    profiles.save_profile(p)
                    text = profiles.FILE.read_text(encoding='utf-8')
                    self.assertNotIn('supersecret', text)
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_m3u_url_not_written_plaintext(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                with patch.object(profiles, 'load_profiles', return_value=[]):
                    secret = 'http://example.test/list.m3u?token=secret-token'
                    p = Profile('M', 'm3u', secret, '', '', '', secret)
                    profiles.save_profile(p)
                    text = profiles.FILE.read_text(encoding='utf-8')
                    self.assertNotIn('secret-token', text)
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_profile_errors_do_not_echo_backend_paths_or_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                leaked = r'C:\Users\Alice\vault?token=supersecret'
                p = Profile('P', 'xtream', 'https://server.test', username='u', password='secret')
                with patch.object(profiles.keyring, 'get_password', side_effect=RuntimeError(leaked)):
                    with self.assertRaises(profiles.ProfileStorageError) as cm:
                        profiles.save_profile(p)
                text = str(cm.exception)
                self.assertNotIn('Alice', text)
                self.assertNotIn('supersecret', text)
                self.assertNotIn('token=', text)
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_secure_store_failure_does_not_write_profile(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                p = Profile('X', 'xtream', 'http://server', '', 'user', 'secret', '')
                with patch.object(profiles.keyring, 'set_password', side_effect=RuntimeError('vault down')):
                    with self.assertRaises(profiles.ProfileStorageError):
                        profiles.save_profile(p)
                self.assertFalse(profiles.FILE.exists())
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file


    def test_profile_delete_removes_metadata_and_secret(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                p = Profile('X', 'xtream', 'http://server', '', 'user', 'secret', '')
                profiles.save_profile(p)
                key = profiles._password_key(p)
                self.assertIn((profiles.SERVICE, key), _fake_store)
                self.assertTrue(profiles.delete_profile('X'))
                self.assertNotIn((profiles.SERVICE, key), _fake_store)
                self.assertEqual(json.loads(profiles.FILE.read_text(encoding='utf-8')), [])
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_load_profiles_fails_closed_when_legacy_migration_and_vault_read_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                root.mkdir(parents=True, exist_ok=True)
                rows = [
                    {
                        'name': 'S', 'source_type': 'stalker',
                        'portal_url': 'https://alice:pw@portal.test/c/?token=url-secret',
                        'mac': '00:1A:79:AA:BB:CC', 'username': '', 'password': '', 'm3u_url': '',
                    },
                    {
                        'name': 'X', 'source_type': 'xtream',
                        'portal_url': 'https://bob:pw@xtream.test/?token=url-secret-2',
                        'mac': '', 'username': 'bob', 'password': 'legacy-pass', 'm3u_url': '',
                    },
                    {
                        'name': 'M', 'source_type': 'm3u',
                        'portal_url': 'https://m3u.test/list.m3u?token=m3u-secret',
                        'mac': '', 'username': '', 'password': '',
                        'm3u_url': 'https://m3u.test/list.m3u?token=m3u-secret',
                    },
                ]
                profiles.FILE.write_text(json.dumps(rows), encoding='utf-8')
                with patch.object(profiles, 'migrate_legacy_profile_secrets', side_effect=profiles.ProfileStorageError('migration failed')), \
                     patch.object(profiles, 'ensure_secure_backend', return_value='fake'), \
                     patch.object(profiles.keyring, 'get_password', side_effect=RuntimeError('vault read failed')):
                    loaded = {p.name: p for p in profiles.load_profiles()}
                self.assertEqual(loaded['S'].mac, '')
                self.assertEqual(loaded['S'].portal_url, 'https://portal.test/c/')
                self.assertEqual(loaded['X'].password, '')
                self.assertEqual(loaded['X'].portal_url, 'https://xtream.test/')
                self.assertEqual(loaded['M'].m3u_url, '')
                self.assertEqual(loaded['M'].portal_url, '')
                dump = repr(loaded)
                for secret in ('AA:BB:CC', 'legacy-pass', 'url-secret', 'url-secret-2', 'm3u-secret', 'alice:pw', 'bob:pw'):
                    self.assertNotIn(secret, dump)
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_load_profiles_fails_closed_when_secure_backend_is_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                root.mkdir(parents=True, exist_ok=True)
                profiles.FILE.write_text(json.dumps([{
                    'name': 'S', 'source_type': 'stalker',
                    'portal_url': 'https://user:pass@portal.test/c/?token=secret',
                    'mac': '00:1A:79:AA:BB:CC', 'username': '', 'password': '', 'm3u_url': '',
                }]), encoding='utf-8')
                with patch.object(profiles, 'migrate_legacy_profile_secrets', side_effect=profiles.ProfileStorageError('migration failed')), \
                     patch.object(profiles, 'ensure_secure_backend', side_effect=profiles.SecureCredentialBackendError('no vault')):
                    loaded = profiles.load_profiles()
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0].mac, '')
                self.assertEqual(loaded[0].portal_url, 'https://portal.test/c/')
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_profile_credential_read_failure_does_not_delete_unknown_secret(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                p = Profile('X', 'xtream', 'http://server', '', 'user', 'secret', '')
                with patch.object(profiles.keyring, 'get_password', side_effect=RuntimeError('vault unreadable')), \
                     patch.object(profiles.keyring, 'delete_password') as delete:
                    with self.assertRaises(profiles.ProfileStorageError):
                        profiles.save_profile(p)
                    delete.assert_not_called()
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_profile_metadata_failure_restores_previous_secret(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                old = Profile('X', 'xtream', 'http://server', '', 'user', 'old-secret', '')
                profiles.save_profile(old)
                replacement = Profile('X', 'xtream', 'http://server', '', 'user', 'new-secret', '')
                with patch.object(profiles, '_write_atomic', side_effect=OSError('disk full')):
                    with self.assertRaises(profiles.ProfileStorageError):
                        profiles.save_profile(replacement)
                self.assertEqual(_fake_store[(profiles.SERVICE, profiles._password_key(old))], 'old-secret')
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file


    def test_legacy_profile_secrets_migrate_atomically_and_all_rows_are_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                legacy_rows = [
                    {
                        'name': 'OldStalker', 'source_type': 'stalker',
                        'portal_url': 'http://portal.test/stalker_portal/c/',
                        'mac': '00:1A:79:AA:BB:CC', 'username': '', 'password': '', 'm3u_url': '',
                        'future_field': 'keep-tolerating-schema',
                    },
                    {
                        'name': 'OldXtream', 'source_type': 'xtream',
                        'portal_url': 'http://xtream.test', 'mac': '', 'username': 'alice',
                        'password': 'legacy-pass', 'm3u_url': '',
                    },
                    {
                        'name': 'OldM3U', 'source_type': 'm3u',
                        'portal_url': 'http://m3u.test/list.m3u?token=legacy-token',
                        'mac': '', 'username': '', 'password': '',
                        'm3u_url': 'http://m3u.test/list.m3u?token=legacy-token',
                    },
                ]
                root.mkdir(parents=True, exist_ok=True)
                profiles.FILE.write_text(json.dumps(legacy_rows), encoding='utf-8')

                loaded = {p.name: p for p in profiles.load_profiles()}
                self.assertEqual(loaded['OldStalker'].mac, '00:1A:79:AA:BB:CC')
                self.assertEqual(loaded['OldXtream'].password, 'legacy-pass')
                self.assertIn('legacy-token', loaded['OldM3U'].m3u_url)

                text = profiles.FILE.read_text(encoding='utf-8')
                for secret in ('00:1A:79:AA:BB:CC', 'legacy-pass', 'legacy-token'):
                    self.assertNotIn(secret, text)
                rows = json.loads(text)
                self.assertEqual(len(rows), 3)
                self.assertEqual(rows[0].get('future_field'), 'keep-tolerating-schema')
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_saving_one_profile_migrates_other_legacy_profiles_first(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                root.mkdir(parents=True, exist_ok=True)
                legacy_mac = '00:1A:79:10:20:30'
                profiles.FILE.write_text(json.dumps([{
                    'name': 'Legacy', 'source_type': 'stalker',
                    'portal_url': 'http://legacy.test/c/', 'mac': legacy_mac,
                    'username': '', 'password': '', 'm3u_url': '',
                }]), encoding='utf-8')
                profiles.save_profile(Profile('New', 'xtream', 'http://x.test', '', 'bob', 'new-pass', ''))
                legacy = Profile('Legacy', 'stalker', 'http://legacy.test/c/', '', '', '', '')
                self.assertEqual(_fake_store[(profiles.SERVICE, profiles._mac_key(legacy))], legacy_mac)
                self.assertNotIn(legacy_mac, profiles.FILE.read_text(encoding='utf-8'))
                self.assertEqual({p.name for p in profiles.load_profiles()}, {'Legacy', 'New'})
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file


    def test_legacy_plaintext_does_not_overwrite_newer_vault_credential(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                root.mkdir(parents=True, exist_ok=True)
                row = {
                    'name': 'S', 'source_type': 'stalker',
                    'portal_url': 'http://portal.test/c/',
                    'mac': '00:1A:79:OLD:00:01', 'username': '', 'password': '', 'm3u_url': '',
                }
                profiles.FILE.write_text(json.dumps([row]), encoding='utf-8')
                metadata_profile = Profile('S', 'stalker', 'http://portal.test/c/', '', '', '', '')
                key = profiles._mac_key(metadata_profile)
                _fake_store[(profiles.SERVICE, key)] = '00:1A:79:NEW:00:02'

                loaded = profiles.load_profiles()[0]
                self.assertEqual(loaded.mac, '00:1A:79:NEW:00:02')
                self.assertEqual(_fake_store[(profiles.SERVICE, key)], '00:1A:79:NEW:00:02')
                self.assertNotIn('00:1A:79:OLD:00:01', profiles.FILE.read_text(encoding='utf-8'))
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_legacy_migration_metadata_failure_rolls_back_staged_vault_secret(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                root.mkdir(parents=True, exist_ok=True)
                legacy_mac = '00:1A:79:12:34:99'
                original = json.dumps([{
                    'name': 'S', 'source_type': 'stalker',
                    'portal_url': 'http://portal.test/c/', 'mac': legacy_mac,
                    'username': '', 'password': '', 'm3u_url': '',
                }])
                profiles.FILE.write_text(original, encoding='utf-8')
                key = profiles._mac_key(Profile('S', 'stalker', 'http://portal.test/c/', '', '', '', ''))

                with patch.object(profiles, '_write_atomic', side_effect=OSError('disk full')):
                    with self.assertRaises(profiles.ProfileStorageError):
                        profiles.migrate_legacy_profile_secrets()

                self.assertNotIn((profiles.SERVICE, key), _fake_store)
                self.assertEqual(profiles.FILE.read_text(encoding='utf-8'), original)
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file


    def test_sensitive_xtream_endpoint_is_vaulted_and_restored(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                raw = 'https://embedded:secret@host.test/base?token=abc123&output=ts#frag'
                p = Profile('X', 'xtream', raw, '', 'alice', 'provider-pass', '')
                profiles.save_profile(p)
                text = profiles.FILE.read_text(encoding='utf-8')
                for secret in ('embedded', 'secret', 'abc123', 'provider-pass'):
                    self.assertNotIn(secret, text)
                stored = json.loads(text)[0]['portal_url']
                self.assertEqual(stored, 'https://host.test/base?output=ts')
                self.assertEqual(_fake_store[(profiles.SERVICE, profiles._endpoint_key(p))], raw)
                loaded = profiles.load_profiles()[0]
                self.assertEqual(loaded.portal_url, raw)
                self.assertEqual(loaded.password, 'provider-pass')
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_plain_provider_endpoint_does_not_create_extra_vault_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                p = Profile('X', 'xtream', 'https://host.test/base', '', 'alice', 'provider-pass', '')
                profiles.save_profile(p)
                self.assertNotIn((profiles.SERVICE, profiles._endpoint_key(p)), _fake_store)
                self.assertEqual(json.loads(profiles.FILE.read_text(encoding='utf-8'))[0]['portal_url'], 'https://host.test/base')
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_profile_identity_survives_plaintext_to_vault_migration(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                mac = '00:1A:79:11:22:33'
                legacy = Profile('S', 'stalker', 'http://portal.test/c/', mac, '', '', '')
                before = profile_identity(legacy)
                root.mkdir(parents=True, exist_ok=True)
                profiles.FILE.write_text(json.dumps([legacy.__dict__]), encoding='utf-8')
                after_profile = profiles.load_profiles()[0]
                self.assertEqual(profile_identity(after_profile), before)
                self.assertEqual(after_profile.mac, mac)
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file


    def test_profile_verify_failure_restores_previous_vault_value(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                p = Profile('X', 'xtream', 'https://host.test', '', 'alice', 'new-pass', '')
                key = profiles._password_key(p)
                _fake_store[(profiles.SERVICE, key)] = 'old-pass'
                original_get = profiles.keyring.get_password
                calls = {'n': 0}
                def flaky_get(service, user):
                    if (service, user) == (profiles.SERVICE, key):
                        calls['n'] += 1
                        if calls['n'] == 1:
                            return 'old-pass'
                        if calls['n'] == 2:
                            return 'wrong-after-write'
                    return original_get(service, user)
                with patch.object(profiles.keyring, 'get_password', side_effect=flaky_get):
                    with self.assertRaises(profiles.ProfileStorageError):
                        profiles.save_profile(p)
                self.assertEqual(_fake_store[(profiles.SERVICE, key)], 'old-pass')
                self.assertFalse(profiles.FILE.exists())
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_legacy_migration_verify_failure_removes_newly_staged_secret(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                root.mkdir(parents=True, exist_ok=True)
                mac = '00:1A:79:44:55:66'
                profiles.FILE.write_text(json.dumps([{
                    'name': 'S', 'source_type': 'stalker', 'portal_url': 'http://p.test/c/',
                    'mac': mac, 'username': '', 'password': '', 'm3u_url': '',
                }]), encoding='utf-8')
                key = profiles._mac_key(Profile('S', 'stalker', 'http://p.test/c/', '', '', '', ''))
                original_get = profiles.keyring.get_password
                calls = {'n': 0}
                def flaky_get(service, user):
                    if (service, user) == (profiles.SERVICE, key):
                        calls['n'] += 1
                        if calls['n'] == 1:
                            return None
                        if calls['n'] == 2:
                            return 'mismatch'
                    return original_get(service, user)
                with patch.object(profiles.keyring, 'get_password', side_effect=flaky_get):
                    with self.assertRaises(profiles.ProfileStorageError):
                        profiles.migrate_legacy_profile_secrets()
                self.assertNotIn((profiles.SERVICE, key), _fake_store)
                self.assertIn(mac, profiles.FILE.read_text(encoding='utf-8'))
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_replacing_sensitive_endpoint_with_plain_one_removes_endpoint_secret(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                first = Profile('X', 'xtream', 'https://host.test/base?token=abc', '', 'alice', 'pass1', '')
                profiles.save_profile(first)
                endpoint_key = profiles._endpoint_key(first)
                self.assertIn((profiles.SERVICE, endpoint_key), _fake_store)
                replacement = Profile('X', 'xtream', 'https://host.test/base', '', 'alice', 'pass2', '')
                profiles.save_profile(replacement)
                self.assertNotIn((profiles.SERVICE, endpoint_key), _fake_store)
                loaded = profiles.load_profiles()[0]
                self.assertEqual(loaded.portal_url, 'https://host.test/base')
                self.assertEqual(loaded.password, 'pass2')
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file

    def test_delete_profile_removes_sensitive_endpoint_secret_too(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                p = Profile('X', 'xtream', 'https://host.test/base?token=abc', '', 'alice', 'pass1', '')
                profiles.save_profile(p)
                endpoint_key = profiles._endpoint_key(p)
                self.assertIn((profiles.SERVICE, endpoint_key), _fake_store)
                self.assertTrue(profiles.delete_profile('X'))
                self.assertNotIn((profiles.SERVICE, endpoint_key), _fake_store)
                self.assertNotIn((profiles.SERVICE, profiles._password_key(p)), _fake_store)
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file


    def test_switching_profile_source_removes_old_source_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = profiles.APP_DIR, profiles.FILE
            profiles.APP_DIR, profiles.FILE = root, root / 'profiles.json'
            try:
                old = Profile('Home', 'xtream', 'https://x.test/api?token=oldtoken', '', 'alice', 'old-pass', '')
                profiles.save_profile(old)
                old_password_key = profiles._password_key(old)
                old_endpoint_key = profiles._endpoint_key(old)
                self.assertIn((profiles.SERVICE, old_password_key), _fake_store)
                self.assertIn((profiles.SERVICE, old_endpoint_key), _fake_store)

                new = Profile('Home', 'stalker', 'https://s.test/stalker_portal/c/', '00:1A:79:AA:10:20', '', '', '')
                profiles.save_profile(new)
                self.assertNotIn((profiles.SERVICE, old_password_key), _fake_store)
                self.assertNotIn((profiles.SERVICE, old_endpoint_key), _fake_store)
                self.assertEqual(_fake_store[(profiles.SERVICE, profiles._mac_key(new))], new.mac)
                loaded = profiles.load_profiles()[0]
                self.assertEqual(loaded.source_type, 'stalker')
                self.assertEqual(loaded.mac, new.mac)
            finally:
                profiles.APP_DIR, profiles.FILE = old_app, old_file


class SettingsSecurityTests(unittest.TestCase):
    def setUp(self):
        _fake_store.clear()

    def test_settings_atomic_write_fsyncs_before_replace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = settings.APP_DIR, settings.FILE
            settings.APP_DIR, settings.FILE = root, root / 'settings.json'
            try:
                with patch.object(settings.os, 'fsync') as fsync:
                    settings._write_atomic({'theme': 'default'})
                fsync.assert_called_once()
                self.assertEqual(json.loads(settings.FILE.read_text(encoding='utf-8'))['theme'], 'default')
            finally:
                settings.APP_DIR, settings.FILE = old_app, old_file

    def test_settings_atomic_write_failure_leaves_original_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = settings.APP_DIR, settings.FILE
            settings.APP_DIR, settings.FILE = root, root / 'settings.json'
            try:
                original = b'{"theme":"old"}'
                settings.FILE.write_bytes(original)
                with patch.object(settings.os, 'fsync', side_effect=OSError('disk flush failed')):
                    with self.assertRaises(OSError):
                        settings._write_atomic({'theme': 'new'})
                self.assertEqual(settings.FILE.read_bytes(), original)
                self.assertFalse(settings.FILE.with_suffix('.json.tmp').exists())
            finally:
                settings.APP_DIR, settings.FILE = old_app, old_file

    def test_corrupt_settings_file_is_not_overwritten_by_save(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = settings.APP_DIR, settings.FILE
            settings.APP_DIR, settings.FILE = root, root / 'settings.json'
            try:
                original = b'{broken-settings-with-secret: legacy-key'
                settings.FILE.write_bytes(original)
                with self.assertRaises(settings.SettingsMetadataCorruptError):
                    settings.save_settings({'tmdb_api_key': 'new-key', 'theme': 'default'})
                self.assertEqual(settings.FILE.read_bytes(), original)
                self.assertNotIn((settings.SERVICE, settings.TMDB_KEY), _fake_store)
                marker = root / 'settings_corruption.json'
                self.assertTrue(marker.is_file())
                marker_text = marker.read_text(encoding='utf-8')
                self.assertNotIn('legacy-key', marker_text)
                self.assertIn(hashlib.sha256(original).hexdigest(), marker_text)
            finally:
                settings.APP_DIR, settings.FILE = old_app, old_file

    def test_corrupt_settings_file_loads_safe_defaults_without_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = settings.APP_DIR, settings.FILE
            settings.APP_DIR, settings.FILE = root, root / 'settings.json'
            try:
                settings.FILE.write_text('{broken', encoding='utf-8')
                loaded = settings.load_settings()
                self.assertEqual(loaded.get('tmdb_api_key'), '')
                self.assertEqual(settings.FILE.read_text(encoding='utf-8'), '{broken')
            finally:
                settings.APP_DIR, settings.FILE = old_app, old_file

    def test_tmdb_key_never_written_plaintext(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = settings.APP_DIR, settings.FILE
            settings.APP_DIR, settings.FILE = root, root / 'settings.json'
            try:
                settings.save_settings({'tmdb_api_key': 'tmdb-supersecret', 'theme': 'default'})
                text = settings.FILE.read_text(encoding='utf-8')
                self.assertNotIn('tmdb-supersecret', text)
                self.assertEqual(json.loads(text)['theme'], 'default')
            finally:
                settings.APP_DIR, settings.FILE = old_app, old_file

    def test_settings_credential_read_failure_does_not_delete_unknown_secret(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = settings.APP_DIR, settings.FILE
            settings.APP_DIR, settings.FILE = root, root / 'settings.json'
            try:
                with patch.object(settings.keyring, 'get_password', side_effect=RuntimeError('vault unreadable')), \
                     patch.object(settings.keyring, 'delete_password') as delete:
                    with self.assertRaises(settings.SettingsStorageError):
                        settings.save_settings({'tmdb_api_key': 'secret'})
                    delete.assert_not_called()
            finally:
                settings.APP_DIR, settings.FILE = old_app, old_file

    def test_settings_errors_do_not_echo_backend_paths_or_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = settings.APP_DIR, settings.FILE
            settings.APP_DIR, settings.FILE = root, root / 'settings.json'
            try:
                leaked = r'C:\Users\Alice\vault?token=supersecret'
                with patch.object(settings.keyring, 'get_password', side_effect=RuntimeError(leaked)):
                    with self.assertRaises(settings.SettingsStorageError) as cm:
                        settings.save_settings({'tmdb_api_key': 'secret'})
                text = str(cm.exception)
                self.assertNotIn('Alice', text)
                self.assertNotIn('supersecret', text)
                self.assertNotIn('token=', text)
            finally:
                settings.APP_DIR, settings.FILE = old_app, old_file

    def test_settings_secure_store_failure_does_not_write_success_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = settings.APP_DIR, settings.FILE
            settings.APP_DIR, settings.FILE = root, root / 'settings.json'
            try:
                with patch.object(settings.keyring, 'set_password', side_effect=RuntimeError('vault down')):
                    with self.assertRaises(settings.SettingsStorageError):
                        settings.save_settings({'tmdb_api_key': 'secret'})
                self.assertFalse(settings.FILE.exists())
            finally:
                settings.APP_DIR, settings.FILE = old_app, old_file


    def test_legacy_tmdb_key_migrates_to_secure_store_and_is_scrubbed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = settings.APP_DIR, settings.FILE
            settings.APP_DIR, settings.FILE = root, root / 'settings.json'
            try:
                root.mkdir(parents=True, exist_ok=True)
                settings.FILE.write_text(json.dumps({
                    'tmdb_api_key': 'legacy-tmdb-key',
                    'theme': 'default',
                }), encoding='utf-8')
                loaded = settings.load_settings()
                self.assertEqual(loaded['tmdb_api_key'], 'legacy-tmdb-key')
                self.assertEqual(loaded['theme'], 'default')
                text = settings.FILE.read_text(encoding='utf-8')
                self.assertNotIn('legacy-tmdb-key', text)
                self.assertNotIn('tmdb_api_key', json.loads(text))
                self.assertEqual(_fake_store[(settings.SERVICE, settings.TMDB_KEY)], 'legacy-tmdb-key')
            finally:
                settings.APP_DIR, settings.FILE = old_app, old_file

    def test_legacy_settings_migration_rolls_back_when_readback_fails_after_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old_app, old_file = settings.APP_DIR, settings.FILE
            settings.APP_DIR, settings.FILE = root, root / 'settings.json'
            try:
                root.mkdir(parents=True, exist_ok=True)
                settings.FILE.write_text(json.dumps({'tmdb_api_key': 'legacy-secret', 'theme': 'default'}), encoding='utf-8')
                previous = 'newer-vault-secret'
                _fake_store[(settings.SERVICE, settings.TMDB_KEY)] = previous
                # Exercise the path where migration must not overwrite a newer
                # vault value at all.
                self.assertTrue(settings.migrate_legacy_settings_secret())
                self.assertEqual(_fake_store[(settings.SERVICE, settings.TMDB_KEY)], previous)
                self.assertNotIn('legacy-secret', settings.FILE.read_text(encoding='utf-8'))

                # Now prove rollback after a successful write followed by a
                # failed read-back verification.
                settings.FILE.write_text(json.dumps({'tmdb_api_key': 'legacy-secret-2'}), encoding='utf-8')
                _fake_store.pop((settings.SERVICE, settings.TMDB_KEY), None)
                original_get = settings.keyring.get_password
                calls = {'n': 0}
                def flaky_get(service, user):
                    calls['n'] += 1
                    if calls['n'] == 1:
                        return None
                    raise RuntimeError('readback failed')
                with patch.object(settings.keyring, 'get_password', side_effect=flaky_get):
                    with self.assertRaises(settings.SettingsStorageError):
                        settings.migrate_legacy_settings_secret()
                self.assertNotIn((settings.SERVICE, settings.TMDB_KEY), _fake_store)
                self.assertIn('legacy-secret-2', settings.FILE.read_text(encoding='utf-8'))
            finally:
                settings.APP_DIR, settings.FILE = old_app, old_file


if __name__ == '__main__':
    unittest.main()
