from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ultrastalker_desktop" / "ui" / "main_window.py"


class MainWindowSourceSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = UI.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.text, filename=str(UI))

    def test_worker_signals_dispatch_through_main_window_slots(self):
        self.assertIn("w.done.connect(self._worker_done)", self.text)
        self.assertIn("w.failed.connect(self._worker_failed)", self.text)
        self.assertIn("w.finished.connect(self._worker_finished)", self.text)
        self.assertNotIn("w.done.connect(lambda", self.text)
        self.assertNotIn("w.failed.connect(lambda", self.text)

    def test_periodic_progress_poll_is_not_synchronous_ui_save(self):
        self.assertIn("self.poll.timeout.connect(self.poll_progress)", self.text)
        self.assertNotIn("self.poll.timeout.connect(self.save_progress)", self.text)
        self.assertIn("self.progress_poll_active", self.text)

    def test_navigation_boundaries_cancel_stale_work(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        return_home = ast.get_source_segment(self.text, functions["return_home"]) or ""
        browser_back = ast.get_source_segment(self.text, functions["browser_back"]) or ""
        self.assertIn("connection_generation", return_home)
        self.assertIn("request_generation", browser_back)
        self.assertIn("artwork_generation", browser_back)

    def test_player_controls_require_ready_playback(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        helper = ast.get_source_segment(self.text, functions["_player_control"]) or ""
        self.assertIn("if not self._playback_active():return", helper)
        for name in ("pause_resume", "seek_by", "toggle_fullscreen", "cycle_audio", "cycle_subtitle"):
            body = ast.get_source_segment(self.text, functions[name]) or ""
            self.assertIn("self._player_control", body)
        volume = ast.get_source_segment(self.text, functions["adjust_volume"]) or ""
        self.assertIn("self._apply_volume_async()", volume)

    def test_player_controls_do_not_call_mpv_ipc_directly_from_gui_handlers(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        player_calls = {"set_volume", "seek", "toggle_pause", "toggle_fullscreen", "cycle_audio_track", "cycle_subtitle_track"}
        for name in ("pause_resume", "seek_by", "adjust_volume", "toggle_fullscreen", "cycle_audio", "cycle_subtitle"):
            fn = functions[name]
            parents = {}
            for parent in ast.walk(fn):
                for child in ast.iter_child_nodes(parent):
                    parents[child] = parent
            for node in ast.walk(fn):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                owner = node.func.value
                if not (isinstance(owner, ast.Attribute) and isinstance(owner.value, ast.Name) and owner.value.id == "self" and owner.attr == "player"):
                    continue
                if node.func.attr not in player_calls:
                    continue
                cur = node
                inside_lambda = False
                while cur in parents:
                    cur = parents[cur]
                    if isinstance(cur, ast.Lambda):
                        inside_lambda = True
                        break
                    if isinstance(cur, ast.FunctionDef):
                        break
                self.assertTrue(inside_lambda, f"{name} performs {node.func.attr} synchronously on the GUI thread")

    def test_async_player_controls_are_bound_to_same_playback_process(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        helper = ast.get_source_segment(self.text, functions["_player_control"]) or ""
        volume = ast.get_source_segment(self.text, functions["_apply_volume_async"]) or ""
        for body in (helper, volume):
            self.assertIn("generation==self.play_request_generation", body.replace(" ", ""))
            self.assertIn("processisself.player.process", body.replace(" ", ""))
            self.assertIn("itemisself.current_playing", body.replace(" ", ""))


    def test_worker_cleanup_runs_from_finished_even_for_stale_results(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        finished = ast.get_source_segment(self.text, functions["_worker_finished"]) or ""
        work = ast.get_source_segment(self.text, functions["work"]) or ""
        self.assertIn("cleanup_callback", finished)
        self.assertIn("_invoke_worker_callback", finished)
        self.assertIn("cleanup=None", work)
        self.assertIn("w.cleanup_callback=cleanup", work.replace(" ", ""))

    def test_worker_callback_failures_are_contained_without_raw_exception_text(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        invoke = ast.get_source_segment(self.text, functions["_invoke_worker_callback"]) or ""
        failed = ast.get_source_segment(self.text, functions["_worker_failed"]) or ""
        self.assertIn("except Exception as exc", invoke)
        self.assertIn("type(exc).__name__", invoke)
        self.assertNotIn("str(exc)", invoke)
        self.assertIn("error_callback", failed)

    def test_progress_poll_flag_is_released_by_worker_cleanup(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        poll = ast.get_source_segment(self.text, functions["poll_progress"]) or ""
        self.assertIn("def cleanup()", poll)
        self.assertIn("self.progress_poll_active=False", poll.replace(" ", ""))
        self.assertIn("cleanup=cleanup", poll)

    def test_long_running_worker_failures_clear_busy_status(self):
        for status in ("Connection failed", "Could not load categories", "Could not load items", "Could not load episodes", "Playback failed"):
            self.assertIn(status, self.text)

    def test_shutdown_is_global_cancellation_boundary(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        close = ast.get_source_segment(self.text, functions["closeEvent"]) or ""
        work = ast.get_source_segment(self.text, functions["work"]) or ""
        artwork = ast.get_source_segment(self.text, functions["_load_selected_artwork"]) or ""
        for token in ("self.closing=True", "self.connection_generation+=1", "self.request_generation+=1", "self.artwork_generation+=1", "self.play_request_generation+=1"):
            self.assertIn(token, close.replace(" ", ""))
        self.assertIn("if self.closing:return None", work)
        self.assertIn("if self.closing or", artwork)

    def test_close_event_stops_player_only_once_across_deferred_worker_shutdown(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        close = ast.get_source_segment(self.text, functions["closeEvent"]) or ""
        self.assertIn("first_close=notself.closing", close.replace(" ", ""))
        self.assertIn("if first_close:", close)
    def test_playback_resume_and_initial_history_io_run_inside_worker_task(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        play = ast.get_source_segment(self.text, functions["play_selected"]) or ""
        task_pos = play.index("def task()")
        started_pos = play.index("def started(")
        task = play[task_pos:started_pos]
        started = play[started_pos:]
        self.assertIn("resume_point(source_key,m)", task.replace(" ", ""))
        self.assertIn("add_history(source_key,m,start,dur)", task.replace(" ", ""))
        self.assertNotIn("resume_point(", play[:task_pos])
        self.assertNotIn("add_history(", started)
        self.assertIn("Playback history unavailable", task)

    def test_storage_failures_do_not_destroy_browser_or_episode_flow(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        episodes = ast.get_source_segment(self.text, functions["set_episodes"]) or ""
        self.assertIn("Episode tracking unavailable", episodes)
        for name, token in (("open_favorites", "Favorites unavailable"), ("open_history", "History unavailable")):
            body = ast.get_source_segment(self.text, functions[name]) or ""
            self.assertIn("except Exception as exc", body)
            self.assertIn(token, body)
            try_pos = body.index("try:")
            clear_pos = body.index("self.browser_history.clear()")
            self.assertLess(try_pos, clear_pos)

    def test_successful_connection_remains_usable_when_secure_profile_save_fails(self):
        functions = {n.name: n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == "UltraStalkerWindow" for n in n.body if isinstance(n, ast.FunctionDef)}
        body = ast.get_source_segment(self.text, functions["connect_profile"]) or ""
        self.assertIn("persisted=True", body.replace(" ", ""))
        self.assertIn("persisted=False", body.replace(" ", ""))
        self.assertIn("session only", body)
        self.assertIn("Nothing was saved in plaintext", body)
        self.assertIn("ifpersisted:self.refresh_profiles()", body.replace(" ", ""))
        # The active in-memory session is assigned after the save attempt either
        # way, so metadata/vault failure does not invalidate a good connection.
        self.assertIn("self.profile=p", body.replace(" ", ""))
        self.assertIn("self.adapter=adapter", body.replace(" ", ""))

    def test_navigation_progress_save_never_calls_mpv_ipc_on_gui_thread(self):
        source = (ROOT / 'ultrastalker_desktop' / 'ui' / 'main_window.py').read_text(encoding='utf-8')
        start = source.index('    def save_progress(self):')
        end = source.index('    def favorite(self):', start)
        body = source[start:end]
        self.assertIn('self.last_progress', body)
        self.assertNotIn('self.player.progress()', body)
        poll_start = source.index('    def poll_progress(self):')
        poll_end = source.index('    def save_progress(self):', poll_start)
        poll_body = source[poll_start:poll_end]
        self.assertIn('self.player.progress()', poll_body)
        self.assertIn('self.last_progress=', poll_body.replace(' ', ''))


if __name__ == "__main__":
    unittest.main()
