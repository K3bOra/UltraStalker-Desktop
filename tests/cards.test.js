/* Real Chromium + the packaged interface, a fake Xtream provider: the premium cards (2.7). */
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { startServer } from "../app/server.js";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");

test("titles: quality, language, year and country come out of the name", () => {
  const ctx = { window: {} };
  vm.runInNewContext(fs.readFileSync(path.join(root, "app", "cards.js"), "utf8"), ctx);
  const p = ctx.window.usCards.parse;
  const pick = (r) => ({ title: r.title, quality: [...r.quality], lang: [...r.lang], year: r.year, country: r.country });
  assert.deepEqual(pick(p("4K-AR - MobLand (2025) (GB)")), { title: "MobLand", quality: ["4K"], lang: ["AR"], year: "2025", country: "GB" });
  assert.deepEqual(pick(p("|AR| Kira & El Gin (2022)")), { title: "Kira & El Gin", quality: [], lang: ["AR"], year: "2022", country: "" });
  assert.equal(p("The Batman [4K]").title, "The Batman");
  assert.equal(p("Mission: Impossible - Fallout").title, "Mission: Impossible - Fallout");
  assert.equal(p("X-Men - Days of Future Past").title, "X-Men - Days of Future Past");
  assert.equal(p("مسلسل الحشاشين").title, "مسلسل الحشاشين");
});

const SHOWS = [
  ["4K-AR - MobLand (2025) (GB)", "8.0", 2, "#5a1d12", "#120707"],
  ["4K-AR - WandaVision (2021) (US)", "8.0", 1, "#3b2a58", "#0c0814"],
  ["4K-AR - The Good Daughter (2026) (US)", "7.0", 1, "#6b5a2a", "#151008"],
  ["4K-AR - American Hostage (2026) (US)", "7.0", 1, "#2f4a3a", "#08110c"],
  ["4K-AR - S.W.A.T. Exiles (2026) (US)", "8.0", 1, "#33363d", "#0a0b0d"],
  ["4K-AR - Youth (2026) (GB)", "7.0", 3, "#5b5b22", "#121206"],
  ["AR - Carrie (2026) (CA)", "8.0", 1, "#1d4a55", "#061114"],
  ["4K-AR - Marshals (2026) (US)", "7.0", 2, "#6a4a2a", "#140d06"],
  ["4K-AR - Kill Jackie (2026) (AU)", "7.0", 1, "#6a1f4a", "#14060e"],
  ["4K-AR - East of Eden (2026) (US)", "8.0", 4, "#7a4a1a", "#160c04"],
  ["4K-AR - PEN15 (2019) (US)", "8.0", 3, "#2a6a9a", "#06121c"],
  ["4K-AR - Crystal Lake (2026) (US)", "6.0", 1, "#2a4a2a", "#060e06"],
];
const poster = (i) => {
  const [name, , , a, b] = SHOWS[i];
  const t = name.replace(/^.* - /, "").replace(/\s*\(.*$/, "");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 600"><defs><linearGradient id="g" x1="0" y1="0" x2=".3" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient><radialGradient id="r" cx=".5" cy=".35" r=".6"><stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs><rect width="400" height="600" fill="url(#g)"/><rect width="400" height="600" fill="url(#r)"/><circle cx="200" cy="230" r="95" fill="#000" opacity=".28"/><rect x="0" y="0" width="400" height="40" fill="#000" opacity=".5"/><text x="200" y="28" font-family="Arial" font-weight="700" font-size="22" fill="#fff" text-anchor="middle">4K ULTRA HD</text><text x="200" y="440" font-family="Georgia" font-weight="700" font-size="44" fill="#fff" text-anchor="middle" opacity=".92">${t.toUpperCase().replace(/&/g, "&amp;")}</text></svg>`;
};

async function open(t) {
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), "us-cards-"));
  const port = 47600 + Math.floor(Math.random() * 200);
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
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript(() => {
    localStorage.setItem("us-web-profiles", JSON.stringify([{
      name: "Test provider", portal: "http://provider.test/get.php?username=test&password=test&type=m3u_plus&output=ts",
      source_type: "m3u", playlist_mode: "xtream", source: "web", explicit_http_accepted: true,
    }]));
    window.usNative = { win: { cmd() {}, state: () => ({ full: false }), onState() {} }, update: { state: async () => ({ state: "idle" }), onState() {} } };
  });
  const asked = { info: 0 };
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/p") {
      const target = new URL(url.searchParams.get("u"));
      if (target.pathname.startsWith("/img/")) return route.fulfill({ contentType: "image/svg+xml", body: poster(+target.pathname.match(/\d+/)[0]) });
      const action = target.searchParams.get("action") || "";
      let body = { user_info: { auth: 1, status: "Active" } };
      if (/get_.*_categories/.test(action)) body = [{ category_id: "1", category_name: "مسلسلات أجنبية 2026" }, { category_id: "2", category_name: "مسلسلات أجنبية 2025" }];
      else if (/get_series$/.test(action)) body = SHOWS.map(([name, rating], i) => ({ series_id: 100 + i, name, rating, year: name.match(/\((\d{4})\)/)[1], cover: `http://provider.test/img/${i}.svg`, category_id: "1" }));
      else if (action === "get_series_info") {
        asked.info++;
        const i = +target.searchParams.get("series_id") - 100;
        const n = SHOWS[i][2];
        const episodes = {};
        for (let s = 1; s <= n; s++) episodes[s] = [{ id: String(i * 100 + s), episode_num: 1, title: "Episode 1", container_extension: "mp4" }];
        body = { info: { plot: "Harry Da Souza, a fixer for a crime family, holds things together as two dynasties go to war.", genre: "Crime, Drama, Thriller" }, episodes };
      } else if (/get_vod_streams|get_live_streams/.test(action)) body = [];
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    }
    if (url.pathname.startsWith("/tmdb/")) return route.fulfill({ contentType: "application/json", body: "{}" });
    if (url.origin !== origin) return route.abort();
    return route.continue();
  });
  await page.goto(origin + "/index.html");
  await page.waitForFunction(() => document.querySelector("#browseAccount")?.options.length > 1);
  return { page, errors, asked };
}

