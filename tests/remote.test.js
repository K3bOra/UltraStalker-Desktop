/* The TV interface in Chromium, driven by arrow keys / Enter / Back like a remote.
   The TV's own server (Kotlin) runs on US_TV_ORIGIN; the provider and VLC are fakes. */
import test from "node:test";
import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const ORIGIN = process.env.US_TV_ORIGIN || "http://127.0.0.1:47450";

async function open(t) {
  const browser = await chromium.launch({
    ...(process.platform === "linux" ? { executablePath: process.env.US_CHROME_PATH || "/usr/bin/chromium", args: ["--no-sandbox"] } : { channel: "chrome" }),
    headless: true,
  });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript(() => {
    localStorage.setItem("us-web-profiles", JSON.stringify([{
      name: "Home IPTV", portal: "http://provider.test/get.php?username=u&password=p&type=m3u_plus&output=ts",
      source_type: "m3u", playlist_mode: "xtream", source: "web", explicit_http_accepted: true,
    }]));
    const T = (window.__t = { plays: [], cmds: [], places: [], state: "playing", time: 30, length: 0 });
    // the app's object, synchronous like Android's JavascriptInterface
    window.USTV = {
      vlcAvailable: () => true,
      vlcPlay: (j) => (T.plays.push(JSON.parse(j)), T.length = JSON.parse(j).live ? 0 : 3600, JSON.stringify({ ok: true, version: "libVLC" })),
      vlcStop: () => {},
      vlcCmd: (n, a) => (T.cmds.push([n, a]), true),
      vlcStatus: () => (JSON.stringify({ state: T.state, time: T.time, length: T.length, info: { width: 1920, height: 1080, vcodec: "h264" } })),
      vlcTracks: () => JSON.stringify({ audio: [], subs: [] }),
      vlcPlace: (r) => T.places.push(r ? JSON.parse(r) : null),
      vlcFit: () => {},
      version: () => "1.0.0",
      exitApp: () => {},
    };
    // the app's file helper: a phone on the Wi-Fi, the TV's Download folder
    window.USTVFiles = {
      phoneOpen: () => JSON.stringify({ ip: "192.168.1.20", port: "47391", code: "123456", url: "http://192.168.1.20:47391/?c=123456", qr: "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'><rect width='1' height='1'/></svg>" }),
      phoneClose: () => (T.phoneClosed = true),
      phoneTake: () => { const f = T.inbox; T.inbox = null; return f ? JSON.stringify(f) : ""; },
      offerFile: (name, b64) => (T.offered = { name, size: atob(b64).length }, JSON.stringify({ ok: true, saved: "Download/Ultra Stalker/" + name, phone: JSON.parse(window.USTVFiles.phoneOpen()) })),
      canPick: () => false,
      pick: () => {},
    };
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/p") {
      const target = new URL(url.searchParams.get("u"));
      const action = target.searchParams.get("action") || "";
      const cat = target.searchParams.get("category_id");
      let body = { user_info: { auth: 1, status: "Active" } };
      if (/get_live_categories/.test(action)) body = [{ category_id: "1", category_name: "News" }, { category_id: "2", category_name: "Sports" }, { category_id: "9", category_name: "XXX Adult" }];
      else if (/get_.*_categories/.test(action)) body = [{ category_id: "1", category_name: "Action" }];
      else if (/get_live_streams/.test(action)) {
        const all = Array.from({ length: 9 }, (_, i) => ({ stream_id: i + 1, num: i + 1, name: "Channel " + (i + 1), category_id: i < 6 ? "1" : "2" }));
        body = cat ? all.filter((r) => r.category_id === cat) : all;
      } else if (/get_vod_streams/.test(action)) body = [{ stream_id: 50, name: "A Film", category_id: "1" }];
      else if (/get_series$/.test(action)) body = [];
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    }
    if (url.pathname.startsWith("/tmdb/")) return route.fulfill({ contentType: "application/json", body: "{}" });
    if (url.origin !== ORIGIN) return route.abort();
    return route.continue();
  });
  await page.goto(ORIGIN + "/index.html");
  return { page, errors };
}
const focused = (page) => page.evaluate(() => {
  const el = document.activeElement;
  return el && el !== document.body ? (el.dataset.t || el.getAttribute("aria-label") || el.textContent || el.className).trim().replace(/\s+/g, " ").slice(0, 60) : "";
});
const back = (page) => page.evaluate(() => window.usTvBack());

