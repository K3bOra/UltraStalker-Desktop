/* Ultra Stalker for Windows — page side of the program's own features.
   - next episode: knows which episode is playing and which one comes after it
     (the player asks window.usDesktopNext; the next season is looked up when needed)
   - opens Live TV at the last channel when the program starts, without playing it (Settings → Program)
   - "a new version is ready" from the program's updater */
(function () {
  const N = window.usNative;
  if (!N) return;
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  const get = (k, d) => {
    try {
      const v = localStorage.getItem(k);
      return v === null ? d : v;
    } catch (_) {
      return d;
    }
  };
  const set = (k, v) => {
    try {
      localStorage.setItem(k, v);
    } catch (_) {}
  };
  const json = async (url) => {
    const r = await fetch(url, { cache: "no-store" });
    const j = await r.json();
    if (!r.ok || (j && j.ok === false)) throw new Error((j && j.error) || "unavailable");
    return j;
  };

  /* ------------------------------------------------------------ next episode */
  let shown = null; // the season list on screen: { rows, series, season }
  let ctx = null; // the episode playing: { rows, index, series, season }
  const seasons = new Map(); // series id → its seasons (in order)
  const has = (name) => typeof window[name] === "function";
  if (has("renderInlineEpisodes")) {
    const orig = window.renderInlineEpisodes;
    window.renderInlineEpisodes = function (rows) {
      try {
        // eslint-disable-next-line no-undef
        shown = { rows: Array.isArray(rows) ? rows : [], series: activeSeries ? String(activeSeries.id) : "", season: activeSeason ? String(activeSeason.id) : "" };
      } catch (_) {
        shown = null;
      }
      return orig.apply(this, arguments);
    };
  }
  async function loadSeasons(series) {
    if (!series || seasons.has(series)) return;
    seasons.set(series, null);
    try {
      const j = await json("api/browse/seasons?item=" + enc(series));
      seasons.set(series, Array.isArray(j.seasons) ? j.seasons : []);
    } catch (_) {
      seasons.delete(series);
    }
  }
  if (has("openPlayerSheet")) {
    const orig = window.openPlayerSheet;
    window.openPlayerSheet = function (row) {
      ctx = null;
      if (row && shown && shown.series) {
        const i = shown.rows.findIndex((r) => r && r.id === row.id);
        if (i >= 0) {
          ctx = Object.assign({ index: i }, shown);
          loadSeasons(ctx.series);
        }
      }
      return orig.apply(this, arguments);
    };
  }
  const code = (r) => {
    const ep = Number(r.episode || 0) || 0;
    let c = r.season ? "S" + String(r.season).padStart(2, "0") : "";
    if (ep) c += "E" + String(ep).padStart(2, "0");
    const t = String(r.title || "").trim();
    return [c, t && !/^episode\s*\d+$/i.test(t) ? t : ep ? "Episode " + ep : ""].filter(Boolean).join(" · ");
  };
  function nextSeason() {
    const list = ctx && seasons.get(ctx.series);
    if (!Array.isArray(list)) return null;
    const i = list.findIndex((s) => String(s.id) === ctx.season);
    return i >= 0 ? list[i + 1] || null : null;
  }
  window.usDesktopNext = {
    info() {
      if (!ctx) return null;
      const r = ctx.rows[ctx.index + 1];
      if (r) return { label: code(r) };
      const s = nextSeason();
      return s ? { label: (s.title || "Next season") + " · Episode 1" } : null;
    },
    async play() {
      if (!ctx) return;
      let r = ctx.rows[ctx.index + 1];
      if (r) shown = { rows: ctx.rows, series: ctx.series, season: ctx.season };
      else {
        const s = nextSeason();
        if (!s) return;
        const j = await json("api/browse/episodes?series=" + enc(ctx.series) + "&season=" + enc(s.id));
        const rows = Array.isArray(j.episodes) ? j.episodes : [];
        if (!rows.length) return;
        shown = { rows, series: ctx.series, season: String(s.id) };
        r = rows[0];
      }
      window.openPlayerSheet(r);
    },
  };

  /* ------------------------------------------------------------ the last live channel */
  const LAST = "us-desk-last-channel";
  const nameOf = (c) => String(c.dataset.t || c.title || (c.querySelector(".item-title") || {}).textContent || "").trim();
  let remembered = "";
  setInterval(() => {
    if (!document.body.classList.contains("dk-tv-mode")) return;
    const card = document.querySelector("#browseItems .live-card.dk-on");
    const sel = $("browseAccount");
    if (!card || !sel || !sel.value) return;
    let cat = "";
    try {
      // eslint-disable-next-line no-undef
      cat = activeCategory ? String(activeCategory.id) : "";
    } catch (_) {}
    const v = JSON.stringify({ account: sel.value, cat, name: nameOf(card) });
    if (v !== remembered) {
      remembered = v;
      set(LAST, v);
    }
  }, 2500);
  async function openLast() {
    if (get("us-desk-last-live", "1") !== "1") return;
    try {
      if (sessionStorage.getItem("us-desk-started")) return; // only when the program starts
      sessionStorage.setItem("us-desk-started", "1");
    } catch (_) {
      return;
    }
    let last;
    try {
      last = JSON.parse(get(LAST, "null"));
    } catch (_) {}
    if (!last || !last.account || !last.name) return;
    const sel = $("browseAccount");
    if (!sel) return;
    const until = async (test, ms) => {
      const end = Date.now() + ms;
      while (Date.now() < end) {
        const v = test();
        if (v) return v;
        await new Promise((r) => setTimeout(r, 200));
      }
      return null;
    };
    // the saved sources are listed, and nothing else was opened meanwhile
    if (!(await until(() => [...sel.options].some((o) => o.value === last.account), 15000))) return;
    if (sel.value || location.hash.length > 1) return;
    remembered = JSON.stringify(last);
    if (last.cat) set("us-web-livecat:" + last.account, last.cat);
    set("us-web-last-src", last.account);
    sel.value = last.account;
    sel.dispatchEvent(new Event("change"));
    const card = await until(() => {
      if (sel.value !== last.account || !document.body.classList.contains("dk-tv-mode")) return null;
      return [...document.querySelectorAll("#browseItems .live-card")].find((c) => nameOf(c) === last.name) || null;
    }, 25000);
    if (!card || sel.value !== last.account || document.querySelector("#browseItems .live-card.dk-on")) return;
    // only show where you were: nothing plays until you choose (no data used by itself)
    card.scrollIntoView({ block: "center" });
    card.classList.add("us-last");
    try {
      card.focus({ preventScroll: true });
    } catch (_) {}
    const clear = () => card.classList.remove("us-last");
    card.addEventListener("click", clear, { once: true });
  }
  if ($("browseAccount")) (document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", openLast) : openLast());

  /* ------------------------------------------------------------ updates */
  if (N.update) {
    let toast = null, said = "";
    const show = (s) => {
      if (!s || s.state !== "ready" || said === s.version) return;
      said = s.version;
      if (!toast) {
        toast = document.createElement("div");
        toast.className = "us-update";
        document.body.appendChild(toast);
        const st = document.createElement("style");
        st.textContent = `.us-update{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:2147482500;display:flex;align-items:center;gap:14px;flex-wrap:wrap;max-width:min(640px,calc(100vw - 40px));padding:12px 14px 12px 18px;border-radius:16px;background:rgba(18,13,7,.96);border:1px solid rgba(240,222,180,.35);box-shadow:0 20px 50px -20px #000;color:#f3e7c7;font-size:13.5px;line-height:1.45}
.us-update b{color:#fff6dc}.us-update .ar{display:block;direction:rtl;font-size:12px;color:#cdb98a;margin-top:2px}.us-update div{flex:1;min-width:220px}
.us-update button{appearance:none;border:1px solid rgba(240,222,180,.3);background:rgba(255,240,210,.06);color:#f6e7b8;border-radius:999px;padding:8px 16px;font:inherit;font-size:12.5px;font-weight:700;cursor:pointer}
.us-update button.go{background:var(--foil,linear-gradient(135deg,#f3dfa6,#c9a25a));color:#1a1306;border-color:transparent}
body.us-mini .us-update{display:none}`;
        document.head.appendChild(st);
      }
      const v = String(s.version || "").replace(/[^\w.\-]/g, "");
      toast.innerHTML = `<div><b>Ultra Stalker ${v} is ready</b> · restart to update<span class="ar">نسخة جديدة ${v} جاهزة — اعمل إعادة تشغيل للبرنامج عشان تتحدّث</span></div><button type="button" class="go">Restart now</button><button type="button" class="later">Later</button>`;
      toast.querySelector(".go").onclick = () => N.update.install();
      toast.querySelector(".later").onclick = () => toast.remove();
      if (!toast.isConnected) document.body.appendChild(toast);
    };
    N.update.onState(show);
    N.update.state().then(show, () => {});
  }
})();
