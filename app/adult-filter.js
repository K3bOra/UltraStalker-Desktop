/* Ultra Stalker for Windows — no adult content.

   Adult ("+18", XXX, censored) categories, channels, movies and series are removed
   everywhere the program lists things: categories, items (also inside "All"), search,
   favorites — and such an item can't be played even from an old link.
   The bundle embeds this file inside the interface's engine (bundle/web/engine.js) and
   calls installAdultFilter() with the engine's API table. */

const ADULT_WORDS = [
  /(^|[^\p{L}\p{N}])(adults?|adulte?s?|adultos?|adulti|xxx+|porn\w*|p0rn\w*|sex|sexy|sexo|erotic\w*|erotik\w*|erotique|érotique|nsfw|hentai|milfs?|playboy|penthouse|hustler|brazzers|dorcel|redlight|red light|x-?rated|onlyfans|only fans|nude|nudes|xvideos?|xhamster|pornhub|bangbros|naughty|camgirls?|blue movies?|erwachsene|yeti[sş]kin|v[iı]vid ?(tv|red)|private (tv|spice|gold)|spice ?tv|venus ?tv|dusk ?tv|babes ?tv|hot ?club|night ?club tv)(?=$|[^\p{L}\p{N}])/iu,
  /(^|[^\d])18\s*\+|\+\s*18(?!\d)|\[\s*18\s*\]|\(\s*18\s*\)|(^|[^\p{L}\p{N}])18\s*plus(?=$|[^\p{L}\p{N}])/iu,
  // Arabic, Persian, Russian
  /سكس|[إا]باحي|للكبار|للبالغين|كبار فقط|بزرگسال|سکس|для взрослых|эрот|порн|секс/iu,
];

export function adultText(text) {
  const t = String(text || "").normalize("NFKC");
  if (!t.trim()) return false;
  return ADULT_WORDS.some((re) => re.test(t));
}

/* A provider row (channel, movie, series): the provider's own "censored" flag, its name
   or its group. */
export function adultRow(row) {
  if (!row || typeof row !== "object") return false;
  const c = row.censored;
  if (c === true || c === 1 || String(c ?? "").trim() === "1") return true;
  for (const k of ["name", "title", "o_name", "_raw_name", "genre", "category", "category_name", "genre_name", "group", "group_title", "tv_genre_title", "genres_str"]) {
    const v = row[k];
    if (typeof v === "string" && adultText(v)) return true;
  }
  return false;
}

export function installAdultFilter({ API, q, cached, WebError }) {
  // account|media → ids of the adult categories seen there
  const hidden = new Map();
  const IDS = ["category_id", "genre_id", "tv_genre_id", "_xtream_category_id", "category"];
  const keyOf = (url, media) => q(url, "account") + "|" + (media || q(url, "type"));
  function entryOf(id) {
    try {
      return cached(id);
    } catch (_) {
      return null;
    }
  }
  function adultItem(item, key) {
    if (!item) return false;
    if (adultText(item.title) || adultText(item.raw_title)) return true;
    const e = entryOf(item.id);
    if (!e) return false;
    if (adultRow(e.item) || adultText(e.category_title)) return true;
    const bad = hidden.get(key || e.account + "|" + e.media);
    if (bad && bad.size && e.item) {
      for (const k of IDS) {
        const v = e.item[k];
        if (v !== undefined && v !== null && v !== "" && bad.has(String(v))) return true;
      }
    }
    if (bad && bad.size && e.category && bad.has(String(e.category))) return true;
    // an episode or season: judge the series it belongs to
    if (e.parent && e.parent !== item.id) {
      const p = entryOf(e.parent);
      if (p && (adultRow(p.item) || adultText(p.category_title))) return true;
    }
    return false;
  }
  function wrap(name, after, before) {
    const orig = API[name];
    if (!orig) return;
    API[name] = async (url, body) => {
      if (before) await before(url, body);
      return after(await orig(url, body), url, body);
    };
  }
  // categories: drop the adult ones and remember them for the item lists
  async function categoriesFor(url, media) {
    const key = keyOf(url, media);
    if (hidden.has(key) || !API["browse/categories"]) return;
    const u = new URL(url.href);
    u.searchParams.set("type", media);
    await API["browse/categories"](u).catch(() => null);
  }
  wrap("browse/categories", (out, url) => {
    if (!out || !Array.isArray(out.categories)) return out;
    const bad = new Set();
    out.categories = out.categories.filter((c) => {
      const no = !!c.censored || adultText(c.title) || adultText(c.name);
      if (no) bad.add(String(c.id));
      return !no;
    });
    out.categories.forEach((c) => delete c.censored);
    out.count = out.categories.length;
    hidden.set(keyOf(url), bad);
    return out;
  });
  wrap(
    "browse/items",
    (out, url) => {
      if (!out || !Array.isArray(out.items)) return out;
      const key = keyOf(url);
      const bad = hidden.get(key);
      const cat = q(url, "category");
      if ((bad && cat && bad.has(cat)) || adultText(q(url, "title"))) {
        out.items = [];
        out.has_next = false;
      } else out.items = out.items.filter((i) => !adultItem(i, key));
      out.count = out.items.length;
      return out;
    },
    // "All" and remembered categories can be opened before the category list was read
    (url) => categoriesFor(url, q(url, "type")),
  );
  wrap("browse/search", (out, url) => {
    if (!out || !Array.isArray(out.groups)) return out;
    const acc = q(url, "account");
    out.groups = out.groups
      .map((g) => Object.assign(g, { copies: (g.copies || []).filter((c) => !adultItem(c, acc + "|" + (c.media_type || g.media_type))) }))
      .filter((g) => g.copies.length && !adultText(g.title) && !adultText(g.raw_title));
    out.groups.forEach((g) => {
      g.copy_count = g.copies.length;
      if (!g.copies.some((c) => c.id === g.poster_item)) g.poster_item = g.copies[0].id;
    });
    out.count = out.groups.length;
    out.copy_count = out.groups.reduce((n, g) => n + g.copy_count, 0);
    out.buckets = { vod: out.groups.filter((g) => g.media_type === "vod").length, series: out.groups.filter((g) => g.media_type === "series").length };
    if (!out.groups.length) out.matched_portals = 0;
    return out;
  });
  wrap("browse/favorites", (out) => {
    if (!out || !Array.isArray(out.items)) return out;
    out.items = out.items.filter((i) => !adultItem(i));
    out.count = out.items.length;
    return out;
  });
  for (const name of ["browse/seasons", "browse/episodes"]) {
    wrap(name, (out, url) => {
      const e = entryOf(q(url, "item") || q(url, "series"));
      if (e && (adultRow(e.item) || adultText(e.category_title))) throw new WebError("Not available", 404);
      return out;
    });
  }
  // nothing adult plays, even from an old link or a remembered favourite
  for (const name of ["browse/prepare", "browse/vlc", "browse/details"]) {
    const orig = API[name];
    if (!orig) continue;
    API[name] = async (url, body) => {
      const id = q(url, "item");
      if (id && adultItem({ id })) throw new WebError("This isn't available in Ultra Stalker.", 404);
      return orig(url, body);
    };
  }
}
