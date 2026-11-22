/* Ultra Stalker for Windows — main process.

   Starts the local server (interface + relay on 127.0.0.1) and opens one window on it.
   The window has no Windows title bar: the app's own gold top bar is the title bar, and
   the minimise / maximise / close buttons sit inside it in the same colours. */
import { app, BrowserWindow, shell, session, nativeTheme, dialog, ipcMain, screen } from "electron";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { startServer, createRecorder } from "./server.js";
import { setupUpdates } from "./updates.js";
import { setupVlc, log } from "./vlc.js";
import http from "node:http";

const HERE = path.dirname(fileURLToPath(import.meta.url));
// Fixed port: the saved sources live in the page's storage, which belongs to this address.
const PORT = 47390;
const CLOUD_RELAY = "https://ultrastalker-web.k3borazz0.workers.dev";

const APP_ID = "com.k3bora.ultrastalker";
app.setAppUserModelId(APP_ID);
// Hardware decoding for HEVC / 4K where the graphics card supports it.
app.commandLine.appendSwitch("enable-features", "PlatformHEVCDecoderSupport,PlatformHEVCEncoderSupport");
app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");
// Machines without a supported graphics card still get WebGL (software), which the
// Ultra engine needs to draw the picture.
app.commandLine.appendSwitch("enable-unsafe-swiftshader");
app.commandLine.appendSwitch("ignore-gpu-blocklist");

if (!app.requestSingleInstanceLock()) app.quit();

function bundleDir() {
  // installed: <app>/resources/bundle ; development: <repo>/bundle
  const packed = path.join(process.resourcesPath || "", "bundle");
  return fs.existsSync(packed) ? packed : path.join(HERE, "..", "bundle");
}

