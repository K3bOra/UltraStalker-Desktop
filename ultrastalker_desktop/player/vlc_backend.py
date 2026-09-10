from __future__ import annotations

import logging
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

from .base import PlayerBackend
from ultrastalker_desktop.runtime import resource_candidates

log = logging.getLogger(__name__)


class PlaybackCancelled(RuntimeError):
    """Internal control-flow exception for a superseded playback request."""


class VLCBackend(PlayerBackend):
    """Drive a dedicated VLC process through VLC's localhost RC interface.

    VLC is intentionally treated as an external player runtime.  The backend
    auto-detects normal Windows installations and keeps one isolated VLC
    process per Ultra Stalker playback session.  No provider URL is written to
    logs.
    """

    def __init__(self):
        self.process = None
        self.current_url = ""
        self._port = None
        self._sock = None
        self._sock_file = None
        self._io_lock = threading.RLock()
        self._play_sequence_lock = threading.RLock()
        self._paused = False
        self._fullscreen = False

    def _exe(self):
        override = os.environ.get("ULTRASTALKER_VLC_EXE", "").strip()
        if override and Path(override).is_file():
            return override

        # Support an optional portable VLC folder beside the packaged app
        # without requiring that VLC be bundled by Ultra Stalker itself.
        for relative in ("VLC/vlc.exe", "vlc/vlc.exe", "vlc.exe"):
            for path in resource_candidates(relative):
                if path.is_file():
                    return str(path)

        seen = set()
        candidates = []
        for env_name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(env_name)
            if base:
                candidates.append(Path(base) / "VideoLAN" / "VLC" / "vlc.exe")
        for path in candidates:
            key = str(path).casefold()
            if key in seen:
                continue
            seen.add(key)
            if path.is_file():
                return str(path)

        return shutil.which("vlc") or shutil.which("vlc.exe")

    @staticmethod
    def _safe_url(url: str) -> str:
        try:
            from urllib.parse import urlsplit, urlunsplit

            p = urlsplit(url)
            host = p.hostname or ""
            if p.port:
                host += f":{p.port}"
            return urlunsplit((p.scheme, host, "/<redacted>", "", ""))
        except Exception:
            return "<stream>"

    @staticmethod
    def _reserve_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])

    def play_candidates(self, urls, start=0, settle_seconds=5.0, should_cancel=None):
        with self._play_sequence_lock:
            last = None
            for url in [x for x in urls if x]:
                if should_cancel and should_cancel():
                    raise PlaybackCancelled("Playback request cancelled")
                try:
                    log.info("Trying VLC playback candidate %s", self._safe_url(url))
                    self.play(url, start)
                    candidate_process = self.process
                    startup = self._wait_for_startup(
                        settle_seconds, should_cancel=should_cancel
                    )
                    if should_cancel and should_cancel():
                        if self.process is candidate_process:
                            self.stop()
                        raise PlaybackCancelled("Playback request cancelled")
                    if startup == "loaded" and self.process is candidate_process:
                        return url
                    if startup == "failed":
                        last = RuntimeError("Playback source failed during VLC startup")
                        continue
                    if (
                        candidate_process
                        and candidate_process.poll() is None
                        and self.process is candidate_process
                    ):
                        return url
                    last = RuntimeError("VLC exited during playback startup")
                except PlaybackCancelled:
                    raise
                except Exception as exc:
                    last = exc
                    log.warning("VLC playback candidate failed: %s", type(exc).__name__)
            self.stop()
            raise last or RuntimeError("No playable source available")

    def play(self, url: str, start: float = 0) -> None:
        self.stop()
        exe = self._exe()
        if not exe:
            raise RuntimeError(
                "VLC Media Player was not found. Install VLC 64-bit in its normal "
                "Windows location, or set ULTRASTALKER_VLC_EXE to vlc.exe."
            )

        self.current_url = url
        self._paused = False
        self._fullscreen = False
        self._port = self._reserve_port()

        args = [
            exe,
            "--intf=dummy",
            "--extraintf=rc",
            f"--rc-host=127.0.0.1:{self._port}",
            "--rc-quiet",
            "--no-one-instance",
            "--no-video-title-show",
            "--play-and-exit",
            "--network-caching=1500",
            "--live-caching=1500",
            "--file-caching=1000",
            "--http-reconnect",
            "--quiet",
        ]
        if start and start > 5:
            args.append(f"--start-time={float(start)}")
        args.append(url)

        try:
            # vlc.exe is a GUI executable.  Do not use SW_HIDE or detached
            # process flags because the actual video window must remain visible.
            self.process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0,
            )
        except Exception:
            self._close_rc()
            self.process = None
            self.current_url = ""
            self._port = None
            raise

    def _connect_rc(self, timeout: float = 0.25) -> bool:
        if self._sock is not None:
            return True
        if not self._port or not self.process or self.process.poll() is not None:
            return False
        try:
            sock = socket.create_connection(("127.0.0.1", self._port), timeout=timeout)
            sock.settimeout(0.12)
            self._sock = sock
            self._sock_file = sock.makefile("rwb", buffering=0)
            # Drain VLC's greeting/prompt so numeric queries cannot accidentally
            # parse a version number from the banner.
            self._drain_rc()
            return True
        except Exception:
            self._close_rc()
            return False

    def _drain_rc(self) -> str:
        if self._sock is None:
            return ""
        chunks = []
        while True:
            try:
                part = self._sock.recv(4096)
                if not part:
                    break
                chunks.append(part)
                if len(part) < 4096:
                    # Give the prompt a tiny chance to arrive in the same burst.
                    time.sleep(0.005)
            except socket.timeout:
                break
            except Exception:
                break
        return b"".join(chunks).decode("utf-8", "replace")

    def _rc_command(self, command: str, *, require_connection: bool = True) -> str:
        with self._io_lock:
            if not self._connect_rc():
                if require_connection:
                    raise RuntimeError("VLC control interface is unavailable")
                return ""
            try:
                self._drain_rc()
                self._sock_file.write((command + "\n").encode("utf-8"))
                time.sleep(0.015)
                return self._drain_rc()
            except Exception:
                self._close_rc()
                if require_connection:
                    raise RuntimeError("VLC control interface is unavailable")
                return ""

    def _wait_for_startup(self, timeout: float, should_cancel=None) -> str:
        deadline = time.monotonic() + max(0.0, float(timeout))
        playing_since = None
        while True:
            if should_cancel and should_cancel():
                return "failed"
            if not self.process or self.process.poll() is not None:
                return "failed"
            now = time.monotonic()
            if self._connect_rc(timeout=0.12):
                try:
                    playing = self._number_from_response(
                        self._rc_command("is_playing", require_connection=False)
                    )
                except Exception:
                    playing = 0.0
                if playing >= 1.0:
                    if playing_since is None:
                        playing_since = now
                    # Keep the candidate alive for a short confirmation window
                    # instead of declaring success on the first transient input.
                    if now - playing_since >= 0.25:
                        return "loaded"
                else:
                    playing_since = None
            if now >= deadline:
                return "timeout"
            time.sleep(0.08)

    @staticmethod
    def _number_from_response(text: str) -> float:
        for line in reversed((text or "").splitlines()):
            value = line.strip().strip("> ")
            if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
                try:
                    return float(value)
                except Exception:
                    pass
        return 0.0

    def get_position(self) -> float:
        return self._number_from_response(self._rc_command("get_time"))

    def get_duration(self) -> float:
        return self._number_from_response(self._rc_command("get_length"))

    def progress(self):
        if not self.process or self.process.poll() is not None:
            return (0.0, 0.0)
        return self.get_position(), self.get_duration()

    def pause(self) -> None:
        if not self._paused:
            self._rc_command("pause")
            self._paused = True
        return True

    def resume(self) -> None:
        if self._paused:
            self._rc_command("pause")
            self._paused = False
        return True

    def toggle_pause(self):
        if self._paused:
            self.resume()
            return False
        self.pause()
        return True

    def seek(self, seconds: float) -> None:
        current = self.get_position()
        target = max(0.0, current + float(seconds))
        self._rc_command(f"seek {int(target)}")
        return True

    def set_volume(self, value: float) -> None:
        percent = max(0.0, min(100.0, float(value)))
        # VLC RC uses 256 as nominal 100% volume.
        rc_value = int(round(percent * 2.56))
        self._rc_command(f"volume {rc_value}")
        return True

    @staticmethod
    def _parse_tracks(text: str) -> list[dict]:
        rows = []
        for line in (text or "").splitlines():
            # Typical VLC RC output: | 1 - Track name *
            m = re.search(r"\|\s*(-?\d+)\s*-\s*(.*?)(\s+\*)?$", line.strip())
            if not m:
                continue
            rows.append(
                {
                    "id": int(m.group(1)),
                    "title": (m.group(2) or "").strip(),
                    "selected": bool(m.group(3)),
                }
            )
        return rows

    def audio_tracks(self) -> list[dict]:
        return self._parse_tracks(self._rc_command("atrack"))

    def subtitle_tracks(self) -> list[dict]:
        return self._parse_tracks(self._rc_command("strack"))

    def _cycle_track(self, command: str):
        tracks = self._parse_tracks(self._rc_command(command))
        if tracks:
            current = next((i for i, row in enumerate(tracks) if row.get("selected")), -1)
            next_row = tracks[(current + 1) % len(tracks)]
            self._rc_command(f"{command} {next_row['id']}")
            return next_row["id"]
        # VLC's hotkey command is a useful fallback on builds whose RC track
        # listing format differs from the classic interface.
        hotkey = "key-audio-track" if command == "atrack" else "key-subtitle-track"
        self._rc_command(f"key {hotkey}")
        return "next"

    def cycle_audio_track(self):
        return self._cycle_track("atrack")

    def cycle_subtitle_track(self):
        return self._cycle_track("strack")

    def toggle_fullscreen(self):
        self._rc_command("f")
        self._fullscreen = not self._fullscreen
        return self._fullscreen

    def _close_rc(self):
        file_obj = self._sock_file
        self._sock_file = None
        if file_obj is not None:
            try:
                file_obj.close()
            except Exception:
                pass
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    def stop(self) -> None:
        proc = self.process
        if proc and proc.poll() is None:
            try:
                self._rc_command("quit", require_connection=False)
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                        proc.wait(timeout=1)
                    except Exception:
                        pass
        self._close_rc()
        self.process = None
        self.current_url = ""
        self._port = None
        self._paused = False
        self._fullscreen = False
