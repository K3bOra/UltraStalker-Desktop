/* Real Chromium + the packaged interface, a fake Xtream provider: the Cinema look (2.8). */
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { startServer } from "../app/server.js";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = process.env.US_SHOTS || os.tmpdir();
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

const wideArt = (i) => {
  const [, , , a, b] = SHOWS[i % SHOWS.length];
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${b}"/><stop offset=".55" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient><radialGradient id="r" cx=".68" cy=".32" r=".5"><stop offset="0" stop-color="#ffd9a0" stop-opacity=".5"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs><rect width="1920" height="1080" fill="url(#g)"/><rect width="1920" height="1080" fill="url(#r)"/><ellipse cx="1250" cy="560" rx="200" ry="320" fill="#000" opacity=".38"/><ellipse cx="1250" cy="300" rx="105" ry="125" fill="#000" opacity=".38"/><ellipse cx="1560" cy="640" rx="170" ry="280" fill="#000" opacity=".32"/><ellipse cx="1560" cy="420" rx="88" ry="104" fill="#000" opacity=".32"/></svg>`;
};
const logoArt = (i) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 240"><rect width="400" height="240" rx="40" fill="#${["1f6feb", "d1242f", "1a7f37", "8250df", "bf8700", "0969da"][i % 6]}"/><text x="200" y="150" font-family="Arial" font-weight="900" font-size="90" fill="#fff" text-anchor="middle">${["MBC", "BBC", "CNN", "OSN", "beIN", "NAT"][i % 6]}</text></svg>`;

async function open(t) {
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), "us-cine-"));
  const port = 47800 + Math.floor(Math.random() * 150);
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
    localStorage.setItem("us-web-profiles", JSON.stringify([
      { name: "Gold line", portal: "http://provider.test/get.php?username=test&password=test&type=m3u_plus&output=ts", source_type: "m3u", playlist_mode: "xtream", source: "web", explicit_http_accepted: true },
      { name: "Second line", portal: "http://second.test/get.php?username=a&password=b&type=m3u_plus&output=ts", source_type: "m3u", playlist_mode: "xtream", source: "web", explicit_http_accepted: true },
    ]));
    window.usNative = { win: { cmd: (c) => (window.__win = c), state: () => ({ full: false }), onState() {} }, update: { state: async () => ({ state: "idle" }), onState() {} } };
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/p") {
      const target = new URL(url.searchParams.get("u"));
      const m = target.pathname.match(/^\/(img|bd|logo)\/(\d+)/);
      if (m) return route.fulfill({ contentType: "image/svg+xml", body: m[1] === "img" ? poster(+m[2]) : m[1] === "bd" ? wideArt(+m[2]) : logoArt(+m[2]) });
      const action = target.searchParams.get("action") || "";
      const cat = target.searchParams.get("category_id");
      let body = { user_info: { auth: 1, status: "Active" } };
      const cats = ["يعرض الآن أجنبي", "مسلسلات أجنبية 2026", "مسلسلات تركية", "مسلسلات عربية", "أنمي", "وثائقي", "رمضان 2026", "مسلسلات كورية", "كرتون", "برامج"];
      if (action === "get_series_categories") body = cats.map((c, i) => ({ category_id: String(i + 1), category_name: c }));
      else if (action === "get_vod_categories") body = ["أفلام أجنبية 2026", "أفلام عربية", "أكشن", "كوميدي"].map((c, i) => ({ category_id: String(i + 1), category_name: c }));
      else if (action === "get_live_categories") body = ["News", "Sports", "Movies", "Kids"].map((c, i) => ({ category_id: String(i + 1), category_name: c }));
      else if (action === "get_series") body = Array.from({ length: 24 }, (_, k) => { const i = (k + (+cat || 0)) % SHOWS.length; const [name, rating] = SHOWS[i]; return { series_id: 100 + k * 13 + i, name, rating, year: name.match(/\((\d{4})\)/)?.[1] || "2025", cover: `http://provider.test/img/${i}.svg`, backdrop_path: [`http://provider.test/bd/${i}.svg`], plot: "A gripping story that keeps you on the edge of your seat.", category_id: cat || "1" }; });
      else if (action === "get_vod_streams") body = Array.from({ length: 18 }, (_, k) => { const i = (k + 3) % SHOWS.length; return { stream_id: 500 + k, name: SHOWS[i][0].replace(/S\.W\.A\.T\./, "Strike"), rating: SHOWS[i][1], year: "2026", stream_icon: `http://provider.test/img/${i}.svg`, backdrop_path: [`http://provider.test/bd/${i}.svg`], container_extension: "mkv", category_id: cat || "1" }; });
      else if (action === "get_live_streams") body = Array.from({ length: 18 }, (_, k) => ({ stream_id: 900 + k, num: k + 1, name: ["MBC 1", "BBC News", "CNN", "OSN Movies", "beIN Sports 1", "Nat Geo"][k % 6] + (k > 5 ? " " + (k + 1) : ""), stream_icon: `http://provider.test/logo/${k}.svg`, category_id: cat || "1" }));
      else if (action === "get_series_info") {
        const sid = +target.searchParams.get("series_id");
        const i = (sid - 100) % 13;
        const n = Math.max(1, SHOWS[i % SHOWS.length][2]);
        const episodes = {};
        for (let s = 1; s <= n; s++) episodes[s] = Array.from({ length: 8 }, (_, e) => ({ id: String(sid * 100 + s * 10 + e), episode_num: e + 1, title: ["Pilot", "The Deal", "Blood Ties", "Old Friends", "Crossroads", "The Fall", "Kingdom", "Endgame"][e], container_extension: "mp4", season: s }));
        body = { info: { plot: "Harry Da Souza, a fixer for a London crime family, holds things together as two dynasties go to war over power and survival.", genre: "Crime, Drama, Thriller", rating: "8.0", backdrop_path: [`http://provider.test/bd/${i}.svg`] }, episodes };
      } else if (action === "get_vod_info") body = { info: { plot: "When a deal goes wrong, a retired agent is pulled back for one last mission across three continents.", genre: "Action, Thriller", duration_secs: 7620, releasedate: "2026-03-01" } };
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    }
    if (url.pathname.startsWith("/tmdb/")) return route.fulfill({ contentType: "application/json", body: "{}" });
    if (url.origin !== origin) return route.abort();
    return route.continue();
  });
  await page.goto(origin + "/index.html");
  await page.waitForFunction(() => document.querySelector("#browseAccount")?.options.length > 1);
  return { page, errors };
}
const shot = (page, name) => page.screenshot({ path: path.join(OUT, "cine-" + name + ".png") });