let win = null;
const recorder = createRecorder();
/* Where pictures (S) and recordings (R) go: Pictures\Ultra Stalker, Videos\Ultra Stalker */
const snapDir = () => path.join(app.getPath("pictures"), "Ultra Stalker");
const recDir = () => path.join(app.getPath("videos"), "Ultra Stalker");
function fileName(title, ext) {
  const d = new Date(), p = (n) => String(n).padStart(2, "0");
  const stamp = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}.${p(d.getMinutes())}.${p(d.getSeconds())}`;
  const name = String(title || "Ultra Stalker").replace(/[\u0000-\u001f\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 80).replace(/[. ]+$/, "") || "Ultra Stalker";
  return `${name} ${stamp}.${ext}`;
}
/* A remembered window place that is still on one of the screens (a monitor may be gone). */
function onScreen(b) {
  if (!b || ![b.x, b.y, b.width, b.height].every(Number.isFinite) || b.width < 400 || b.height < 300) return null;
  const ok = screen.getAllDisplays().some(({ workArea: a }) => b.x < a.x + a.width - 80 && b.x + b.width > a.x + 80 && b.y >= a.y - 20 && b.y < a.y + a.height - 80);
  return ok ? b : null;
}
/* Remembered window choice (full screen or window) in the user folder. */
const prefsFile = () => path.join(app.getPath("userData"), "window.json");
let prefs = {};
function loadPrefs() {
  try {
    prefs = JSON.parse(fs.readFileSync(prefsFile(), "utf8")) || {};
  } catch (_) {
    prefs = {};
  }
}
function savePrefs(p) {
  prefs = Object.assign(prefs, p);
  try {
    fs.writeFileSync(prefsFile(), JSON.stringify(prefs));
  } catch (_) {}
}

async function createWindow(origin, shortLink) {
  loadPrefs();
  nativeTheme.themeSource = "dark";
  const place = onScreen(prefs.bounds);
  win = new BrowserWindow({
    width: place ? place.width : 1600,
    height: place ? place.height : 940,
    ...(place ? { x: place.x, y: place.y } : {}),
    minWidth: 900,
    minHeight: 600,
    show: false,
    backgroundColor: "#09090a",
    title: "Ultra Stalker",
    icon: path.join(bundleDir(), "web", "icons", "gold-512.png"),
    // No Windows frame at all: the gold top bar carries the window's own buttons.
    frame: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(HERE, "preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      spellcheck: false,
      backgroundThrottling: false,
      autoplayPolicy: "no-user-gesture-required",
    },
  });
  win.removeMenu();
  // Identify the installed desktop app on the embed document request.
  const playerHost = win.webContents.id;
  win.webContents.session.webRequest.onBeforeSendHeaders(
    { urls: ["https://www.youtube-nocookie.com/embed/*"] },
    (request, done) => {
      const headers = request.requestHeaders;
      if (request.webContentsId === playerHost && request.resourceType === "subFrame") {
        const name = Object.keys(headers).find(key => key.toLowerCase() === "referer") || "Referer";
        headers[name] = "https://" + APP_ID + "/";
      }
      done({ requestHeaders: headers });
    }
  );
  const winState = () => ({ full: win.isFullScreen(), max: win.isMaximized(), mini: !!miniFrom });
  const sendState = () => !win.isDestroyed() && win.webContents.send("win:state", winState());
  for (const ev of ["enter-full-screen", "leave-full-screen", "maximize", "unmaximize"]) win.on(ev, sendState);
  /* Mini player: the same window, small, in the screen's corner and above every other
     window; the page shows only the player. Back: where and how it was. */
  let miniFrom = null;
  const setMini = (on) => {
    if (on && !miniFrom) {
      miniFrom = { full: win.isFullScreen(), max: win.isMaximized(), bounds: win.getNormalBounds() };
      const go = () => {
        const a = screen.getDisplayMatching(win.getBounds()).workArea;
        const w = 520, h = 325;
        win.setMinimumSize(320, 210);
        win.setBounds({ x: a.x + a.width - w - 20, y: a.y + a.height - h - 20, width: w, height: h });
        win.setAlwaysOnTop(true, "floating");
        sendState();
      };
      if (win.isFullScreen()) {
        win.once("leave-full-screen", () => setTimeout(go, 80));
        win.setFullScreen(false);
      } else {
        if (win.isMaximized()) win.unmaximize();
        go();
      }
    } else if (!on && miniFrom) {
      const f = miniFrom;
      miniFrom = null;
      win.setAlwaysOnTop(false);
      win.setMinimumSize(900, 600);
      win.setBounds(f.bounds);
      if (f.max) win.maximize();
      if (f.full) win.setFullScreen(true);
      sendState();
    }
  };
  // remember the window's place and size (not the mini player's)
  win.on("close", () => {
    const b = miniFrom ? miniFrom.bounds : win.getNormalBounds();
    savePrefs({ bounds: b });
    const r = recorder.stop();
    if (r) log("recording saved on close:", r.file, r.bytes, "bytes");
  });
  const toggleFull = () => {
    const on = !win.isFullScreen();
    win.setFullScreen(on);
    savePrefs({ full: on });
  };
  win.webContents.on("before-input-event", (e, input) => {
    if (input.type === "keyDown" && input.key === "F11") {
      e.preventDefault();
      toggleFull();
    }
  });
  ipcMain.removeAllListeners("win:cmd");
  ipcMain.on("win:cmd", (_, c) => {
    if (c === "min") win.minimize();
    else if (c === "mini") setMini(true);
    else if (c === "unmini") setMini(false);
    else if (c === "full") {
      if (miniFrom) setMini(false);
      else toggleFull();
    }
    else if (c === "close") win.close();
  });
  ipcMain.removeAllListeners("win:state");
  ipcMain.on("win:state", (e) => (e.returnValue = winState()));
  const vlc = setupVlc({ win, bundle: bundleDir(), shortLink, snapDir: snapDir() });

  /* Pictures (S): VLC saves its own; the browser player sends the picture; the Ultra
     engine's picture is taken from the window. */
  for (const n of ["app:snap", "rec:start", "rec:stop", "rec:status"]) ipcMain.removeHandler(n);
  ipcMain.handle("app:snap", async (_, o) => {
    try {
      o = o || {};
      const dir = snapDir();
      fs.mkdirSync(dir, { recursive: true });
      const file = path.join(dir, fileName(o.title, "png"));
      if (o.vlc) fs.renameSync(await vlc.snapshot(), file);
      else if (typeof o.dataUrl === "string" && o.dataUrl.startsWith("data:image/png;base64,")) {
        const png = Buffer.from(o.dataUrl.slice(22), "base64");
        if (png.length < 100) throw new Error("empty picture");
        fs.writeFileSync(file, png);
      } else if (o.rect) {
        const r = o.rect;
        const rect = { x: Math.max(0, r.x | 0), y: Math.max(0, r.y | 0), width: Math.max(1, r.width | 0), height: Math.max(1, r.height | 0) };
        const img = await win.webContents.capturePage(rect);
        if (img.isEmpty()) throw new Error("empty picture");
        fs.writeFileSync(file, img.toPNG());
      } else throw new Error("nothing to save");
      log("picture saved", file);
      return { ok: true, file, folder: dir };
    } catch (e) {
      log("picture failed:", (e && e.message) || e);
      return { ok: false, error: String((e && e.message) || e) };
    }
  });
  /* Recording (R): the live channel's bytes as they pass through the local server. */
  ipcMain.handle("rec:start", (_, o) => {
    try {
      const file = path.join(recDir(), fileName(o && o.title, "ts"));
      recorder.start(file);
      log("recording", file);
      return { ok: true, file, folder: recDir() };
    } catch (e) {
      return { ok: false, error: String((e && e.message) || e) };
    }
  });
  ipcMain.handle("rec:stop", () => {
    const r = recorder.stop();
    if (r) log("recording saved", r.file, r.bytes, "bytes", r.seconds, "s");
    return r ? Object.assign({ ok: true, folder: recDir() }, r) : { ok: false };
  });
  ipcMain.handle("rec:status", () => recorder.status());
  ipcMain.removeAllListeners("app:show");
  ipcMain.on("app:show", (_, file) => {
    const f = path.resolve(String(file || ""));
    if ([snapDir(), recDir()].some((d) => f.startsWith(d + path.sep)) && fs.existsSync(f)) shell.showItemInFolder(f);
  });
  setupUpdates(win);
  if (process.env.US_SELFTEST) win.webContents.once("did-finish-load", () => selfTest(vlc).catch((e) => (console.error(e), app.exit(3))));
  else win.webContents.once("did-finish-load", () => setTimeout(() => vlc.warm(), 1500));
  win.once("ready-to-show", () => {
    // Opens taking the whole screen (as it was left last time; F11 switches).
    if (prefs.full !== false) win.setFullScreen(true);
    win.show();
    if (process.env.US_SMOKE) win.webContents.openDevTools({ mode: "detach" });
  });

  // Links to other sites open in the normal browser, never inside the app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(origin)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith(origin) && !url.startsWith("data:")) {
      e.preventDefault();
      if (/^https?:/i.test(url)) shell.openExternal(url);
    }
  });

  // "Open in VLC": the page offers an .m3u playlist; open it with the program Windows
  // uses for playlists (VLC when it is installed) instead of saving it somewhere.
  session.defaultSession.on("will-download", (e, item) => {
    const name = item.getFilename() || "";
    if (/\.m3u8?$/i.test(name)) {
      const file = path.join(os.tmpdir(), "ultra-stalker-" + Date.now() + ".m3u");
      item.setSavePath(file);
      item.once("done", (_, state) => {
        if (state === "completed") shell.openPath(file).then((err) => err && dialog.showMessageBox(win, { type: "info", message: "No video player is set up for playlists on this computer.", detail: "Install VLC to open channels outside Ultra Stalker." }));
      });
    }
    // Backups and other files: Windows' normal "Save as" dialog.
  });

  // Keep the window controls matching the bar when the page asks (light/dark bar areas).
  win.webContents.on("page-title-updated", (e) => e.preventDefault());
  // Files come from this computer, so nothing is worth keeping between runs; clearing the
  // cache makes an updated program start with its own new files.
  await session.defaultSession.clearCache().catch(() => {});
  await win.loadURL(origin + "/index.html");
}

/* Build-machine check: VLC plays a test stream inside the window (US_SELFTEST = folder
   for the result, US_SELFTEST_FILE = a .ts file). */
async function selfTest(vlc) {
  const out = process.env.US_SELFTEST;
  fs.mkdirSync(out, { recursive: true });
  const file = process.env.US_SELFTEST_FILE;
  const srv = http.createServer((req, res) => {
    res.writeHead(200, { "Content-Type": "video/mp2t" });
    // the 8-second file six times over, so there is time for every check
    const data = fs.readFileSync(file);
    let n = 0;
    const more = () => {
      while (n < 6) {
        n++;
        if (!res.write(data)) return res.once("drain", more);
      }
      res.end();
    };
    res.on("error", () => {});
    more();
  });
  await new Promise((r) => srv.listen(0, "127.0.0.1", r));
  await new Promise((r) => setTimeout(r, 1500));
  const result = await vlc.selfTest({ url: "http://127.0.0.1:" + srv.address().port + "/test.ts", outDir: out });
  fs.writeFileSync(path.join(out, "result.json"), JSON.stringify(result, null, 2));
  console.log("SELFTEST", result.ok ? "OK" : "FAILED", JSON.stringify({ status: result.status, pictureLit: result.pictureLit, window: result.window }));
  app.exit(result.ok ? 0 : 1);
}

app.on("second-instance", () => {
  if (win) {
    if (win.isMinimized()) win.restore();
    win.focus();
  }
});

app.whenReady().then(async () => {
  log("start", app.getVersion());
  const bundle = bundleDir();
  let origin, shortLink;
  try {
    ({ origin, shortLink } = await startServer({
      webDir: path.join(bundle, "web"),
      relayFile: path.join(bundle, "relay", "index.mjs"),
      appCssFile: path.join(HERE, "desktop-app.css"),
      userDir: app.getPath("userData"),
      port: PORT,
      cloudRelay: CLOUD_RELAY,
      version: app.getVersion(),
      recorder,
    }));
  } catch (e) {
    dialog.showErrorBox("Ultra Stalker", "Ultra Stalker could not start its local service (port " + PORT + " is busy?).\n\n" + String((e && e.message) || e));
    app.quit();
    return;
  }
  await createWindow(origin, shortLink);
});

app.on("window-all-closed", () => app.quit());
