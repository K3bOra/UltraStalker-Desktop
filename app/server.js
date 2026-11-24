/* Ultra Stalker for Windows — the local server.

   One small HTTP server on 127.0.0.1 does two jobs:
     1. serves the Ultra Stalker interface (the same pages as the website), with the
        headers that make the page "cross-origin isolated" so the Ultra engine can use
        every CPU core;
     2. runs the website's relay code (/p, /ticket, /play, /health) right here, so the
        portal, Xtream and M3U servers are reached directly from this computer's own
        connection — no cloud relay in between, channels open as fast as in VLC.
   Artwork lookups (/tmdb/…) are forwarded to the online relay, which keeps the TMDB key.

   Everything listens on 127.0.0.1 only; nothing is reachable from other machines. */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { Readable } from "node:stream";
import { pathToFileURL } from "node:url";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".wasm": "application/wasm",
  ".txt": "text/plain; charset=utf-8",
};
const ISOLATE = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "credentialless",
  "Cross-Origin-Resource-Policy": "same-origin",
};
const SHORT = new Map();
const RELAY_PATHS = /^\/(p|ticket|health)$|^\/play\//;

/* The relay secret seals play tickets; one per installation, kept in the user folder. */
export function relayKey(dir) {
  const file = path.join(dir, "relay.key");
  try {
    const k = fs.readFileSync(file, "utf8").trim();
    if (/^[0-9a-f]{64}$/i.test(k)) return k;
  } catch (_) {}
  const k = crypto.randomBytes(32).toString("hex");
  try {
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(file, k, { mode: 0o600 });
  } catch (_) {}
  return k;
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const parts = [];
    let size = 0;
    req.on("data", (c) => {
      size += c.length;
      if (size > 1 << 20) {
        reject(new Error("body too large"));
        req.destroy();
      } else parts.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(parts)));
    req.on("error", reject);
  });
}

/* Hand a fetch Response back to the Node response, streaming the body. When the page
   stops reading (channel change, player closed) the upstream connection is closed too:
   many IPTV lines allow only one stream at a time. */
async function send(res, req, response, tap) {
  const headers = {};
  response.headers.forEach((v, k) => {
    if (k !== "content-encoding" && k !== "transfer-encoding") headers[k] = v;
  });
  res.writeHead(response.status, headers);
  if (!response.body || req.method === "HEAD") return res.end();
  const stream = Readable.fromWeb(response.body);
  const stop = () => stream.destroy();
  req.on("close", stop);
  res.on("close", stop);
  stream.on("error", () => res.destroy());
  if (tap) stream.on("data", tap);
  stream.pipe(res);
}

/* Recording a live channel: the picture already comes through this server (VLC, the
   browser and the Ultra engine all open /play/… here), so the program keeps a copy of
   those bytes in a file — no second connection to the line, which many lines refuse. */
