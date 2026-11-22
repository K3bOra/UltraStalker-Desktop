/* Exercise the bundled website and desktop relay code with in-memory providers.
   No real subscriptions, cloud relay or Electron installation are needed. */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const webDir = path.join(root, "bundle", "web");
const read = (file) => fs.readFileSync(path.join(webDir, file), "utf8");

// Just the DOM operations used by import.js; the actual parser, checker, saving
// and export handlers all run unmodified from the packaged web sources.
class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.listeners = new Map();
    this.textContent = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
  }
  append(...nodes) { this.children.push(...nodes.flatMap((n) => n.tagName === "fragment" ? n.children : [n])); }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(key, value) { this[key] = value; }
  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(fn);
  }
  async fire(type, event = {}) {
    await Promise.all((this.listeners.get(type) || []).map((fn) => fn({ target: this, ...event })));
  }
  click() { return this.fire("click"); }
  remove() {}
}

function page(origin, relayFetch) {
  const ids = new Map();
  const downloads = [];
  const document = new Element("document");
  document.body = new Element("body");
  document.getElementById = (id) => {
    if (!ids.has(id)) ids.set(id, new Element());
    return ids.get(id);
  };
  document.createElement = (tag) => {
    const node = new Element(tag);
    if (tag === "a") node.click = () => downloads.push({ name: node.download, url: node.href });
    return node;
  };
  document.createDocumentFragment = () => new Element("fragment");
  document.dispatchEvent = (event) => document.fire(event.type, event);
  const storage = new Map();
  const context = vm.createContext({
    document, console, URL, URLSearchParams, TextEncoder, TextDecoder, AbortController,
    Blob, Response, Request, Headers, Event, btoa, atob, setTimeout, clearTimeout,
    navigator: {}, location: new URL(origin + "/sources.html#importPanel"),
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key),
    },
    fetch: relayFetch,
    loadManager: async () => {},
    US_WEB_CONFIG: { relay: origin, desktop: "test" },
  });
  context.window = context;
  for (const file of ["hash.js", "engine.js", "import.js"]) vm.runInContext(read(file), context, { filename: file });
  return { engine: context.USEngine, ids, downloads, storage };
}

