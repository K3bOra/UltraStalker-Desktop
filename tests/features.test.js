/* Real Chromium + the packaged interface, fake provider / VLC / program:
   the program's own features (2.6). */
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { startServer } from "../app/server.js";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");

async function open(t, { viewport = { width: 1600, height: 1000 } } = {}) {
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), "us-feat-"));
  const port = 47393 + Math.floor(Math.random() * 200);
  const { server, origin } = await startServer({
    webDir: path.join(root, "bundle", "web"), relayFile: path.join(root, "bundle", "relay", "index.mjs"),
    appCssFile: path.join(root, "app", "desktop-app.css"), userDir, port,
    cloudRelay: "https://example.invalid", version: "test",
  });
  const browser = await chromium.launch({
    ...(process.platform === "linux" ? { executablePath: process.env.US_CHROME_PATH || "/usr/bin/chromium", args: ["--no-sandbox"] } : { channel: "chrome" }),
    headless: true,
  });
  t.after(async () => {
    await browser.close();
    server.closeAllConnections();
    await new Promise((r) => server.close(r));
    fs.rmSync(userDir, { recursive: true, force: true });
  });
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript(() => {
    localStorage.setItem("us-web-profiles", JSON.stringify([{
      name: "Test provider", portal: "http://provider.test/get.php?username=test&password=test&type=m3u_plus&output=ts",
      source_type: "m3u", playlist_mode: "xtream", source: "web", explicit_http_accepted: true,
    }]));
    const T = (window.__t = { cmds: [], places: [], snaps: [], win: [], rec: null, recStarts: 0, state: "playing", time: 100, length: 3600, pointer: null, stateCb: null });
    window.usNative = {
      win: { cmd: (c) => T.win.push(c), state: () => ({ full: false }), onState: (cb) => (T.stateCb = cb) },
      vlc: {
        available: true, play: async () => ({ ok: true, version: "3.0.21" }), stop() {}, fit() {},
        place: (r) => T.places.push(r),
        cmd: async (name, value) => (T.cmds.push([name, value]), true),
        status: async () => ({ state: T.state, time: T.time, length: T.length, info: { width: 1920, height: 1080, vcodec: "h264" } }),
        tracks: async () => ({ audio: [], subs: [] }),
        onPointer: (cb) => (T.pointer = cb),
      },
      snap: async (o) => (T.snaps.push(o), { ok: true, file: "C:\\Users\\me\\Pictures\\Ultra Stalker\\Test 1.png", folder: "C:\\Users\\me\\Pictures\\Ultra Stalker" }),
      showFile() {},
      rec: {
        start: async (o) => ((T.rec = { title: o.title, bytes: 0, at: Date.now() }), T.recStarts++, { ok: true, file: "C:\\v\\" + o.title + ".ts", folder: "C:\\v" }),
        stop: async () => { const r = T.rec; T.rec = null; return r ? { ok: true, file: "C:\\v\\" + r.title + ".ts", folder: "C:\\v", bytes: 2 << 20 } : { ok: false }; },
        status: async () => (T.rec ? { on: true, bytes: (T.rec.bytes += 1 << 20), seconds: Math.round((Date.now() - T.rec.at) / 1000) } : { on: false }),
      },
      update: { state: async () => ({ state: "idle" }), onState: (cb) => (T.update = cb), install: () => (T.installed = true) },
    };
  });
  const adult = new Set(["7", "8"]);
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/p") {
      const target = new URL(url.searchParams.get("u"));
      const action = target.searchParams.get("action") || "";
      const cat = target.searchParams.get("category_id");
      let body = { user_info: { auth: 1, status: "Active" } };
      if (/get_.*_categories/.test(action)) body = Array.from({ length: 10 }, (_, i) => ({ category_id: String(i + 1), category_name: i === 6 ? "XXX | Adult" : i === 7 ? "قنوات +18" : "Category " + (i + 1) }));
      else if (/get_live_streams/.test(action)) {
        const all = Array.from({ length: 12 }, (_, i) => ({ stream_id: i + 1, num: i + 1, name: i === 10 ? "Hot Night" : i === 11 ? "Playboy TV HD" : "Channel " + (i + 1), category_id: i === 10 ? "7" : i === 11 ? "2" : "1" }));
        body = cat ? all.filter((r) => r.category_id === cat) : all;
      } else if (/get_vod_streams/.test(action)) {
        const all = [{ stream_id: 50, name: "Good Movie", category_id: "1" }, { stream_id: 51, name: "Quiet film", category_id: "8" }, { stream_id: 52, name: "Brazzers Night", category_id: "1" }];
        body = cat ? all.filter((r) => r.category_id === cat) : all;
      } else if (/get_series$/.test(action)) body = [];
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    }
    if (url.pathname.startsWith("/tmdb/")) return route.fulfill({ contentType: "application/json", body: "{}" });
    if (url.origin !== origin) return route.abort();
    return route.continue();
  });
  await page.goto(origin + "/index.html");
  await page.waitForFunction(() => document.querySelector("#browseAccount")?.options.length > 1);
  const account = await page.locator("#browseAccount option").nth(1).getAttribute("value");
  return { page, errors, origin, account, adult };
}

