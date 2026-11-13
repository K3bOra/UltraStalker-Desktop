/* Ultra Stalker Desktop — interface logic.
   Talks to Python through QWebChannel (bridge.call -> bridge.reply). When the page is opened in a
   normal browser (development), mock.js provides the same API with sample data. */
"use strict";

/* ------------------------------------------------------------------ strings */
const STR = {
  ar: {
    home: "الرئيسية", live: "البث المباشر", movies: "الأفلام", series: "المسلسلات", search: "البحث", favorites: "المفضلة",
    sources: "المصادر", settings: "الإعدادات", categories: "الأقسام", all: "الكل", channels: "القنوات",
    play: "تشغيل", resume: "استكمال", fromStart: "من الأول", details: "التفاصيل", trailer: "الإعلان", favorite: "مفضلة",
    fullscreen: "ملء الشاشة", overview: "القصة", cast: "الأبطال", country: "البلد", language: "اللغة",
    season: "الموسم", seasons: "المواسم", episode: "حلقة", episodes: "حلقة", min: "دقيقة", now: "الآن", next: "التالي",
    noEpg: "لا يوجد دليل برامج لهذه القناة", pickChannel: "اختار قناة للمعاينة", previewOff: "المعاينة متوقفة — دبل كليك للتشغيل",
    filter: "فلترة بالاسم…", searchAll: "ابحث في القنوات والأفلام والمسلسلات…", items: "عنصر",
    continueW: "كمل مشاهدة", recentLive: "آخر القنوات", favShelf: "مفضلتك", seeAll: "عرض الكل",
    connectFirst: "اختار مصدر الأول", addSource: "إضافة مصدر", editSource: "تعديل المصدر", connect: "اتصال", save: "حفظ",
    cancel: "إلغاء", delete: "حذف", edit: "تعديل", connecting: "جاري الاتصال…", connected: "متصل", active: "المصدر الحالي",
    srcName: "اسم المصدر", srcUrl: "عنوان البورتال / السيرفر", srcMac: "عنوان MAC", srcUser: "اسم المستخدم", srcPass: "كلمة المرور",
    keepPass: "سيبها فاضية عشان تفضل القديمة", m3uUrl: "رابط قائمة M3U", sourcesSub: "بياناتك محفوظة في خزنة ويندوز، ومش بتتبعت لأي حد.",
    yourSources: "مصادرك", noSources: "لسه مفيش مصادر", noSourcesSub: "ضيف بورتال ستالكر أو Xtream أو قائمة M3U وابدأ.",
    loading: "جاري التحميل…", empty: "مفيش حاجة هنا", emptyCat: "القسم ده فاضي", noResults: "مفيش نتايج",
    favAdded: "اتضافت للمفضلة", favRemoved: "اتشالت من المفضلة", saved: "اتحفظ", deleted: "اتحذف",
    confirmDelete: "متأكد إنك عايز تحذف المصدر ده؟", starting: "جاري تجهيز التشغيل…",
    setLang: "لغة البرنامج", setLangSub: "لغة القوائم والأزرار.", setMeta: "بيانات الأفلام", setMetaSub: "صور الخلفية والأبطال والقصة من TMDb.",
    metaLang: "لغة القصة", tmdbKey: "مفتاح TMDb خاص (اختياري)", tmdbKeySub: "لو سبته فاضي هيستخدم المفتاح المدمج.",
    setPlayer: "المشغل", setPlayerSub: "الفيديو بيشتغل جوه البرنامج.", livePrev: "معاينة القنوات في عمود المعاينة", on: "تشغيل", off: "إيقاف",
    about: "عن البرنامج", version: "الإصدار", design: "تصميم وتطوير", arabic: "العربية", english: "English",
    keysBack: "رجوع", keysFav: "مفضلة", keysSearch: "بحث", keysCats: "الأقسام", keysPlay: "تشغيل", keysFull: "ملء الشاشة",
    page: "صفحة", serverOk: "السيرفر متصل", notConnected: "مش متصل", lastUpdate: "آخر تحديث",
    watched: "اتشافت", nextEp: "الحلقة الجاية", noEpisodes: "المصدر مرجعش حلقات للمسلسل ده",
    days: ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"],
  },
  en: {
    home: "Home", live: "Live TV", movies: "Movies", series: "Series", search: "Search", favorites: "Favorites",
    sources: "Sources", settings: "Settings", categories: "Categories", all: "All", channels: "Channels",
    play: "Play", resume: "Resume", fromStart: "From start", details: "Details", trailer: "Trailer", favorite: "Favorite",
    fullscreen: "Full screen", overview: "Overview", cast: "Cast", country: "Country", language: "Language",
    season: "Season", seasons: "Seasons", episode: "episode", episodes: "episodes", min: "min", now: "NOW", next: "NEXT",
    noEpg: "No programme guide for this channel", pickChannel: "Pick a channel to preview", previewOff: "Preview is off — double-click to play",
    filter: "Filter by name…", searchAll: "Search channels, movies and series…", items: "items",
    continueW: "Continue watching", recentLive: "Recent channels", favShelf: "Your favorites", seeAll: "See all",
    connectFirst: "Choose a source first", addSource: "Add source", editSource: "Edit source", connect: "Connect", save: "Save",
    cancel: "Cancel", delete: "Delete", edit: "Edit", connecting: "Connecting…", connected: "Connected", active: "Current source",
    srcName: "Source name", srcUrl: "Portal / server address", srcMac: "MAC address", srcUser: "Username", srcPass: "Password",
    keepPass: "Leave empty to keep the saved one", m3uUrl: "M3U playlist link", sourcesSub: "Your logins stay in Windows Credential Manager and are never shared.",
    yourSources: "Your sources", noSources: "No sources yet", noSourcesSub: "Add a Stalker portal, an Xtream account or an M3U playlist to start.",
    loading: "Loading…", empty: "Nothing here yet", emptyCat: "This category is empty", noResults: "No results",
    favAdded: "Added to favorites", favRemoved: "Removed from favorites", saved: "Saved", deleted: "Deleted",
    confirmDelete: "Delete this source?", starting: "Preparing playback…",
    setLang: "App language", setLangSub: "Language of menus and buttons.", setMeta: "Movie details", setMetaSub: "Backdrops, cast and overviews from TMDb.",
    metaLang: "Overview language", tmdbKey: "Personal TMDb key (optional)", tmdbKeySub: "Leave empty to use the built-in key.",
    setPlayer: "Player", setPlayerSub: "Video plays inside the app.", livePrev: "Preview channels in the preview column", on: "On", off: "Off",
    about: "About", version: "Version", design: "Design & development", arabic: "العربية", english: "English",
    keysBack: "Back", keysFav: "Favorite", keysSearch: "Search", keysCats: "Categories", keysPlay: "Play", keysFull: "Full screen",
    page: "Page", serverOk: "Server connected", notConnected: "Not connected", lastUpdate: "Last update",
    watched: "Watched", nextEp: "Next episode", noEpisodes: "The source returned no episodes for this series",
    days: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
  },
};
let LANG = "ar";
const t = (k) => (STR[LANG] && STR[LANG][k]) ?? STR.en[k] ?? k;

/* ------------------------------------------------------------------ helpers */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const h = (html) => { const d = document.createElement("template"); d.innerHTML = html.trim(); return d.content.firstElementChild; };
const debounce = (fn, ms) => { let id; return (...a) => { clearTimeout(id); id = setTimeout(() => fn(...a), ms); }; };
const imgTag = (x, extra = "") => x.poster ? `<img src="${esc(x.poster)}" ${x.poster_alt ? `data-alt="${esc(x.poster_alt)}"` : ""} alt="" loading="lazy" ${extra} onerror="imgFail(this)">` : "";
window.imgFail = (el) => { const alt = el.dataset.alt; if (alt) { el.removeAttribute("data-alt"); el.src = alt; } else el.remove(); };
const initials = (s) => String(s || "?").replace(/^[A-Z0-9]{2,4}\s*[|:\-]\s*/, "").trim().slice(0, 28);
const fmtTime = (sec) => new Date(sec * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

let toastTimer;
function toast(msg, err = false) {
  const el = $("#toast"); el.textContent = msg; el.classList.toggle("err", !!err); el.classList.add("on");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("on"), err ? 4200 : 2400);
}

