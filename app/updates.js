/* Ultra Stalker for Windows — updates by themselves.

   New versions are published as GitHub releases of K3bOra/UltraStalker-Desktop (the
   build workflow does it). The program looks there a little after it starts and every
   few hours, downloads a newer version in the background and tells the page; the page
   offers "Restart now". Otherwise the update installs when the program is closed. */
import { app, ipcMain } from "electron";
import updater from "electron-updater";
import { log } from "./vlc.js";

const { autoUpdater } = updater;

export function setupUpdates(win) {
  let state = { state: "idle", version: app.getVersion() };
  const send = (s) => {
    state = Object.assign({ current: app.getVersion() }, s);
    if (win && !win.isDestroyed()) win.webContents.send("upd:state", state);
  };
  ipcMain.handle("upd:state", () => state);
  if (!app.isPackaged || process.env.US_SELFTEST || process.env.US_NO_UPDATES) return;

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.allowPrerelease = false;
  autoUpdater.logger = {
    info: (m) => log("update:", m),
    warn: (m) => log("update warning:", m),
    error: (m) => log("update error:", m),
    debug: () => {},
  };
  autoUpdater.on("update-available", (i) => send({ state: "downloading", version: i.version, percent: 0 }));
  autoUpdater.on("download-progress", (p) => send({ state: "downloading", version: state.version, percent: Math.round(p.percent || 0) }));
  autoUpdater.on("update-downloaded", (i) => send({ state: "ready", version: i.version }));
  autoUpdater.on("update-not-available", () => send({ state: "current" }));
  autoUpdater.on("error", (e) => {
    log("update failed:", (e && e.message) || e);
    if (state.state !== "ready") send({ state: "idle" });
  });
  ipcMain.on("upd:install", () => {
    if (state.state !== "ready") return;
    log("update: restarting to install", state.version);
    // silent install, then start the new version
    setImmediate(() => autoUpdater.quitAndInstall(true, true));
  });
  const check = () => autoUpdater.checkForUpdates().catch((e) => log("update check failed:", (e && e.message) || e));
  setTimeout(check, 20000);
  setInterval(check, 4 * 3600 * 1000);
}