test("player features: icons, hiding controls over VLC, speed, sleep, picture, mini, next episode", { timeout: 90000 }, async (t) => {
  const { page, errors } = await open(t);
  await page.evaluate(() => {
    let left = 1;
    window.usDesktopNext = { info: () => (left > 0 ? { label: "S01E02 · Episode 2" } : null), play: async () => { left--; window.__t.nextPlayed = (window.__t.nextPlayed || 0) + 1; } };
    window.USPlayer.play({ title: "Feature test", stream: "http://provider.test/movie.mkv", live: false, _plan: ["vlc"], _step: 0 });
  });
  await page.waitForFunction(() => !document.querySelector(".usp-bar .skip-forward")?.disabled);

  await t.test("10-second buttons draw a circular arrow with 10 inside", async () => {
    const icon = await page.locator(".usp-bar .skip-back svg").evaluate((s) => ({ paths: s.querySelectorAll("path").length, text: s.querySelector("text").textContent, w: s.getBoundingClientRect().width }));
    assert.deepEqual([icon.paths, icon.text], [2, "10"]);
    assert.ok(icon.w >= 26);
  });

  await t.test("controls hide over VLC, VLC takes the whole picture, a mouse move over VLC brings them back", async () => {
    await page.mouse.move(800, 400);
    await page.waitForFunction(() => document.querySelector(".usp-stage").classList.contains("idle"), null, { timeout: 6000 });
    const full = await page.evaluate(() => {
      const s = document.querySelector(".usp-stage").getBoundingClientRect();
      return { h: Math.round(s.height), last: window.__t.places.at(-1) };
    });
    await page.waitForFunction((h) => Math.abs((window.__t.places.at(-1) || {}).h - h) <= 2, full.h);
    await page.evaluate(() => window.__t.pointer());
    assert.equal(await page.evaluate(() => document.querySelector(".usp-stage").classList.contains("idle")), false);
    await page.waitForFunction((h) => (window.__t.places.at(-1) || {}).h < h - 40, full.h);
  });

  await t.test("speed from Settings and with ] [ keys goes to VLC", async () => {
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.locator('.usp-menu [data-xr="1.5"]').click();
    assert.deepEqual(await page.evaluate(() => window.__t.cmds.filter((c) => c[0] === "rate").at(-1)), ["rate", "1.50"]);
    assert.ok(await page.locator('.usp-menu [data-xr="1.5"].on').isVisible());
    await page.keyboard.press("Escape");
    await page.keyboard.press("]");
    assert.deepEqual(await page.evaluate(() => window.__t.cmds.filter((c) => c[0] === "rate").at(-1)), ["rate", "2.00"]);
    await page.keyboard.press("=");
    assert.deepEqual(await page.evaluate(() => window.__t.cmds.filter((c) => c[0] === "rate").at(-1)), ["rate", "1.00"]);
  });

  await t.test("sleep timer shows the minutes left and can be turned off", async () => {
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.locator('.usp-menu [data-xs="30"]').click();
    assert.match(await page.locator(".usx-pill.sleep").textContent(), /30 min/);
    assert.match(await page.locator(".usx-sleepnow").textContent(), /30 min/);
    await page.locator('.usp-menu [data-xs="0"]').click();
    assert.equal(await page.locator(".usx-pill.sleep").isVisible(), false);
    await page.keyboard.press("Escape");
  });

  await t.test("S saves a picture through VLC and says where", async () => {
    await page.keyboard.press("s");
    await page.waitForFunction(() => window.__t.snaps.length === 1);
    assert.equal(await page.evaluate(() => window.__t.snaps[0].vlc), true);
    await page.waitForSelector(".usx-strip .usx-card");
    assert.match(await page.locator(".usx-strip .usx-card").textContent(), /Picture saved/);
  });

  await t.test("digits jump through the film, the wheel changes the volume", async () => {
    await page.keyboard.press("5");
    await page.waitForFunction(() => window.__t.cmds.some((c) => c[0] === "seek" && c[1] === "1800"));
    const before = await page.evaluate(() => +localStorage.getItem("us-vol") || 1);
    const s = await page.locator(".usp-stage").boundingBox();
    await page.mouse.move(s.x + s.width / 2, s.y + 100);
    await page.mouse.wheel(0, 300);
    const after = await page.evaluate(() => +localStorage.getItem("us-vol"));
    assert.ok(after < before, `volume ${before} → ${after}`);
  });

  await t.test("mini player: P makes the window small with its own title bar, P again brings it back", async () => {
    await page.keyboard.press("p");
    assert.deepEqual(await page.evaluate(() => window.__t.win.at(-1)), "mini");
    assert.ok(await page.evaluate(() => document.body.classList.contains("us-mini") && document.querySelector(".usp").parentNode === document.body));
    await page.setViewportSize({ width: 520, height: 325 });
    assert.ok(await page.locator(".usx-minibar").isVisible());
    const st = await page.locator(".usp-stage").boundingBox();
    assert.ok(st.width >= 515 && st.height > 250, JSON.stringify(st));
    await page.keyboard.press("p");
    assert.deepEqual(await page.evaluate(() => window.__t.win.at(-1)), "unmini");
    await page.setViewportSize({ width: 1600, height: 1000 });
    assert.equal(await page.evaluate(() => document.body.classList.contains("us-mini")), false);
  });

  await t.test("next episode: button, and a 10-second countdown when the episode ends", async () => {
    assert.ok(await page.getByRole("button", { name: "Next episode", exact: true }).isVisible());
    // an end in the middle of the film is a dropped line, not the end
    await page.evaluate(() => { window.__t.time = 1200; });
    await page.waitForTimeout(1200);
    await page.evaluate(() => { window.__t.state = "stopped"; });
    await page.waitForTimeout(4000);
    assert.equal(await page.locator(".usx-ring").count(), 0);
  });
  await page.evaluate(() => { const t = window.__t; t.state = "playing"; t.time = 100; window.USPlayer.play({ title: "Episode 1", stream: "http://provider.test/ep1.mkv", live: false, _plan: ["vlc"], _step: 0 }); });
  await page.waitForFunction(() => !document.querySelector(".usp-bar .skip-forward")?.disabled);
  await t.test("the real end of an episode counts down and plays the next one", async () => {
    await page.evaluate(() => { window.__t.time = 3590; });
    await page.waitForTimeout(2200);
    await page.evaluate(() => { window.__t.state = "stopped"; window.__t.time = 0; window.__t.length = 0; });
    await page.waitForSelector(".usx-ring", { timeout: 8000 });
    assert.match(await page.locator(".usx-strip").textContent(), /Next episode.*S01E02/);
    await page.getByRole("button", { name: "Play now", exact: true }).click();
    assert.equal(await page.evaluate(() => window.__t.nextPlayed), 1);
    assert.equal(await page.locator(".usx-ring").count(), 0);
  });
  await page.evaluate(() => window.USPlayer.close());

  await t.test("live: R records, the REC pill counts, R again saves", async () => {
    await page.evaluate(() => { const t = window.__t; t.state = "playing"; t.time = 5; t.length = 0; window.USPlayer.play({ title: "Live Channel", stream: "http://provider.test/live.ts", live: true, _plan: ["vlc"], _step: 0 }); });
    await page.waitForFunction(() => document.querySelector(".usp-bar .usx-rec") && !document.querySelector(".usp-bar .usx-rec").hidden);
    assert.equal(await page.getByRole("button", { name: "Next episode", exact: true }).isVisible(), false);
    await page.keyboard.press("r");
    await page.waitForFunction(() => window.__t.recStarts === 1);
    await page.waitForFunction(() => /REC/.test(document.querySelector(".usx-pill.rec")?.textContent || "") && !document.querySelector(".usx-pill.rec").hidden, null, { timeout: 5000 });
    await page.keyboard.press("r");
    await page.waitForFunction(() => /Recording saved/.test(document.querySelector(".usx-strip")?.textContent || ""));
    assert.equal(await page.locator(".usx-pill.rec").isVisible(), false);
    // a recording stops by itself when the channel changes
    await page.keyboard.press("r");
    await page.waitForFunction(() => window.__t.recStarts === 2 && window.__t.rec);
    await page.evaluate(() => window.USPlayer.close());
    await page.waitForFunction(() => !window.__t.rec);
    await page.waitForFunction(() => /Recording saved/.test(document.querySelector(".usx-toast")?.textContent || ""));
  });

  await t.test("an update that is ready is offered with Restart now", async () => {
    await page.evaluate(() => window.__t.update({ state: "ready", version: "2.6.1" }));
    await page.waitForSelector(".us-update");
    assert.match(await page.locator(".us-update").textContent(), /2\.6\.1 is ready/);
    await page.getByRole("button", { name: "Restart now", exact: true }).click();
    assert.equal(await page.evaluate(() => window.__t.installed), true);
  });
  assert.deepEqual(errors, []);
});

