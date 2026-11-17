/* The local server: interface with isolation headers, relay answering, path safety. */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { startServer } from "../app/server.js";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const bundle = path.join(root, "bundle");

test("local server", { skip: !fs.existsSync(path.join(bundle, "web", "index.html")) && "run npm run bundle first" }, async () => {
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), "us-test-"));
  const { server, origin } = await startServer({
    webDir: path.join(bundle, "web"),
    relayFile: path.join(bundle, "relay", "index.mjs"),
    appCssFile: path.join(root, "app", "desktop-app.css"),
    userDir,
    port: 47391,
    cloudRelay: "https://example.invalid",
    version: "test",
  });
  try {
    const page = await fetch(origin + "/");
    assert.equal(page.status, 200);
    assert.equal(page.headers.get("cross-origin-embedder-policy"), "credentialless");
    assert.equal(page.headers.get("cross-origin-opener-policy"), "same-origin");
    const html = await page.text();
    assert.match(html, /us-app/);
    assert.match(html, /usAppCss/);

    const cfg = await (await fetch(origin + "/config.js")).text();
    assert.match(cfg, new RegExp(origin.replace(/[.:/]/g, "\\$&")));

    const health = await (await fetch(origin + "/health")).json();
    assert.equal(health.ok, true);
    assert.equal(health.tickets, true);

    const escape = await fetch(origin + "/..%2f..%2fpackage.json");
    assert.notEqual(escape.status, 200);

    // a relay request with this page as origin is accepted (a bad URL gives 400, not 403)
    const bad = await fetch(origin + "/p?u=notaurl", { headers: { Origin: origin } });
    assert.equal(bad.status, 400);
    // the same request from another site is refused
    const foreign = await fetch(origin + "/p?u=http://example.com/", { headers: { Origin: "https://evil.example" } });
    assert.equal(foreign.status, 403);

    // the relay key persists per installation
    const key1 = fs.readFileSync(path.join(userDir, "relay.key"), "utf8");
    assert.match(key1, /^[0-9a-f]{64}$/);
  } finally {
    server.close();
  }
});
