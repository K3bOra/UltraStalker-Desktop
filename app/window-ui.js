/* Ultra Stalker for Windows: the window's own buttons in the gold top bar
   (minimise · full screen / window · close). The program has no Windows frame. */
(function () {
  const W = window.usNative && window.usNative.win;
  if (!W) return;
  // The program's own version where the website shows its own (drawer, footer).
  const appVersion = (window.US_APP && window.US_APP.version) || "";
  function showVersion() {
    if (!appVersion) return;
    const label = "Program · V" + appVersion;
    const v = document.getElementById("dkVer");
    if (v && v.textContent !== label) v.textContent = label;
    document.querySelectorAll(".footer").forEach((f) => {
      if (/Web · V/.test(f.textContent)) f.innerHTML = "<b>Ultra Stalker</b> · " + label;
    });
  }
  // the page writes its own version once the drawer is built: put ours back then
  let tries = 0;
  const keep = setInterval(() => {
    showVersion();
    if (++tries > 20) clearInterval(keep);
  }, 500);
  document.addEventListener("DOMContentLoaded", showVersion);
  // the clear top bar gets a shade once the page scrolls under it
  const scrolled = () => document.body && document.body.classList.toggle("us-scrolled", window.scrollY > 24);
  window.addEventListener("scroll", scrolled, { passive: true });
  document.addEventListener("DOMContentLoaded", scrolled);
  // A section change uses the current source. Keep the items stage (and its
  // three tabs) on screen while the shared browser loads the new categories.
  async function switchSection(event) {
    const tab = event.target.closest("#dkTvCats .dk-secseg button[data-go]");
    if (!tab) return;
    const byId = (id) => document.getElementById(id);
    const account = byId("browseAccount").value;
    if (!account || byId("itemsStage").classList.contains("hidden")) return;
    event.stopPropagation();
    const media = tab.dataset.go;
    const column = tab.closest("#dkTvCats").querySelector(".dk-tvc-body");
    if (media === browseMedia && !column.querySelector(".us-section-retry")) return;

    browseMedia = media;
    syncMediaButtons();
    const loaded = loadCategories(true);
    const generation = categoryGeneration;
    // loadCategories has reset the old item request and history synchronously.
    showItems();
    const items = byId("browseItems");
    items.replaceChildren();
    byId("itemsSummary").textContent = "";
    byId("dkTvFind").value = "";
    byId("dkTvCat").textContent = mediaName(media);
    byId("dkTvCount").textContent = "";
    delete column.dataset.sig;
    const status = document.createElement("p");
    status.className = "us-section-status";
    status.setAttribute("role", "status");
    status.textContent = "Loading " + tab.textContent.trim() + "…";
    column.replaceChildren(status);
    window.scrollTo({ top: 0, behavior: "instant" });

    await loaded;
    if (generation !== categoryGeneration || browseMedia !== media ||
        byId("browseAccount").value !== account || byId("itemsStage").classList.contains("hidden")) return;
    const categories = [...byId("browseCategories").querySelectorAll(".category")];
    if (categories.length) {
      const key = media === "itv" ? "us-web-livecat:" : "us-web-cat:" + media + ":";
      let remembered;
      try { remembered = localStorage.getItem(key + account); } catch (_) {}
      const category = categories.find((el) => (el.dataset.categoryId || "*") === remembered) || categories[0];
      await openCategory({ id: category.dataset.categoryId || "*", title: category.title }, false);
      return;
    }
    // Empty libraries and provider errors stay in the frame and can be retried.
    const empty = byId("browseCategories").querySelector(".empty");
    const summary = byId("browseStatus").textContent;
    status.textContent = /^0 categories/.test(summary) ? empty?.textContent || "No categories returned." : summary;
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "us-section-retry";
    retry.textContent = "Try again";
    retry.onclick = () => tab.click();
    column.replaceChildren(retry);
    // A non-empty wall suppresses the poster placeholders when loading is over.
    items.replaceChildren(status);
  }
  document.addEventListener("click", switchSection, true);

  // The desktop auto-opens categories without pushing a history entry. Mark
  // that entry as the loaded wall before the details page pushes its own entry.
  function rememberWall(event) {
    if (event.type === "keydown" && !["Enter", " "].includes(event.key)) return;
    const card = event.target.closest("body.dk-vg-mode #browseItems .poster-card");
    if (!card || event.target.closest(".favorite-action") || !activeCategory || !history.state?.usBrowse) return;
    history.replaceState({ ...history.state, view: "items", category: { ...activeCategory },
      account: document.getElementById("browseAccount").value, media: browseMedia,
      scrollY: window.scrollY, posterItem: card.dataset.item }, document.title);
  }
  document.addEventListener("click", rememberWall, true);
  document.addEventListener("keydown", rememberWall, true);
  window.addEventListener("popstate", ({state}) => {
    if (state?.view !== "items" || !state.posterItem) return;
    requestAnimationFrame(() => {
      const card = document.querySelector("#browseItems .poster-card[data-item=" + CSS.escape(state.posterItem) + "]");
      card?.focus({ preventScroll: true });
    });
  });

  let storyLanguage = "ar";
  try { if (localStorage.getItem("us-story-language") === "en") storyLanguage = "en"; } catch (_) {}
  const storyObservers = new Map();
  function showTrailer(videoId, title) {
    const dialog = document.createElement("dialog");
    dialog.className = "us-trailer-dialog";
    dialog.setAttribute("aria-label", "Trailer");
    const header = document.createElement("header");
    const heading = document.createElement("strong");
    heading.textContent = title ? "Trailer · " + title : "Trailer";
    heading.dir = "auto";
    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "Close";
    close.autofocus = true;
    close.onclick = () => dialog.close();
    header.append(heading, close);
    const frame = document.createElement("iframe");
    frame.title = heading.textContent;
    frame.setAttribute("credentialless", "");
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-presentation");
    frame.allow = "autoplay; encrypted-media; fullscreen; picture-in-picture";
    frame.allowFullscreen = true;
    frame.referrerPolicy = "strict-origin-when-cross-origin";
    const dismiss = () => dialog.close();
    const offline = document.createElement("p");
    offline.textContent = "تعذّر الاتصال بمشغّل الإعلان.";
    offline.hidden = true;
    frame.onerror = () => { offline.hidden = false; };
    dialog.append(header, frame, offline);
    dialog.addEventListener("close", () => {
      window.removeEventListener("popstate", dismiss);
      dialog.remove();
    }, {once: true});
    window.addEventListener("popstate", dismiss);
    document.body.append(dialog);
    dialog.showModal();
    frame.src = "https://www.youtube-nocookie.com/embed/" + videoId + "?autoplay=1&playsinline=1";
  }
  document.addEventListener("us-details", async ({detail}) => {
    if (!detail || !["vod", "series"].includes(detail.media)) return;
    const series = detail.media === "series";
    const current = () => (series ? activeSeries : activeMovie)?.id === detail.item;
    if (!current()) return;
    const prefix = series ? "series" : "movie";
    const overview = document.getElementById(prefix + "Overview");
    const actions = document.getElementById(prefix + "HeroActions");
    storyObservers.get(prefix)?.disconnect();
    const observer = new MutationObserver(mount);
    storyObservers.set(prefix, observer);
    let payload;
    if (detail.tmdb) {
      payload = await window.USEngine.tmdbGet((series ? "tv/" : "movie/") + detail.tmdb,
        { language: "en-US", append_to_response: "translations,videos" });
    }
    if (!current() || storyObservers.get(prefix) !== observer) return;
    const translations = payload?.translations?.translations || [];
    const textFor = lang => translations.find(row => row.iso_639_1 === lang && row.data?.overview?.trim())?.data.overview.trim() || "";
    const stories = { ar: textFor("ar"), en: textFor("en") || payload?.overview?.trim() || "" };
    const videos = (payload?.videos?.results || []).filter(v => v.site === "YouTube" && v.type === "Trailer" && /^[a-zA-Z0-9_-]{11}$/.test(v.key));
    const trailer = videos.find(v => v.official) || videos[0];
    actions.querySelector(".us-trailer")?.remove();
    if (trailer) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "us-trailer";
      button.textContent = "Trailer";
      button.lang = "en";
      button.setAttribute("aria-haspopup", "dialog");
      button.onclick = () => showTrailer(trailer.key, document.getElementById(prefix + "Title").textContent);
      actions.insertBefore(button, actions.querySelector(".series-season-stack"));
    }
    function mount() {
      if (!current() || overview.classList.contains("episodes-mode") || overview.querySelector(".us-story-head")) return;
      const original = overview.textContent.trim();
      const originalLang = /[\u0600-\u06ff]/.test(original) ? "ar" : "en";
      const head = document.createElement("div");
      head.className = "us-story-head";
      head.innerHTML = '<strong></strong><div role="group" aria-label="لغة القصة"><button type="button" lang="ar" data-lang="ar">العربية</button><button type="button" lang="en" data-lang="en">English</button></div>';
      const copy = document.createElement("p");
      copy.className = "us-story-copy";
      const note = document.createElement("small");
      note.className = "us-story-note";
      function paint() {
        const ar = storyLanguage === "ar";
        const chosen = stories[storyLanguage] || (originalLang === storyLanguage ? original : "");
        const other = stories[ar ? "en" : "ar"] || original;
        head.querySelector("strong").textContent = ar ? "القصة" : "Story";
        head.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.lang === storyLanguage)));
        copy.textContent = chosen || other;
        copy.dir = "auto";
        copy.lang = /[\u0600-\u06ff]/.test(copy.textContent) ? "ar" : "en";
        note.textContent = chosen ? "" : ar ? "الوصف العربي غير متاح لهذا العنوان." : "An English description is unavailable for this title.";
      }
      head.onclick = (e) => {
        const button = e.target.closest("button[data-lang]");
        if (!button) return;
        storyLanguage = button.dataset.lang;
        try { localStorage.setItem("us-story-language", storyLanguage); } catch (_) {}
        paint();
      };
      paint();
      overview.replaceChildren(head, note, copy);
    }
    mount();
    observer.observe(overview, { childList: true });
  });
  const I = {
    min: '<svg viewBox="0 0 24 24"><path d="M6 12.5h12"/></svg>',
    full: '<svg viewBox="0 0 24 24"><path d="M4 9V5a1 1 0 0 1 1-1h4M20 9V5a1 1 0 0 0-1-1h-4M4 15v4a1 1 0 0 0 1 1h4M20 15v4a1 1 0 0 1-1 1h-4"/></svg>',
    window: '<svg viewBox="0 0 24 24"><path d="M9 4v4a1 1 0 0 1-1 1H4M15 4v4a1 1 0 0 0 1 1h4M9 20v-4a1 1 0 0 0-1-1H4M15 20v-4a1 1 0 0 1 1-1h4"/></svg>',
    close: '<svg viewBox="0 0 24 24"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>',
  };
  function add() {
    const right = document.querySelector("#dkBar .dk-bar-right");
    if (!right) return setTimeout(add, 150);
    if (right.querySelector(".usw")) return;
    // The compact title bar hides the text visually; keep the button names.
    for (const button of right.querySelectorAll(".dk-qb")) {
      button.setAttribute("aria-label", button.textContent.trim());
      button.querySelector(".dk-ic")?.setAttribute("aria-hidden", "true");
    }
    const box = document.createElement("div");
    box.className = "usw";
    box.innerHTML =
      `<button type="button" class="dk-bar-icon usw-min" data-a="min" title="Minimise">${I.min}</button>` +
      `<button type="button" class="dk-bar-icon usw-full" data-a="full" title="Full screen (F11)">${I.full}</button>` +
      `<button type="button" class="dk-bar-icon usw-x" data-a="close" title="Close">${I.close}</button>`;
    right.appendChild(box);
    box.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-a]");
      if (b) W.cmd(b.dataset.a);
    });
    const paint = (s) => {
      document.documentElement.classList.toggle("us-full", !!(s && s.full));
      const f = box.querySelector(".usw-full");
      f.innerHTML = s && s.full ? I.window : I.full;
      f.title = s && s.full ? "Window (F11)" : "Full screen (F11)";
    };
    W.onState(paint);
    paint(W.state());
  }
  // Esc leaves the player's full screen (a browser does this by itself; the program must)
  document.addEventListener(
    "keydown",
    (e) => {
      // F11: normally the program catches it first; this is the fallback
      if (e.key === "F11") {
        e.preventDefault();
        W.cmd("full");
        return;
      }
      if (e.key === "Escape" && document.fullscreenElement) {
        e.preventDefault();
        e.stopImmediatePropagation();
        document.exitFullscreen().catch(() => {});
      }
    },
    true
  );
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", add);
  else add();
})();