test("no adult content: categories, items (also in All), search, playback", { timeout: 60000 }, async (t) => {
  const { page, errors, account } = await open(t);
  const api = (p) => page.evaluate(async (p) => (await fetch(p)).json(), p);
  const acc = encodeURIComponent(account);
  for (const media of ["itv", "vod"]) {
    const c = await api(`api/browse/categories?account=${acc}&type=${media}`);
    const names = c.categories.map((x) => x.title);
    assert.equal(names.length, 8, names.join(", "));
    assert.ok(!names.some((n) => /adult|18/i.test(n)), names.join(", "));
  }
  const live = await api(`api/browse/items?account=${acc}&type=itv&category=*&title=All`);
  const titles = live.items.map((i) => i.title);
  assert.equal(titles.length, 10, titles.join(", "));
  assert.ok(!titles.includes("Hot Night") && !titles.includes("Playboy TV HD"));
  const inAdult = await api(`api/browse/items?account=${acc}&type=itv&category=7&title=XXX`);
  assert.equal(inAdult.items.length, 0);
  const vod = await api(`api/browse/items?account=${acc}&type=vod&category=*&title=All`);
  assert.deepEqual(vod.items.map((i) => i.title), ["Good Movie"]);
  const search = await api(`api/browse/search?account=${acc}&q=night`);
  assert.ok(!JSON.stringify(search).includes("Brazzers"));
  assert.deepEqual(errors, []);
});