test("the Cinema look: home, series, details with episodes, movies, live, search, back to classic", { timeout: 120000 }, async (t) => {
  const { page, errors } = await open(t);
  await page.waitForSelector("#usCineBtn", { state: "attached" });
  await page.evaluate(() => document.getElementById("usCineBtn").click());
  await page.waitForSelector("#usCine .cn-row .cn-card.ok", { timeout: 20000 });
  await page.waitForFunction(() => document.querySelector("#usCine .cn-title")?.textContent.length > 0);
  await page.waitForTimeout(1600);
  await shot(page, "1-home");
  assert.equal(await page.evaluate(() => localStorage.getItem("us-desk-look")), '"cinema"');

  // the picture follows the title the mouse rests on
  const card = page.locator("#usCine .cn-row .cn-card").nth(2);
  const name = (await card.locator(".cn-name").textContent()).trim();
  await card.hover();
  await page.waitForFunction((n) => document.querySelector("#usCine .cn-title").textContent === n, name);

  // series: folders as tabs, posters below the picture
  await page.locator('#usCine .cn-rail [data-v="series"]').click();
  await page.waitForSelector("#usCine .cn-grid .cn-card.ok");
  assert.ok((await page.locator("#usCine .cn-tabs button[data-c]").count()) >= 5);
  await page.waitForTimeout(1300);
  await shot(page, "2-series");
  await page.locator("#usCine .cn-tabs .cn-all").click();
  await page.waitForSelector("#usCine .cn-folders");
  await shot(page, "3-folders");
  await page.locator('#usCine .cn-folders-l button:has-text("أنمي")').click();
  await page.waitForFunction(() => document.querySelector("#usCine .cn-grid-h h3").textContent === "أنمي");

  // one series: the big picture, seasons and episodes
  await page.locator("#usCine .cn-grid .cn-card").first().click();
  await page.waitForSelector("#usCine .cn-ep");
  await page.waitForTimeout(1300);
  await shot(page, "4-details");
  assert.ok((await page.locator("#usCine .cn-seasons button").count()) >= 1);
  await page.evaluate(() => {
    window.openPlayerSheet = (r) => (window.__played = r);
  });
  await page.locator("#usCine .cn-ep").nth(1).click();
  const played = await page.evaluate(() => window.__played);
  assert.equal(played.episode, 2);
  const cont = await page.evaluate(() => JSON.parse(localStorage.getItem("us-cine-continue")));
  assert.equal(cont[0].code, "S01E02");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#usCine .cn-grid .cn-card");

  // movies, live, search
  await page.locator('#usCine .cn-rail [data-v="vod"]').click();
  await page.waitForSelector("#usCine .cn-grid .cn-card.ok");
  await page.locator("#usCine .cn-grid .cn-card").nth(1).hover();
  await page.waitForTimeout(1300);
  await shot(page, "5-movies");
  await page.locator('#usCine .cn-rail [data-v="live"]').click();
  await page.waitForSelector("#usCine .cn-grid .cn-card.live.ok");
  await page.waitForTimeout(600);
  await shot(page, "6-live");
  await page.locator("#usCine .cn-grid .cn-card.live").first().click();
  assert.equal((await page.evaluate(() => window.__played)).title, "MBC 1");

  // home again: continue watching is there
  await page.locator('#usCine .cn-rail [data-v="home"]').click();
  await page.waitForSelector("#usCine .cn-wide");
  await page.waitForTimeout(1200);
  await shot(page, "7-home-continue");

  // another server from the top bar
  await page.locator("#usCine .cn-acc-b").click();
  await page.locator('#usCine .cn-acc-m button:has-text("Second line")').click();
  await page.waitForFunction(() => document.querySelector("#usCine .cn-acc-b b").textContent === "Second line");

  // back to the classic look, and it stays chosen
  await page.locator('#usCine .cn-rail [data-a="classic"]').click();
  assert.equal(await page.locator("#usCine").isVisible(), false);
  assert.equal(await page.evaluate(() => localStorage.getItem("us-desk-look")), '"classic"');
  assert.deepEqual(errors, []);
});
