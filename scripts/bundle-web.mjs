/* Copies the Ultra Stalker interface (web/) and the relay code from the UltraStalker
   repository into ./bundle, which the installer ships next to the app.
   Source: $ULTRASTALKER_DIR, or ../UltraStalker / ../ultrastalker next to this repo. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const candidates = [process.env.ULTRASTALKER_DIR, path.join(root, "..", "UltraStalker"), path.join(root, "..", "ultrastalker"), path.join(root, "ultrastalker-src")].filter(Boolean);
const src = candidates.find((d) => fs.existsSync(path.join(d, "web", "index.html")) && fs.existsSync(path.join(d, "worker", "src", "index.js")));
if (!src) {
  console.error("UltraStalker checkout not found. Set ULTRASTALKER_DIR to the UltraStalker repository folder.");
  process.exit(1);
}
const out = path.join(root, "bundle");
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(path.join(out, "relay"), { recursive: true });
fs.cpSync(path.join(src, "web"), path.join(out, "web"), { recursive: true });
fs.copyFileSync(path.join(src, "worker", "src", "index.js"), path.join(out, "relay", "index.mjs"));
let count = 0;
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : count++));
walk(out);
console.log("bundled", count, "files from", src);