test("the program opens Live TV at the last channel without playing it; episodes know the next one", { timeout: 60000 }, async (t) => {
  const { page, errors, account } = await open(t);
  await page.evaluate((account) => {
    localStorage.setItem("us-desk-last-channel", JSON.stringify({ account, cat: "1", name: "Channel 3" }));
    sessionStorage.clear();
  }, account);
  await page.reload();
  await page.waitForFunction(() => document.querySelector("#browseItems .live-card.us-last"), null, { timeout: 30000 });
  assert.equal(await page.locator("#browseItems .live-card.us-last").evaluate((c) => c.dataset.t || c.title || c.textContent.trim()), "Channel 3");
  // nothing plays by itself
  await page.waitForTimeout(2500);
  assert.equal(await page.locator("#browseItems .live-card.dk-on").count(), 0);
  assert.equal(await page.evaluate(() => window.__t.places.length + window.__t.cmds.length), 0);
  await page.locator("#browseItems .live-card.us-last").click();
  await page.waitForFunction(() => document.querySelector("#browseItems .live-card.dk-on"), null, { timeout: 15000 });
  // the playing channel shows three smooth bars (moved on the graphics card, not redrawn)
  await page.waitForFunction(() => document.querySelectorAll("#browseItems .live-card.dk-on .us-eq i").length === 3);
  assert.equal(await page.locator("#browseItems .us-eq").count(), 1);
  await page.locator("#browseItems .live-card.dk-on").screenshot({ path: path.join(os.tmpdir(), "us-eq.png") });
  assert.match(await page.locator("#browseItems .us-eq i").first().evaluate((i) => getComputedStyle(i).animationName), /usEqBar/);
  assert.equal(await page.locator("#browseItems .live-card.dk-on .item-title").evaluate((t) => getComputedStyle(t, "::after").content), "none");
  await t.test("the Live TV screen's player goes into the mini window and comes back", async () => {
    await page.waitForFunction(() => document.querySelector("#dkTvScreen .usp:not(.hidden)"));
    await page.locator("#dkTvScreen .usp-stage").hover();
    await page.keyboard.press("p");
    await page.setViewportSize({ width: 520, height: 325 });
    assert.ok(await page.evaluate(() => document.querySelector(".usp").parentNode === document.body));
    const st = await page.locator(".usp-stage").boundingBox();
    assert.ok(st.width >= 515 && st.height > 200, JSON.stringify(st));
    await page.keyboard.press("p");
    await page.setViewportSize({ width: 1600, height: 1000 });
    assert.ok(await page.evaluate(() => document.querySelector(".usp").parentNode.id === "dkTvScreen"));
  });
  await page.evaluate(() => window.USPlayer.close());
  await t.test("next episode in the same season", async () => {
    const info = await page.evaluate(() => {
      // eslint-disable-next-line no-undef
      activeSeries = { id: "series-token" };
      // eslint-disable-next-line no-undef
      activeSeason = { id: "season-token" };
      const rows = [1, 2, 3].map((n) => ({ id: "ep" + n, season: 1, episode: n, title: "Episode " + n }));
      window.renderInlineEpisodes(rows, "Season 1");
      window.openPlayerSheet(rows[1]);
      return window.usDesktopNext.info();
    });
    assert.deepEqual(info, { label: "S01E03 · Episode 3" });
    const last = await page.evaluate(() => (window.openPlayerSheet({ id: "ep3", season: 1, episode: 3 }), window.usDesktopNext.info()));
    assert.equal(last, null); // no other season known
    const movie = await page.evaluate(() => (window.openPlayerSheet({ id: "movie-1" }), window.usDesktopNext.info()));
    assert.equal(movie, null);
    await page.evaluate(() => window.USPlayer.close());
  });
  assert.deepEqual(errors.filter((e) => !/Stream unavailable|cached|expired/i.test(e)), []);
});