test("premium cards: the poster is the card, badges, seasons, hover story, progress", { timeout: 90000 }, async (t) => {
  const { page, errors, asked } = await open(t);
  await page.locator(".dk-src.xtream").first().click();
  await page.getByRole("button", { name: /^Series/ }).first().click();
  await page.waitForSelector("#browseItems .poster-card.usc");
  await page.waitForFunction(() => document.querySelectorAll("#browseItems .poster-card.usc .usc-seasons:not(.wait)").length >= 6, null, { timeout: 15000 });

  const first = page.locator("#browseItems .poster-card.usc").first();
  assert.equal(await first.locator(".usc-title").textContent(), "MobLand");
  assert.deepEqual(await first.locator(".usc-tags :is(.usc-q,.usc-l)").allTextContents(), ["4K", "AR"]);
  assert.match(await first.locator(".usc-meta").textContent(), /8\.0.*2025.*GB/);
  assert.equal(await first.locator(".usc-seasons").textContent(), "2 Seasons");
  assert.equal(await first.locator(".poster-copy").isVisible(), false);
  assert.ok(asked.info >= 6 && asked.info <= 12, "season counts asked for the cards on screen: " + asked.info);
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(os.tmpdir(), "us-cards-grid.png") });

  await first.hover();
  await page.waitForFunction(() => document.querySelector("#browseItems .poster-card.usc")?.classList.contains("usc-has-more"), null, { timeout: 8000 });
  assert.match(await first.locator(".usc-genres").textContent(), /Crime · Drama · Thriller/);
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(os.tmpdir(), "us-cards-hover.png"), clip: { x: 300, y: 0, width: 1000, height: 700 } });

  // how far you got, kept by the program, shows on the card
  await page.evaluate(() => {
    const acc = document.querySelector("#browseAccount").value;
    localStorage.setItem("us-desk-watching", JSON.stringify({ [acc + "|youth"]: { p: 0.42, ep: "S02E04", at: Date.now() } }));
  });
  await page.reload();
  await page.waitForFunction(() => document.querySelector("#browseAccount")?.options.length > 1);
  await page.waitForTimeout(1500);
  if (await page.locator(".dk-src.xtream").first().isVisible()) await page.locator(".dk-src.xtream").first().click();
  if (!(await page.locator("#browseItems .poster-card").count())) await page.getByRole("button", { name: /^Series/ }).first().click();
  await page.waitForSelector("#browseItems .poster-card.usc-watched");
  assert.match(await page.locator("#browseItems .poster-card.usc-watched .usc-resume").textContent(), /Continue S02E04/);
  // counts come from memory the second time
  assert.ok(await page.locator("#browseItems .poster-card.usc .usc-seasons:not(.wait)").count() >= 6);
  await page.mouse.move(5, 500);
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(os.tmpdir(), "us-cards-watched.png"), clip: { x: 300, y: 0, width: 1620, height: 520 } });
  assert.deepEqual(errors, []);
});