export function createRecorder() {
  let cur = null;
  const MEDIA = /^(video\/|audio\/|application\/(octet-stream|x-mpegts|mp2t|vnd\.dlna\.mpeg-tts))/i;
  return {
    start(file) {
      this.stop();
      fs.mkdirSync(path.dirname(file), { recursive: true });
      const out = fs.createWriteStream(file);
      cur = { file, out, bytes: 0, at: Date.now(), error: "" };
      out.on("error", (e) => cur && cur.out === out && (cur.error = String(e.message || e)));
      return { file };
    },
    stop() {
      if (!cur) return null;
      const r = { file: cur.file, bytes: cur.bytes, seconds: Math.round((Date.now() - cur.at) / 1000), error: cur.error };
      const { out, file, bytes } = cur;
      cur = null;
      out.end(() => {
        if (!bytes) fs.rm(file, { force: true }, () => {});
      });
      return r;
    },
    status() {
      return cur ? { on: true, file: cur.file, bytes: cur.bytes, seconds: Math.round((Date.now() - cur.at) / 1000), error: cur.error } : { on: false };
    },
    /* the copy for one relayed response, or null when it isn't the picture */
    tap(pathname, method, response) {
      if (!cur || method !== "GET" || !/^\/play\//.test(pathname) || response.status >= 300) return null;
      const type = response.headers.get("content-type") || "";
      if (type && !MEDIA.test(type)) return null;
      const mine = cur;
      return (chunk) => {
        if (cur !== mine || mine.error) return;
        mine.bytes += chunk.length;
        mine.out.write(chunk);
      };
    },
  };
}

export async function startServer({ webDir, relayFile, appCssFile, userDir, port, cloudRelay, version, recorder }) {
  const worker = (await import(pathToFileURL(relayFile).href)).default;
  const env = { RELAY_KEY: relayKey(userDir), ALLOW_PRIVATE: "1" };
  const origin = `http://127.0.0.1:${port}`;
  const appCss = appCssFile && fs.existsSync(appCssFile) ? fs.readFileSync(appCssFile, "utf8") : "";

  const server = http.createServer(async (req, res) => {
    let url;
    try {
      url = new URL(req.url, origin);
    } catch (_) {
      res.writeHead(400).end();
      return;
    }
    // the program's own window buttons and features
    const own = url.pathname.match(/^\/__app\/(window-ui|features|sources-ui|cards)\.js$/);
    if (own) {
      const f = path.join(path.dirname(appCssFile || ""), own[1] + ".js");
      if (appCssFile && fs.existsSync(f)) {
        res.writeHead(200, Object.assign({ "Content-Type": TYPES[".js"], "Cache-Control": "no-cache" }, ISOLATE));
        return res.end(fs.readFileSync(f));
      }
    }
    // Short links for VLC (its control line can't carry a 3,000-character ticket).
    const short = url.pathname.match(/^\/v\/([A-Za-z0-9]{10,24})(?:\.[a-z0-9]{1,5})?$/);
    if (short) {
      const target = SHORT.get(short[1]);
      if (!target) {
        res.writeHead(404).end();
        return;
      }
      url = new URL(target, origin);
    }
    try {
      // 1) relay, run locally
      if (RELAY_PATHS.test(url.pathname) || (req.method === "OPTIONS" && url.pathname === "/p")) {
        const headers = new Headers();
        for (const [k, v] of Object.entries(req.headers)) if (typeof v === "string") headers.set(k, v);
        // The page and its players are this same local origin.
        if (!headers.get("origin") && !headers.get("referer")) headers.set("origin", origin);
        const init = { method: req.method, headers };
        if (req.method === "POST") init.body = await readBody(req);
        const response = await worker.fetch(new Request(url.toString(), init), env);
        if (process.env.US_DEBUG) console.log("[relay]", req.method, url.pathname.slice(0, 18), url.search.slice(0, 30), response.status, String(req.headers["user-agent"] || "").slice(0, 30));
        return send(res, req, response, recorder && recorder.tap(url.pathname, req.method, response));
      }
      // 2) artwork lookups: the online relay keeps the TMDB key
      if (url.pathname.startsWith("/tmdb/")) {
        const r = await fetch(cloudRelay + url.pathname + url.search, { headers: { Origin: "https://k3bora.github.io", Accept: "application/json" } });
        const body = Buffer.from(await r.arrayBuffer());
        res.writeHead(r.status, { "Content-Type": r.headers.get("content-type") || "application/json", "Cache-Control": "max-age=3600" });
        return res.end(body);
      }
      // 3) the interface
      let rel = decodeURIComponent(url.pathname);
      if (rel === "/" || rel === "") rel = "/index.html";
      const file = path.normalize(path.join(webDir, rel));
      if (!file.startsWith(path.normalize(webDir + path.sep))) {
        res.writeHead(403).end();
        return;
      }
      if (rel === "/config.js") {
        res.writeHead(200, Object.assign({ "Content-Type": TYPES[".js"], "Cache-Control": "no-cache" }, ISOLATE));
        return res.end(`window.US_WEB_CONFIG = { relay: ${JSON.stringify(origin)}, desktop: ${JSON.stringify(version || "")} };`);
      }
      // the page must never try to register the website's isolation helper here
      if (rel === "/coi-sw.js" || rel === "/coi.js") {
        res.writeHead(200, Object.assign({ "Content-Type": TYPES[".js"], "Cache-Control": "no-cache" }, ISOLATE));
        return res.end("/* the desktop app is isolated by its own server */");
      }
      fs.stat(file, (err, st) => {
        if (err || !st.isFile()) {
          res.writeHead(404, ISOLATE).end("Not found");
          return;
        }
        const type = TYPES[path.extname(file).toLowerCase()] || "application/octet-stream";
        // Always check with the server (it is local, so this costs nothing): a new version
        // of the program must never run with yesterday's files from the cache.
        const tag = '"' + st.size.toString(36) + "-" + Math.floor(st.mtimeMs).toString(36) + '"';
        const head = Object.assign({ "Content-Type": type, "Cache-Control": "no-cache", ETag: tag }, ISOLATE);
        if (!type.startsWith("text/html") && req.headers["if-none-match"] === tag) {
          res.writeHead(304, head);
          return res.end();
        }
        if (type.startsWith("text/html")) {
          let html = fs.readFileSync(file, "utf8");
          const inject = `<script>document.documentElement.classList.add("us-app");window.US_APP=${JSON.stringify({ version: version || "" })};</script>` + (appCss ? `<style id="usAppCss">${appCss}</style>` : "") + '<script defer src="/__app/window-ui.js"></script><script defer src="/__app/features.js"></script><script defer src="/__app/sources-ui.js"></script><script defer src="/__app/cards.js"></script>';
          // the "this is the program" marker first (the page reads it as it starts), the styles last
          const mark = inject.match(/^<script>[\s\S]*?<\/script>/)[0];
          html = html.replace(/<head[^>]*>/i, (h) => h + mark).replace("</head>", inject.slice(mark.length) + "</head>");
          res.writeHead(200, head);
          return res.end(html);
        }
        head["Content-Length"] = st.size;
        res.writeHead(200, head);
        if (req.method === "HEAD") return res.end();
        fs.createReadStream(file).pipe(res);
      });
    } catch (e) {
      if (!res.headersSent) res.writeHead(502, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: String((e && e.message) || e).slice(0, 200) }));
    }
  });
  server.keepAliveTimeout = 65000;
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", resolve);
  });
  /* A short local link standing for a long one on this same server (kept for the
     last 64 links). */
  function shortLink(long) {
    const u = new URL(long, origin);
    if (u.origin !== origin) return long;
    const id = crypto.randomBytes(9).toString("base64url").replace(/[-_]/g, "x");
    SHORT.set(id, u.pathname + u.search);
    while (SHORT.size > 64) SHORT.delete(SHORT.keys().next().value);
    const ext = (u.pathname.match(/\.([a-z0-9]{1,5})$/i) || [])[0] || "";
    return origin + "/v/" + id + ext;
  }
  return { server, origin, shortLink };
}
