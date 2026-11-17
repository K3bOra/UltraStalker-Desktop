/* VLC inside Ultra Stalker.

   The program starts one VLC (the copy shipped with Ultra Stalker, else an installed one)
   with no window of its own and its remote-control interface on a private local port.
   VLC draws into a plain borderless window owned by the main window, which the page keeps
   exactly over the free part of the player — so the picture is VLC's (graphics-card
   decoding, every codec) while the gold controls stay the app's own and drive VLC. */
import { BaseWindow, ipcMain, app, shell, desktopCapturer, screen } from "electron";
import { spawn } from "node:child_process";
import net from "node:net";
import fs from "node:fs";
import path from "node:path";
import { Rc, parseInfo, parseTracks, parseStats } from "./vlc-rc.js";

const WIN = process.platform === "win32";

export function findVlc(bundle) {
  const list = [];
  if (process.env.US_VLC_PATH) list.push(process.env.US_VLC_PATH);
  if (WIN) {
    list.push(path.join(bundle, "..", "vlc", "vlc.exe"), path.join(bundle, "vlc", "vlc.exe"));
    for (const pf of [process.env.ProgramFiles, process.env["ProgramFiles(x86)"], process.env.ProgramW6432, "C:\\Program Files", "C:\\Program Files (x86)"]) {
      if (pf) list.push(path.join(pf, "VideoLAN", "VLC", "vlc.exe"));
    }
  } else list.push("/usr/bin/vlc", "/usr/local/bin/vlc", "/Applications/VLC.app/Contents/MacOS/VLC");
  return (
    list.find((f) => {
      try {
        return fs.statSync(f).isFile();
      } catch (_) {
        return false;
      }
    }) || ""
  );
}

/* "3.0.21" from the VLC folder (NEWS.txt ships with every Windows build). */
function vlcVersion(exe) {
  try {
    const news = fs.readFileSync(path.join(path.dirname(exe), "NEWS.txt"), "utf8").slice(0, 400);
    const m = news.match(/Changes between [\d.]+ and ([\d.]+)/);
    return m ? m[1] : "";
  } catch (_) {
    return "";
  }
}

function freePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.unref();
    s.on("error", reject);
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
}

/* The program's own log (user folder → ultra-stalker-log.txt), for "why didn't it play?". */
const LOG_DIR = () => app.getPath("userData");
export function log(...parts) {
  try {
    const file = path.join(LOG_DIR(), "ultra-stalker-log.txt");
    try {
      if (fs.statSync(file).size > 1024 * 1024) fs.writeFileSync(file, "");
    } catch (_) {}
    fs.appendFileSync(file, new Date().toISOString() + "  " + parts.map(String).join(" ") + "\n");
  } catch (_) {}
}