/* ------------------------------------------------------------------ bridge */
const pending = new Map(); let seq = 0; let BR = null;
function api(method, ...args) {
  return new Promise((resolve, reject) => {
    const id = ++seq; pending.set(id, { resolve, reject });
    BR.call(JSON.stringify({ id, method, args }));
  });
}
function onReply(text) {
  document.title = "Ultra Stalker · " + seq;
  let m; try { m = JSON.parse(text); } catch { return; }
  const p = pending.get(m.id); if (!p) return; pending.delete(m.id);
  m.ok ? p.resolve(m.data) : p.reject(new Error(m.error || "Error"));
}
function onPush(text) {
  let e; try { e = JSON.parse(text); } catch { return; }
  if (e.type === "toast") toast(e.message, e.error);
  if (e.type === "player" && e.state === "closed" && S.route === "live") Live.rearm();
  if (e.type === "player" && e.state === "error") toast(e.message || "Playback failed", true);
  if (e.type === "player" && e.state === "preview-error") Live.previewFailed(e.message);
}

/* ------------------------------------------------------------------ state */
const S = {
  route: "", settings: {}, connected: null, profiles: [], version: "", author: "",
  cats: {}, cat: {}, items: new Map(), det: new Map(), view: new Map(), hist: null,
};
const remember = (rows) => { rows.forEach((x) => S.view.set(x.ref, x)); return rows; };

async function categories(kind) {
  if (!S.cats[kind]) S.cats[kind] = await api("categories", kind);
  return S.cats[kind];
}
async function items(kind, cat) {
  const key = kind + "|" + (cat || "");
  if (!S.items.has(key)) S.items.set(key, remember(await api("items", kind, cat || "")));
  return S.items.get(key);
}
async function details(ref) {
  if (!S.det.has(ref)) S.det.set(ref, api("details", ref).then((d) => { S.view.set(ref, Object.assign(S.view.get(ref) || {}, d)); return d; }));
  return S.det.get(ref);
}

/* ------------------------------------------------------------------ backdrop */
let bdFlip = false, bdUrl = "";
function backdrop(url) {
  if ((url || "") === bdUrl) return; bdUrl = url || "";
  const a = $("#bd-a"), b = $("#bd-b"); const on = bdFlip ? a : b, off = bdFlip ? b : a; bdFlip = !bdFlip;
  if (!url) { a.classList.remove("on"); b.classList.remove("on"); return; }
  const img = new Image(); img.onload = () => { if (bdUrl !== url) return; on.style.backgroundImage = `url("${url}")`; on.classList.add("on"); off.classList.remove("on"); };
  img.src = url;
}

