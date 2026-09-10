from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ultrastalker_desktop.player.mpv_backend import MPVBackend


@unittest.skipIf(os.name == "nt", "POSIX fake-mpv IPC integration is for non-Windows CI/dev only")
class PlayerProcessIntegrationTests(unittest.TestCase):
    def test_real_subprocess_unix_ipc_play_progress_pause_and_stop(self):
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "fake-mpv"
            script.write_text(
                r'''#!/usr/bin/env python3
import json
import os
import signal
import socket
import sys
import time

pipe = ""
for arg in sys.argv[1:]:
    if arg.startswith("--input-ipc-server="):
        pipe = arg.split("=", 1)[1]
        break
if not pipe:
    raise SystemExit(4)
try:
    os.unlink(pipe)
except FileNotFoundError:
    pass

running = True
def stop(_sig, _frame):
    global running
    running = False
signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(pipe)
server.listen(1)
server.settimeout(5)
conn, _ = server.accept()
fp = conn.makefile("rwb", buffering=0)
fp.write((json.dumps({"event": "file-loaded"}) + "\n").encode())
paused = False
while running:
    line = fp.readline()
    if not line:
        time.sleep(0.01)
        continue
    request = json.loads(line.decode())
    cmd = request.get("command") or []
    rid = request.get("request_id")
    data = None
    if cmd[:2] == ["get_property", "time-pos"]:
        data = 12.5
    elif cmd[:2] == ["get_property", "duration"]:
        data = 100.0
    elif cmd[:2] == ["get_property", "pause"]:
        data = paused
    elif len(cmd) >= 3 and cmd[:2] == ["set_property", "pause"]:
        paused = bool(cmd[2])
    elif cmd[:2] == ["get_property", "fullscreen"]:
        data = False
    elif cmd[:2] == ["get_property", "aid"]:
        data = 1
    elif cmd[:2] == ["get_property", "sid"]:
        data = "no"
    elif cmd[:2] == ["get_property", "track-list"]:
        data = [{"type": "audio", "id": 1, "lang": "eng"}]
    response = {"error": "success", "request_id": rid, "data": data}
    fp.write((json.dumps(response) + "\n").encode())

try:
    fp.close()
    conn.close()
    server.close()
finally:
    try:
        os.unlink(pipe)
    except FileNotFoundError:
        pass
''',
                encoding="utf-8",
            )
            script.chmod(0o755)

            player = MPVBackend()
            with patch.object(player, "_exe", return_value=str(script)):
                chosen = player.play_candidates(
                    ["http://provider.invalid/live/1"], settle_seconds=2.0
                )
                self.assertEqual(chosen, "http://provider.invalid/live/1")
                self.assertIsNotNone(player.process)
                self.assertIsNone(player.process.poll())
                self.assertEqual(player.progress(), (12.5, 100.0))
                self.assertFalse(player.is_paused())
                player.pause()
                self.assertTrue(player.is_paused())
                tracks = player.audio_tracks()
                self.assertEqual(tracks[0]["id"], 1)
                pipe_path = player.pipe
                process = player.process
                player.stop()

            self.assertIsNotNone(process.poll())
            self.assertIsNone(player.process)
            self.assertIsNone(player.pipe)
            self.assertFalse(Path(pipe_path).exists())


if __name__ == "__main__":
    unittest.main()
