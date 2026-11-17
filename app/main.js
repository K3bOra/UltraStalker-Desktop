/* Ultra Stalker for Windows — main process.

   Starts the local server (interface + relay on 127.0.0.1) and opens one window on it.
   The window has no Windows title bar: the app's own gold top bar is the title bar, and
   the minimise / maximise / close buttons sit inside it in the same colours. */
import { app, BrowserWindow, shell, session, nativeTheme, dialog } from "electron";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { startServer } from "./server.js";
import { setupVlc, log } from "./vlc.js";
import http from "node:http";

const HERE = path.dirname(fileURLToPath(import.meta.url));
// Fixed port: the saved sources live in the page's storage, which belongs to this address.
const PORT = 47390;
const CLOUD_RELAY = "https://ultrastalker-web.k3borazz0.workers.dev";
const BAR = 76;

app.setAppUserModelId("com.k3bora.ultrastalker");
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

async function createWindow(origin, shortLink) {
  nativeTheme.themeSource = "dark";
  win = new BrowserWindow({
    width: 1600,
    height: 940,
    minWidth: 1180,
    minHeight: 720,
    show: false,
    backgroundColor: "#09090a",
    title: "Ultra Stalker",
    icon: path.join(bundleDir(), "web", "icons", "gold-512.png"),
    titleBarStyle: "hidden",
    titleBarOverlay: { color: "#141210", symbolColor: "#e6cb8c", height: BAR },
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
  const vlc = setupVlc({ win, bundle: bundleDir(), shortLink });
  if (process.env.US_SELFTEST) win.webContents.once("did-finish-load", () => selfTest(vlc).catch((e) => (console.error(e), app.exit(3))));
  win.once("ready-to-show", () => {
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
    fs.createReadStream(file).pipe(res);
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
    }));
  } catch (e) {
    dialog.showErrorBox("Ultra Stalker", "Ultra Stalker could not start its local service (port " + PORT + " is busy?).\n\n" + String((e && e.message) || e));
    app.quit();
    return;
  }
  await createWindow(origin, shortLink);
});

app.on("window-all-closed", () => app.quit());