test("Servers & Backup: one section at a time, and My servers picks from a list", { timeout: 60000 }, async (t) => {
  const { page, errors, origin } = await open(t);
  await page.goto(origin + "/sources.html#managerPanel");
  await page.waitForSelector("#usSrv .us-srv-nav a.on");
  assert.equal(await page.locator("#usSrv .us-srv-nav a.on").getAttribute("data-sec"), "managerPanel");
  assert.equal(await page.locator("#managerPanel").isVisible(), true);
  assert.equal(await page.locator("#connectionPanel").isVisible(), false);
  assert.equal(await page.locator("#dkBarNav").isVisible(), false);
  // the test source is an Xtream one
  await page.waitForFunction(() => /No saved servers/.test(document.querySelector(".us-srv-list")?.textContent || ""));
  await page.locator('.manager-group-tab[data-group="xtream"]').click();
  await page.waitForFunction(() => document.querySelectorAll(".us-srv-list button").length === 1);
  assert.equal(await page.locator("#usStatAll").textContent(), "1");
  await page.locator(".us-srv-list button").first().click();
  await page.waitForFunction(() => document.getElementById("managerName").value === "Test provider");
  assert.equal(await page.locator(".us-srv-list button.on").count(), 1);
  // the page's own links switch sections
  await page.locator('#usSrv .us-srv-nav a[data-sec="backupPanel"]').click();
  assert.equal(await page.locator("#backupPanel").isVisible(), true);
  assert.equal(await page.locator("#managerPanel").isVisible(), false);
  assert.equal(await page.locator("#importCheck").isVisible(), false);
  assert.deepEqual(errors, []);
});
