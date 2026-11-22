/* Real Chromium + the packaged interface; fake provider/VLC, no subscriptions. */
import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { startServer } from "../app/server.js";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
test("desktop player controls, category scrollbar and update costs", { timeout: 45000 }, async (t) => {
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), "us-ui-"));
  const { server, origin } = await startServer({
    webDir: path.join(root, "bundle", "web"), relayFile: path.join(root, "bundle", "relay", "index.mjs"),
    appCssFile: path.join(root, "app", "desktop-app.css"), userDir, port: 47392,
    cloudRelay: "https://example.invalid", version: "test",
  });
  let browser;
  try {
    browser = await chromium.launch({
      ...(process.platform === "linux" ? { executablePath: process.env.US_CHROME_PATH || "/usr/bin/chromium", args: ["--no-sandbox"] } : { channel: "chrome" }),
      headless: true,
      ignoreDefaultArgs: ["--hide-scrollbars"],
    });
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.addInitScript(() => {
      localStorage.setItem("us-web-profiles", JSON.stringify([{
        name: "Test provider", portal: "http://provider.test/get.php?username=test&password=test&type=m3u_plus&output=ts",
        source_type: "m3u", playlist_mode: "xtream", source: "web", explicit_http_accepted: true,
      }]));
      window.__nativeTest = { seeks: [], statusTime: 100, statusDelay: 0, inFlight: 0, maxInFlight: 0, categoryQueries: 0 };
      const queryAll = document.querySelectorAll.bind(document);
      document.querySelectorAll = (selector) => {
        if (selector === "#browseCategories .category") window.__nativeTest.categoryQueries++;
        return queryAll(selector);
      };
      window.usNative = {
        win: { cmd() {}, state: () => ({ full: false }), onState() {} },
        vlc: {
          available: true, play: async () => ({ ok: true, version: "3.0.21" }), stop() {}, place() {}, fit() {},
          cmd: async (name, value) => { if (name === "seek") window.__nativeTest.seeks.push(Number(value)); return true; },
          status: async () => {
            const state = window.__nativeTest;
            state.inFlight++; state.maxInFlight = Math.max(state.maxInFlight, state.inFlight);
            await new Promise((r) => setTimeout(r, state.statusDelay));
            state.inFlight--;
            return { state: "playing", time: state.statusTime, length: 3600, info: { width: 1920, height: 1080, vcodec: "h264" } };
          },
          tracks: async () => ({
            audio: [{ id: 1, on: true, name: "English" }],
            subs: Array.from({ length: 35 }, (_, id) => ({ id, on: id === 12, name: id === 12 ? "Arabic" : "Subtitle " + id })),
          }),
        },
      };
    });
    await page.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/p") {
        const target = new URL(url.searchParams.get("u"));
        const action = target.searchParams.get("action");
        const body = /get_.*_categories/.test(action || "") ? Array.from({ length: 488 }, (_, i) => ({ category_id: String(i + 1), category_name: "Category " + (i + 1) }))
          : /get_.*_streams/.test(action || "") ? [{ stream_id: 1, name: "Test channel", category_id: "1" }]
            : { user_info: { auth: 1, status: "Active" } };
        return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
      }
      if (url.pathname.startsWith("/tmdb/")) return route.fulfill({ contentType: "application/json", body: "{}" });
      if (url.origin !== origin) return route.abort();
      return route.continue();
    });
    await page.goto(origin + "/index.html");
    await page.waitForFunction(() => document.querySelector("#browseAccount")?.options.length > 1);
    const account = await page.locator("#browseAccount option").nth(1).getAttribute("value");
    await page.locator("#browseAccount").selectOption(account, { force: true });
    await page.waitForFunction(() => document.querySelectorAll("#dkTvCats .dk-tvc-list button").length === 488);
    await page.waitForFunction(() => document.body.classList.contains("dk-frame"));

    await t.test("category scrollbar is visible, wide and draggable", async () => {
      const list = page.locator("#dkTvCats .dk-tvc-list");
      const info = await list.evaluate((el) => ({
        width: el.offsetWidth - el.clientWidth, overflow: el.scrollHeight > el.clientHeight,
        mask: getComputedStyle(el).webkitMaskImage,
        display: getComputedStyle(el, "::-webkit-scrollbar").display,
      }));
      assert.ok(info.overflow);
      assert.ok(info.width >= 10, "Scrollbar must reserve a usable drag target");
      assert.equal(info.mask, "none");
      assert.equal(info.display, "block");
      const b = await list.boundingBox();
      await page.mouse.move(b.x + b.width - 6, b.y + 18);
      await page.mouse.down();
      await page.mouse.move(b.x + b.width - 6, b.y + 220, { steps: 10 });
      await page.mouse.up();
      assert.ok(await list.evaluate((el) => el.scrollTop > 100));
    });

    await page.evaluate(() => window.USPlayer.play({
      title: "Player controls test", stream: "http://provider.test/movie.mp4", live: false, _plan: ["vlc"], _step: 0,
    }));
    await page.waitForFunction(() => !document.querySelector(".usp-bar .skip-forward")?.disabled);
    // Track discovery follows the first playing status.
    await page.waitForTimeout(150);
    await t.test("Settings and subtitles stay separate, including long subtitle lists", async () => {
      await page.getByRole("button", { name: "Audio & subtitles", exact: true }).click();
      await page.waitForFunction(() => document.querySelectorAll(".usp-menu [data-s]").length > 30);
      await page.locator(".usp-menu").evaluate((el) => { el.scrollTop = 300; });
      await page.getByRole("button", { name: "Settings", exact: true }).click();
      assert.equal(await page.locator(".usp-menu .usp-mh").textContent(), "Settings");
      assert.equal(await page.locator(".usp-menu [data-s]").count(), 0);
      assert.equal(await page.locator(".usp-menu [data-a]").count(), 0);
      assert.equal(await page.locator(".usp-menu").evaluate((el) => el.scrollTop), 0);
      assert.ok(await page.locator('.usp-menu [data-f="fit"]').isVisible());
      await page.getByRole("button", { name: "Audio & subtitles", exact: true }).click();
      assert.ok(await page.locator('.usp-menu [data-s="12"]').isVisible());
      await page.getByRole("button", { name: "Audio & subtitles", exact: true }).click();
    });

    await t.test("five +10 presses accumulate to +50 despite stale VLC samples", async () => {
      for (let i = 0; i < 5; i++) await page.getByRole("button", { name: "Forward 10 seconds", exact: true }).click();
      await page.waitForFunction(() => window.__nativeTest.seeks.at(-1) === 150);
      await page.waitForTimeout(1100); // another stale 100-second status arrives
      for (let i = 0; i < 3; i++) await page.getByRole("button", { name: "Back 10 seconds", exact: true }).click();
      await page.waitForFunction(() => window.__nativeTest.seeks.at(-1) === 120);
      assert.ok((await page.locator(".usp-seek .c").textContent()).includes("2:00"));
    });

    await t.test("player class updates do not rescan 488 categories", async () => {
      await page.waitForTimeout(200);
      await page.evaluate(async () => {
        window.__nativeTest.categoryQueries = 0;
        const stage = document.querySelector(".usp-stage");
        for (let i = 0; i < 8; i++) {
          stage.classList.toggle("test-ui-update");
          await new Promise((r) => setTimeout(r, 45));
        }
      });
      await page.waitForTimeout(100);
      assert.equal(await page.evaluate(() => window.__nativeTest.categoryQueries), 0);
    });

    await t.test("slow VLC responses do not create overlapping polls", async () => {
      await page.evaluate(() => { window.__nativeTest.statusDelay = 1400; window.__nativeTest.maxInFlight = 0; });
      await page.waitForTimeout(3300);
      assert.equal(await page.evaluate(() => window.__nativeTest.maxInFlight), 1);
      await page.evaluate(() => { window.__nativeTest.statusDelay = 0; });
    });

    const reportDir = process.env.US_UI_REPORT_DIR;
    if (reportDir) {
      fs.mkdirSync(reportDir, { recursive: true });
      await page.screenshot({ path: path.join(reportDir, "player-controls.png") });
    }
    await page.evaluate(() => window.USPlayer.close());
    await t.test("navigation still updates categories and live playback hides seek buttons", async () => {
      await page.locator('#dkTvCats .dk-secseg [data-go="vod"]').click();
      await page.waitForFunction(() => document.body.classList.contains("dk-vg-mode"));
      assert.equal(await page.locator("#dkTvCats .dk-tvc-list button").count(), 488);
      await page.evaluate(() => window.USPlayer.play({
        title: "Live controls test", stream: "http://provider.test/live.ts", live: true, _plan: ["vlc"], _step: 0,
      }));
      assert.equal(await page.getByRole("button", { name: "Forward 10 seconds", exact: true }).isVisible(), false);
      assert.equal(await page.getByRole("button", { name: "Back 10 seconds", exact: true }).isVisible(), false);
      await page.evaluate(() => window.USPlayer.close());
    });
    assert.deepEqual(errors, []);
  } finally {
    await browser?.close();
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(userDir, { recursive: true, force: true });
  }
});
