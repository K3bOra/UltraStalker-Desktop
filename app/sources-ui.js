/* Ultra Stalker for Windows — the Servers & Backup page, laid out for the program.

   The website's page stacks four big panels; here they become one page with a menu:
   a header with the counts, a list of sections on the left (Add · Manage · Import ·
   Backup) and one section at a time on the right. Manage shows the saved servers as a
   list to pick from instead of a drop-down. The page's own forms, buttons and code
   stay as they are — only where they sit changes. */
(function () {
  "use strict";
  if (!document.documentElement.classList.contains("us-app")) return;
  const $ = (id) => document.getElementById(id);
  if (!$("connectionPanel") || !$("managerPanel")) return;

  const SECTIONS = [
    ["connectionPanel", "Add a server", "إضافة سيرفر", "plus"],
    ["managerPanel", "My servers", "سيرفراتي", "servers"],
    ["importPanel", "Import a file", "استيراد ملف", "file"],
    ["backupPanel", "Backup & Restore", "باك اب الرسيفر", "backup"],
  ];
  const ICONS = {
    plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
    servers: '<svg viewBox="0 0 24 24"><rect x="3.5" y="4" width="17" height="6.5" rx="2"/><rect x="3.5" y="13.5" width="17" height="6.5" rx="2"/><path d="M7.5 7.25h.01M7.5 16.75h.01"/></svg>',
    file: '<svg viewBox="0 0 24 24"><path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8z"/><path d="M14 3.5V8h4.5M12 11.5v5M9.5 14l2.5 2.5 2.5-2.5"/></svg>',
    backup: '<svg viewBox="0 0 24 24"><path d="M7 18.5a4.5 4.5 0 0 1-.6-8.96A6 6 0 0 1 18 9.5a4 4 0 0 1-.5 8.97"/><path d="M12 12v8M9 15l3-3 3 3"/></svg>',
    search: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>',
    pick: '<svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h10M4 17h7"/></svg>',
  };
  const esc = (t) => String(t || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function build() {
    if ($("usSrv")) return;
    document.body.classList.add("us-srv-page");
    const main = document.querySelector("main.shell");
    const page = document.createElement("div");
    page.id = "usSrv";
    page.className = "us-srv";
    page.innerHTML =
      '<header class="us-srv-head"><div class="us-srv-title"><small>Servers &amp; Backup · السيرفرات والباك أب</small>' +
      '<h1>Your <span>servers</span></h1><p>Add, edit and import your Stalker, Xtream and M3U servers, and move them to and from the receiver.</p></div>' +
      '<div class="us-srv-stats"><div><b id="usStatAll">—</b><span>Servers · سيرفر</span></div><div><b id="usStatPortal">—</b><span>Stalker</span></div><div><b id="usStatXtream">—</b><span>Xtream / M3U</span></div></div></header>' +
      '<div class="us-srv-body"><nav class="us-srv-nav" aria-label="Sections"></nav><div class="us-srv-stage"></div></div>';
    main.parentNode.insertBefore(page, main);
    const nav = page.querySelector(".us-srv-nav");
    const stage = page.querySelector(".us-srv-stage");
    for (const [id, en, ar, icon] of SECTIONS) {
      const panel = $(id);
      if (!panel) continue;
      const a = document.createElement("a");
      a.href = "#" + id;
      a.dataset.sec = id;
      a.innerHTML = `<i>${ICONS[icon]}</i><span><b>${en}</b><small>${ar}</small></span><em></em>`;
      nav.appendChild(a);
      panel.classList.add("us-srv-sec");
      stage.appendChild(panel);
    }
    const tip = document.createElement("div");
    tip.className = "us-srv-tip";
    tip.innerHTML = "<b>Tip</b> Your servers are kept on this computer. Use <i>Backup &amp; Restore</i> to move them to the receiver.<span>سيرفراتك محفوظة على الكمبيوتر ده، واستخدم الباك أب عشان تنقلها للرسيفر.</span>";
    nav.appendChild(tip);
    manageList();
    counts();
    show(location.hash.slice(1));
  }

  /* one section at a time; the drawer's links and the page's own links lead here too */
  function show(id) {
    if (!SECTIONS.some((s) => s[0] === id)) id = "connectionPanel";
    document.querySelectorAll("#usSrv .us-srv-sec").forEach((p) => p.classList.toggle("on", p.id === id));
    document.querySelectorAll("#usSrv .us-srv-nav a, .dk-tools a[data-sec]").forEach((a) => a.classList.toggle("on", a.dataset.sec === id));
    if (location.hash !== "#" + id) history.replaceState(history.state, "", "#" + id);
    window.scrollTo({ top: 0 });
  }
  document.addEventListener(
    "click",
    (e) => {
      const a = e.target.closest && e.target.closest('a[href^="#"], a[href^="sources.html#"], a[data-sec]');
      if (!a || !$("usSrv")) return;
      const id = a.dataset.sec || (a.getAttribute("href").split("#")[1] || "");
      if (!SECTIONS.some((s) => s[0] === id)) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      show(id);
      if (document.body.classList.contains("dk-drawer-open")) {
        const x = document.querySelector(".dk-drawer-x");
        if (x) x.click();
      }
    },
    true,
  );
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));

  /* My servers: a list to pick from (the page's drop-down stays, hidden, and drives the form) */
  function manageList() {
    const select = $("managerSelect");
    const panel = $("managerPanel");
    if (!select || panel.querySelector(".us-srv-list")) return;
    const wrap = document.createElement("div");
    wrap.className = "us-srv-manage";
    const list = document.createElement("div");
    list.className = "us-srv-listbox";
    list.innerHTML = `<label class="us-srv-find">${ICONS.search}<input type="search" placeholder="Find a server · دوّر على سيرفر" autocomplete="off"></label><div class="us-srv-list" role="listbox"></div>`;
    const edit = document.createElement("div");
    edit.className = "us-srv-edit";
    edit.innerHTML = `<div class="us-srv-empty">${ICONS.pick}<b>Choose a server from the list</b><span>اختار سيرفر من القايمة عشان تعدّله أو تغيّر ترتيبه أو تمسحه.</span></div>`;
    const grid = $("managerFields");
    const actions = panel.querySelector(".manager-actions");
    const result = $("managerResult");
    select.closest(".manager-select-wrap").after(wrap);
    wrap.append(list, edit);
    edit.append(grid, actions, result);
    const box = list.querySelector(".us-srv-list");
    const find = list.querySelector("input");
    function draw() {
      const q = find.value.trim().toLowerCase();
      const opts = [...select.options].filter((o) => o.value);
      box.innerHTML = opts.length
        ? opts
            .map((o) => {
              const m = o.text.match(/^(\d+)\s*—\s*(.*)$/) || [null, "", o.text];
              const parts = m[2].split(" · ");
              const kind = parts.length > 1 ? parts.pop() : "";
              const name = parts.join(" · ") || kind;
              return `<button type="button" role="option" data-v="${esc(o.value)}" class="${o.value === select.value ? "on" : ""}"${q && !m[2].toLowerCase().includes(q) ? " hidden" : ""}><i>${esc(m[1])}</i><span><b>${esc(name)}</b><small>${esc(kind)}</small></span></button>`;
            })
            .join("")
        : '<div class="us-srv-none">No saved servers in this group yet · مفيش سيرفرات هنا لسه</div>';
      edit.classList.toggle("picked", !!select.value);
    }
    box.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-v]");
      if (!b || select.disabled) return;
      select.value = b.dataset.v;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      draw();
    });
    find.addEventListener("input", draw);
    new MutationObserver(draw).observe(select, { childList: true, attributes: true });
    select.addEventListener("change", draw);
    draw();
  }

  /* the header's counts, from the page's own group counts */
  function counts() {
    const read = () => {
      const n = (g) => {
        const el = document.querySelector(`.manager-group-tab[data-group="${g}"] .manager-group-count`);
        const v = el ? parseInt(el.textContent, 10) : NaN;
        return Number.isFinite(v) ? v : null;
      };
      const p = n("stalker"), x = n("xtream");
      if (p === null || x === null) return;
      $("usStatAll").textContent = p + x;
      $("usStatPortal").textContent = p;
      $("usStatXtream").textContent = x;
    };
    document.querySelectorAll(".manager-group-count").forEach((el) => new MutationObserver(read).observe(el, { childList: true, characterData: true, subtree: true }));
    read();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(build, 0));
  else setTimeout(build, 0);
})();
