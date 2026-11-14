/* Development-only stand-in for the Python bridge (used when the page runs in a normal browser). */
(function () {
  const hues = [[150, 350], [200, 20], [20, 160], [280, 40], [340, 190], [45, 210], [170, 300], [0, 120]];
  const svg = (w, hgt, title, k, sub) => {
    const [a, b] = hues[k % hues.length];
    const s = `<svg xmlns='http://www.w3.org/2000/svg' width='${w}' height='${hgt}' viewBox='0 0 ${w} ${hgt}'>
      <defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='hsl(${a},55%,30%)'/><stop offset='1' stop-color='hsl(${b},60%,14%)'/></linearGradient>
      <radialGradient id='r' cx='.7' cy='.25' r='.7'><stop offset='0' stop-color='hsla(${a},80%,70%,.55)'/><stop offset='1' stop-color='transparent'/></radialGradient></defs>
      <rect width='100%' height='100%' fill='url(#g)'/><rect width='100%' height='100%' fill='url(#r)'/>
      <circle cx='${w * 0.3}' cy='${hgt * 0.62}' r='${w * 0.42}' fill='hsla(${b},50%,8%,.55)'/>
      <text x='50%' y='${sub ? hgt * 0.8 : hgt * 0.84}' text-anchor='middle' font-family='Arial Black,Arial' font-weight='900' font-size='${w / 9}' fill='white' letter-spacing='1'>${title.toUpperCase().slice(0, 16)}</text>
      ${sub ? `<text x='50%' y='${hgt * 0.88}' text-anchor='middle' font-family='Arial' font-size='${w / 18}' fill='rgba(255,255,255,.75)'>${sub}</text>` : ""}</svg>`;
    return "data:image/svg+xml;utf8," + encodeURIComponent(s);
  };
  const logo = (name, k) => {
    const [a] = hues[k % hues.length];
    const s = `<svg xmlns='http://www.w3.org/2000/svg' width='120' height='80'><rect x='6' y='10' width='108' height='60' rx='12' fill='hsl(${a},65%,38%)'/><text x='60' y='50' text-anchor='middle' font-family='Arial Black,Arial' font-size='22' fill='white'>${name}</text></svg>`;
    return "data:image/svg+xml;utf8," + encodeURIComponent(s);
  };
  const face = (k) => {
    const s = `<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'><rect width='100' height='100' fill='hsl(${(k * 47) % 360},30%,35%)'/><circle cx='50' cy='40' r='18' fill='hsl(30,40%,${55 + (k % 3) * 8}%)'/><ellipse cx='50' cy='92' rx='34' ry='26' fill='hsl(${(k * 91) % 360},35%,25%)'/></svg>`;
    return "data:image/svg+xml;utf8," + encodeURIComponent(s);
  };
  const MOV = ["Homestead", "Hudson & Rex", "Conan", "Made in Chelsea", "High Country", "Babylon Berlin", "Heartland", "Suits", "Shooter", "All American", "Dune Part Two", "The Batman", "Oppenheimer", "Gladiator II", "Wicked", "Heart of the Beast", "Paddington", "Interstellar", "Inception", "Tenet", "Top Gun", "Joker", "Arrival", "Sicario", "Prisoners", "El Hareef", "Kira & El Gin", "Welad Rizk", "El Fil El Azraq", "Mafia"];
  const CH = ["beIN SPORTS 1", "beIN SPORTS 2", "beIN SPORTS 3", "SKY SPORT NEWS", "SKY SPORT F1", "SKY SPORT GOLF", "TNT SPORT 1", "TNT SPORT 2", "MBC 1", "MBC 2", "MBC MASR", "ON E", "CBC", "AL JAZEERA", "AL ARABIYA", "BBC ONE", "BBC TWO", "CNN", "NAT GEO", "DISCOVERY", "CARTOON NETWORK", "SPACETOON"];
  const cats = {
    live: ["UNITED KINGDOM", "SPORTS 8K", "beIN SPORTS", "ARABIC", "EGYPT", "NEWS", "DOCUMENTARY", "KIDS", "MUSIC", "FRANCE", "GERMANY", "TURKEY"].map((x, i) => ({ id: "l" + i, title: x })),
    movies: ["EN| NEW RELEASES 4K", "AR| أفلام عربي", "EN| ACTION", "EN| DRAMA", "NETFLIX", "APPLE+ MOVIES 4K", "KIDS", "EN| COMEDY"].map((x, i) => ({ id: "m" + i, title: x })),
    series: ["EN| ENGLISH SERIES", "AR| مسلسلات عربي", "TURKISH", "NETFLIX SERIES", "RAMADAN 2026"].map((x, i) => ({ id: "s" + i, title: x })),
  };
  const items = {};
  const mk = (kind, cat, n) => {
    const key = kind + "|" + cat; if (items[key]) return items[key];
    const rows = [];
    for (let i = 0; i < n; i++) {
      const k = (i * 7 + cat.length * 3) % 30;
      if (kind === "live") { const name = CH[(i + cat.length) % CH.length] + (i >= CH.length ? " HD" : ""); rows.push({ ref: `${key}|${i}`, title: name, kind, poster: logo(name.split(" ")[0].slice(0, 6), i), number: String(i + 1), epg: i % 4 !== 3 }); }
      else { const title = MOV[k] + (i >= 30 ? " " + (i + 1) : ""); rows.push({ ref: `${key}|${i}`, title, kind, poster: svg(300, 450, MOV[k], k, kind === "series" ? "THE SERIES" : ""), year: String(2008 + (k % 18)), rating: (5.5 + (k % 9) * 0.4).toFixed(1), description: "" }); }
    }
    return (items[key] = rows);
  };
  const all = (kind) => cats[kind].flatMap((c) => mk(kind, c.id, kind === "live" ? 40 : 48));
  const byRef = (ref) => { const [kind] = ref.split("|"); return all(kind).find((x) => x.ref === ref) || Object.values(items).flat().find((x) => x.ref === ref); };
  let profiles = new URLSearchParams(location.search).get('noprof') ? [] : [
    { name: "Ahmed HadarY", type: "stalker", host: "portal.example.tv:8080", mac: "00:1A:79:••:••:4C", user: "" },
    { name: "Xtream Gold", type: "xtream", host: "gold.example.net", mac: "", user: "ahmed" },
    { name: "My M3U", type: "m3u", host: "lists.example.org", mac: "", user: "" },
  ];
  let connected = { name: "Ahmed HadarY", type: "stalker", host: "portal.example.tv:8080" };
  const fav = new Set();
  const settings = { ui_language: new URLSearchParams(location.search).get("lang") || "ar", tmdb_language: "en", player: "mpv", live_preview: true };
  const now = () => Math.floor(Date.now() / 1000);
  const H = {
    hello: () => ({ version: "0.2.0", author: "Ahmed L-HadarY", settings, has_tmdb_key: false, profiles, connected: new URLSearchParams(location.search).get("noconn") ? null : connected }),
    profiles: () => profiles,
    profile: (n) => { const p = profiles.find((x) => x.name === n); return { name: p.name, type: p.type, url: "http://" + p.host + "/c/", mac: "00:1A:79:12:34:4C", username: p.user, has_password: p.type === "xtream" }; },
    profile_save: (d) => { profiles = profiles.filter((p) => p.name !== d.original); profiles.push({ name: d.name || "Source", type: d.type, host: d.url.replace(/^https?:\/\//, "").split("/")[0], mac: d.mac, user: d.username }); connected = { name: d.name, type: d.type, host: "x" }; return { saved: true, connected, profiles }; },
    profile_delete: (n) => (profiles = profiles.filter((p) => p.name !== n)),
    connect: (n) => (connected = { name: n, type: "stalker", host: profiles.find((p) => p.name === n).host }),
    categories: (k) => cats[k],
    items: (k, c) => (c ? mk(k, c, k === "live" ? 40 : 48) : all(k)),
    details: (ref) => {
      const x = byRef(ref); if (!x) throw new Error("gone"); const k = parseInt(ref.split("|").pop(), 10) || 0;
      if (x.kind === "live") return x;
      return Object.assign({}, x, {
        backdrop: svg(1280, 720, "", k + 2), favorite: fav.has(ref),
        description: "After a nuclear bomb detonates off the coast of Los Angeles, a once-pampered nation devolves into brutal chaos. The survivors within the Homestead clash over how to protect what is left.",
        resume: k % 5 === 1 ? { position: 1800, duration: 6000, label: "30:00 / 1:40:00" } : undefined,
        tmdb: { title: x.title, tagline: k % 2 ? "Every family has a price." : "", rating: 7.0 + (k % 3) / 10, year: x.year, runtime: x.kind === "movies" ? 101 + k : 0, seasons: x.kind === "series" ? 2 + (k % 4) : 0, episodes: x.kind === "series" ? 9 + k : 0,
          genres: ["Drama", "Action & Adventure", "Sci-Fi & Fantasy"].slice(0, 2 + (k % 2)), countries: ["United States"], language: "EN", certification: "+14",
          trailer: "https://www.youtube.com/watch?v=x", cast: ["Jacq Reynolds", "Jenna Ross", "Charles Esten", "Bailey Chase", "Neal McDonough", "Dawn Olivieri"].map((n, i) => ({ name: n, role: ["Jacq", "Jenna", "Cain Ross", "Jeff Eriksson", "Ty", "Ruth"][i], photo: face(i + k) })) },
      });
    },
    episodes: (ref) => ({
      seasons: [1, 2, 3].map((s) => ({ season: s, episodes: Array.from({ length: 8 }, (_, i) => { const e = { ref: ref + `|S${s}E${i + 1}`, title: `Episode ${i + 1}`, kind: "episode", season: s, episode: i + 1, watched: s === 1 || (s === 2 && i < 3) }; return e; }) })),
      next: ref + "|S2E4",
    }),
    epg: (ref) => { const t0 = now() - 1500; return { now: now(), rows: ref.endsWith("|3") ? [] : [{ title: "Sports Sunday", start: t0, end: t0 + 3600, description: "Live coverage and analysis from the weekend's biggest matches." }, { title: "Premier League Highlights", start: t0 + 3600, end: t0 + 7200 }] }; },
    search: (q) => { q = q.toLowerCase(); const f = (k) => all(k).filter((x) => x.title.toLowerCase().includes(q)).slice(0, 30); return { live: f("live"), movies: f("movies"), series: f("series") }; },
    favorite: (ref) => { fav.has(ref) ? fav.delete(ref) : fav.add(ref); return { favorite: fav.has(ref) }; },
    favorites: () => { const out = { live: [], movies: [], series: [] }; [...fav].map(byRef).filter(Boolean).forEach((x) => out[x.kind].push(x)); if (!fav.size) { out.movies = mk("movies", "m0", 48).slice(3, 9); out.live = mk("live", "l1", 40).slice(0, 5); } return out; },
    history: () => [...mk("movies", "m0", 48).slice(0, 5).map((x, i) => Object.assign({}, x, { percent: 20 + i * 15, progress: "30:00" })), ...mk("series", "s0", 48).slice(2, 5).map((x, i) => Object.assign({}, x, { percent: 50 + i * 10 })), ...mk("live", "l2", 40).slice(0, 6)],
    settings_save: (d) => Object.assign(settings, d),
    clear_cache: () => true, disconnect: () => { connected = null; return true; },
    play: () => ({ started: true }), preview: () => ({ started: true }),
    ui_preview_rect: () => true, ui_stop_preview: () => true, ui_fullscreen: () => true, ui_open_url: () => true,
  };
  const listeners = [];
  window.MockBridge = {
    reply: { connect: (fn) => listeners.push(fn) },
    push: { connect: () => {} },
    call(text) {
      const m = JSON.parse(text); const fn = H[m.method];
      setTimeout(() => {
        let out; try { out = { id: m.id, ok: true, data: fn ? fn(...m.args) : null }; } catch (e) { out = { id: m.id, ok: false, error: e.message }; }
        listeners.forEach((l) => l(JSON.stringify(out)));
      }, m.method === "details" ? 120 : 40);
    },
  };
})();
