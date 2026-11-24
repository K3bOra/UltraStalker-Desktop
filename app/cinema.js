/* Ultra Stalker for Windows — the "Cinema" look.

   A second way to see the program, chosen from the top bar (and back from its own rail):
   a big picture of the title you rest on, its name, story and buttons over it, and the
   posters in rows below it, like a streaming service. It is built on the page's own
   data (api/browse/…) and plays with the page's own player, so servers, favorites,
   the player and its features stay the same. The classic look is untouched. */
(function () {
  "use strict";
  if (!document.documentElement.classList.contains("us-app")) return;
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const get = (k, d) => {
    try {
      const v = JSON.parse(localStorage.getItem(k));
      return v == null ? d : v;
    } catch (_) {
      return d;
    }
  };
  const set = (k, v) => {
    try {
      localStorage.setItem(k, JSON.stringify(v));
    } catch (_) {}
  };
  async function api(path) {
    const r = await fetch("api/browse/" + path, { cache: "no-store" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw new Error(j.error || "The server did not answer");
    return j;
  }
  const parse = (t) => (window.usCards && window.usCards.parse ? window.usCards.parse(t) : { title: String(t || ""), quality: [], lang: [], year: "", country: "" });
  const nice = (t) => parse(t).title || String(t || "");
  const E = () => window.USEngine || {};
  const art = (id, media) => {
    try {
      return (E().art && E().art(id, media)) || "";
    } catch (_) {
      return "";
    }
  };
  const backdrop = (id) => {
    try {
      return (E().backdrop && E().backdrop(id)) || "";
    } catch (_) {
      return "";
    }
  };
  const extras = (id) => {
    try {
      return (E().extras && E().extras(id)) || {};
    } catch (_) {
      return {};
    }
  };

  const ICON = {
    home: '<path d="M4 11l8-7 8 7v8.5a1.5 1.5 0 0 1-1.5 1.5H15v-6H9v6H5.5A1.5 1.5 0 0 1 4 19.5z"/>',
    live: '<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M8 2.5l4 3.5 4-3.5M10 10.5v5l4-2.5z"/>',
    vod: '<rect x="3" y="5" width="18" height="15" rx="2.5"/><path d="M3 9.5h18M7.5 5l2 4.5M12.5 5l2 4.5M17.5 5l2 4.5"/>',
    series: '<rect x="6.5" y="3" width="14.5" height="13" rx="2"/><path d="M3 7v12.5a1.5 1.5 0 0 0 1.5 1.5H17M11.5 7.5v5l4-2.5z"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    star: '<path d="M12 3.2l2.6 5.4 5.9.8-4.3 4.1 1 5.8L12 16.5l-5.2 2.8 1-5.8L3.5 9.4l5.9-.8z"/>',
    servers: '<rect x="3.5" y="4" width="17" height="6.5" rx="2"/><rect x="3.5" y="13.5" width="17" height="6.5" rx="2"/><path d="M7.5 7.25h.01M7.5 16.75h.01"/>',
    classic: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.6"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.6"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.6"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.6"/>',
    cinema: '<rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M10 9v6l5-3z"/>',
    play: '<path class="f" d="M7.5 5.2v13.6a1 1 0 0 0 1.52.85l10.9-6.8a1 1 0 0 0 0-1.7L9.02 4.35A1 1 0 0 0 7.5 5.2z"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    back: '<path d="M15 5l-7 7 7 7"/>',
    down: '<path d="M6 9l6 6 6-6"/>',
    left: '<path d="M15 5l-7 7 7 7"/>',
    right: '<path d="M9 5l7 7-7 7"/>',
    min: '<path d="M6 12h12"/>',
    full: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    window: '<path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    grid: '<rect x="4" y="4" width="6" height="6" rx="1.4"/><rect x="14" y="4" width="6" height="6" rx="1.4"/><rect x="4" y="14" width="6" height="6" rx="1.4"/><rect x="14" y="14" width="6" height="6" rx="1.4"/>',
    layers: '<path d="M12 3.5l9 4.8-9 4.8-9-4.8z"/><path d="M3.5 12.4L12 17l8.5-4.6"/>',
  };
  const ic = (n) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICON[n] || ""}</svg>`;

  /* ------------------------------------------------------------ the look is on or off */
  const ON = "us-desk-look";
  const isOn = () => get(ON, "classic") === "cinema";
  let built = false;
  function turn(on) {
    set(ON, on ? "cinema" : "classic");
    document.documentElement.classList.toggle("us-cine", on);
    if (on) enter(state.view === "details" ? state.from || "home" : state.view || "home");
  }
  // the page must have a server chosen: the one it remembers, or the first
  function enter(view) {
    build();
    let n = 0;
    const ready = () => {
      if (!isOn()) return;
      const sel = $("browseAccount");
      const first = sel && [...sel.options].find((o) => o.value);
      if (sel && sel.value) {
        paintAccount();
        return go(view, true);
      }
      if (first) {
        sel.value = get("us-cine-account", "") && [...sel.options].some((o) => o.value === get("us-cine-account", "")) ? get("us-cine-account", "") : first.value;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
        return; // the change below opens the view
      }
      if (n++ > 40) return go(view, true);
      setTimeout(ready, 250);
    };
    ready();
  }
  // a button in the classic top bar to come back to the Cinema look
  function classicButton() {
    if ($("usCineBtn")) return true;
    const near = document.querySelector(".dk-qb");
    if (!near) return false;
    const b = document.createElement("button");
    b.type = "button";
    b.id = "usCineBtn";
    b.className = "dk-qb us-cine-btn";
    b.title = "Cinema look";
    b.innerHTML = `<span class="dk-ic">${ic("cinema")}</span>Cinema`;
    b.onclick = () => turn(true);
    near.parentNode.insertBefore(b, near);
    return true;
  }

  /* ------------------------------------------------------------ state */
  const state = { view: "home", from: "", media: "series", cats: {}, cat: {}, items: [], page: 0, more: false, loading: false, gen: 0, hero: null, detail: null };
  const account = () => ($("browseAccount") && $("browseAccount").value) || "";
  let root, main, tabs, heroBox, bgA, bgB, rail;

  function build() {
    if (built) return;
    built = true;
    root = document.createElement("div");
    root.id = "usCine";
    root.innerHTML =
      '<div class="cn-bg"><img alt=""><img alt=""></div><div class="cn-shade"></div>' +
      '<nav class="cn-rail">' +
      '<div class="cn-logo" title="Ultra Stalker"></div>' +
      [["home", "Home"], ["live", "Live TV"], ["vod", "Movies"], ["series", "Series"], ["search", "Search"], ["favorites", "Favorites"]]
        .map(([v, t]) => `<button type="button" data-v="${v}" title="${t}">${ic(v === "favorites" ? "star" : v)}<span>${t}</span></button>`)
        .join("") +
      '<i class="cn-sp"></i>' +
      `<button type="button" data-a="servers" title="Servers &amp; Backup">${ic("servers")}<span>Servers</span></button>` +
      `<button type="button" data-a="classic" title="Classic look">${ic("classic")}<span>Classic</span></button>` +
      "</nav>" +
      '<header class="cn-top"><div class="cn-tabs"></div><i class="cn-sp"></i>' +
      '<div class="cn-acc"><button type="button" class="cn-acc-b"><b></b><small></small>' + ic("down") + '</button><div class="cn-acc-m"></div></div>' +
      `<div class="cn-win"><button type="button" data-w="min" title="Minimise">${ic("min")}</button><button type="button" data-w="full" title="Full screen (F11)">${ic("full")}</button><button type="button" data-w="close" title="Close">${ic("close")}</button></div>` +
      "</header>" +
      '<main class="cn-main"></main>';
    document.body.appendChild(root);
    main = root.querySelector(".cn-main");
    wire();
    tabs = root.querySelector(".cn-tabs");
    rail = root.querySelector(".cn-rail");
    [bgA, bgB] = root.querySelectorAll(".cn-bg img");
    [bgA, bgB].forEach((im) => {
      im.onload = () => {
        const other = im === bgA ? bgB : bgA;
        im.classList.add("on");
        other.classList.remove("on");
      };
      im.onerror = () => im.classList.remove("on");
    });
    rail.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.v) return go(b.dataset.v);
      if (b.dataset.a === "classic") return turn(false);
      if (b.dataset.a === "servers") {
        turn(false);
        const portals = [...document.querySelectorAll(".dk-qb")].find((x) => /portal/i.test(x.textContent));
        if (portals) portals.click();
      }
    });
    root.querySelector(".cn-win").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-w]");
      if (b && window.usNative && window.usNative.win) window.usNative.win.cmd(b.dataset.w);
    });
    const W = window.usNative && window.usNative.win;
    if (W && W.onState) {
      const paint = (s) => {
        const f = root.querySelector('[data-w="full"]');
        f.innerHTML = ic(s && s.full ? "window" : "full");
      };
      W.onState(paint);
      try {
        paint(W.state());
      } catch (_) {}
    }
    const accB = root.querySelector(".cn-acc-b");
    accB.onclick = () => root.querySelector(".cn-acc").classList.toggle("open");
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".cn-acc")) root.querySelector(".cn-acc").classList.remove("open");
    });
    paintAccount();
    const sel = $("browseAccount");
    if (sel) sel.addEventListener("change", () => {
      if (sel.value) set("us-cine-account", sel.value);
      paintAccount();
      state.cats = {};
      state.cat = {};
      if (isOn()) go(state.view === "details" ? "home" : state.view, true);
    });
    document.addEventListener("keydown", (e) => {
      if (!isOn() || playerOpen()) return;
      if (e.target.closest && e.target.closest("input,textarea")) return;
      if ((e.key === "Escape" || e.key === "Backspace") && state.view === "details") {
        e.preventDefault();
        back();
      }
    });
  }

  function playerOpen() {
    const p = document.querySelector(".usp");
    return !!p && getComputedStyle(p).display !== "none" && getComputedStyle(p).visibility !== "hidden" && p.getClientRects().length > 0;
  }

  function paintAccount() {
    if (!root) return;
    const sel = $("browseAccount");
    const opts = sel ? [...sel.options].filter((o) => o.value) : [];
    const cur = opts.find((o) => o.value === sel.value);
    root.querySelector(".cn-acc-b b").textContent = cur ? cur.textContent.trim() : "Choose a server";
    root.querySelector(".cn-acc-b small").textContent = opts.length > 1 ? opts.length + " servers" : "";
    root.querySelector(".cn-acc-m").innerHTML = opts.map((o) => `<button type="button" data-acc="${esc(o.value)}" class="${o.value === sel.value ? "on" : ""}">${esc(o.textContent.trim())}</button>`).join("");
    root.querySelectorAll(".cn-acc-m button").forEach((b) => {
      b.onclick = () => {
        root.querySelector(".cn-acc").classList.remove("open");
        if (sel.value === b.dataset.acc) return;
        sel.value = b.dataset.acc;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      };
    });
  }

  /* ------------------------------------------------------------ the big picture behind everything */
  let bgWant = "";
  function picture(url) {
    if (!url || url === bgWant) return;
    bgWant = url;
    const next = bgA.classList.contains("on") ? bgB : bgA;
    next.classList.toggle("soft", false);
    next.src = url;
  }

  /* ------------------------------------------------------------ views */
  function mark() {
    rail.querySelectorAll("button[data-v]").forEach((b) => b.classList.toggle("on", b.dataset.v === (state.view === "details" ? state.from : state.view)));
    root.dataset.view = state.view;
  }
  function go(view, force) {
    if (!force && view === state.view && view !== "details") return;
    state.gen++;
    if (view !== "details") state.from = view;
    state.view = view;
    main.scrollTop = 0;
    root.classList.remove("cn-compact");
    mark();
    tabs.innerHTML = "";
    if (!account()) return empty("Add a server first", "Open Servers to add your portal, Xtream line or playlist.", true);
    if (view === "home") return home();
    if (view === "vod" || view === "series" || view === "live") return browse(view === "live" ? "itv" : view);
    if (view === "search") return search();
    if (view === "favorites") return favorites();
  }
  function empty(title, text, servers) {
    main.innerHTML = `<section class="cn-empty"><h2>${esc(title)}</h2><p>${esc(text)}</p>${servers ? `<button type="button" class="cn-btn p">${ic("servers")}Servers</button>` : ""}</section>`;
    const b = main.querySelector(".cn-btn");
    if (b) b.onclick = () => rail.querySelector('[data-a="servers"]').click();
  }

  /* the hero: name, facts, story and buttons of one title */
  const details = new Map();
  function info(id) {
    if (!details.has(id)) details.set(id, api("details?item=" + enc(id)).catch(() => null));
    return details.get(id);
  }
  function heroHtml(withButtons) {
    return (
      '<section class="cn-hero"><div class="cn-hero-in">' +
      '<div class="cn-kick"></div><img class="cn-logo-t" alt=""><h1 class="cn-title" dir="auto"></h1>' +
      '<div class="cn-meta"></div><p class="cn-story" dir="auto"></p>' +
      (withButtons ? '<div class="cn-acts"></div>' : "") +
      "</div></section>"
    );
  }
  async function showHero(row, media, opts = {}) {
    const box = main.querySelector(".cn-hero");
    if (!box || !row) return;
    state.hero = { row, media };
    const gen = state.gen;
    const p = parse(row.raw_title || row.title);
    const t = box.querySelector(".cn-title");
    const logo = box.querySelector(".cn-logo-t");
    t.textContent = p.title;
    box.querySelector(".cn-kick").innerHTML = opts.kick ? `<i></i>${esc(opts.kick)}` : "";
    const facts = (d) => {
      const out = [];
      const rating = Number((d && d.rating) || row.rating);
      if (rating > 0) out.push(`<span class="r">${ic("star")}${rating.toFixed(1)}</span>`);
      const y = (d && d.year) || row.year || p.year;
      if (y) out.push(`<span>${esc(y)}</span>`);
      if (row.age_rating) out.push(`<span class="b">${esc(row.age_rating)}</span>`);
      const n = Number(row.season_count) || (window.usCardsSeasons ? window.usCardsSeasons(row) : 0);
      if (media === "series" && n) out.push(`<span>${n} Season${n === 1 ? "" : "s"}</span>`);
      if (d && d.runtime) out.push(`<span>${esc(d.runtime)} min</span>`);
      const g = d && Array.isArray(d.genres) ? d.genres.slice(0, 3) : [];
      if (g.length) out.push(`<span class="g">${esc(g.join(" · "))}</span>`);
      p.quality.concat(p.lang).forEach((q) => out.push(`<span class="b">${esc(q)}</span>`));
      return out.join("");
    };
    box.querySelector(".cn-meta").innerHTML = facts(null);
    box.querySelector(".cn-story").textContent = "";
    logo.classList.remove("on");
    box.classList.remove("in");
    void box.offsetWidth;
    box.classList.add("in");
    const poster = art(row.id, media);
    if (!backdrop(row.id) && poster) picture(poster), root.classList.add("cn-soft");
    if (opts.buttons) heroButtons(row, media);
    const d = await info(row.id);
    if (gen !== state.gen || !state.hero || state.hero.row !== row) return;
    const back = backdrop(row.id);
    if (back) {
      root.classList.remove("cn-soft");
      picture(back);
    } else if (poster) {
      root.classList.add("cn-soft");
      picture(poster);
    }
    box.querySelector(".cn-meta").innerHTML = facts(d);
    box.querySelector(".cn-story").textContent = (d && d.overview) || "";
    const ex = extras(row.id);
    if (ex.logo) {
      logo.onload = () => logo.classList.add("on");
      logo.src = ex.logo;
      box.classList.add("has-logo");
    } else box.classList.remove("has-logo");
  }

  /* ------------------------------------------------------------ continue watching (kept across restarts) */
  const CONT = "us-cine-continue";
  const entryOf = (id) => {
    try {
      return sessionStorage.getItem("usi:" + id) || "";
    } catch (_) {
      return "";
    }
  };
  const revive = (entries) => {
    for (const [k, v] of Object.entries(entries || {})) {
      try {
        if (v && !sessionStorage.getItem("usi:" + k)) sessionStorage.setItem("usi:" + k, v);
      } catch (_) {}
    }
  };
  let playing = null;
  function remember(rec) {
    const list = get(CONT, []).filter((x) => !(x.account === rec.account && x.key === rec.key));
    list.unshift(rec);
    set(CONT, list.slice(0, 30));
    playing = rec;
  }
  setInterval(() => {
    if (!playing || typeof window.usxState !== "function") return;
    const s = window.usxState();
    if (!s || s.live || !(s.d > 60) || !(s.t > 0)) return;
    const list = get(CONT, []);
    const it = list.find((x) => x.account === playing.account && x.key === playing.key);
    if (!it) return;
    it.p = +(s.t / s.d).toFixed(3);
    it.at = Date.now();
    const done = it.p > 0.95 && it.media === "vod";
    set(CONT, done ? list.filter((x) => x !== it) : list);
  }, 5000);

  function play(row, ctx = {}) {
    if (!row || typeof window.openPlayerSheet !== "function") return;
    try {
      if (ctx.series) {
        // the page's next-episode feature reads these
        // eslint-disable-next-line no-undef
        activeSeries = ctx.series;
        // eslint-disable-next-line no-undef
        activeSeason = ctx.season;
        if (typeof window.renderInlineEpisodes === "function") window.renderInlineEpisodes(ctx.episodes || [], (ctx.season && ctx.season.title) || "Episodes");
      }
    } catch (_) {}
    const acc = account();
    if (ctx.media === "series" && ctx.series) {
      const code = (row.season ? "S" + String(row.season).padStart(2, "0") : "") + "E" + String(Number(row.episode) || 1).padStart(2, "0");
      const entries = {};
      [ctx.series.id, ctx.season && ctx.season.id, row.id].forEach((id) => id && (entries[id] = entryOf(id)));
      remember({ account: acc, key: "s|" + nice(ctx.series.title), media: "series", series: ctx.series, season: ctx.season, ep: row, code, entries, p: 0, at: Date.now() });
    } else if (ctx.media === "vod") {
      remember({ account: acc, key: "m|" + nice(row.title), media: "vod", movie: row, entries: { [row.id]: entryOf(row.id) }, p: 0, at: Date.now() });
    } else playing = null;
    window.openPlayerSheet(row);
  }

  /* ------------------------------------------------------------ cards */
  function poster(row, media) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "cn-card" + (media === "itv" ? " live" : "");
    el.dataset.id = row.id;
    const name = media === "itv" ? row.title : nice(row.raw_title || row.title);
    const src = art(row.id, media);
    el.innerHTML =
      `<span class="cn-pic">${src ? `<img loading="lazy" decoding="async" alt="" src="${esc(src)}">` : ""}<i class="cn-ph">${esc(name.slice(0, 1))}</i></span>` +
      `<span class="cn-name" dir="auto">${esc(name)}</span>`;
    const img = el.querySelector("img");
    if (img) {
      img.onload = () => el.classList.add("ok");
      img.onerror = () => img.remove();
    }
    if (media === "itv") el.onclick = () => play(row, { media });
    else {
      el.onclick = () => openDetails(row, media);
      el.addEventListener("mouseenter", () => hoverHero(row, media));
      el.addEventListener("focus", () => hoverHero(row, media));
    }
    return el;
  }
  let hoverT = 0;
  function hoverHero(row, media) {
    clearTimeout(hoverT);
    hoverT = setTimeout(() => {
      if (state.view === "details") return;
      showHero(row, media, { buttons: true });
    }, 260);
  }
  function wide(rec) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "cn-wide";
    revive(rec.entries);
    const id = rec.media === "vod" ? rec.movie.id : rec.series.id;
    const src = backdrop(id) || art(id, rec.media);
    const name = nice(rec.media === "vod" ? rec.movie.title : rec.series.title);
    el.innerHTML =
      `<span class="cn-pic">${src ? `<img loading="lazy" alt="" src="${esc(src)}">` : ""}</span>` +
      `<span class="cn-wide-t"><b dir="auto">${esc(name)}</b><small>${esc(rec.code || "Continue")}</small></span>` +
      `<span class="cn-prog"><i style="width:${Math.round(Math.max(0.03, rec.p || 0) * 100)}%"></i></span>` +
      `<span class="cn-wide-play">${ic("play")}</span>`;
    el.onclick = async () => {
      revive(rec.entries);
      if (rec.media === "vod") return play(rec.movie, { media: "vod" });
      try {
        const j = await api("episodes?series=" + enc(rec.series.id) + "&season=" + enc(rec.season.id));
        const eps = j.episodes || [];
        const at = eps.find((e) => e.id === rec.ep.id) || rec.ep;
        play(at, { media: "series", series: rec.series, season: rec.season, episodes: eps });
      } catch (_) {
        openDetails(rec.series, "series");
      }
    };
    el.addEventListener("mouseenter", () => hoverHero(rec.media === "vod" ? rec.movie : rec.series, rec.media));
    return el;
  }
  function row(title, sub) {
    const s = document.createElement("section");
    s.className = "cn-row";
    s.innerHTML = `<h3>${esc(title)}${sub ? `<small>${esc(sub)}</small>` : ""}</h3><div class="cn-strip-w"><button type="button" class="cn-arrow l">${ic("left")}</button><div class="cn-strip"></div><button type="button" class="cn-arrow r">${ic("right")}</button></div>`;
    const strip = s.querySelector(".cn-strip");
    s.querySelector(".cn-arrow.l").onclick = () => strip.scrollBy({ left: -strip.clientWidth * 0.85, behavior: "smooth" });
    s.querySelector(".cn-arrow.r").onclick = () => strip.scrollBy({ left: strip.clientWidth * 0.85, behavior: "smooth" });
    return s;
  }

  /* ------------------------------------------------------------ home */
  async function home() {
    const gen = state.gen;
    main.innerHTML = heroHtml(true) + '<div class="cn-rows"></div>';
    const rows = main.querySelector(".cn-rows");
    const acc = account();
    const cont = get(CONT, []).filter((x) => x.account === acc);
    let first = null;
    if (cont.length) {
      const r = row("Continue watching", cont.length + (cont.length === 1 ? " title" : " titles"));
      cont.forEach((c) => r.querySelector(".cn-strip").appendChild(wide(c)));
      rows.appendChild(r);
      const c = cont[0];
      first = { row: c.media === "vod" ? c.movie : c.series, media: c.media, kick: c.code ? "CONTINUE " + c.code : "CONTINUE WATCHING" };
    }
    // favorites, then the first folders of Series and Movies; each row loads when it comes near
    const plan = [];
    for (const m of ["series", "vod"]) plan.push({ fav: m, title: m === "series" ? "My series" : "My movies" });
    for (const m of ["series", "vod"]) plan.push({ media: m });
    let firstSet = !!first;
    if (first) showHero(first.row, first.media, { buttons: true, kick: first.kick });
    const lazy = new IntersectionObserver((es) => {
      for (const e of es) if (e.isIntersecting) {
        lazy.unobserve(e.target);
        e.target._load();
      }
    }, { root: main, rootMargin: "400px 0px" });
    for (const step of plan) {
      if (gen !== state.gen) return;
      if (step.fav) {
        const j = await api("favorites?account=" + enc(acc) + "&type=" + step.fav).catch(() => null);
        const items = (j && j.items) || [];
        if (!items.length || gen !== state.gen) continue;
        const r = row(step.title, items.length + "");
        items.forEach((it) => r.querySelector(".cn-strip").appendChild(poster(it, step.fav)));
        rows.appendChild(r);
        if (!firstSet) {
          firstSet = true;
          showHero(items[0], step.fav, { buttons: true, kick: "FROM YOUR FAVORITES" });
        }
        continue;
      }
      const cats = await categories(step.media).catch(() => []);
      if (gen !== state.gen) return;
      const pick = cats.filter((c) => c.id !== "*").slice(0, 4);
      for (const c of pick) {
        const r = row(c.title, step.media === "series" ? "Series" : "Movies");
        r._load = async () => {
          const j = await api("items?account=" + enc(acc) + "&type=" + step.media + "&category=" + enc(c.id) + "&title=" + enc(c.title) + "&page=1").catch(() => null);
          if (gen !== state.gen) return;
          const items = (j && j.items) || [];
          if (!items.length) return r.remove();
          items.slice(0, 30).forEach((it) => r.querySelector(".cn-strip").appendChild(poster(it, step.media)));
          if (!firstSet) {
            firstSet = true;
            showHero(items[0], step.media, { buttons: true, kick: c.title.toUpperCase() });
          }
        };
        rows.appendChild(r);
        lazy.observe(r);
      }
    }
  }

  /* ------------------------------------------------------------ Movies, Series, Live: folders as tabs */
  async function categories(media) {
    const key = account() + "|" + media;
    if (!state.cats[key]) state.cats[key] = api("categories?account=" + enc(account()) + "&type=" + media).then((j) => j.categories || []);
    try {
      return await state.cats[key];
    } catch (e) {
      delete state.cats[key];
      throw e;
    }
  }
  async function browse(media) {
    const gen = state.gen;
    state.media = media;
    root.classList.toggle("cn-live", media === "itv");
    main.innerHTML = (media === "itv" ? '<section class="cn-head"><h2></h2><small></small></section>' : heroHtml(true)) + '<section class="cn-grid-w"><div class="cn-grid-h"><h3></h3><small></small></div><div class="cn-grid"></div><div class="cn-more"></div></section>';
    let cats;
    try {
      cats = await categories(media);
    } catch (e) {
      return gen === state.gen && empty("This server did not answer", e.message || "");
    }
    if (gen !== state.gen) return;
    if (!cats.length) return empty("Nothing here", "This server has no " + (media === "itv" ? "channels" : media === "vod" ? "movies" : "series") + ".");
    const key = account() + "|" + media;
    const cur = state.cat[key] && cats.find((c) => c.id === state.cat[key].id) ? state.cat[key] : cats[0];
    paintTabs(cats, cur, media);
    openCategory(cur, media);
  }
  function paintTabs(cats, cur, media) {
    const shown = cats.slice(0, 7);
    if (!shown.some((c) => c.id === cur.id)) shown[shown.length - 1] = cur;
    tabs.innerHTML =
      shown.map((c) => `<button type="button" data-c="${esc(c.id)}" class="${c.id === cur.id ? "on" : ""}" dir="auto">${esc(c.title)}</button>`).join("") +
      (cats.length > shown.length ? `<button type="button" class="cn-all">${ic("grid")}All ${cats.length}</button>` : "");
    tabs.querySelectorAll("button[data-c]").forEach((b) => (b.onclick = () => openCategory(cats.find((c) => c.id === b.dataset.c), media, cats)));
    const all = tabs.querySelector(".cn-all");
    if (all) all.onclick = () => allFolders(cats, media);
  }
  function allFolders(cats, media) {
    const pane = document.createElement("div");
    pane.className = "cn-folders";
    pane.innerHTML = `<div class="cn-folders-in"><div class="cn-folders-h"><h2>All ${media === "itv" ? "channel" : media === "vod" ? "movie" : "series"} folders</h2><input type="search" placeholder="Find a folder" autocomplete="off"><button type="button" class="cn-x">${ic("close")}</button></div><div class="cn-folders-l"></div></div>`;
    const list = pane.querySelector(".cn-folders-l");
    const paint = (q) => {
      const s = q.trim().toLowerCase();
      list.innerHTML = cats.filter((c) => !s || c.title.toLowerCase().includes(s)).map((c) => `<button type="button" data-c="${esc(c.id)}" dir="auto">${esc(c.title)}</button>`).join("");
    };
    paint("");
    const close = () => pane.remove();
    pane.querySelector(".cn-x").onclick = close;
    pane.onclick = (e) => {
      if (e.target === pane) return close();
      const b = e.target.closest("button[data-c]");
      if (!b) return;
      close();
      openCategory(cats.find((c) => c.id === b.dataset.c), media, cats);
    };
    pane.querySelector("input").oninput = (e) => paint(e.target.value);
    pane.addEventListener("keydown", (e) => e.key === "Escape" && close());
    root.appendChild(pane);
    pane.querySelector("input").focus();
  }
  async function openCategory(cat, media, cats) {
    if (!cat) return;
    state.cat[account() + "|" + media] = cat;
    if (cats) paintTabs(cats, cat, media);
    else tabs.querySelectorAll("button[data-c]").forEach((b) => b.classList.toggle("on", b.dataset.c === cat.id));
    const gen = ++state.gen;
    state.items = [];
    state.page = 0;
    state.more = true;
    state.loading = false;
    const grid = main.querySelector(".cn-grid");
    grid.innerHTML = "";
    main.querySelector(".cn-grid-h h3").textContent = cat.title;
    main.querySelector(".cn-grid-h small").textContent = "";
    const head = main.querySelector(".cn-head");
    if (head) {
      head.querySelector("h2").textContent = cat.title;
      head.querySelector("small").textContent = "";
    }
    main.scrollTop = 0;
    root.classList.remove("cn-compact");
    await more(cat, media, gen);
    const first = state.items[0];
    if (first && media !== "itv" && gen === state.gen) showHero(first, media, { buttons: true, kick: cat.title.toUpperCase() });
  }
  async function more(cat, media, gen) {
    if (state.loading || !state.more || gen !== state.gen) return;
    state.loading = true;
    const box = main.querySelector(".cn-more");
    if (box) box.innerHTML = '<i class="cn-spin"></i>';
    try {
      const j = await api("items?account=" + enc(account()) + "&type=" + media + "&category=" + enc(cat.id) + "&title=" + enc(cat.title) + "&page=" + (state.page + 1));
      if (gen !== state.gen) return;
      const items = j.items || [];
      state.page++;
      state.more = !!j.has_next;
      state.items.push(...items);
      const grid = main.querySelector(".cn-grid");
      items.forEach((it) => grid.appendChild(poster(it, media)));
      const total = Number(j.total) || state.items.length;
      const label = total + " " + (media === "itv" ? "channels" : media === "vod" ? "movies" : "series");
      main.querySelector(".cn-grid-h small").textContent = label;
      const head = main.querySelector(".cn-head small");
      if (head) head.textContent = label;
      if (!state.items.length) grid.innerHTML = '<p class="cn-none">Nothing in this folder.</p>';
    } catch (e) {
      if (gen === state.gen && box) box.innerHTML = `<button type="button" class="cn-btn g">Try again</button>`;
      const b = box && box.querySelector("button");
      if (b) b.onclick = () => more(cat, media, gen);
      state.loading = false;
      return;
    } finally {
      if (gen === state.gen) state.loading = false;
    }
    if (box) box.innerHTML = "";
    near();
  }
  function near() {
    if (!main || state.view === "details" || state.view === "home") return;
    if (main.scrollTop + main.clientHeight > main.scrollHeight - 900) {
      const key = account() + "|" + state.media;
      more(state.cat[key], state.media, state.gen);
    }
  }

  /* ------------------------------------------------------------ one title */
  function openDetails(row, media) {
    state.detail = { row, media, back: state.view, scroll: main.scrollTop, html: null };
    const keep = document.createElement("div");
    keep.className = "cn-keep";
    while (main.firstChild) keep.appendChild(main.firstChild);
    state.detail.keep = keep;
    state.detail.tabs = tabs.innerHTML;
    state.view = "details";
    state.gen++;
    mark();
    tabs.innerHTML = `<button type="button" class="cn-backb">${ic("back")}Back</button>`;
    tabs.querySelector(".cn-backb").onclick = back;
    main.scrollTop = 0;
    main.innerHTML = heroHtml(true).replace("cn-hero", "cn-hero cn-full") + (media === "series" ? '<section class="cn-eps"><div class="cn-seasons"></div><div class="cn-strip cn-eplist"></div></section>' : "");
    showHero(row, media, { buttons: true, details: true });
    if (media === "series") seasons(row);
  }
  function back() {
    const d = state.detail;
    if (!d) return go("home", true);
    state.view = d.back;
    state.gen++;
    main.innerHTML = "";
    while (d.keep.firstChild) main.appendChild(d.keep.firstChild);
    tabs.innerHTML = d.tabs;
    // the tab buttons lost their handlers with innerHTML: paint them again
    if (d.back === "vod" || d.back === "series" || d.back === "live") {
      const media = d.back === "live" ? "itv" : d.back;
      categories(media).then((cats) => paintTabs(cats, state.cat[account() + "|" + media] || cats[0], media)).catch(() => {});
    }
    mark();
    main.scrollTop = d.scroll;
    state.detail = null;
    if (state.hero && main.querySelector(".cn-hero")) showHero(state.hero.row, state.hero.media, { buttons: true });
  }
  function heroButtons(row, media) {
    const box = main.querySelector(".cn-acts");
    if (!box) return;
    const acc = account();
    const cont = get(CONT, []).find((x) => x.account === acc && x.key === (media === "vod" ? "m|" : "s|") + nice(row.raw_title || row.title));
    const inDetails = state.view === "details";
    const playLabel = cont ? (media === "series" && cont.code ? "Continue " + cont.code : "Continue") : media === "series" ? "Play" : "Play";
    box.innerHTML =
      `<button type="button" class="cn-btn p" data-b="play">${ic("play")}${esc(playLabel)}</button>` +
      (inDetails ? "" : `<button type="button" class="cn-btn g" data-b="more">${ic("info")}${media === "series" ? "Episodes" : "Details"}</button>`) +
      `<button type="button" class="cn-btn g ${row.favorite ? "on" : ""}" data-b="fav">${ic(row.favorite ? "check" : "plus")}My list</button>`;
    box.querySelector('[data-b="play"]').onclick = async () => {
      if (media === "vod") return play(row, { media });
      if (cont && cont.series) {
        revive(cont.entries);
        try {
          const j = await api("episodes?series=" + enc(cont.series.id) + "&season=" + enc(cont.season.id));
          const eps = j.episodes || [];
          return play(eps.find((e) => e.id === cont.ep.id) || cont.ep, { media, series: cont.series, season: cont.season, episodes: eps });
        } catch (_) {}
      }
      // the first episode of the first season
      try {
        const s = (await api("seasons?item=" + enc(row.id))).seasons || [];
        if (!s.length) return openDetails(row, media);
        const j = await api("episodes?series=" + enc(row.id) + "&season=" + enc(s[0].id));
        const eps = j.episodes || [];
        if (eps.length) play(eps[0], { media, series: row, season: s[0], episodes: eps });
      } catch (_) {
        openDetails(row, media);
      }
    };
    const m = box.querySelector('[data-b="more"]');
    if (m) m.onclick = () => openDetails(row, media);
    const f = box.querySelector('[data-b="fav"]');
    f.onclick = async () => {
      f.disabled = true;
      try {
        const r = await fetch("api/browse/favorite", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item: row.id }) });
        const j = await r.json();
        if (r.ok) {
          row.favorite = !!j.favorite;
          f.classList.toggle("on", row.favorite);
          f.innerHTML = ic(row.favorite ? "check" : "plus") + "My list";
        }
      } catch (_) {}
      f.disabled = false;
    };
  }
  async function seasons(series) {
    const gen = state.gen;
    const box = main.querySelector(".cn-seasons");
    const list = main.querySelector(".cn-eplist");
    box.innerHTML = '<i class="cn-spin"></i>';
    let s;
    try {
      s = (await api("seasons?item=" + enc(series.id))).seasons || [];
    } catch (e) {
      if (gen === state.gen) box.innerHTML = `<span class="cn-none">${esc(e.message)}</span>`;
      return;
    }
    if (gen !== state.gen) return;
    if (!s.length) return (box.innerHTML = '<span class="cn-none">No episodes yet.</span>');
    const meta = main.querySelector(".cn-meta");
    if (meta && !/Season/.test(meta.textContent)) {
      const tag = document.createElement("span");
      tag.textContent = s.length + (s.length === 1 ? " Season" : " Seasons");
      const y = [...meta.children].find((x) => /^\d{4}$/.test(x.textContent.trim()));
      if (y) y.after(tag);
      else meta.appendChild(tag);
    }
    const acc = account();
    const cont = get(CONT, []).find((x) => x.account === acc && x.key === "s|" + nice(series.raw_title || series.title));
    let at = cont ? Math.max(0, s.findIndex((x) => x.id === (cont.season && cont.season.id))) : 0;
    box.innerHTML = s.map((x, i) => `<button type="button" data-i="${i}" class="${i === at ? "on" : ""}">${esc(x.title || "Season " + x.number)}${x.episode_count ? `<small>${x.episode_count}</small>` : ""}</button>`).join("");
    const show = async (i) => {
      at = i;
      box.querySelectorAll("button").forEach((b) => b.classList.toggle("on", +b.dataset.i === i));
      list.innerHTML = '<i class="cn-spin"></i>';
      let eps;
      try {
        eps = (await api("episodes?series=" + enc(series.id) + "&season=" + enc(s[i].id))).episodes || [];
      } catch (e) {
        if (gen === state.gen) list.innerHTML = `<span class="cn-none">${esc(e.message)}</span>`;
        return;
      }
      if (gen !== state.gen || at !== i) return;
      const still = backdrop(series.id) || art(series.id, "series");
      list.innerHTML = "";
      eps.forEach((e) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "cn-ep" + (cont && cont.ep && cont.ep.id === e.id ? " last" : "");
        const n = Number(e.episode) || 1;
        const title = String(e.title || "").trim();
        b.innerHTML =
          `<span class="cn-pic">${still ? `<img loading="lazy" alt="" src="${esc(still)}">` : ""}</span>` +
          `<span class="cn-ep-n">E${String(n).padStart(2, "0")}</span>` +
          `<span class="cn-ep-t" dir="auto">${esc(/^episode\s*\d+$/i.test(title) ? "Episode " + n : title || "Episode " + n)}</span>` +
          (cont && cont.ep && cont.ep.id === e.id ? `<span class="cn-prog"><i style="width:${Math.round(Math.max(0.03, cont.p || 0) * 100)}%"></i></span>` : "") +
          `<span class="cn-wide-play">${ic("play")}</span>`;
        b.onclick = () => play(e, { media: "series", series, season: s[i], episodes: eps });
        list.appendChild(b);
      });
      const last = list.querySelector(".cn-ep.last");
      if (last) last.scrollIntoView({ inline: "center", block: "nearest" });
    };
    box.querySelectorAll("button").forEach((b) => (b.onclick = () => show(+b.dataset.i)));
    show(at);
  }

  /* ------------------------------------------------------------ search and favorites */
  function search() {
    main.innerHTML = `<section class="cn-search"><div class="cn-sbox">${ic("search")}<input type="search" placeholder="Search movies and series" autocomplete="off"></div><div class="cn-rows"></div></section>`;
    const input = main.querySelector("input");
    const rows = main.querySelector(".cn-rows");
    let t = 0;
    input.oninput = () => {
      clearTimeout(t);
      t = setTimeout(run, 450);
    };
    async function run() {
      const q = input.value.trim();
      const gen = ++state.gen;
      if (q.length < 2) return (rows.innerHTML = "");
      rows.innerHTML = '<i class="cn-spin"></i>';
      const j = await api("search?account=" + enc(account()) + "&q=" + enc(q) + "&mode=full&limit=80").catch((e) => ({ error: e.message }));
      if (gen !== state.gen) return;
      rows.innerHTML = "";
      const groups = (j && j.groups) || [];
      if (!groups.length) return (rows.innerHTML = `<p class="cn-none">${esc(j.error || "Nothing found for “" + q + "”.")}</p>`);
      for (const m of ["series", "vod"]) {
        const g = groups.filter((x) => x.media_type === m);
        if (!g.length) continue;
        const r = row(m === "series" ? "Series" : "Movies", g.length + "");
        g.forEach((x) => r.querySelector(".cn-strip").appendChild(poster((x.copies && x.copies[0]) || { id: x.poster_item, title: x.title }, m)));
        rows.appendChild(r);
      }
    }
    setTimeout(() => input.focus(), 50);
  }
  async function favorites() {
    const gen = state.gen;
    main.innerHTML = '<section class="cn-head"><h2>Favorites</h2><small>Your saved channels, movies and series</small></section><div class="cn-rows"></div>';
    const rows = main.querySelector(".cn-rows");
    let any = false;
    for (const [m, t] of [["series", "Series"], ["vod", "Movies"], ["itv", "Channels"]]) {
      const j = await api("favorites?account=" + enc(account()) + "&type=" + m).catch(() => null);
      if (gen !== state.gen) return;
      const items = (j && j.items) || [];
      if (!items.length) continue;
      any = true;
      const r = row(t, items.length + "");
      items.forEach((it) => r.querySelector(".cn-strip").appendChild(poster(it, m)));
      rows.appendChild(r);
    }
    if (!any) rows.innerHTML = '<p class="cn-none">Nothing saved yet. Use “My list” on a movie or a series.</p>';
  }

  /* ------------------------------------------------------------ the grid shrinks the picture when you scroll */
  function wire() {
    main.addEventListener("scroll", () => {
      root.classList.toggle("cn-compact", main.scrollTop > 60 && state.view !== "details" && state.view !== "home");
      near();
    }, { passive: true });
  }

  /* ------------------------------------------------------------ start */
  function start() {
    const tryBtn = () => classicButton() || setTimeout(tryBtn, 500);
    tryBtn();
    if (!isOn()) return;
    document.documentElement.classList.add("us-cine");
    enter("home");
  }
  window.usCinema = { on: () => turn(true), off: () => turn(false), go: (v) => go(v, true) };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