async function until(predicate) {
  const end = Date.now() + 10000;
  while (!predicate()) {
    if (Date.now() > end) throw new Error("Import did not finish");
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

test("bundled server cleaner and checker", { timeout: 30000 }, async (t) => {
  const requests = [];
  // Three MPEG-TS packets: enough to confirm media, independent of codecs.
  const media = Buffer.alloc(188 * 3);
  for (let i = 0; i < media.length; i += 188) media[i] = 0x47;
  const providerOrigin = "http://provider.test";
  const nativeFetch = globalThis.fetch;
  const relay = (await import(pathToFileURL(path.join(root, "bundle", "relay", "index.mjs")).href)).default;
  t.mock.method(globalThis, "fetch", async (input, options) => {
    const url = new URL(input);
    assert.equal(url.origin, providerOrigin, "A check must not contact any real provider");
    requests.push({ url, headers: Object.fromEntries(new Headers(options.headers)) });
    const json = (body) => Response.json(body);
    if (url.pathname.endsWith("player_api.php")) {
      const user = url.searchParams.get("username");
      const action = url.searchParams.get("action");
      if (!action) return json({ user_info: {
        auth: user === "rejected" ? 0 : 1,
        status: user === "expired" ? "Expired" : "Active",
        exp_date: user === "expired" ? "1" : "4102444800",
      } });
      return json(action === "get_live_streams" ? [{ stream_id: 1 }] : []);
    }
    if (/portal\.php$|server\/load\.php$/.test(url.pathname)) {
      const action = url.searchParams.get("action");
      if (action === "handshake") return json({ js: { token: "test-token", random: "test" } });
      if (action === "get_profile") return json({ js: { id: 1 } });
      if (action === "get_main_info") return json({ js: { status: "active", end_date: "2100-01-01" } });
      if (action === "get_ordered_list") return json({ js: { data: [{ id: "1", name: "Test", cmd: "ffmpeg http://localhost/ch/1" }] } });
      if (action === "create_link") return json({ js: { cmd: "ffmpeg " + providerOrigin + "/media.ts" } });
      return json({ js: [] });
    }
    if (url.pathname === "/playlist.m3u") {
      return new Response("#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4,\nmedia.ts\n", { headers: { "Content-Type": "application/vnd.apple.mpegurl" } });
    }
    if (url.pathname === "/get.php" || url.pathname.includes("/nostream/") || url.pathname === "/login.html") {
      return new Response("<html>Login required</html>", { headers: { "Content-Type": "text/html" } });
    }
    return new Response(media, { headers: { "Content-Type": "video/mp2t" } });
  });
  const origin = "http://127.0.0.1:47390";
  const state = page(origin, async (input, options) => {
    const url = new URL(input, origin);
    assert.equal(url.origin, origin, "Import checks must use the desktop relay");
    const headers = new Headers(options?.headers);
    headers.set("Origin", origin);
    return relay.fetch(new Request(url, { ...options, headers }), { ALLOW_PRIVATE: "1" });
  });
  const { engine, ids } = state;
  await engine.ready;
  const profile = (user) => engine.normalizeProfile({
    portal: engine.xtreamPlaylist(providerOrigin, user, "test-password"),
    source_type: "m3u", playlist_mode: "xtream", explicit_http_accepted: true,
  });
  const check = (p) => engine.checkImportedProfile(p, new AbortController().signal);

  await t.test("Xtream must return media; expired/rejected logins and HTML are not working", async () => {
    assert.equal((await check(profile("active"))).status, "working");
    assert.equal((await check(profile("expired"))).status, "expired");
    assert.equal((await check(profile("rejected"))).status, "auth_failed");
    assert.equal((await check(profile("nostream"))).status, "no_stream");
  });
  await t.test("Portal sends MAG identity and verifies the created stream locally", async () => {
    const portal = engine.normalizeProfile({ portal: providerOrigin + "/c/", mac: "00:1A:79:00:00:01", explicit_http_accepted: true });
    assert.equal((await check(portal)).status, "working");
    const handshake = requests.find(({ url }) => url.searchParams.get("action") === "handshake");
    assert.match(handshake.headers.cookie, /mac=00:1A:79:00:00:01/i);
    assert.match(handshake.headers["user-agent"], /MAG254/);
    assert.ok(requests.some(({ url }) => url.searchParams.get("action") === "create_link"));
    assert.ok(requests.some(({ url }) => url.pathname === "/media.ts"));
  });
  await t.test("M3U/HLS follows relative segments; cancellation leaves a pending result", async () => {
    const m3u = (pathname) => engine.normalizeProfile({ portal: providerOrigin + pathname, source_type: "m3u", playlist_mode: "m3u", explicit_http_accepted: true });
    assert.equal((await check(m3u("/playlist.m3u"))).status, "working");
    assert.equal((await check(m3u("/login.html"))).status, "no_stream");
    const controller = new AbortController();
    controller.abort();
    assert.equal((await engine.checkImportedProfile(profile("active"), controller.signal)).status, "pending");
  });
  await t.test("TXT import removes duplicates, exports and appends without replacing saved data", async () => {
    const old = profile("existing");
    engine.appendProfiles([old]);
    state.storage.set("us-web-favorites", JSON.stringify([{ title: "Keep me" }]));
    const file = ids.get("importFile");
    const input = [
      providerOrigin + "/c/|00:1A:79:00:00:01",
      providerOrigin + "/c/|00:1a:79:00:00:01",
      "", profile("active").portal, profile("expired").portal,
    ].join("\n");
    await file.fire("change", { target: { files: [new Blob([input])] } });
    await until(() => ids.get("importStop").hidden);
    assert.match(ids.get("importNotice").textContent, /3 found · 1 duplicates removed · 3 checked · 2 working/);
    await ids.get("importClean").click();
    await ids.get("importWorking").click();
    const outputs = await Promise.all(state.downloads.map(async ({ name, url }) => ({ name, text: await (await nativeFetch(url)).text() })));
    assert.equal(outputs[0].name, "UltraStalker-cleaned.txt");
    assert.equal(outputs[0].text.trim().split("\n").length, 3);
    assert.equal(outputs[1].name, "UltraStalker-working.txt");
    assert.equal(outputs[1].text.trim().split("\n").length, 2);
    assert.ok(!outputs[1].text.includes("username=expired"));
    await ids.get("importAll").click();
    assert.equal(engine.activeProfiles().length, 3);
    assert.ok(engine.activeProfiles().some((p) => p.portal === old.portal));
    assert.equal(state.storage.get("us-web-favorites"), '[{"title":"Keep me"}]');
    assert.match(ids.get("importSaved").textContent, /2 added/);
  });
  await t.test("UTF-16 JSON import detects already saved accounts and cannot add duplicates", async () => {
    const data = JSON.stringify({ xtream: [{ host: providerOrigin, username: "active", password: "test-password" }] });
    const file = new Blob([Buffer.from("\ufeff" + data, "utf16le")]);
    await ids.get("importFile").fire("change", { target: { files: [file] } });
    await until(() => ids.get("importStop").hidden);
    assert.match(ids.get("importNotice").textContent, /1 found/);
    assert.equal(ids.get("importAll").disabled, true);
    assert.equal(engine.activeProfiles().length, 3);
  });
  for (const { url } of state.downloads) URL.revokeObjectURL(url);
});
