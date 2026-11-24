/* Ultra Stalker for Windows — movie and series cards.

   The cards stay the website's own; series also show how many seasons they have (asked
   for the cards on screen, two at a time, remembered for a week), and what you started
   watching shows a thin gold line with how far you got. */
(function () {
  "use strict";
  const QUALITY = /^(8K|4K|UHD|2160P?|FHD|1080P?|HD|720P?|SD|HEVC|H\.?265|X265|3D|HDR10?\+?|DV|DOLBY ?VISION)$/i;
  const LANG = /^(AR|EN|FR|DE|ES|IT|TR|PT|NL|RU|PL|IN|HI|FA|KU|UR|KR|KO|JP|JA|CN|ZH|GR|SE|NO|DK|FI|RO|AL|BG|HR|RS|EX|NF|MULTI|SUB|DUB|VOSTFR|VF|VO)$/i;
  const COUNTRY = /^[A-Z]{2,3}$/;
  const TOKEN = /[A-Za-z0-9.+]{1,12}/g;

  const isQuality = (t) => QUALITY.test(t);
  const isLang = (t) => LANG.test(t);
  const normQ = (t) => {
    const u = t.toUpperCase().replace(/\s+/g, "");
    if (/^(2160P?|UHD)$/.test(u)) return "4K";
    if (/^1080P?$/.test(u)) return "FHD";
    if (/^720P?$/.test(u)) return "HD";
    if (/^(H\.?265|X265)$/.test(u)) return "HEVC";
    if (/^DOLBYVISION$/.test(u)) return "DV";
    return u;
  };

  /* "4K-AR - MobLand (2025) (GB)" → { title: "MobLand", quality: ["4K"], lang: ["AR"], year: "2025", country: "GB" } */
  function parse(raw) {
    let t = String(raw || "").replace(/\s+/g, " ").trim();
    const out = { title: t, quality: [], lang: [], year: "", country: "" };
    if (!t) return out;
    const take = (tokens) => {
      for (const k of tokens) {
        if (isQuality(k)) out.quality.push(normQ(k));
        else if (isLang(k)) out.lang.push(k.toUpperCase());
      }
    };
    // a prefix made only of quality / language codes, then a separator
    for (let i = 0; i < 3; i++) {
      const m = t.match(/^[\[(|]?\s*([A-Za-z0-9.+]{1,12}(?:\s*[-_/| ]\s*[A-Za-z0-9.+]{1,12}){0,3})\s*[\])|]?\s*(?:[-|:•]+\s*|\|\s*)(?=\S)/);
      if (!m) break;
      const tokens = m[1].match(TOKEN) || [];
      if (!tokens.length || !tokens.every((k) => isQuality(k) || isLang(k))) break;
      take(tokens);
      t = t.slice(m[0].length).trim();
    }
    // trailing (2025) (GB) [4K] | AR …
    for (let i = 0; i < 6; i++) {
      const m = t.match(/\s*(?:[(\[]\s*([^()\[\]]{1,24})\s*[)\]]|[|-]\s*([A-Za-z0-9 +.]{2,14}))\s*$/);
      if (!m) break;
      const inner = (m[1] || m[2] || "").trim();
      const tokens = inner.match(TOKEN) || [];
      if (/^(19|20)\d{2}$/.test(inner)) out.year = out.year || inner;
      else if (tokens.length && tokens.every((k) => isQuality(k) || isLang(k))) take(tokens);
      else if (COUNTRY.test(inner) && m[1]) out.country = out.country || inner;
      else break;
      const rest = t.slice(0, t.length - m[0].length).trim();
      if (!rest) break;
      t = rest;
    }
    out.title = t.replace(/[\s\-|:•]+$/, "").trim() || out.title;
    out.quality = [...new Set(out.quality)].slice(0, 2);
    out.lang = [...new Set(out.lang)].slice(0, 2);
    return out;
  }

  window.usCards = { parse };
  if (typeof document === "undefined" || !document.documentElement.classList.contains("us-app")) return;

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const enc = encodeURIComponent;
  const ICON = {
    star: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.8l2.75 5.7 6.25.85-4.55 4.35 1.12 6.2L12 16.9l-5.57 3 1.12-6.2L3 9.35l6.25-.85z"/></svg>',
    seasons: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5l9 4.8-9 4.8-9-4.8z"/><path d="M3.5 12.4L12 17l8.5-4.6"/><path d="M3.5 16.4L12 21l8.5-4.6"/></svg>',
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8.5 6.2v11.6a.9.9 0 0 0 1.37.77l9.1-5.8a.9.9 0 0 0 0-1.54l-9.1-5.8A.9.9 0 0 0 8.5 6.2z"/></svg>',
  };

  /* ------------------------------------------------------------ small memories */
  const store = {
    get(k, d) {
      try {
        const v = JSON.parse(localStorage.getItem(k));
        return v == null ? d : v;
      } catch (_) {
        return d;
      }
    },
    set(k, v) {
      try {
        localStorage.setItem(k, JSON.stringify(v));
      } catch (_) {}
    },
  };
  const account = () => ($("browseAccount") && $("browseAccount").value) || "";
  const keyOf = (title) => account() + "|" + String(title || "").replace(/\s+/g, " ").trim().toLowerCase();

  // season counts, kept for a week (the same series on the same server)
  const SEASONS = "us-desk-season-counts";
  const seasonCounts = store.get(SEASONS, {});
  const WEEK = 7 * 864e5;
  function knownSeasons(k) {
    const v = seasonCounts[k];
    return v && Date.now() - v[1] < WEEK ? v[0] : 0;
  }
  let seasonSave = 0;
  function rememberSeasons(k, n) {
    seasonCounts[k] = [n, Date.now()];
    clearTimeout(seasonSave);
    seasonSave = setTimeout(() => {
      const keys = Object.keys(seasonCounts);
      if (keys.length > 3000) keys.sort((a, b) => seasonCounts[a][1] - seasonCounts[b][1]).slice(0, keys.length - 2500).forEach((x) => delete seasonCounts[x]);
      store.set(SEASONS, seasonCounts);
    }, 800);
  }

  // what you watched: { key: { p: 0..1, ep: "S02E05", at } }
  const WATCH = "us-desk-watching";
  const watched = () => store.get(WATCH, {});

  /* ------------------------------------------------------------ the card */
  const seasonsLabel = (n) => n + (n === 1 ? " Season" : " Seasons");

  function factsOf(card) {
    const f = { rating: "", year: "", age: "", seasons: 0 };
    card.querySelectorAll(".poster-fact").forEach((el) => {
      const v = (el.textContent || "").trim();
      if (el.classList.contains("rating")) f.rating = v;
      else if (el.classList.contains("year")) f.year = v;
      else if (el.classList.contains("age")) f.age = v;
      else if (el.classList.contains("seasons")) f.seasons = parseInt(v, 10) || 0;
    });
    return f;
  }

  // the page's own fact chip, with its seasons icon
  function seasonsFact(n) {
    const el = document.createElement("span");
    el.className = "poster-fact seasons usc-fact" + (n ? "" : " wait");
    el.innerHTML = ICON.seasons + '<span class="poster-fact-text">' + (n ? esc(seasonsLabel(n)) : "") + "</span>";
    return el;
  }

  /* The card stays the website's card (poster, title and facts below it); it only gets
     the season count next to the rating, and a thin gold line for what you started. */
  function enhance(card) {
    if (card.classList.contains("usc") || !card.dataset.item) return;
    const frame = card.querySelector(".poster-frame");
    const copy = card.querySelector(".poster-copy");
    const titleEl = copy && copy.querySelector(".item-title");
    if (!frame || !titleEl) return;
    card.classList.add("usc");
    const raw = (titleEl.textContent || card.title || "").trim();
    card.dataset.uscKey = keyOf(parse(raw).title);
    const series = card.classList.contains("series-result");
    if (series && !factsOf(card).seasons) {
      let facts = copy.querySelector(".poster-facts");
      if (!facts) {
        facts = document.createElement("div");
        facts.className = "poster-facts";
        copy.appendChild(facts);
      }
      const n = knownSeasons(card.dataset.uscKey);
      facts.appendChild(seasonsFact(n));
      if (!n) watchSeasons(card);
    }
    const bar = document.createElement("span");
    bar.className = "usc-bar";
    bar.innerHTML = "<i></i>";
    frame.appendChild(bar);
    progress(card);
  }

  function progress(card) {
    const w = watched()[card.dataset.uscKey];
    const bar = card.querySelector(".usc-bar");
    if (!bar) return;
    card.classList.toggle("usc-watched", !!w);
    if (w) bar.firstChild.style.width = Math.round(Math.min(1, Math.max(0.03, w.p || 0)) * 100) + "%";
  }

  /* ------------------------------------------------------------ season counts (visible cards, two at a time) */
  const waiting = new Set();
  let busy = 0;
  const seen = "IntersectionObserver" in window
    ? new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) waiting.add(e.target);
        else waiting.delete(e.target);
      }
      pump();
    }, { rootMargin: "150px 0px" })
    : null;
  function watchSeasons(card) {
    if (seen) seen.observe(card);
  }
  function pump() {
    for (const card of [...waiting]) {
      if (busy >= 2) return;
      waiting.delete(card);
      seen.unobserve(card);
      if (!card.isConnected) continue;
      busy++;
      fetch("api/browse/season-count?item=" + enc(card.dataset.item), { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((j) => {
          const n = j && Number(j.count);
          const slot = card.querySelector(".usc-fact.wait");
          if (Number.isSafeInteger(n) && n > 0) {
            rememberSeasons(card.dataset.uscKey, n);
            if (slot) slot.replaceWith(seasonsFact(n));
          } else if (slot) slot.remove();
        })
        .catch(() => {
          const slot = card.querySelector(".usc-fact.wait");
          if (slot) slot.remove();
        })
        .finally(() => {
          busy--;
          pump();
        });
    }
  }

  /* ------------------------------------------------------------ remember what plays (the player tells us its time) */
  let playing = null; // { key, ep }
  const has = (n) => typeof window[n] === "function";
  if (has("openPlayerSheet")) {
    const orig = window.openPlayerSheet;
    window.openPlayerSheet = function (row) {
      playing = null;
      try {
        const acc = account();
        // eslint-disable-next-line no-undef
        const series = typeof activeSeries !== "undefined" && activeSeries && row && (row.season || row.episode) ? activeSeries : null;
        if (acc && row) {
          if (series) {
            const ep = Number(row.episode || 0) || 0;
            const code = (row.season ? "S" + String(row.season).padStart(2, "0") : "") + (ep ? "E" + String(ep).padStart(2, "0") : "");
            playing = { key: keyOf(parse(series.title || series.raw_title || "").title), ep: code };
          } else if (row.media_type === "vod") {
            playing = { key: keyOf(parse(row.title || row.raw_title || "").title), ep: "" };
          }
        }
      } catch (_) {}
      return orig.apply(this, arguments);
    };
  }
  setInterval(() => {
    if (!playing || typeof window.usxState !== "function") return;
    const s = window.usxState();
    if (!s || s.live || !(s.d > 60) || !(s.t > 0)) return;
    const all = watched();
    const p = s.t / s.d;
    if (p > 0.95 && !playing.ep) delete all[playing.key];
    else all[playing.key] = { p: +p.toFixed(3), ep: playing.ep, at: Date.now() };
    const keys = Object.keys(all);
    if (keys.length > 500) keys.sort((a, b) => all[a].at - all[b].at).slice(0, keys.length - 400).forEach((x) => delete all[x]);
    store.set(WATCH, all);
    const card = document.querySelector(`#browseItems .poster-card.usc[data-usc-key="${CSS.escape(playing.key)}"]`);
    if (card) progress(card);
  }, 5000);

  /* ------------------------------------------------------------ every card, now and later */
  function scan(root) {
    (root || document).querySelectorAll("#browseItems .poster-card:not(.usc)").forEach(enhance);
  }
  const box = () => $("browseItems");
  function start() {
    const b = box();
    if (!b) return;
    new MutationObserver((list) => {
      for (const m of list) for (const n of m.addedNodes) {
        if (n.nodeType !== 1) continue;
        if (n.classList.contains("poster-card")) enhance(n);
        else if (n.querySelector) n.querySelectorAll(".poster-card:not(.usc)").forEach(enhance);
      }
    }).observe(b, { childList: true, subtree: true });
    scan();
    document.body.classList.add("usc-on");
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