export function setupVlc({ win, bundle, shortLink }) {
  const exe = findVlc(bundle);
  const vlcLog = path.join(LOG_DIR(), "vlc-log.txt");
  let logMark = 0;
  log("program", app.getVersion(), process.platform, process.arch, "· VLC:", exe || "not found");
  /* VLC's own error lines since the current channel started (e.g. "HTTP 403"). */
  function vlcErrors() {
    try {
      const all = fs.readFileSync(vlcLog, "utf8");
      const lines = all.slice(logMark).split(/\r?\n/).filter((l) => /error|warning: (?:http|access)/i.test(l) && !/dbus|interface "|no suitable interface/i.test(l));
      return lines.slice(-3).map((l) => l.replace(/^.*?(?:main |)(\w+ (?:error|warning)):?\s*/i, "$1: ").slice(0, 160)).join(" · ");
    } catch (_) {
      return "";
    }
  }
  let proc = null, rc = null, starting = null, vwin = null;
  const version = vlcVersion(exe);
  let rect = null, fit = "fit", info = {}, polls = 0, lastStats = null;
  let ops = Promise.resolve(), pendingVol = null;
  /* While VLC is paused its control answers only "pause" (everything else gets "Type
     'pause' to continue"), so un-pause before stopping, switching or seeking. */
  async function resumeIfPaused(r) {
    const st = await r.cmd("status");
    if (/Type 'pause' to continue/.test(st.join("\n"))) {
      await r.cmd("pause");
      r.state = "playing";
      if (pendingVol != null) {
        await r.cmd("volume " + pendingVol);
        pendingVol = null;
      }
      return true;
    }
    return false;
  }
  const queue = (fn) => {
    const p = ops.then(fn, fn);
    ops = p.catch(() => {});
    return p;
  };

  ipcMain.on("vlc:available", (e) => (e.returnValue = !!exe));

  function videoWindow() {
    if (vwin && !vwin.isDestroyed()) return vwin;
    vwin = new BaseWindow({
      parent: win,
      show: false,
      frame: false,
      focusable: false,
      skipTaskbar: true,
      resizable: false,
      movable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      hasShadow: false,
      roundedCorners: false,
      thickFrame: false,
      backgroundColor: "#000000",
      width: 320,
      height: 180,
      title: "Ultra Stalker video",
    });
    return vwin;
  }
  function handleArg() {
    const h = videoWindow().getNativeWindowHandle();
    if (WIN) return "--drawable-hwnd=" + (h.length >= 8 ? h.readBigUInt64LE(0) : BigInt(h.readUInt32LE(0))).toString();
    if (process.platform === "darwin") return "";
    return "--drawable-xid=" + h.readUInt32LE(0);
  }

  async function ensure() {
    if (rc && !rc.closed && proc && proc.exitCode === null) return rc;
    if (starting) return starting;
    starting = (async () => {
      kill();
      if (!exe) throw new Error("VLC isn't installed");
      const port = await freePort();
      try {
        fs.writeFileSync(vlcLog, "");
      } catch (_) {}
      logMark = 0;
      const args = [
        "--intf=dummy",
        "--extraintf=oldrc",
        "--rc-host=127.0.0.1:" + port,
        WIN ? "--rc-quiet" : "--rc-fake-tty",
        WIN ? "--dummy-quiet" : "",
        "--ignore-config",
        "--no-video-title-show",
        "--no-osd",
        "--no-snapshot-preview",
        "--no-mouse-events",
        "--no-keyboard-events",
        "--no-video-deco",
        "--no-sub-autodetect-file",
        "--no-metadata-network-access",
        "--avcodec-hw=any",
        "--http-reconnect",
        "--stats",
        "--verbose=0",
        "--file-logging",
        "--logfile=" + vlcLog,
        "--log-verbose=0",
        handleArg(),
      ].filter(Boolean);
      log("starting VLC", exe, args.join(" "));
      // (no windowsHide: VLC's picture window must be allowed to show)
      proc = spawn(exe, args, { stdio: ["ignore", "ignore", "pipe"], env: Object.assign({}, process.env, { LANGUAGE: "en", LC_ALL: "C", LANG: "C" }) });
      let stderr = "";
      proc.stderr.on("data", (d) => (stderr = (stderr + d).slice(-2000)));
      proc.on("error", (e) => log("VLC failed to start:", e.message));
      proc.on("exit", (code) => {
        log("VLC exited", code, stderr.trim().split(/\r?\n/).slice(-3).join(" | "));
        if (rc) rc.closed = true;
      });
      // connect to its control port (VLC needs a moment to start)
      const t0 = Date.now();
      let sock = null;
      while (!sock && Date.now() - t0 < 10000) {
        if (proc.exitCode !== null) throw new Error("VLC closed right away (" + proc.exitCode + ") " + stderr.trim().split(/\r?\n/).slice(-1)[0]);
        sock = await new Promise((r) => {
          const s = net.connect(port, "127.0.0.1");
          s.once("connect", () => r(s));
          s.once("error", () => r(null));
        });
        if (!sock) await new Promise((r) => setTimeout(r, 150));
      }
      if (!sock) throw new Error("VLC's control didn't answer on port " + port);
      log("VLC control connected on port", port, "after", Date.now() - t0, "ms");
      rc = new Rc(sock);
      await rc.cmd("volume", { timeout: 1500 }); // answers once VLC is ready
      return rc;
    })();
    try {
      return await starting;
    } finally {
      starting = null;
    }
  }
  function kill() {
    try {
      if (rc && !rc.closed) rc.sock.end("quit\n");
    } catch (_) {}
    rc = null;
    if (proc && proc.exitCode === null) {
      const p = proc;
      setTimeout(() => p.exitCode === null && p.kill(), 800);
    }
    proc = null;
  }

  /* Picture placement: page coordinates (CSS px) → screen, in step with the window. */
  function place() {
    if (!vwin || vwin.isDestroyed()) return;
    if (!rect || !win || win.isDestroyed() || win.isMinimized() || !win.isVisible()) {
      if (vwin.isVisible()) vwin.hide();
      return;
    }
    const cb = win.getContentBounds();
    const z = win.webContents.getZoomFactor() || 1;
    const b = { x: Math.round(cb.x + rect.x * z), y: Math.round(cb.y + rect.y * z), width: Math.max(2, Math.round(rect.w * z)), height: Math.max(2, Math.round(rect.h * z)) };
    vwin.setBounds(b);
    if (!vwin.isVisible()) vwin.showInactive();
    applyFit();
  }
  let fitKey = "";
  function applyFit() {
    if (!rc || rc.closed || !rect) return;
    let crop = "";
    if (fit === "fill" && rect.w && rect.h) crop = rect.w + ":" + rect.h;
    else if (info.width && info.height) crop = info.width + ":" + info.height;
    if (!crop || crop === fitKey) return;
    fitKey = crop;
    rc.cmd("vcrop " + crop).catch(() => {});
  }
  for (const ev of ["move", "resize", "maximize", "unmaximize", "restore", "enter-full-screen", "leave-full-screen", "show"]) win.on(ev, place);
  win.on("minimize", () => vwin && !vwin.isDestroyed() && vwin.hide());
  win.on("hide", () => vwin && !vwin.isDestroyed() && vwin.hide());
  win.webContents.on("render-process-gone", () => {
    rect = null;
    place();
    queue(async () => rc && !rc.closed && (await resumeIfPaused(rc), await rc.cmd("stop"), await rc.cmd("clear")));
  });
  win.webContents.on("did-start-navigation", (e) => {
    if (e.isMainFrame && !e.isSameDocument) {
      rect = null;
      place();
      queue(async () => rc && !rc.closed && (await resumeIfPaused(rc), await rc.cmd("stop"), await rc.cmd("clear")));
    }
  });

  const play = (o) =>
    queue(async () => {
      try {
        if (!o || !/^https?:\/\//i.test(String(o.url || ""))) throw new Error("bad link");
        if (process.env.US_DEBUG) console.log("[vlc] play", o.url);
        const r = await ensure();
        info = {};
        fitKey = "";
        polls = 0;
        lastStats = null;
        fit = o.fit === "fill" ? "fill" : "fit";
        pendingVol = null;
        await resumeIfPaused(r);
        await r.cmd("stop");
        await r.cmd("clear");
        const caching = Math.max(300, Math.min(20000, +o.caching || 3000));
        const opts = [":network-caching=" + caching, ":http-reconnect"];
        const link = shortLink ? shortLink(String(o.url)) : String(o.url);
        try {
          logMark = fs.statSync(vlcLog).size;
        } catch (_) {
          logMark = 0;
        }
        await r.cmd("add " + link.replace(/\s/g, "%20") + " " + opts.join(" "));
        if (o.volume != null) await r.cmd("volume " + Math.max(0, Math.min(512, Math.round(+o.volume) || 0)));
        log("VLC playing", link);
        return { ok: true, version };
      } catch (e) {
        log("VLC play failed:", (e && e.message) || e);
        return { ok: false, error: String((e && e.message) || e) };
      }
    });
  ipcMain.handle("vlc:play", (_, o) => play(o));
  ipcMain.on("vlc:stop", () => {
    rect = null;
    place();
    info = {};
    queue(async () => {
      if (rc && !rc.closed) {
        await resumeIfPaused(rc);
        await rc.cmd("stop");
        await rc.cmd("clear");
      }
    });
  });
  const ALLOWED = { pause: false, play: false, volume: true, seek: true, atrack: true, strack: true };
  ipcMain.handle("vlc:cmd", async (_, name, arg) => {
    if (!(name in ALLOWED) || !rc || rc.closed) return false;
    let line = name;
    if (ALLOWED[name]) {
      if (!/^-?\d{1,9}$/.test(String(arg))) return false;
      line += " " + arg;
    }
    // "pause" toggles in VLC: only send it when the state really changes
    if (name === "pause") {
      if (rc.state === "paused") return true;
      await rc.cmd("pause");
      rc.state = "paused";
      return true;
    }
    if (name === "play") return queue(() => resumeIfPaused(rc));
    if (rc.state === "paused") {
      // volume waits for play; seeking or changing a track resumes playback
      if (name === "volume") {
        pendingVol = arg;
        return true;
      }
      return queue(async () => {
        await resumeIfPaused(rc);
        await rc.cmd(line);
        return true;
      });
    }
    await rc.cmd(line);
    return true;
  });
  const status = async () => {
    if (!rc || rc.closed) return { state: starting ? "opening" : "stopped", time: 0, length: 0, error: rc && rc.closed ? "VLC closed" : "" };
    const st = await rc.cmd("status");
    const txt = st.join("\n");
    let state = rc.state;
    if (/Type 'pause' to continue/.test(txt)) state = "paused";
    const time = await rc.number("get_time");
    const length = await rc.number("get_length");
    const playing = await rc.number("is_playing");
    if (!playing && state !== "paused") state = "stopped";
    else if (playing && state === "stopped") state = "playing";
    rc.state = state;
    polls++;
    if (state !== "stopped" && (!info.width || polls % 5 === 0)) {
      const i = parseInfo(await rc.cmd("info", { block: /end of stream info|^no input/ }));
      if (i.vcodec || i.acodec) {
        const was = info.width;
        info = i;
        if (!was) applyFit();
      }
      lastStats = parseStats(await rc.cmd("stats"));
    }
    return { state, time, length, info, stats: lastStats, version, error: state === "stopped" ? vlcErrors() : "" };
  };
  ipcMain.handle("vlc:status", () => status());
  ipcMain.on("app:logs", () => shell.showItemInFolder(path.join(LOG_DIR(), "ultra-stalker-log.txt")));
  ipcMain.handle("vlc:tracks", async () => {
    if (!rc || rc.closed) return { audio: [], subs: [] };
    return { audio: parseTracks(await rc.cmd("atrack")), subs: parseTracks(await rc.cmd("strack")) };
  });
  ipcMain.on("vlc:place", (_, r) => {
    rect = r && [r.x, r.y, r.w, r.h].every((n) => Number.isFinite(n)) && r.w > 0 && r.h > 0 ? { x: r.x, y: r.y, w: r.w, h: r.h } : null;
    place();
  });
  ipcMain.on("vlc:fit", (_, f) => {
    fit = f === "fill" ? "fill" : "fit";
    fitKey = "";
    applyFit();
  });

  app.on("before-quit", kill);
  win.on("closed", () => {
    kill();
    if (vwin && !vwin.isDestroyed()) vwin.destroy();
  });
  /* Self-test (build machine): play a file in the window, read VLC's state, take a
     picture of the screen and say whether VLC's picture is really there. */
  async function selfTest({ url, outDir }) {
    const result = { exe, version, steps: [] };
    const step = (k, v) => result.steps.push([k, v]);
    rect = { x: 120, y: 160, w: 640, h: 360 };
    const r = await play({ url, live: true, caching: 1500, volume: 0 });
    step("play", r);
    let last = null;
    for (let i = 0; i < 24; i++) {
      await new Promise((ok) => setTimeout(ok, 500));
      last = await status();
      if (i % 4 === 0) step("status", { state: last.state, time: last.time, info: last.info, error: last.error });
      if (last.time >= 2 && last.info && last.info.width) break;
    }
    place();
    await new Promise((ok) => setTimeout(ok, 1500));
    result.status = last;
    result.window = vwin && !vwin.isDestroyed() ? { visible: vwin.isVisible(), bounds: vwin.getBounds() } : null;
    try {
      const d = screen.getPrimaryDisplay();
      const shots = await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: d.size.width, height: d.size.height } });
      const img = shots[0].thumbnail;
      fs.writeFileSync(path.join(outDir, "screen.png"), img.toPNG());
      // how colourful is the area where VLC draws? (black = no picture)
      const b = result.window.bounds, scale = img.getSize().width / d.size.width;
      const crop = img.crop({ x: Math.round((b.x - d.bounds.x) * scale), y: Math.round((b.y - d.bounds.y) * scale), width: Math.round(b.width * scale), height: Math.round(b.height * scale) }).toBitmap();
      let lit = 0, n = 0;
      for (let i = 0; i < crop.length; i += 4 * 97, n++) if (crop[i] + crop[i + 1] + crop[i + 2] > 120) lit++;
      result.pictureLit = n ? Math.round((lit / n) * 100) : 0;
    } catch (e) {
      result.captureError = String(e.message || e);
    }
    result.ok = !!(r && r.ok && last && last.time >= 1 && last.info && last.info.width && result.pictureLit > 20);
    try {
      result.log = fs.readFileSync(path.join(LOG_DIR(), "ultra-stalker-log.txt"), "utf8").slice(-4000);
      result.vlcLog = fs.readFileSync(vlcLog, "utf8").slice(-3000);
    } catch (_) {}
    return result;
  }

  return { exe, selfTest };
}
