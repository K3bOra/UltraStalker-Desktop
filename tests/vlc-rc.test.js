/* Reading VLC's remote-control replies (captured from VLC 3.0.20). */
import test from "node:test";
import assert from "node:assert/strict";
import net from "node:net";
import { Rc, parseInfo, parseTracks, parseStats } from "../app/vlc-rc.js";

const INFO = "+----[ Stream 0 ]\r\n| \r\n| Original ID: 256\r\n| Codec: MPEG-H Part2/HEVC (H.265) (hevc)\r\n| Type: Video\r\n| Video resolution: 3840x2160\r\n| Buffer dimensions: 3840x2160\r\n| Frame rate: 50\r\n| \r\n+----[ Stream 1 ]\r\n| \r\n| Codec: MPEG Audio layer 1/2 (mpga)\r\n| Type: Audio\r\n| Channels: 3F2R/LFE\r\n| Sample rate: 48000 Hz\r\n| \r\n+----[ end of stream info ]";
const lines = (t) => t.split(/\r?\n/);

test("stream info", () => {
  assert.deepEqual(parseInfo(lines(INFO)), { vcodec: "hevc", width: 3840, height: 2160, fps: 50, acodec: "mp3", channels: "5.1" });
});
test("tracks", () => {
  const t = parseTracks(lines("+----[ Audio Track ]\r\n| -1 - Disable\r\n| 257 - Track 1 - [English] *\r\n| 258 - Track 2 - [Arabic]\r\n+----[ end of Audio Track ]"));
  assert.deepEqual(t, [{ id: -1, name: "Disable", on: false }, { id: 257, name: "English", on: true }, { id: 258, name: "Arabic", on: false }]);
});
test("track names as VLC writes them", () => {
  const t = parseTracks(lines("+----[ Audio Track ]\r\n| -1 - Disable\r\n| 1 - English - [English] *\r\n| 2 - Commentary - [English]\r\n| 3 - Track 3 - [Arabic]\r\n+----[ end of Audio Track ]"));
  assert.deepEqual(t.map((x) => x.name), ["Disable", "English", "Commentary · English", "Arabic"]);
  assert.equal(t[1].on, true);
});
test("stats", () => {
  assert.deepEqual(parseStats(lines("+-[Video Decoding]\r\n| video decoded    :      307\r\n| frames displayed :      127\r\n| frames lost      :        2")), { shown: 127, lost: 2, decoded: 307 });
});
test("command replies over the socket", async () => {
  // a tiny stand-in for VLC with its reply shapes, status changes mixed in
  const srv = net.createServer((c) => {
    c.on("data", (d) => {
      for (const cmd of String(d).split("\n").filter(Boolean)) {
        if (cmd === "get_time") c.write("status change: ( play state: 3 )\r\n42\r\n");
        else if (cmd === "info") c.write(INFO + "\r\n");
        else if (cmd === "pause") c.write("pause: returned 0 (no error)\r\nstatus change: ( pause state: 3 ): Pause\r\n");
        else c.write("Trying to add x to playlist.\r\n" + cmd.split(" ")[0] + ": returned 0 (no error)\r\n");
      }
    });
  });
  await new Promise((r) => srv.listen(0, "127.0.0.1", r));
  const sock = net.connect(srv.address().port, "127.0.0.1");
  await new Promise((r) => sock.once("connect", r));
  const rc = new Rc(sock);
  const [time, info, add] = await Promise.all([rc.number("get_time"), rc.cmd("info", { block: /end of stream info/ }), rc.cmd("add http://x")]);
  assert.equal(time, 42);
  assert.equal(parseInfo(info).width, 3840);
  assert.deepEqual(add, ["Trying to add x to playlist."]);
  await rc.cmd("pause");
  await new Promise((r) => setTimeout(r, 30));
  assert.equal(rc.state, "paused");
  sock.destroy();
  srv.close();
});

test("a paused VLC prompt completes the request without waiting for a timeout", async () => {
  const { EventEmitter } = await import("node:events");
  const sock = new EventEmitter();
  sock.setEncoding = sock.setNoDelay = () => {};
  sock.write = () => queueMicrotask(() => sock.emit("data", "Type 'pause' to continue.\r\n"));
  const rc = new Rc(sock);
  const reply = await Promise.race([
    rc.cmd("status"),
    new Promise((_, reject) => setTimeout(() => reject(new Error("paused prompt stalled")), 200)),
  ]);
  assert.deepEqual(reply, ["Type 'pause' to continue."]);
});
