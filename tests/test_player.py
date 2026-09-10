from __future__ import annotations

import unittest
import threading
import time
from unittest.mock import Mock, patch

from ultrastalker_desktop.player.mpv_backend import MPVBackend, PlaybackCancelled


class PlayerTests(unittest.TestCase):
    def test_playback_cancellation_uses_typed_control_flow(self):
        p = MPVBackend()
        with self.assertRaises(PlaybackCancelled):
            p.play_candidates(['https://stream.test/a'], should_cancel=lambda: True)

    def test_unrelated_runtime_error_with_cancel_text_is_not_treated_as_cancellation(self):
        p = MPVBackend()
        with patch.object(p, 'play', side_effect=RuntimeError('Playback request cancelled')):
            with self.assertRaises(RuntimeError) as cm:
                p.play_candidates(['https://stream.test/a'], settle_seconds=0)
        self.assertNotIsInstance(cm.exception, PlaybackCancelled)

    def test_player_control_commands(self):
        p = MPVBackend()
        with patch.object(p, '_command_exchange', return_value=(True, None)) as command:
            self.assertTrue(p.pause())
            command.assert_called_with('set_property', 'pause', True)
            self.assertTrue(p.resume())
            command.assert_called_with('set_property', 'pause', False)
            self.assertTrue(p.seek(30))
            command.assert_called_with('seek', 30.0, 'relative')
            self.assertTrue(p.set_volume(150))
            command.assert_called_with('set_property', 'volume', 100.0)

    def test_cycle_audio_and_subtitle_tracks(self):
        p = MPVBackend()
        with patch.object(p, '_command_exchange', side_effect=[(True, None), (True, 2), (True, None), (True, 3)]) as command:
            self.assertEqual(p.cycle_audio_track(), 2)
            self.assertEqual(p.cycle_subtitle_track(), 3)
            self.assertEqual(
                [call.args for call in command.call_args_list],
                [('cycle', 'aid'), ('get_property', 'aid'), ('cycle', 'sid'), ('get_property', 'sid')],
            )

    def test_toggle_fullscreen_uses_mpv_property(self):
        p = MPVBackend()
        with patch.object(p, '_command_exchange', side_effect=[(True, None), (True, True)]) as command:
            self.assertTrue(p.toggle_fullscreen())
            self.assertEqual(
                [call.args for call in command.call_args_list],
                [('cycle', 'fullscreen'), ('get_property', 'fullscreen')],
            )


    def test_control_methods_raise_when_ipc_command_fails(self):
        p = MPVBackend()
        with patch.object(p, '_command_exchange', return_value=(False, None)):
            for action in (p.pause, p.resume, lambda: p.seek(10), lambda: p.set_volume(50), p.toggle_fullscreen, p.cycle_audio_track, p.cycle_subtitle_track):
                with self.subTest(action=action):
                    with self.assertRaisesRegex(RuntimeError, 'mpv IPC'):
                        action()

    def test_successful_null_ipc_payload_is_not_treated_as_failure(self):
        p = MPVBackend()
        with patch.object(p, '_command_exchange', return_value=(True, None)):
            self.assertTrue(p.pause())
            self.assertTrue(p.seek(5))
            self.assertTrue(p.set_volume(20))

    def test_track_filtering(self):
        p = MPVBackend()
        rows = [
            {'type': 'audio', 'id': 1, 'lang': 'eng'},
            {'type': 'sub', 'id': 2, 'lang': 'ara'},
        ]
        with patch.object(p, 'command', return_value=rows):
            self.assertEqual(p.audio_tracks()[0]['id'], 1)
            self.assertEqual(p.subtitle_tracks()[0]['id'], 2)

    def test_position_duration(self):
        p = MPVBackend()
        with patch.object(p, 'command', side_effect=[12.5, 100.0]):
            self.assertEqual(p.get_position(), 12.5)
            self.assertEqual(p.get_duration(), 100.0)

    def test_ipc_ignores_async_event_and_matches_request_id(self):
        p = MPVBackend()

        class FakePipe:
            def __init__(self):
                self.lines = []
            def write(self, data):
                req = __import__('json').loads(data.decode())
                rid = req['request_id']
                self.lines = [
                    b'{"event":"property-change"}\n',
                    (__import__('json').dumps({"error":"success","data":42,"request_id":rid})+'\n').encode(),
                ]
            def readline(self):
                return self.lines.pop(0) if self.lines else b''
            def close(self):
                pass

        p.fp = FakePipe()
        p.pipe = 'fake'
        p.process = type('P', (), {'poll': lambda self: None})()
        self.assertEqual(p.command('get_property', 'time-pos'), 42)


    def test_startup_events_and_command_responses_use_separate_queues(self):
        p = MPVBackend()
        p.process = type('P', (), {'poll': lambda self: None})()

        class SinkPipe:
            def write(self, _data):
                pass
            def close(self):
                pass

        p.fp = SinkPipe()
        p.pipe = 'fake'
        p._open = Mock(return_value=True)
        p._events.put({'event': 'file-loaded'})
        p._responses.put({'error': 'success', 'data': 42, 'request_id': 1})

        self.assertEqual(p._wait_for_startup(0.1), 'loaded')
        self.assertEqual(p.command('get_property', 'time-pos'), 42)
        self.assertTrue(p._events.empty())
        self.assertTrue(p._responses.empty())

    def test_concurrent_commands_serialize_ipc_open(self):
        p = MPVBackend()
        p.process = type('P', (), {'poll': lambda self: None})()
        active = 0
        peak = 0
        guard = threading.Lock()

        class FakePipe:
            def write(self, data):
                req = __import__('json').loads(data.decode())
                p._responses.put({'error': 'success', 'data': req['request_id'], 'request_id': req['request_id']})
            def close(self):
                pass

        p.fp = FakePipe(); p.pipe = 'fake'
        def fake_open():
            nonlocal active, peak
            with guard:
                active += 1; peak = max(peak, active)
            time.sleep(0.03)
            with guard:
                active -= 1
            return True
        p._open = Mock(side_effect=fake_open)
        results = []
        threads = [threading.Thread(target=lambda: results.append(p.command('get_property','time-pos'))) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(1.0)
        self.assertEqual(peak, 1)
        self.assertEqual(len(results), 2)

    def test_ipc_timeout_is_bounded_even_if_pipe_read_blocks(self):
        p = MPVBackend()

        class BlockingPipe:
            def write(self, data):
                pass
            def readline(self):
                time.sleep(3)
                return b''
            def close(self):
                pass

        p.fp = BlockingPipe()
        p.pipe = 'fake'
        p.process = type('P', (), {'poll': lambda self: None})()
        started = time.monotonic()
        self.assertIsNone(p.command('get_property', 'time-pos'))
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 1.5)
        p._close_ipc()

    def test_stop_kills_and_reaps_process_when_graceful_terminate_fails(self):
        p = MPVBackend()
        proc = Mock(); proc.poll.return_value = None
        proc.terminate.side_effect = RuntimeError('terminate failed')
        p.process = proc; p.pipe = 'fake'; p.current_url = 'https://secret.test/a'
        with patch.object(p, '_close_ipc') as close_ipc:
            p.stop()
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
        proc.wait.assert_called_once_with(timeout=1)
        close_ipc.assert_called_once()
        self.assertIsNone(p.process)
        self.assertEqual(p.current_url, '')
        self.assertIsNone(p.pipe)

    def test_stop_closes_ipc_even_when_process_already_exited(self):
        p = MPVBackend()
        proc = Mock(); proc.poll.return_value = 0
        p.process = proc; p.pipe = 'fake'; p.current_url = 'https://stream.test/a'
        with patch.object(p, '_close_ipc') as close_ipc:
            p.stop()
        proc.terminate.assert_not_called()
        close_ipc.assert_called_once()
        self.assertIsNone(p.process)
        self.assertEqual(p.current_url, '')
        self.assertIsNone(p.pipe)

    def test_play_launch_failure_does_not_leave_half_started_backend_state(self):
        p = MPVBackend()
        with patch.object(p, 'stop'), \
             patch.object(p, '_exe', return_value='mpv.exe'), \
             patch.object(p, '_close_ipc') as close_ipc, \
             patch('ultrastalker_desktop.player.mpv_backend.subprocess.Popen', side_effect=OSError('blocked')):
            with self.assertRaises(OSError):
                p.play('https://stream.test/live')
        close_ipc.assert_called_once()
        self.assertIsNone(p.process)
        self.assertEqual(p.current_url, '')
        self.assertIsNone(p.pipe)

    def test_windows_launch_hides_console_without_hiding_video_window(self):
        p = MPVBackend()
        fake_process = type('P', (), {'poll': lambda self: None})()
        with patch.object(p, 'stop'), \
             patch.object(p, '_exe', return_value='mpv.exe'), \
             patch('ultrastalker_desktop.player.mpv_backend.os.name', 'nt'), \
             patch('ultrastalker_desktop.player.mpv_backend.subprocess.Popen', return_value=fake_process) as popen:
            p.play('http://example.test/stream')
        kwargs = popen.call_args.kwargs
        self.assertEqual(kwargs['creationflags'], 0x08000000)
        self.assertNotIn('startupinfo', kwargs)
        args = popen.call_args.args[0]
        self.assertIn('--force-window=yes', args)

    def test_startup_event_file_loaded_is_success(self):
        p = MPVBackend()
        p.process = Mock()
        p.process.poll.return_value = None
        p._open = Mock(return_value=True)
        p._events.put({'event': 'file-loaded'})
        self.assertEqual(p._wait_for_startup(0.2), 'loaded')

    def test_startup_event_end_file_is_failure(self):
        p = MPVBackend()
        p.process = Mock()
        p.process.poll.return_value = None
        p._open = Mock(return_value=True)
        p._events.put({'event': 'end-file', 'reason': 'error'})
        self.assertEqual(p._wait_for_startup(0.2), 'failed')

    def test_play_candidates_keeps_slow_source_when_startup_event_times_out(self):
        p = MPVBackend()
        proc = Mock(); proc.poll.return_value = None
        def fake_play(_url, _start=0):
            p.process = proc
        p.play = Mock(side_effect=fake_play)
        p._wait_for_startup = Mock(return_value='timeout')
        chosen = p.play_candidates(['http://slow.test/live'], settle_seconds=0.01)
        self.assertEqual(chosen, 'http://slow.test/live')
        p.play.assert_called_once()

    def test_play_candidates_uses_next_source_after_startup_failure(self):
        p = MPVBackend()
        first = Mock(); first.poll.return_value = None
        second = Mock(); second.poll.return_value = None
        processes = iter([first, second])
        def fake_play(_url, _start=0):
            p.process = next(processes)
        p.play = Mock(side_effect=fake_play)
        p._wait_for_startup = Mock(side_effect=['failed', 'loaded'])
        chosen = p.play_candidates(['http://one.test/a', 'http://two.test/b'])
        self.assertEqual(chosen, 'http://two.test/b')
        self.assertEqual(p.play.call_count, 2)

    def test_play_candidates_honors_cancellation_before_start(self):
        p = MPVBackend()
        with patch.object(p, 'play') as play:
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                p.play_candidates(['http://example.test/stream'], should_cancel=lambda: True)
            play.assert_not_called()

    def test_overlapping_play_requests_do_not_let_old_request_kill_new_process(self):
        p = MPVBackend()
        first_process = Mock(); first_process.poll.return_value = None
        second_process = Mock(); second_process.poll.return_value = None
        first_started = threading.Event()
        release_first = threading.Event()
        cancel_first = threading.Event()
        play_order = []

        def fake_play(url, start=0):
            play_order.append(url)
            if 'old' in url:
                p.process = first_process
                first_started.set()
            else:
                p.process = second_process

        def fake_wait(_timeout, should_cancel=None):
            if p.process is first_process:
                release_first.wait(1.0)
                return 'failed'
            return 'loaded'

        def fake_stop():
            p.process = None

        p.play = Mock(side_effect=fake_play)
        p._wait_for_startup = Mock(side_effect=fake_wait)
        p.stop = Mock(side_effect=fake_stop)
        results = {}

        def run_old():
            try:
                results['old'] = p.play_candidates(
                    ['http://old.test/a'],
                    should_cancel=lambda: cancel_first.is_set(),
                )
            except Exception as exc:
                results['old_error'] = str(exc)

        def run_new():
            results['new'] = p.play_candidates(['http://new.test/b'])

        t1 = threading.Thread(target=run_old)
        t1.start()
        self.assertTrue(first_started.wait(1.0))
        cancel_first.set()
        t2 = threading.Thread(target=run_new)
        t2.start()
        # New startup must remain serialized until the stale request observes
        # cancellation and relinquishes ownership of the shared backend.
        time.sleep(0.03)
        self.assertEqual(play_order, ['http://old.test/a'])
        release_first.set()
        t1.join(1.0); t2.join(1.0)

        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())
        self.assertIn('cancelled', results.get('old_error', '').lower())
        self.assertEqual(results.get('new'), 'http://new.test/b')
        self.assertIs(p.process, second_process)
        self.assertEqual(play_order, ['http://old.test/a', 'http://new.test/b'])



if __name__ == '__main__':
    unittest.main()
