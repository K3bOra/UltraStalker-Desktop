/* VLC's remote control: the connection and reading its replies (no Electron here, so
   it can be tested on its own). */
/* VLC's remote control over TCP. Commands run one at a time; a reply ends with the
   "<command>: returned N" line, or is a single line (get_time, is_playing…), or a
   block (info). "status change:" lines arrive at any time and only update the state. */
export class Rc {
  constructor(sock) {
    this.sock = sock;
    this.buf = "";
    this.cur = null;
    this.chain = Promise.resolve();
    this.state = "stopped";
    this.closed = false;
    sock.setEncoding("utf8");
    sock.setNoDelay(true);
    sock.on("data", (d) => {
      this.buf += d;
      let i;
      while ((i = this.buf.indexOf("\n")) >= 0) {
        const line = this.buf.slice(0, i).replace(/\r$/, "");
        this.buf = this.buf.slice(i + 1);
        this.line(line);
      }
    });
    const gone = () => {
      this.closed = true;
      if (this.cur) this.cur.done();
    };
    sock.on("close", gone);
    sock.on("error", gone);
  }
  line(l) {
    const sc = l.match(/^status change: \( (play|pause|stop) state: (\d+) \)(?::\s*(\w+))?/);
    if (sc) {
      if (sc[1] === "stop" || sc[3] === "End") this.state = "stopped";
      else if (sc[3] === "Pause") this.state = "paused";
      else if (sc[3] === "Play" || sc[1] === "play") this.state = "playing";
      return;
    }
    if (/^status change:/.test(l)) return;
    const c = this.cur;
    if (!c) return;
    c.lines.push(l);
    if (c.end(l)) c.done();
  }
  cmd(text, { single = false, block = null, timeout = 1500 } = {}) {
    const run = () =>
      new Promise((resolve) => {
        if (this.closed) return resolve([]);
        const name = text.split(" ")[0];
        const c = {
          lines: [],
          end: (l) => (single ? true : block ? block.test(l) : new RegExp("^" + name + ": returned -?\\d+").test(l)) || /^Unknown command/.test(l),
          done: () => {
            if (this.cur !== c) return;
            clearTimeout(t);
            this.cur = null;
            resolve(c.lines.filter((l) => !/: returned -?\d+/.test(l)));
          },
        };
        const t = setTimeout(() => c.done(), timeout);
        this.cur = c;
        this.sock.write(text + "\n");
      });
    const p = this.chain.then(run, run);
    this.chain = p.catch(() => {});
    return p;
  }
  async number(text) {
    const l = await this.cmd(text, { single: true, timeout: 800 });
    const n = parseFloat((l[0] || "").trim());
    return isFinite(n) ? n : 0;
  }
}

const CODEC = { h264: "h264", hevc: "hevc", h265: "hevc", mpgv: "mpeg2", mp2v: "mpeg2", mp1v: "mpeg1", av01: "av1", vp09: "vp9", mpga: "mp3", mp3: "mp3", a52: "ac-3", eac3: "ec-3", mp4a: "aac", opus: "opus", dts: "dts", vorb: "vorbis", flac: "flac" };
function codecOf(line) {
  const m = String(line || "").match(/\(([a-z0-9 ]{3,4})\)\s*$/i);
  const k = m ? m[1].trim().toLowerCase() : "";
  return CODEC[k] || k;
}
function channels(s) {
  s = String(s || "").trim();
  if (/3F2R\/LFE|5\.1/i.test(s)) return "5.1";
  if (/3F4R\/LFE|7\.1/i.test(s)) return "7.1";
  return s;
}
/* "info" → picture size, frame rate, codecs, channels */
export function parseInfo(lines) {
  const out = {};
  let blk = null;
  const flush = () => {
    if (!blk) return;
    if (/video/i.test(blk.type) && !out.vcodec) {
      out.vcodec = codecOf(blk.codec);
      const r = (blk.res || "").match(/(\d{2,5})x(\d{2,5})/);
      if (r) {
        out.width = +r[1];
        out.height = +r[2];
      }
      if (blk.fps) out.fps = parseFloat(blk.fps) || 0;
    } else if (/audio/i.test(blk.type) && !out.acodec) {
      out.acodec = codecOf(blk.codec);
      out.channels = channels(blk.ch);
    }
  };
  for (const l of lines) {
    if (/^\+----\[/.test(l)) {
      flush();
      blk = {};
      continue;
    }
    if (!blk) continue;
    const m = l.match(/^\|\s*([^:]+):\s*(.*)$/);
    if (!m) continue;
    const k = m[1].trim().toLowerCase(), v = m[2];
    if (k === "codec") blk.codec = v;
    else if (k === "type") blk.type = v;
    else if (k === "video resolution") blk.res = v;
    else if (k === "frame rate") blk.fps = v;
    else if (k === "channels") blk.ch = v;
  }
  flush();
  return out;
}
/* "atrack" / "strack" → [{id, name, on}] */
export function parseTracks(lines) {
  const out = [];
  for (const l of lines) {
    const m = l.match(/^\|\s*(-?\d+)\s*-\s*(.*?)\s*(\*)?\s*$/);
    if (m) out.push({ id: +m[1], name: m[2].replace(/^Track \d+\s*-\s*/, "").replace(/^\[|\]$/g, "") || m[2], on: !!m[3] });
  }
  return out;
}
export function parseStats(lines) {
  const get = (re) => {
    const l = lines.find((x) => re.test(x));
    const m = l && l.match(/:\s*(\d+)/);
    return m ? +m[1] : null;
  };
  return { shown: get(/frames displayed/), lost: get(/frames lost/), decoded: get(/video decoded/) };
}
