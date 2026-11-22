/* Recording keeps a copy of a live channel as it passes through the local server. */
import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { startServer, createRecorder } from "../app/server.js";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
test("a live channel played through /play is copied into the recording", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "us-rec-"));
  const chunk = Buffer.alloc(188 * 50, 0x47);
  const upstream = http.createServer((req, res) => {
    if (req.url.endsWith(".m3u8")) {
      res.writeHead(200, { "Content-Type": "application/vnd.apple.mpegurl" });
      return res.end("#EXTM3U\n#EXTINF:2,\nseg1.ts\n");
    }
    res.writeHead(200, { "Content-Type": "video/mp2t" });
    let n = 0;
    const t = setInterval(() => (n++ < 4 ? res.write(chunk) : (clearInterval(t), res.end())), 20);
  });
  await new Promise((r) => upstream.listen(0, "127.0.0.1", r));
  const recorder = createRecorder();
  const { server, origin } = await startServer({
    webDir: path.join(root, "bundle", "web"), relayFile: path.join(root, "bundle", "relay", "index.mjs"),
    appCssFile: path.join(root, "app", "desktop-app.css"), userDir: dir, port: 47620, cloudRelay: "https://example.invalid", version: "test", recorder,
  });
  try {
    const ticket = async (u) => (await (await fetch(origin + "/ticket", { method: "POST", headers: { Origin: origin, "Content-Type": "application/json" }, body: JSON.stringify({ mode: "direct", u }) })).json()).url;
    const live = await ticket(`http://127.0.0.1:${upstream.address().port}/live/1.ts`);
    // not recording: nothing is kept
    assert.equal((await (await fetch(live)).arrayBuffer()).byteLength, chunk.length * 4);
    const file = path.join(dir, "out", "Channel.ts");
    recorder.start(file);
    assert.equal((await (await fetch(live)).arrayBuffer()).byteLength, chunk.length * 4);
    // a playlist is not part of the picture
    const list = await ticket(`http://127.0.0.1:${upstream.address().port}/live/1.m3u8`);
    await (await fetch(list)).text();
    assert.equal(recorder.status().bytes, chunk.length * 4);
    const r = recorder.stop();
    assert.equal(r.bytes, chunk.length * 4);
    await new Promise((ok) => setTimeout(ok, 100));
    assert.equal(fs.statSync(file).size, chunk.length * 4);
    // a recording that got nothing leaves no empty file behind
    const empty = path.join(dir, "out", "Empty.ts");
    recorder.start(empty);
    recorder.stop();
    await new Promise((ok) => setTimeout(ok, 100));
    assert.equal(fs.existsSync(empty), false);
  } finally {
    server.closeAllConnections();
    await new Promise((r) => server.close(r));
    upstream.close();
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