/* ------------------------------------------------------------------ chrome */
function bar(ctx, keys, count) {
  $("#bar-ctx").textContent = ctx || "";
  $("#bar-keys").innerHTML = (keys || []).map(([k, label, dot]) => `<span>${dot ? `<i class="dot ${dot}"></i>` : `<kbd>${esc(k)}</kbd>`}${esc(label)}</span>`).join("");
  $("#bar-count").textContent = count || "";
}
function applyLang() {
  document.documentElement.lang = LANG; document.documentElement.dir = LANG === "ar" ? "rtl" : "ltr";
  $$("[data-t]").forEach((el) => (el.textContent = t(el.dataset.t)));
}
function markRail(name) { $$("#rail a[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === name)); }

function posterHTML(x, opts = {}) {
  const img = imgTag(x);
  const prog = opts.percent ? `<div class="prog"><i style="width:${opts.percent}%"></i></div>` : "";
  return `<div class="poster" data-ref="${esc(x.ref)}" tabindex="-1">
    <div class="art"><div class="ph">${esc(initials(x.title))}</div>${img}
      ${x.year ? `<span class="badge b-year">${esc(x.year)}</span>` : ""}${x.rating ? `<span class="badge b-rate">${esc(x.rating)}</span>` : ""}${prog}</div>
    <div class="cap">${esc(x.title)}</div></div>`;
}
function logoHTML(d, fallbackTitle) {
  const tm = d.tmdb || {};
  return tm.logo ? `<img src="${esc(tm.logo)}" alt="${esc(tm.title || fallbackTitle)}">` : `<div class="t">${esc(tm.title || fallbackTitle)}</div>`;
}
function metaChips(d) {
  const tm = d.tmdb || {}; const out = [];
  const y = d.year || tm.year; if (y) out.push(`<span class="chip"><i class="ic ic-cal"></i>${esc(y)}</span>`);
  if (tm.certification) out.push(`<span class="chip">${esc(tm.certification)}</span>`);
  if (tm.runtime) out.push(`<span class="chip"><i class="ic ic-clock"></i>${tm.runtime} ${t("min")}</span>`);
  if (tm.seasons) out.push(`<span class="chip"><i class="ic ic-layers"></i>${tm.seasons} ${t("seasons")}</span>`);
  if (tm.episodes) out.push(`<span class="chip"><i class="ic ic-series"></i>${tm.episodes} ${t("episodes")}</span>`);
  return out.join("");
}
function castHTML(tm, n) {
  return (tm.cast || []).slice(0, n).map((c) => `<div class="p"><div class="ph">${c.photo ? `<img src="${esc(c.photo)}" alt="" loading="lazy">` : esc((c.name || "?")[0])}</div><b>${esc(c.name)}</b><span>${esc(c.role)}</span></div>`).join("");
}
function scoresHTML(d) {
  const tm = d.tmdb || {}; const out = [];
  if (d.rating && (!tm.rating || String(tm.rating) !== String(d.rating))) out.push(`<span class="score"><span class="lbl prov">★</span>${esc(d.rating)}</span>`);
  if (tm.rating) out.push(`<span class="score"><span class="lbl tmdb">TMDB</span>${Number(tm.rating).toFixed(1)}</span>`);
  return out.join("");
}

function needConnection() {
  if (S.connected) return false;
  location.hash = "#/sources"; toast(t("connectFirst")); return true;
}

/* ------------------------------------------------------------------ router */
const views = {};
let cleanup = null;
function route() {
  const parts = (location.hash || "#/home").slice(2).split("/");
  const name = parts[0] || "home";
  if (cleanup) { try { cleanup(); } catch {} cleanup = null; }
  closeDrawer();
  document.body.classList.remove("dim");
  S.route = name; markRail(name === "details" ? (S.view.get(parts[1])?.kind === "series" ? "series" : "movies") : name);
  document.title = "Ultra Stalker";
  const v = $("#view"); v.innerHTML = "";
  (views[name] || views.home)(v, parts.slice(1).map(decodeURIComponent));
}
window.addEventListener("hashchange", route);

/* ------------------------------------------------------------------ home */
views.home = (v) => {
  if (!S.connected && !S.profiles.length) { location.hash = "#/sources"; return; }
  const page = h(`<section class="home">
    <div class="home-top">
      <div class="hero-info" id="hero"></div>
      <div class="clock glass" id="clock"></div>
    </div>
    <div class="tiles">
      ${[["live", "ic-live"], ["movies", "ic-movies"], ["series", "ic-series"], ["favorites", "ic-star"], ["search", "ic-search"], ["sources", "ic-sources"], ["settings", "ic-settings"]]
        .map(([k, ic]) => `<a class="tile" href="#/${k}"><i class="ic ${ic}"></i>${t(k)}</a>`).join("")}
    </div>
    <div id="shelves" style="display:grid;gap:22px"></div>
  </section>`);
  v.appendChild(page);
  const tick = () => {
    const d = new Date(); const c = $("#clock"); if (!c) return;
    c.innerHTML = `<div class="time" dir="ltr">${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" })}</div>
      <div class="day">${t("days")[d.getDay()]}</div>
      <div class="date">${d.toLocaleDateString(LANG === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { day: "numeric", month: "long", year: "numeric" })}</div>
      <div class="status">${S.connected ? `<span><i class="live-dot"></i>${t("serverOk")}</span><b>${esc(S.connected.name)}</b><span dir="ltr">${esc(S.connected.host)}</span>` : `<span>${t("notConnected")}</span>`}<span>v${esc(S.version)}</span></div>`;
  };
  tick(); const iv = setInterval(tick, 15000); cleanup = () => clearInterval(iv);
  bar(S.connected ? S.connected.name : "Ultra Stalker", [["", t("live"), "red"], ["", t("movies"), "green"], ["", t("series"), "yellow"], ["", t("search"), "blue"]], "");
  if (!S.connected) { $("#hero").innerHTML = `<div class="logo"><div class="t">ULTRA STALKER</div></div><p>${t("connectFirst")}</p><a class="btn primary" href="#/sources">${t("sources")}</a>`; return; }
  homeShelves(); homeHero();
};
async function homeShelves() {
  let hist = [];
  try { hist = remember(await api("history", 40)); } catch {}
  let fav = { live: [], movies: [], series: [] };
  try { fav = await api("favorites"); Object.values(fav).forEach(remember); } catch {}
  const box = $("#shelves"); if (!box) return;
  const cont = hist.filter((x) => x.kind !== "live" && x.percent > 0 && x.percent < 97).slice(0, 14);
  const live = hist.filter((x) => x.kind === "live").slice(0, 14);
  const favs = [...fav.movies, ...fav.series].slice(0, 16);
  const shelf = (title, html, link, wide) => `<section class="shelf"><h3>${title}${link ? `<a href="${link}">${t("seeAll")}</a>` : ""}</h3><div class="strip ${wide ? "wide" : ""}">${html}</div></section>`;
  let html = "";
  if (cont.length) html += shelf(t("continueW"), cont.map((x) => posterHTML(x, { percent: x.percent })).join(""));
  if (live.length) html += shelf(t("recentLive"), live.map((x) => `<div class="row ch" data-ref="${esc(x.ref)}" data-play="1" style="min-width:250px"><span class="logo">${x.poster ? imgTag(x) : esc(initials(x.title).slice(0, 3))}</span><span class="t">${esc(x.title)}</span></div>`).join(""));
  if (favs.length) html += shelf(t("favShelf"), favs.map((x) => posterHTML(x)).join(""), "#/favorites");
  box.innerHTML = html;
  box.addEventListener("click", (e) => {
    const el = e.target.closest("[data-ref]"); if (!el) return;
    const x = S.view.get(el.dataset.ref);
    if (el.dataset.play || x.kind === "live" || x.kind === "episode") play(x.ref); else location.hash = "#/details/" + encodeURIComponent(x.ref);
  });
  $$(".strip", box).forEach(dragScroll);
}
async function homeHero() {
  try {
    let pick = (await api("history", 12)).find((x) => x.kind === "movies" || x.kind === "series");
    if (!pick) {
      const cats = await categories("movies"); const first = cats[0];
      if (first) { const rows = await items("movies", first.id); pick = rows[Math.floor(Math.random() * Math.min(rows.length, 24))]; }
    }
    if (!pick) return; remember([pick]);
    const d = await details(pick.ref); if (S.route !== "home") return;
    backdrop(d.backdrop || (d.tmdb || {}).backdrop || "");
    $("#hero").innerHTML = `<div class="logo">${logoHTML(d, d.title)}</div><div class="meta" style="display:flex;gap:8px;flex-wrap:wrap">${metaChips(d)}</div>
      <p>${esc(d.description || (d.tmdb || {}).overview || "")}</p>
      <div style="display:flex;gap:10px"><button class="btn primary" data-a="play"><i class="ic ic-play"></i>${d.resume ? t("resume") : t("play")}</button><a class="btn" href="#/details/${encodeURIComponent(d.ref)}"><i class="ic ic-info"></i>${t("details")}</a></div>`;
    $("#hero [data-a=play]").onclick = () => play(d.ref);
  } catch (e) { /* hero is decoration */ }
}
function dragScroll(el) {
  el.addEventListener("wheel", (e) => { if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { el.scrollLeft += (LANG === "ar" ? -1 : 1) * e.deltaY; e.preventDefault(); } }, { passive: false });
}

/* ------------------------------------------------------------------ grid 3 (movies + series) */
views.movies = (v) => Grid.open(v, "movies");
views.series = (v) => Grid.open(v, "series");
const Grid = {
  kind: "", rows: [], shown: 0, sel: -1, filter: "", io: null,
  async open(v, kind) {
    if (needConnection()) return;
    this.kind = kind; this.rows = []; this.shown = 0; this.sel = -1; this.filter = "";
    document.body.classList.add("dim"); backdrop("");
    v.appendChild(h(`<section class="g3">
      <div class="g3-main">
        <div class="g3-head">
          <button class="btn cat-btn" id="cat-btn"><i class="ic ic-list"></i><span id="cat-name">${t("categories")}</span></button>
          <input class="input filter" id="flt" placeholder="${t("filter")}">
        </div>
        <div class="g3-grid" id="grid"><div class="spinner"></div></div>
      </div>
      <aside class="spot glass edge" id="spot"></aside>
    </section>`));
    $("#cat-btn").onclick = () => this.drawer();
    $("#flt").oninput = debounce((e) => { this.filter = e.target.value.trim().toLowerCase(); this.render(); }, 160);
    const grid = $("#grid");
    grid.addEventListener("click", (e) => { const p = e.target.closest(".poster"); if (p) this.select(+p.dataset.i, true); });
    grid.addEventListener("dblclick", (e) => { const p = e.target.closest(".poster"); if (p) this.activate(); });
    grid.addEventListener("mouseover", debounce((e) => { const p = e.target.closest?.(".poster"); if (p && +p.dataset.i !== this.sel) this.select(+p.dataset.i, false); }, 260));
    this.keys();
    let cats = [];
    try { cats = await categories(kind); } catch (e) { grid.innerHTML = `<div class="empty"><b>${esc(e.message)}</b></div>`; return; }
    const remembered = S.cat[kind];
    const cat = cats.find((c) => c.id === remembered) || (remembered === "" ? { id: "", title: t("all") } : null);
    if (cat) this.load(cat); else { grid.innerHTML = ""; this.spotEmpty(); this.drawer(true); }
  },
  keys() {
    this.bar();
  },
  bar(count) {
    const cat = (S.cats[this.kind] || []).find((c) => c.id === S.cat[this.kind]);
    bar(cat ? cat.title : t(this.kind), [["Enter", t("details")], ["F", t("keysFav")], ["C", t("keysCats")], ["/", t("keysSearch")]], count || "");
  },
  drawer(force) {
    const cats = [{ id: "", title: t("all") }, ...(S.cats[this.kind] || [])];
    openDrawer(t("categories") + " · " + t(this.kind), cats, S.cat[this.kind], (c) => this.load(c), force);
  },
  async load(cat) {
    S.cat[this.kind] = cat.id; $("#cat-name").textContent = cat.title; this.bar();
    const grid = $("#grid"); grid.innerHTML = Array.from({ length: 12 }, () => `<div class="poster"><div class="art skel"></div><div class="cap">&nbsp;</div></div>`).join("");
    try { this.rows = await items(this.kind, cat.id); } catch (e) { grid.innerHTML = `<div class="empty"><b>${esc(e.message)}</b></div>`; return; }
    if (S.route !== this.kind) return;
    this.render(); if (this.list().length) this.select(0, false);
  },
  list() { return this.filter ? this.rows.filter((x) => x.title.toLowerCase().includes(this.filter)) : this.rows; },
  render() {
    const grid = $("#grid"); const L = this.list(); this.shown = 0; this.sel = -1; grid.innerHTML = "";
    if (!L.length) { grid.innerHTML = `<div class="empty"><b>${this.rows.length ? t("noResults") : t("emptyCat")}</b></div>`; this.spotEmpty(); this.bar("0"); return; }
    this.more(); this.bar(`${L.length} ${t("items")}`);
    if (this.io) this.io.disconnect();
    this.io = new IntersectionObserver((en) => { if (en.some((e) => e.isIntersecting)) this.more(); }, { root: grid, rootMargin: "600px" });
    const s = document.createElement("div"); s.id = "sentinel"; s.style.gridColumn = "1/-1"; grid.appendChild(s); this.io.observe(s);
  },
  more() {
    const grid = $("#grid"); const L = this.list(); if (this.shown >= L.length) return;
    const end = Math.min(L.length, this.shown + 90); let html = "";
    for (let i = this.shown; i < end; i++) html += posterHTML(L[i]).replace('class="poster"', `class="poster" data-i="${i}"`);
    const frag = document.createRange().createContextualFragment(html);
    const s = $("#sentinel", grid); s ? grid.insertBefore(frag, s) : grid.appendChild(frag); this.shown = end;
  },
  cols() { const g = $("#grid"); const first = $(".poster", g); if (!first) return 1; const w = first.getBoundingClientRect().width + 16; return Math.max(1, Math.floor((g.clientWidth + 16) / w)); },
  select(i, scroll) {
    const L = this.list(); if (i < 0 || i >= L.length) return;
    while (i >= this.shown) this.more();
    $$("#grid .poster.sel").forEach((p) => p.classList.remove("sel"));
    const el = $(`#grid .poster[data-i="${i}"]`); if (el) { el.classList.add("sel"); if (scroll) el.scrollIntoView({ block: "nearest" }); }
    this.sel = i; this.spot(L[i]);
  },
  activate() { const x = this.list()[this.sel]; if (x) location.hash = "#/details/" + encodeURIComponent(x.ref); },
  spotEmpty() { const s = $("#spot"); if (s) { s.innerHTML = `<div class="empty" style="margin:auto"><i class="ic ic-${this.kind === "series" ? "series" : "movies"}" style="width:46px;height:46px;color:var(--emerald)"></i><b>${t(this.kind)}</b><span>${t("pickChannel").replace(/.*/, t("categories"))}</span></div>`; s.style.removeProperty("--spot-bd"); } },
  async spot(x) {
    const s = $("#spot"); if (!s) return;
    const draw = (d) => {
      const tm = d.tmdb || {};
      const bd = d.backdrop || tm.backdrop; bd ? s.style.setProperty("--spot-bd", `url("${bd}")`) : s.style.removeProperty("--spot-bd");
      s.innerHTML = `<div class="logo">${logoHTML(d, d.title)}</div>
        <div class="meta">${metaChips(d)}</div>
        ${tm.genres && tm.genres.length ? `<div class="genres">${tm.genres.map((g) => `<span>${esc(g)}</span>`).join("")}</div>` : ""}
        ${(tm.countries || []).length || tm.language ? `<div class="facts"><div><b><i class="ic ic-pin" style="width:14px;height:14px;vertical-align:-2px"></i> ${t("country")}</b><span>${esc((tm.countries || []).join("، ") || "—")}</span></div><div><b><i class="ic ic-lang" style="width:14px;height:14px;vertical-align:-2px"></i> ${t("language")}</b><span>${esc(tm.language || "—")}</span></div></div>` : ""}
        <div class="scores">${scoresHTML(d)}</div>
        ${(d.description || tm.overview) ? `<div class="sec-t">${t("overview")}</div><p class="ov">${esc(d.description || tm.overview)}</p>` : ""}
        ${(tm.cast || []).length ? `<div class="sec-t">${t("cast")}</div><div class="cast">${castHTML(tm, 4)}</div>` : ""}
        <div class="actions">
          <button class="btn primary" data-a="open"><i class="ic ${x.kind === "series" ? "ic-layers" : "ic-play"}"></i>${x.kind === "series" ? t("seasons") : (d.resume ? t("resume") : t("play"))}</button>
          <button class="btn icon ${d.favorite ? "on" : ""}" data-a="fav" title="${t("favorite")}"><i class="ic ic-star"></i></button>
          ${tm.trailer ? `<button class="btn icon" data-a="trailer" title="${t("trailer")}"><i class="ic ic-trailer"></i></button>` : ""}
          <button class="btn icon" data-a="info" title="${t("details")}"><i class="ic ic-info"></i></button>
        </div>`;
      s.onclick = (e) => {
        const a = e.target.closest("[data-a]")?.dataset.a; if (!a) return;
        if (a === "open") x.kind === "series" ? (location.hash = "#/details/" + encodeURIComponent(x.ref)) : play(x.ref);
        if (a === "info") location.hash = "#/details/" + encodeURIComponent(x.ref);
        if (a === "fav") toggleFav(x.ref, e.target.closest(".btn"));
        if (a === "trailer") api("ui_open_url", tm.trailer);
      };
    };
    s.classList.add("loading"); draw(Object.assign({}, x, S.view.get(x.ref)));
    try { const d = await details(x.ref); if (this.list()[this.sel] === x) { s.classList.remove("loading"); draw(d); } } catch { s.classList.remove("loading"); }
  },
  key(e) {
    const L = this.list(); if (!L.length) return false; const c = this.cols(); let i = this.sel < 0 ? 0 : this.sel;
    const fwd = LANG === "ar" ? -1 : 1;
    switch (e.key) {
      case "ArrowRight": i += fwd; break; case "ArrowLeft": i -= fwd; break;
      case "ArrowDown": i += c; break; case "ArrowUp": i -= c; break;
      case "PageDown": i += c * 3; break; case "PageUp": i -= c * 3; break;
      case "Home": i = 0; break; case "End": i = L.length - 1; break;
      case "Enter": this.activate(); return true;
      case "f": case "F": toggleFav(L[this.sel]?.ref, $("#spot [data-a=fav]")); return true;
      case "c": case "C": this.drawer(); return true;
      default: return false;
    }
    this.select(Math.max(0, Math.min(L.length - 1, i)), true); return true;
  },
};

/* ------------------------------------------------------------------ drawer */
function openDrawer(title, rows, current, pick, force) {
  closeDrawer();
  const d = $("#drawer"); d.hidden = false;
  d.innerHTML = `<h3>${esc(title)}</h3><input class="input" placeholder="${t("filter")}"><div class="list"></div>`;
  const list = $(".list", d);
  const draw = (q) => {
    list.innerHTML = rows.filter((c) => !q || c.title.toLowerCase().includes(q)).map((c, i) =>
      `<div class="row ${c.id === current ? "on" : ""}" data-id="${esc(c.id)}"><span class="n">${i + 1}</span><span class="t">${esc(c.title)}</span></div>`).join("");
  };
  draw(""); $(".input", d).oninput = (e) => draw(e.target.value.trim().toLowerCase());
  list.onclick = (e) => { const r = e.target.closest(".row"); if (!r) return; const c = rows.find((x) => x.id === r.dataset.id); closeDrawer(); pick(c); };
  const scrim = h(`<div class="drawer-scrim"></div>`); scrim.onclick = () => closeDrawer(); document.body.appendChild(scrim);
  $(".row.on", list)?.scrollIntoView({ block: "center" });
  setTimeout(() => $(".input", d).focus(), 30);
}
function closeDrawer() { const d = $("#drawer"); d.hidden = true; d.innerHTML = ""; $$(".drawer-scrim").forEach((x) => x.remove()); }

/* ------------------------------------------------------------------ live (3 columns) */
views.live = (v) => Live.open(v);
const Live = {
  cat: null, rows: [], filter: "", sel: null, epgTimer: null, previewOn: false,
  async open(v) {
    if (needConnection()) return;
    document.body.classList.add("dim"); backdrop("");
    v.appendChild(h(`<section class="live3">
      <div class="col"><div class="col-h"><h2>${t("categories")}</h2><span class="count" id="cat-count"></span></div><div class="list" id="lcats"><div class="spinner"></div></div></div>
      <div class="col"><div class="col-h"><h2 id="lcat-name">${t("channels")}</h2><span class="count" id="ch-count"></span></div>
        <input class="input" id="lflt" placeholder="${t("filter")}"><div class="list" id="lch"></div></div>
      <div class="col">
        <div class="preview" id="pv"><div class="idle"><div><b>${t("pickChannel")}</b></div></div></div>
        <div class="nownext glass" id="nn"></div>
      </div></section>`));
    cleanup = () => { this.stopPreview(); clearInterval(this.epgTimer); window.removeEventListener("resize", this.onResize); };
    window.addEventListener("resize", this.onResize);
    $("#lflt").oninput = debounce((e) => { this.filter = e.target.value.trim().toLowerCase(); this.drawChannels(); }, 140);
    $("#lch").addEventListener("click", (e) => { const r = e.target.closest(".row"); if (r) this.select(r.dataset.ref); });
    $("#lch").addEventListener("dblclick", (e) => { const r = e.target.closest(".row"); if (r) play(r.dataset.ref); });
    $("#lcats").addEventListener("click", (e) => { const r = e.target.closest(".row"); if (r) this.load(r.dataset.id); });
    $("#pv").addEventListener("dblclick", () => this.sel && play(this.sel));
    this.drawNN(null);
    let cats;
    try { cats = await categories("live"); } catch (e) { $("#lcats").innerHTML = `<div class="empty"><b>${esc(e.message)}</b></div>`; return; }
    this.cats = [{ id: "", title: t("all") }, ...cats];
    $("#cat-count").textContent = cats.length;
    $("#lcats").innerHTML = this.cats.map((c, i) => `<div class="row" data-id="${esc(c.id)}"><span class="n">${i + 1}</span><span class="t">${esc(c.title)}</span></div>`).join("");
    const keep = S.cat.live ?? (cats[0] ? cats[0].id : "");
    this.load(this.cats.some((c) => c.id === keep) ? keep : "");
  },
  onResize: debounce(() => Live.sendRect(), 60),
  async load(id) {
    S.cat.live = id; this.filter = ""; const fl = $("#lflt"); if (fl) fl.value = "";
    $$("#lcats .row").forEach((r) => r.classList.toggle("on", r.dataset.id === id));
    $("#lcats .row.on")?.scrollIntoView({ block: "nearest" });
    const c = this.cats.find((x) => x.id === id); $("#lcat-name").textContent = c ? c.title : t("channels");
    $("#lch").innerHTML = `<div class="spinner"></div>`;
    try { this.rows = await items("live", id); } catch (e) { $("#lch").innerHTML = `<div class="empty"><b>${esc(e.message)}</b></div>`; return; }
    if (S.route !== "live" || S.cat.live !== id) return;
    this.drawChannels();
    bar(c ? c.title : t("live"), [["Enter", t("keysPlay")], ["F", t("keysFav")], ["↑↓", t("channels")], ["/", t("keysSearch")]], `${this.rows.length} ${t("channels")}`);
  },
  list() { return this.filter ? this.rows.filter((x) => x.title.toLowerCase().includes(this.filter)) : this.rows; },
  drawChannels() {
    const L = this.list(); $("#ch-count").textContent = L.length;
    $("#lch").innerHTML = L.length ? L.map((x, i) => `<div class="row ch ${x.ref === this.sel ? "on" : ""}" data-ref="${esc(x.ref)}"><span class="n">${esc(x.number || i + 1)}</span>
      <span class="logo">${x.poster ? imgTag(x) : esc(initials(x.title).slice(0, 3))}</span>
      <span class="t">${esc(x.title)}</span>${x.epg ? `<span class="epg">EPG</span>` : ""}</div>`).join("") : `<div class="empty"><b>${t("emptyCat")}</b></div>`;
  },
  select(ref) {
    if (!ref) return; this.sel = ref; const x = S.view.get(ref);
    $$("#lch .row").forEach((r) => r.classList.toggle("on", r.dataset.ref === ref));
    $(`#lch .row[data-ref="${CSS.escape(ref)}"]`)?.scrollIntoView({ block: "nearest" });
    this.drawNN(x); this.loadEpg(ref);
    clearInterval(this.epgTimer); this.epgTimer = setInterval(() => this.sel && this.loadEpg(this.sel), 60000);
    if (S.settings.live_preview !== false) this.preview(ref);
    else $("#pv").innerHTML = `<div class="idle"><div>${x.poster ? `<img src="${esc(x.poster)}" alt="">` : ""}<b>${esc(x.title)}</b><div>${t("previewOff")}</div></div></div>`;
  },
  rect() { const r = $("#pv")?.getBoundingClientRect(); return r ? { x: Math.round(r.left + 3), y: Math.round(r.top + 3), w: Math.round(r.width - 6), h: Math.round(r.height - 6) } : null; },
  sendRect() { if (Live.previewOn && S.route === "live") api("ui_preview_rect", Live.rect()); },
  preview: debounce(async function (ref) {
    if (S.route !== "live" || Live.sel !== ref) return;
    const x = S.view.get(ref); const pv = $("#pv");
    pv.classList.add("native"); pv.innerHTML = `<div class="idle"><div>${x.poster ? `<img src="${esc(x.poster)}" alt="">` : ""}<div class="spinner" style="margin:6px auto"></div></div></div>`;
    try { Live.previewOn = true; await api("preview", ref, Live.rect()); } catch (e) { Live.previewFailed(e.message); }
  }, 350),
  previewFailed(msg) {
    this.previewOn = false; const pv = $("#pv"); if (!pv) return; pv.classList.remove("native");
    pv.innerHTML = `<div class="idle"><div><b>${esc(msg || "")}</b></div></div>`;
  },
  stopPreview() { if (this.previewOn) { this.previewOn = false; api("ui_stop_preview").catch(() => {}); } },
  rearm() { if (this.sel && S.settings.live_preview !== false) this.preview(this.sel); },
  async loadEpg(ref) {
    let e; try { e = await api("epg", ref); } catch { return; }
    if (this.sel !== ref) return; this.drawNN(S.view.get(ref), e);
  },
  drawNN(x, e) {
    const nn = $("#nn"); if (!nn) return;
    if (!x) { nn.innerHTML = `<div class="name">${t("live")}</div><p class="desc" style="text-align:center">${t("pickChannel")}</p>`; return; }
    const rows = (e && e.rows) || []; const now = (e && e.now) || Date.now() / 1000;
    const cur = rows.find((r) => r.start <= now && r.end > now) || rows[0]; const nxt = cur ? rows[rows.indexOf(cur) + 1] : null;
    const pct = cur ? Math.max(0, Math.min(100, (100 * (now - cur.start)) / (cur.end - cur.start))) : 0;
    nn.innerHTML = `<div class="name">${esc(x.title)}</div>
      ${cur ? `<div class="prog-row"><span class="tag">${t("now")}</span><span class="ttl">${esc(cur.title)}</span><span class="tm" dir="ltr">${fmtTime(cur.start)} – ${fmtTime(cur.end)}</span></div>
        <div class="bar-prog"><i style="width:${pct}%"></i></div>
        ${nxt ? `<div class="prog-row next"><span class="tag">${t("next")}</span><span class="ttl">${esc(nxt.title)}</span><span class="tm" dir="ltr">${fmtTime(nxt.start)}</span></div>` : ""}
        ${cur.description ? `<p class="desc" style="margin-top:10px">${esc(cur.description)}</p>` : ""}`
        : `<p class="desc" style="text-align:center">${e ? t("noEpg") : t("loading")}</p>`}
      <div class="acts" style="margin-top:12px">
        <button class="btn primary" data-a="play"><i class="ic ic-full"></i>${t("fullscreen")}</button>
        <button class="btn ${x.favorite ? "on" : ""}" data-a="fav"><i class="ic ic-star"></i>${t("favorite")}</button>
        <button class="btn" data-a="search"><i class="ic ic-search"></i>${t("search")}</button>
      </div>`;
    nn.onclick = (ev) => {
      const a = ev.target.closest("[data-a]")?.dataset.a; if (!a) return;
      if (a === "play") play(x.ref); if (a === "fav") toggleFav(x.ref, ev.target.closest(".btn")); if (a === "search") location.hash = "#/search";
    };
  },
  key(e) {
    const L = this.list(); if (!L.length) return false; let i = L.findIndex((x) => x.ref === this.sel);
    if (e.key === "ArrowDown") i = Math.min(L.length - 1, i + 1); else if (e.key === "ArrowUp") i = Math.max(0, i - 1);
    else if (e.key === "PageDown") i = Math.min(L.length - 1, i + 12); else if (e.key === "PageUp") i = Math.max(0, i - 12);
    else if (e.key === "Enter") { if (this.sel) play(this.sel); return true; }
    else if (e.key === "f" || e.key === "F") { toggleFav(this.sel, $("#nn [data-a=fav]")); return true; }
    else return false;
    this.select(L[Math.max(0, i)].ref); return true;
  },
};

/* ------------------------------------------------------------------ details (+ seasons) */
views.details = async (v, [ref]) => {
  if (needConnection()) return;
  const x = S.view.get(ref);
  if (!x) { history.back(); return; }
  const page = h(`<section class="det"><button class="btn icon back" onclick="history.back()"><i class="ic ic-back"></i></button><div id="det-body"><div class="spinner"></div></div></section>`);
  v.appendChild(page);
  bar(x.title, [["Esc", t("keysBack")], ["Enter", t("keysPlay")], ["F", t("keysFav")]], "");
  const draw = (d) => {
    const tm = d.tmdb || {};
    backdrop(d.backdrop || tm.backdrop || "");
    $("#det-body").innerHTML = `<div class="det-top">
        <div>${posterHTML(Object.assign({}, d, { poster: d.poster || tm.poster }))}</div>
        <div>
          <div class="logo">${logoHTML(d, d.title)}</div>
          ${tm.tagline ? `<div class="tag">${esc(tm.tagline)}</div>` : ""}
          <div class="meta">${metaChips(d)}${(tm.genres || []).map((g) => `<span class="chip">${esc(g)}</span>`).join("")}</div>
          <div class="scores" style="justify-content:flex-start">${scoresHTML(d)}</div>
          <p class="ov">${esc(d.description || tm.overview || "")}</p>
          <div class="actions">
            ${x.kind !== "series" ? `<button class="btn primary" data-a="play"><i class="ic ic-play"></i>${d.resume ? t("resume") + " · " + esc(d.resume.label) : t("play")}</button>${d.resume ? `<button class="btn" data-a="start">${t("fromStart")}</button>` : ""}` : `<button class="btn primary" data-a="next"><i class="ic ic-play"></i>${t("nextEp")}</button>`}
            <button class="btn ${d.favorite ? "on" : ""}" data-a="fav"><i class="ic ic-star"></i>${t("favorite")}</button>
            ${tm.trailer ? `<button class="btn" data-a="trailer"><i class="ic ic-trailer"></i>${t("trailer")}</button>` : ""}
          </div>
        </div>
      </div>
      ${(tm.cast || []).length ? `<div class="block"><h3>${t("cast")}</h3><div class="cast">${castHTML(tm, 10)}</div></div>` : ""}
      ${x.kind === "series" ? `<div class="block" id="seasons-box"><h3>${t("seasons")}</h3><div class="spinner"></div></div>` : ""}`;
    $("#det-body").onclick = (e) => {
      const a = e.target.closest("[data-a]")?.dataset.a; if (!a) return;
      if (a === "play") play(ref); if (a === "start") play(ref, true);
      if (a === "fav") toggleFav(ref, e.target.closest(".btn"));
      if (a === "trailer") api("ui_open_url", tm.trailer);
      if (a === "next" && Seasons.next) play(Seasons.next);
    };
  };
  draw(x);
  try { draw(await details(ref)); } catch (e) { toast(e.message, true); }
  if (x.kind === "series") Seasons.load(ref);
};
const Seasons = {
  next: null, data: null, cur: 0,
  async load(ref) {
    let d; try { d = await api("episodes", ref); } catch (e) { const b = $("#seasons-box"); if (b) b.innerHTML = `<div class="empty"><b>${esc(e.message)}</b></div>`; return; }
    if (S.route !== "details") return;
    d.seasons.forEach((s) => remember(s.episodes)); this.data = d; this.next = d.next;
    const box = $("#seasons-box"); if (!box) return;
    if (!d.seasons.length) { box.innerHTML = `<h3>${t("seasons")}</h3><div class="empty"><b>${t("noEpisodes")}</b></div>`; return; }
    let start = d.seasons.findIndex((s) => s.episodes.some((e) => e.ref === d.next)); if (start < 0) start = 0;
    box.innerHTML = `<h3>${t("seasons")}</h3><div class="seasons"><div class="list" id="slist">${d.seasons.map((s, i) => `<div class="row" data-i="${i}"><i class="ic ic-layers" style="width:18px;height:18px;color:var(--muted)"></i><span class="t">${t("season")} ${s.season}</span><span class="n">${s.episodes.length}</span></div>`).join("")}</div><div class="eps" id="eps"></div></div>`;
    $("#slist").onclick = (e) => { const r = e.target.closest(".row"); if (r) this.show(+r.dataset.i); };
    $("#eps").onclick = (e) => { const r = e.target.closest(".ep"); if (r) play(r.dataset.ref); };
    this.show(start);
  },
  show(i) {
    this.cur = i; $$("#slist .row").forEach((r) => r.classList.toggle("on", +r.dataset.i === i));
    const s = this.data.seasons[i];
    $("#eps").innerHTML = s.episodes.map((e, k) => `<div class="ep ${e.watched ? "watched" : ""} ${e.ref === this.next ? "next" : ""}" data-ref="${esc(e.ref)}">
      <span class="num">${e.episode ?? k + 1}</span><div style="min-width:0"><div class="t">${esc(e.title)}</div><div class="s">${e.watched ? t("watched") : e.ref === this.next ? t("nextEp") : `${t("season")} ${s.season}`}</div></div><span class="pi"><i class="ic ic-play"></i></span></div>`).join("");
  },
};

/* ------------------------------------------------------------------ search */
views.search = (v, [q0]) => {
  if (needConnection()) return;
  document.body.classList.add("dim"); backdrop("");
  v.appendChild(h(`<section class="std"><div class="std-head"><div class="search-box"><i class="ic ic-search"></i><input class="input" id="q" placeholder="${t("searchAll")}" value="${esc(q0 || "")}"></div></div><div id="res"></div></section>`));
  bar(t("search"), [["Enter", t("search")], ["Esc", t("keysBack")]], "");
  let token = 0;
  const run = async (q) => {
    const my = ++token; const res = $("#res");
    if (q.length < 2) { res.innerHTML = ""; return; }
    res.innerHTML = `<div class="spinner"></div>`;
    let r; try { r = await api("search", q); } catch (e) { res.innerHTML = `<div class="empty"><b>${esc(e.message)}</b></div>`; return; }
    if (my !== token) return; Object.values(r).forEach(remember);
    const total = r.live.length + r.movies.length + r.series.length;
    if (!total) { res.innerHTML = `<div class="empty"><b>${t("noResults")}</b></div>`; return; }
    res.innerHTML = [
      r.live.length ? `<section class="shelf"><h3>${t("live")} <span class="muted">${r.live.length}</span></h3><div class="res-live">${r.live.map((x) => `<div class="row ch" data-ref="${esc(x.ref)}"><span class="logo">${x.poster ? imgTag(x) : esc(initials(x.title).slice(0, 3))}</span><span class="t">${esc(x.title)}</span></div>`).join("")}</div></section>` : "",
      r.movies.length ? `<section class="shelf" style="margin-top:22px"><h3>${t("movies")} <span class="muted">${r.movies.length}</span></h3><div class="res-grid">${r.movies.map((x) => posterHTML(x)).join("")}</div></section>` : "",
      r.series.length ? `<section class="shelf" style="margin-top:22px"><h3>${t("series")} <span class="muted">${r.series.length}</span></h3><div class="res-grid">${r.series.map((x) => posterHTML(x)).join("")}</div></section>` : "",
    ].join("");
    bar(t("search"), [["Esc", t("keysBack")]], `${total} ${t("items")}`);
  };
  const q = $("#q"); q.oninput = debounce((e) => run(e.target.value.trim()), 380); q.focus(); if (q0) run(q0);
  $("#res").onclick = (e) => { const el = e.target.closest("[data-ref]"); if (!el) return; const x = S.view.get(el.dataset.ref); x.kind === "live" ? play(x.ref) : (location.hash = "#/details/" + encodeURIComponent(x.ref)); };
};

/* ------------------------------------------------------------------ favorites */
views.favorites = async (v, [tab]) => {
  if (needConnection()) return;
  document.body.classList.add("dim"); backdrop("");
  tab = tab || "movies";
  v.appendChild(h(`<section class="std"><div class="std-head"><h1 class="h-title">${t("favorites")}</h1>
    <div class="tabs" style="margin-inline-start:auto">${["live", "movies", "series"].map((k) => `<button data-k="${k}" class="${k === tab ? "on" : ""}">${t(k)}</button>`).join("")}</div></div><div id="fv"><div class="spinner"></div></div></section>`));
  $(".tabs").onclick = (e) => { const b = e.target.closest("button"); if (b) location.hash = "#/favorites/" + b.dataset.k; };
  let f; try { f = await api("favorites"); } catch (e) { $("#fv").innerHTML = `<div class="empty"><b>${esc(e.message)}</b></div>`; return; }
  Object.values(f).forEach(remember); const rows = f[tab] || [];
  bar(t("favorites"), [["Esc", t("keysBack")]], `${rows.length} ${t("items")}`);
  $("#fv").innerHTML = !rows.length ? `<div class="empty"><i class="ic ic-star" style="width:44px;height:44px;color:var(--gold)"></i><b>${t("empty")}</b></div>`
    : tab === "live" ? `<div class="res-live">${rows.map((x) => `<div class="row ch" data-ref="${esc(x.ref)}"><span class="logo">${esc(initials(x.title).slice(0, 3))}</span><span class="t">${esc(x.title)}</span><span class="fav"><i class="ic ic-star-fill"></i></span></div>`).join("")}</div>`
    : `<div class="res-grid">${rows.map((x) => posterHTML(x)).join("")}</div>`;
  $("#fv").onclick = (e) => { const el = e.target.closest("[data-ref]"); if (!el) return; const x = S.view.get(el.dataset.ref); x.kind === "live" || x.kind === "episode" ? play(x.ref) : (location.hash = "#/details/" + encodeURIComponent(x.ref)); };
};

/* ------------------------------------------------------------------ sources */
const TYPE_LABEL = { stalker: "Stalker / MAG", xtream: "Xtream Codes", m3u: "M3U" };
views.sources = (v) => {
  backdrop("");
  v.appendChild(h(`<section class="sources"><div class="sources-head"><div><div class="eyebrow">ULTRA STALKER</div><h1 class="h-title">${t("yourSources")}</h1><div class="muted">${t("sourcesSub")}</div></div>
    <button class="btn primary" style="margin-inline-start:auto" id="add"><i class="ic ic-plus"></i>${t("addSource")}</button></div><div class="src-grid" id="srcs"></div></section>`));
  bar(t("sources"), [["Enter", t("connect")]], `${S.profiles.length}`);
  $("#add").onclick = () => sourceForm();
  drawSources();
};
function drawSources() {
  const g = $("#srcs"); if (!g) return;
  g.innerHTML = S.profiles.map((p) => `<div class="src ${S.connected && S.connected.name === p.name ? "active" : ""}" data-n="${esc(p.name)}">
      <div class="type"><i class="ic ${p.type === "m3u" ? "ic-list" : p.type === "xtream" ? "ic-sources" : "ic-live"}"></i>${TYPE_LABEL[p.type] || p.type}${S.connected && S.connected.name === p.name ? `<span style="margin-inline-start:auto;color:var(--emerald)"><i class="live-dot"></i>${t("active")}</span>` : ""}</div>
      <h3>${esc(p.name)}</h3><div class="host" dir="ltr">${esc(p.host)}</div><div class="muted" dir="ltr" style="font-size:13px">${esc(p.mac || p.user || "")}</div>
      <div class="foot"><button class="btn primary" data-a="connect"><i class="ic ic-play"></i>${t("connect")}</button><span class="sp"></span>
        <button class="btn icon" data-a="edit" title="${t("edit")}"><i class="ic ic-edit"></i></button><button class="btn icon danger" data-a="del" title="${t("delete")}"><i class="ic ic-trash"></i></button></div></div>`).join("")
    + `<div class="src add" data-a="add"><i class="ic ic-plus"></i><h3>${t("addSource")}</h3><div class="muted">Stalker · Xtream · M3U</div></div>`;
  g.onclick = async (e) => {
    const card = e.target.closest(".src"); if (!card) return; const a = e.target.closest("[data-a]")?.dataset.a || "connect";
    if (card.classList.contains("add")) return sourceForm();
    const name = card.dataset.n;
    if (a === "edit") { try { sourceForm(await api("profile", name)); } catch (er) { toast(er.message, true); } return; }
    if (a === "del") { if (!confirm(t("confirmDelete"))) return; try { S.profiles = await api("profile_delete", name); if (S.connected && S.connected.name === name) disconnected(); drawSources(); toast(t("deleted")); } catch (er) { toast(er.message, true); } return; }
    card.classList.add("busy"); toast(t("connecting"));
    try { connectedTo(await api("connect", name)); location.hash = "#/home"; } catch (er) { toast(er.message, true); } finally { card.classList.remove("busy"); }
  };
}
function connectedTo(c) {
  S.connected = c; S.cats = {}; S.cat = {}; S.items.clear(); S.det.clear(); S.view.clear();
  S.profiles.forEach((p) => (p.active = p.name === c.name)); toast(t("connected") + " · " + c.name);
}
function disconnected() { S.connected = null; S.cats = {}; S.items.clear(); }
function sourceForm(p) {
  const edit = !!p; p = p || { type: "stalker", name: "", url: "", mac: "00:1A:79:", username: "" };
  let type = p.type;
  const wrap = h(`<div class="modal-wrap"><form class="modal glass edge" autocomplete="off">
    <h2>${edit ? t("editSource") : t("addSource")}</h2><p class="sub">${t("sourcesSub")}</p>
    <div class="seg">${["stalker", "xtream", "m3u"].map((k) => `<button type="button" data-k="${k}">${TYPE_LABEL[k]}</button>`).join("")}</div>
    <div class="field"><label>${t("srcName")}</label><input class="input" name="name" value="${esc(p.name)}" maxlength="60"></div>
    <div class="field"><label id="url-l">${t("srcUrl")}</label><input class="input" name="url" dir="ltr" value="${esc(p.url)}" placeholder="http://example.com:8080/c/"></div>
    <div class="field f-mac"><label>${t("srcMac")}</label><input class="input" name="mac" dir="ltr" value="${esc(p.mac || "00:1A:79:")}" placeholder="00:1A:79:XX:XX:XX"></div>
    <div class="field f-x"><label>${t("srcUser")}</label><input class="input" name="username" dir="ltr" value="${esc(p.username || "")}"></div>
    <div class="field f-x"><label>${t("srcPass")}</label><input class="input" name="password" type="password" dir="ltr" placeholder="${edit && p.has_password ? t("keepPass") : ""}"></div>
    <div class="form-err" id="ferr"></div>
    <div class="row-acts"><button class="btn primary" type="submit"><i class="ic ic-play"></i>${t("save")} · ${t("connect")}</button><button class="btn" type="button" data-a="cancel">${t("cancel")}</button></div>
  </form></div>`);
  document.body.appendChild(wrap);
  const f = $("form", wrap);
  const sync = () => {
    $$(".seg button", f).forEach((b) => b.classList.toggle("on", b.dataset.k === type));
    $$(".f-mac", f).forEach((x) => (x.hidden = type !== "stalker")); $$(".f-x", f).forEach((x) => (x.hidden = type !== "xtream"));
    $("#url-l", f).textContent = type === "m3u" ? t("m3uUrl") : t("srcUrl");
    f.url.placeholder = type === "m3u" ? "https://example.com/playlist.m3u" : type === "xtream" ? "http://example.com:8080" : "http://example.com:8080/c/";
  };
  sync();
  $(".seg", f).onclick = (e) => { const b = e.target.closest("button"); if (b) { type = b.dataset.k; sync(); } };
  const close = () => wrap.remove();
  $("[data-a=cancel]", f).onclick = close; wrap.addEventListener("mousedown", (e) => { if (e.target === wrap) close(); });
  f.onsubmit = async (e) => {
    e.preventDefault(); const btn = $("button[type=submit]", f); btn.disabled = true; $("#ferr", f).textContent = t("connecting");
    const data = { type, name: f.name.value, url: f.url.value, mac: f.mac.value, username: f.username.value, password: f.password.value, original: edit ? p.name : "" };
    try {
      const r = await api("profile_save", data, true);
      S.profiles = r.profiles; if (r.connected) connectedTo(r.connected); if (r.save_error) toast(r.save_error, true);
      close(); location.hash = "#/home";
    } catch (er) { $("#ferr", f).textContent = er.message; btn.disabled = false; }
  };
  setTimeout(() => (edit ? f.url : f.name).focus(), 40);
}

/* ------------------------------------------------------------------ settings */
views.settings = (v) => {
  backdrop(""); document.body.classList.add("dim");
  const st = S.settings;
  v.appendChild(h(`<section class="std"><div class="std-head"><h1 class="h-title">${t("settings")}</h1></div><div class="set-grid">
    <div class="set-card glass"><h3><i class="ic ic-lang"></i>${t("setLang")}</h3><p>${t("setLangSub")}</p>
      <div class="tabs" data-set="ui_language"><button data-v="ar">${t("arabic")}</button><button data-v="en">${t("english")}</button></div></div>
    <div class="set-card glass"><h3><i class="ic ic-movies"></i>${t("setMeta")}</h3><p>${t("setMetaSub")}</p>
      <div class="field"><label>${t("metaLang")}</label><div class="tabs" data-set="tmdb_language"><button data-v="ar">${t("arabic")}</button><button data-v="en">${t("english")}</button></div></div>
      <div class="field"><label>${t("tmdbKey")}</label><input class="input" id="tmdbkey" dir="ltr" type="password" placeholder="${S.hasKey ? "••••••••••••" : ""}"><span class="muted" style="font-size:13px">${t("tmdbKeySub")}</span></div>
      <button class="btn" id="savekey">${t("save")}</button></div>
    <div class="set-card glass"><h3><i class="ic ic-play"></i>${t("setPlayer")}</h3><p>${t("setPlayerSub")}</p>
      <div class="field"><div class="tabs" data-set="player"><button data-v="mpv">mpv</button><button data-v="vlc">VLC</button></div></div>
      <div class="field"><label>${t("livePrev")}</label><div class="tabs" data-set="live_preview"><button data-v="true">${t("on")}</button><button data-v="false">${t("off")}</button></div></div></div>
    <div class="set-card glass about"><h3><i class="ic ic-info"></i>${t("about")}</h3>
      <div>Ultra Stalker Desktop</div><div>${t("version")}: <b>${esc(S.version)}</b></div><div>${t("design")}: <b>${esc(S.author)}</b></div></div>
  </div></section>`));
  bar(t("settings"), [["Esc", t("keysBack")]], "");
  const cur = { ui_language: LANG, tmdb_language: st.tmdb_language || LANG, player: st.player || "mpv", live_preview: String(st.live_preview !== false) };
  $$("[data-set]").forEach((g) => {
    const k = g.dataset.set; $$("button", g).forEach((b) => b.classList.toggle("on", b.dataset.v === cur[k]));
    g.onclick = async (e) => {
      const b = e.target.closest("button"); if (!b) return; let val = b.dataset.v; if (k === "live_preview") val = val === "true";
      try { const r = await api("settings_save", { [k]: val }); Object.assign(S.settings, r); S.det.clear(); toast(t("saved")); } catch (er) { toast(er.message, true); return; }
      if (k === "ui_language") { LANG = val; applyLang(); }
      route();
    };
  });
  $("#savekey").onclick = async () => { try { const r = await api("settings_save", { tmdb_api_key: $("#tmdbkey").value }); S.hasKey = r.has_tmdb_key; S.det.clear(); toast(t("saved")); } catch (er) { toast(er.message, true); } };
};

/* ------------------------------------------------------------------ actions */
async function play(ref, fromStart) {
  if (!ref) return; toast(t("starting"));
  if (S.route === "live") Live.stopPreview();
  try { await api("play", ref, !!fromStart); } catch (e) { toast(e.message, true); if (S.route === "live") Live.rearm(); }
}
async function toggleFav(ref, btn) {
  if (!ref) return;
  try {
    const r = await api("favorite", ref); const x = S.view.get(ref); if (x) x.favorite = r.favorite;
    const d = S.det.get(ref); if (d) d.then((v) => (v.favorite = r.favorite));
    if (btn) btn.classList.toggle("on", r.favorite); toast(r.favorite ? t("favAdded") : t("favRemoved"));
  } catch (e) { toast(e.message, true); }
}

/* ------------------------------------------------------------------ keyboard */
document.addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "");
  if (e.key === "Escape") {
    if ($(".modal-wrap")) { $(".modal-wrap").remove(); return; }
    if (!$("#drawer").hidden) { closeDrawer(); return; }
    if (typing) { document.activeElement.blur(); return; }
    if (S.route !== "home") history.length > 1 ? history.back() : (location.hash = "#/home");
    return;
  }
  if (typing || $(".modal-wrap") || !$("#drawer").hidden) return;
  if (e.key === "/" || (e.ctrlKey && e.key.toLowerCase() === "f")) { e.preventDefault(); location.hash = "#/search"; return; }
  if (e.key === "F11") { e.preventDefault(); api("ui_fullscreen"); return; }
  if (e.key === "Backspace") { e.preventDefault(); history.back(); return; }
  let used = false;
  if (S.route === "movies" || S.route === "series") used = Grid.key(e);
  else if (S.route === "live") used = Live.key(e);
  if (used) e.preventDefault();
});
document.addEventListener("contextmenu", (e) => { if (!/INPUT/.test(e.target.tagName)) e.preventDefault(); });