test("the remote: sources, Live TV, channels, full picture and back", { timeout: 90000 }, async (t) => {
  const { page, errors } = await open(t);
  assert.ok(await page.evaluate(() => document.documentElement.classList.contains("us-tv") && window.usNative.vlc.available));
  assert.ok(await page.evaluate(() => document.body.classList.contains("desk")), "computer layout at 1280");
  await page.waitForFunction(() => document.activeElement && document.activeElement !== document.body, null, { timeout: 15000 });
  // walk to the source card and open it
  let tries = 0;
  while (!/Home IPTV/.test(await focused(page)) && tries++ < 25) await page.keyboard.press(tries < 12 ? "ArrowDown" : "ArrowRight");
  assert.match(await focused(page), /Home IPTV/);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.body.classList.contains("dk-tv-mode") && document.querySelectorAll("#browseItems .live-card").length >= 6, null, { timeout: 20000 });
  // no adult category reached the TV
  assert.equal(await page.locator("#dkTvCats .dk-tvc-list button", { hasText: "XXX" }).count(), 0);
  // reach a channel and play it
  await page.evaluate(() => document.querySelector("#browseItems .live-card").focus());
  await page.keyboard.press("ArrowDown");
  const name = await focused(page);
  assert.match(name, /Channel/);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.__t.plays.length === 1);
  assert.equal(await page.evaluate(() => window.__t.plays[0].live), true);
  assert.match(await focused(page), /Channel/, "the focus stays on the list while it plays in the small picture");
  // OK again on the playing channel: the picture fills the screen
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector(".usp.expanded"));
  await page.waitForFunction(() => { const p = window.__t.places.at(-1); return p && p.w > 1000; });
  // ↓ in the full picture: next channel
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await page.keyboard.press("ArrowDown");
  await page.waitForFunction(() => window.__t.plays.length === 2);
  // OK shows the controls with the focus on them; Back hides them, Back again leaves the full picture
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.activeElement && document.activeElement.closest(".usp-bar"));
  assert.equal(await back(page), true);
  assert.equal(await page.evaluate(() => !!(document.activeElement && document.activeElement.closest(".usp-bar"))), false);
  assert.equal(await back(page), true);
  await page.waitForFunction(() => !document.querySelector(".usp.expanded"));
  assert.equal(await page.evaluate(() => !document.querySelector(".usp").classList.contains("hidden")), true, "still playing in the small picture");
  assert.deepEqual(errors, []);
});

test("the remote in a film: seek, controls, settings, back", { timeout: 60000 }, async (t) => {
  const { page, errors } = await open(t);
  await page.waitForFunction(() => window.USPlayer && document.querySelector("#browseAccount")?.options.length > 1);
  await page.evaluate(() => window.USPlayer.play({ title: "A Film", stream: "http://provider.test/film.mkv", live: false }));
  await page.waitForFunction(() => window.__t.plays.length === 1 && !document.querySelector(".usp-bar .skip-forward")?.disabled);
  await page.evaluate(() => document.activeElement && document.activeElement.blur());
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(() => window.__t.cmds.some((c) => c[0] === "seek" && c[1] === "40"));
  // ↓ shows the controls on play/pause; → goes to "forward 10"
  await page.keyboard.press("ArrowDown");
  assert.match(await focused(page), /Play \/ pause/);
  await page.keyboard.press("ArrowRight");
  assert.match(await focused(page), /Forward 10 seconds/);
  // the settings: arrows stay inside, Back closes them and comes back to the controls
  let n = 0;
  while (!/^Settings$/.test(await focused(page)) && n++ < 15) await page.keyboard.press("ArrowRight");
  assert.equal(await focused(page), "Settings");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".usp-menu.on");
  await page.keyboard.press("ArrowDown");
  assert.ok(await page.evaluate(() => !!document.activeElement.closest(".usp-menu")));
  assert.equal(await back(page), true);
  assert.equal(await page.locator(".usp-menu.on").count(), 0);
  assert.ok(await page.evaluate(() => !!document.activeElement.closest(".usp-bar")));
  // Back: hide the controls, then close the film
  assert.equal(await back(page), true);
  assert.equal(await back(page), true);
  await page.waitForFunction(() => document.querySelector(".usp").classList.contains("hidden"));
  // nothing else open: the app goes back a page or leaves
  assert.equal(await back(page), false);
  assert.deepEqual(errors, []);
});

test("backups on the TV: the file comes from a phone, the backup goes to Downloads and the phone", { timeout: 60000 }, async (t) => {
  const { page, errors } = await open(t);
  const asked = [];
  page.on("dialog", (d) => (asked.push(d.message()), d.accept()));
  await page.goto(ORIGIN + "/sources.html#backupPanel");
  await page.waitForSelector("label[for=backupFile]");
  // the remote reaches "Choose backup file" and OK opens the file window
  await page.evaluate(() => { const l = document.querySelector("label[for=backupFile]"); l.tabIndex = -1; l.focus(); });
  await page.keyboard.press("Enter");
  await page.waitForSelector(".us-tv-dlg .qr img");
  assert.match(await page.locator(".us-tv-dlg").textContent(), /192\.168\.1\.20:47391.*123456/);
  assert.ok(await page.evaluate(() => !!document.activeElement.closest(".us-tv-dlg")));
  // the phone sends a backup: the page reads it like a chosen file
  const zip = "UEsFBgAAAAAAAAAAAAAAAAAAAAAAAA=="; // an empty zip
  await page.evaluate((b64) => { window.__t.inbox = { name: "UltraStalker-backup.zip", b64 }; }, zip);
  await page.waitForFunction(() => !document.querySelector(".us-tv-dlg"));
  await page.waitForFunction(() => /UltraStalker-backup\.zip/.test(document.body.textContent));
  assert.equal(await page.evaluate(() => window.__t.phoneClosed), true);
  // Back closes the window without a file
  await page.evaluate(() => { const l = document.querySelector("label[for=backupFile]"); l.tabIndex = -1; l.focus(); });
  await page.keyboard.press("Enter");
  await page.waitForSelector(".us-tv-dlg");
  assert.equal(await back(page), true);
  assert.equal(await page.locator(".us-tv-dlg").count(), 0);
  // saving a backup: Download folder + phone
  await page.evaluate(() => document.getElementById("backupSaveBtn").click());
  await page.waitForSelector(".us-tv-dlg");
  assert.match(await page.locator(".us-tv-dlg").textContent(), /Saved on the TV.*Download\/Ultra Stalker\//);
  assert.match(await page.evaluate(() => window.__t.offered.name), /\.zip$/);
  assert.ok((await page.evaluate(() => window.__t.offered.size)) > 100);
  await page.keyboard.press("Enter");
  assert.equal(await page.locator(".us-tv-dlg").count(), 0);
  assert.deepEqual(errors, []);
});
