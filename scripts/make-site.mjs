/* The interface for the TV app: the Windows program's bundle (the website's pages with
   the program's player, adult filter and features) plus the TV's own files.
   node scripts/make-site.mjs <UltraStalker-Desktop checkout with bundle/ built> */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const desktop = path.resolve(process.argv[2] || path.join(root, "..", "ultrastalker-desktop"));
const web = path.join(desktop, "bundle", "web");
for (const f of [path.join(web, "index.html"), path.join(web, "player.js"), path.join(desktop, "app", "features.js"), path.join(desktop, "app", "desktop-app.css")]) {
  if (!fs.existsSync(f)) throw new Error("Missing " + f + " — build the desktop bundle first (npm run bundle in UltraStalker-Desktop v2).");
}
if (!fs.readFileSync(path.join(web, "player.js"), "utf8").includes("const usX = (() =>")) throw new Error("The desktop bundle has no player extras (needs UltraStalker-Desktop 2.6 or newer).");
if (!fs.readFileSync(path.join(web, "engine.js"), "utf8").includes("installAdultFilter({")) throw new Error("The desktop bundle has no adult filter.");
const out = path.join(root, "app", "src", "main", "assets", "site");
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(path.join(out, "app"), { recursive: true });
fs.cpSync(web, path.join(out, "web"), { recursive: true });
fs.copyFileSync(path.join(desktop, "app", "features.js"), path.join(out, "app", "features.js"));
fs.copyFileSync(path.join(desktop, "app", "desktop-app.css"), path.join(out, "app", "desktop-app.css"));
for (const f of fs.readdirSync(path.join(root, "tv-web"))) fs.copyFileSync(path.join(root, "tv-web", f), path.join(out, "app", f));
let n = 0;
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : n++));
walk(out);
console.log("site:", n, "files from", desktop);
