from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import socket
import threading
import time
import uuid

from .base import PlayerBackend
from ultrastalker_desktop.runtime import resource_candidates

log = logging.getLogger(__name__)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


class PlaybackCancelled(RuntimeError):
    """Internal control-flow exception for a superseded playback request."""


class MPVBackend(PlayerBackend):
    def __init__(self):
        self.process = None
        self.pipe = None
        self.fp = None
        self.lock = threading.Lock()
        self.current_url = ""
        self._request_id = 0
        self._responses = queue.Queue()
        self._events = queue.Queue()
        self._reader_thread = None
        self._reader_stop = threading.Event()
        self._play_sequence_lock = threading.RLock()

    def _exe(self):
        for path in resource_candidates("mpv.exe"):
            if path.is_file():
                return str(path)
        return shutil.which("mpv") or shutil.which("mpv.exe")

    def play_candidates(self, urls, start=0, settle_seconds=4.0, should_cancel=None):
        """Serialize startup/fallback sequences on the shared mpv backend.

        UI generation checks cancel stale requests, but two worker threads can
        still overlap between that check and ``play()``. Serializing the whole
        startup sequence prevents an older request from replacing or stopping a
        newer process. The lock lives on a worker thread, so the Qt UI remains
        responsive while a superseded request exits.
        """
        with self._play_sequence_lock:
            return self._play_candidates_locked(
                urls, start, settle_seconds, should_cancel
            )

    def _play_candidates_locked(self, urls, start=0, settle_seconds=4.0, should_cancel=None):
        """Try sources in order and use mpv startup events when possible."""
        last = None
        for url in [x for x in urls if x]:
            if should_cancel and should_cancel():
                raise PlaybackCancelled("Playback request cancelled")
            try:
                log.info("Trying playback candidate %s", self._safe_url(url))
                self.play(url, start)
                candidate_process = self.process
                startup = self._wait_for_startup(settle_seconds, should_cancel=should_cancel)
                if should_cancel and should_cancel():
                    # Never kill a newer playback request that may already have
                    # replaced this process on the shared backend.
                    if self.process is candidate_process:
                        self.stop()
                    raise PlaybackCancelled("Playback request cancelled")
                if startup == "loaded" and self.process is candidate_process:
                    return url
                if startup == "failed":
                    last = RuntimeError("Playback source failed during startup")
                    continue
                # If mpv did not emit a definitive event within the bounded
                # startup window, preserve support for slow portals/streams.
                if candidate_process and candidate_process.poll() is None and self.process is candidate_process:
                    return url
                last = RuntimeError("Playback source exited during startup")
            except PlaybackCancelled:
                raise
            except Exception as exc:
                last = exc
                log.warning("Playback candidate failed: %s", type(exc).__name__)
        self.stop()
        raise last or RuntimeError("No playable source available")

    def _wait_for_startup(self, timeout: float, should_cancel=None) -> str:
        """Return ``loaded``, ``failed`` or ``timeout`` for the current mpv file."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        # Opening IPC is best-effort.  If it is not ready, the caller still has
        # the process-liveness fallback used by earlier releases.
        if not self._open():
            return "timeout"
        while True:
            if should_cancel and should_cancel():
                return "failed"
            if not self.process or self.process.poll() is not None:
                return "failed"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "timeout"
            try:
                obj = self._events.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                continue
            event = str(obj.get("event") or "")
            if event == "file-loaded":
                return "loaded"
            if event == "end-file":
                # Any end-file during startup means this candidate never became
                # a usable playback session, regardless of eof/error reason.
                return "failed"
            # Ignore start-file, metadata-update and unrelated async events.

    @staticmethod
    def _safe_url(url: str) -> str:
        # Avoid writing embedded username/password values to logs.
        try:
            from urllib.parse import urlsplit, urlunsplit
            p = urlsplit(url)
            host = p.hostname or ""
            if p.port:
                host += f":{p.port}"
            return urlunsplit((p.scheme, host, "/<redacted>", "", ""))
        except Exception:
            return "<stream>"

    def play(self, url, start=0):
        self.stop()
        exe = self._exe()
        if not exe:
            raise RuntimeError(
                "mpv.exe was not found beside Ultra Stalker Desktop. "
                "Reinstall the application using a complete release package."
            )
        self.current_url = url
        if os.name == "nt":
            self.pipe = r"\\.\pipe\ultrastalker_" + uuid.uuid4().hex
        else:
            self.pipe = os.path.join("/tmp", "ultrastalker_" + uuid.uuid4().hex + ".sock")
        args = [
            exe,
            "--force-window=yes",
            "--hwdec=auto-safe",
            "--keep-open=no",
            "--cache=yes",
            "--demuxer-max-bytes=64MiB",
            "--network-timeout=15",
            "--input-ipc-server=" + self.pipe,
        ]
        if start and start > 5:
            args += ["--start=" + str(float(start))]
        args.append(url)
        # Suppress mpv's console window on Windows without using SW_HIDE.
        # STARTF_USESHOWWINDOW/SW_HIDE can also hide the actual video window on
        # some mpv/Windows combinations. CREATE_NO_WINDOW only detaches the
        # console subsystem and leaves mpv's video window visible.
        creationflags = CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            self.fp = None
        except Exception:
            # Keep direct PlayerBackend.play() exception-safe too. Candidate
            # playback normally performs a final stop(), but callers should
            # never observe a half-started backend merely because process launch
            # itself failed (missing DLL, blocked executable, etc.).
            self._close_ipc()
            self.process = None
            self.current_url = ""
            self.pipe = None
            raise

    def _open(self):
        if self.fp:
            self._start_reader()
            return True
        if not self.pipe:
            return False
        # mpv creates the IPC endpoint shortly after process startup.
        for _ in range(40):
            if not self.process or self.process.poll() is not None:
                return False
            try:
                if os.name == "nt":
                    # Windows mpv exposes a named pipe. Python's binary open is
                    # sufficient once the pipe exists and keeps the dependency
                    # surface small (no pywin32 requirement).
                    self.fp = open(self.pipe, "r+b", buffering=0)
                else:
                    # On Unix the IPC endpoint is a Unix-domain socket, not a
                    # regular file. Keep this path correct for CI/dev runs too.
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    sock.settimeout(0.8)
                    sock.connect(self.pipe)
                    self.fp = sock.makefile("rwb", buffering=0)
                    self._ipc_socket = sock
                self._start_reader()
                return True
            except Exception:
                try:
                    sock.close()  # type: ignore[name-defined]
                except Exception:
                    pass
                time.sleep(0.05)
        return False

    def _start_reader(self):
        if self._reader_thread and self._reader_thread.is_alive():
            return
        self._reader_stop.clear()
        for pending in (self._responses, self._events):
            while True:
                try:
                    pending.get_nowait()
                except queue.Empty:
                    break

        def reader():
            fp = self.fp
            while not self._reader_stop.is_set() and fp is not None:
                try:
                    line = fp.readline()
                    if not line:
                        if self._reader_stop.is_set():
                            break
                        time.sleep(0.01)
                        continue
                    obj = json.loads(line.decode("utf-8", "replace"))
                    if isinstance(obj, dict):
                        # mpv multiplexes asynchronous events and command
                        # responses on one IPC stream. Keep them in separate
                        # queues so startup detection and UI commands cannot
                        # consume each other's messages from different threads.
                        if obj.get("request_id") is not None:
                            self._responses.put(obj)
                        else:
                            self._events.put(obj)
                except Exception:
                    break

        self._reader_thread = threading.Thread(
            target=reader, name="UltraStalker-mpv-ipc", daemon=True
        )
        self._reader_thread.start()

    def _close_ipc(self):
        self._reader_stop.set()
        if self.fp:
            try:
                self.fp.close()
            except Exception:
                pass
        self.fp = None
        sock = getattr(self, "_ipc_socket", None)
        if sock:
            try:
                sock.close()
            except Exception:
                pass
        self._ipc_socket = None
        thread = self._reader_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.2)
        self._reader_thread = None
        for pending in (self._responses, self._events):
            while True:
                try:
                    pending.get_nowait()
                except queue.Empty:
                    break

    def _command_exchange(self, *args):
        """Return ``(success, data)`` without conflating JSON ``null`` with failure.

        mpv legitimately returns ``data: null`` for successful commands such as
        ``set_property`` and ``seek``.  Keeping transport success separate from
        the payload lets UI controls report a real IPC failure instead of
        announcing success merely because ``None`` is also a valid result.
        """
        # Serialize IPC open + command exchange as one transaction. Progress
        # polling and UI controls may arrive from different threads; allowing
        # both to open the same named pipe concurrently can create duplicate
        # readers or steal the transport from the other command.
        with self.lock:
            if not self._open():
                return False, None
            try:
                self._request_id += 1
                rid = self._request_id
                req = {"command": list(args), "request_id": rid}
                self.fp.write((json.dumps(req) + "\n").encode())
                deadline = time.monotonic() + 1.0
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        log.debug("mpv IPC command timed out: %s", args[0] if args else "command")
                        return False, None
                    try:
                        obj = self._responses.get(timeout=remaining)
                    except queue.Empty:
                        log.debug("mpv IPC command timed out: %s", args[0] if args else "command")
                        return False, None
                    # Responses are isolated from async events by the reader.
                    # The lock serializes commands, but keep the ID check as a
                    # defensive guard against stale responses after an IPC reset.
                    if obj.get("request_id") != rid:
                        continue
                    if obj.get("error") == "success":
                        return True, obj.get("data")
                    log.debug("mpv IPC command failed: %s", obj.get("error"))
                    return False, None
            except Exception as exc:
                log.debug("mpv IPC transport reset: %s", type(exc).__name__)
                self._close_ipc()
        return False, None

    def command(self, *args):
        ok, data = self._command_exchange(*args)
        return data if ok else None

    def get_position(self):
        value = self.command("get_property", "time-pos")
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    def get_duration(self):
        value = self.command("get_property", "duration")
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    def progress(self):
        if not self.process or self.process.poll() is not None:
            return (0.0, 0.0)
        return self.get_position(), self.get_duration()

    @staticmethod
    def _require_command(result, action):
        ok, data = result
        if not ok:
            raise RuntimeError(f"mpv IPC {action} failed")
        return data

    def pause(self):
        self._require_command(self._command_exchange("set_property", "pause", True), "pause")
        return True

    def resume(self):
        self._require_command(self._command_exchange("set_property", "pause", False), "resume")
        return True

    def is_paused(self):
        data = self._require_command(self._command_exchange("get_property", "pause"), "pause status")
        return bool(data)

    def toggle_pause(self):
        paused = self.is_paused()
        if paused:
            self.resume()
            return False
        self.pause()
        return True

    def seek(self, seconds):
        self._require_command(self._command_exchange("seek", float(seconds), "relative"), "seek")
        return True

    def set_volume(self, value):
        volume = max(0.0, min(100.0, float(value)))
        self._require_command(self._command_exchange("set_property", "volume", volume), "volume")
        return True

    def _tracks(self, track_type):
        rows = self.command("get_property", "track-list") or []
        if not isinstance(rows, list):
            return []
        return [x for x in rows if isinstance(x, dict) and x.get("type") == track_type]

    def audio_tracks(self):
        return self._tracks("audio")

    def subtitle_tracks(self):
        return self._tracks("sub")

    def toggle_fullscreen(self):
        self._require_command(self._command_exchange("cycle", "fullscreen"), "fullscreen toggle")
        return bool(self._require_command(self._command_exchange("get_property", "fullscreen"), "fullscreen status"))

    def cycle_audio_track(self):
        self._require_command(self._command_exchange("cycle", "aid"), "audio track cycle")
        return self._require_command(self._command_exchange("get_property", "aid"), "audio track status")

    def cycle_subtitle_track(self):
        self._require_command(self._command_exchange("cycle", "sid"), "subtitle track cycle")
        return self._require_command(self._command_exchange("get_property", "sid"), "subtitle track status")

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                    # Reap the killed child as well. Calling kill() without a
                    # subsequent wait can leave a zombie/resource warning and
                    # leak process handles across repeated playback sessions.
                    self.process.wait(timeout=1)
                except Exception:
                    pass
        # Closing a Windows named pipe after mpv exits guarantees a blocked
        # reader is released instead of risking a UI-thread hang on stop.
        self._close_ipc()
        self.process = None
        self.current_url = ""
        if self.pipe and os.name != "nt":
            try:
                os.unlink(self.pipe)
            except Exception:
                pass
        self.pipe = None