/* ------------------------------------------------------------------ boot */
async function boot() {
  const hello = await api("hello");
  S.version = hello.version; S.author = hello.author; S.settings = hello.settings || {}; S.hasKey = hello.has_tmdb_key;
  S.profiles = hello.profiles || []; S.connected = hello.connected;
  LANG = S.settings.ui_language === "en" ? "en" : "ar"; applyLang();
  const last = S.settings.last_profile;
  if (!S.connected && last && S.profiles.some((p) => p.name === last)) {
    $("#view").innerHTML = `<div class="empty" style="height:100%"><div class="spinner"></div><b>${t("connecting")}</b><span>${esc(last)}</span></div>`;
    try { connectedTo(await api("connect", last)); } catch (e) { toast(e.message, true); location.hash = "#/sources"; route(); return; }
    location.hash = "#/home"; route(); return;
  }
  if (!location.hash || location.hash === "#/") location.hash = S.connected || S.profiles.length ? "#/" + (S.connected ? "home" : "sources") : "#/sources";
  route();
}
function start(bridge) {
  BR = bridge; BR.reply.connect(onReply); BR.push.connect(onPush); boot().catch((e) => toast(e.message, true));
}
if (window.qt && window.qt.webChannelTransport) {
  new QWebChannel(qt.webChannelTransport, (ch) => start(ch.objects.bridge));
} else {
  const s = document.createElement("script"); s.src = "mock.js"; s.onload = () => start(window.MockBridge); document.head.appendChild(s);
}
