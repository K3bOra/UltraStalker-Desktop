/* Ultra Stalker for TV — the remote control.

   Arrows move a gold focus to the nearest thing in that direction (cards, buttons,
   categories, menus); OK opens it; Back closes whatever is on top (window.usTvBack,
   asked by the app). In the player:
     ← →  10 seconds (films) · ↑ ↓ channel (live) · OK pause / play and show the controls
     ↓ / OK show the controls, ← → move between them, ↑ hides them again. */
(function () {
  "use strict";
  if (!document.documentElement.classList.contains("us-tv")) return;
  const ARROW = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
  const ITEMS =
    'a[href],button,input:not([type=hidden]):not([type=range]),select,textarea,summary,[tabindex]:not([tabindex="-1"]),[role=button],[role=option],' +
    ".live-card,.poster-card,.item-card,.category,.inline-episode,.dk-src,.dk-sp-row";
  const NATIVE = /^(A|BUTTON|INPUT|SELECT|TEXTAREA|SUMMARY)$/;
  let last = null;

  const $ = (s, r = document) => r.querySelector(s);
  const box = () => $(".usp:not(.hidden)");
  const stage = () => $(".usp:not(.hidden) .usp-stage");
  /* the player covers the screen (not the small Live TV picture) */
  function watching() {
    const b = box();
    return !!b && (!b.classList.contains("docked") || b.classList.contains("expanded") || document.body.classList.contains("us-mini"));
  }
  function shown(el) {
    if (!el || el.hidden || el.disabled || el.closest("[hidden],.hidden,[aria-hidden=true],[inert]")) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    // (not opacity: menus and panels fade in; the player's hidden controls are "idle")
    if (el.closest(".usp-stage.idle .usp-bar")) return false;
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === "none" || cs.visibility === "hidden") return false;
    }
    return true;
  }
  /* where the focus may go now: the open menu, the player's controls, a panel, the page */
  function scope() {
    const menu = $(".usp:not(.hidden) .usp-menu.on");
    if (menu) return menu;
    if (watching()) return $(".usp:not(.hidden) .usp-bar");
    for (const s of [".dk-cats.on", ".dk-srcpanel.on", "dialog[open]", "#playerSheet:not(.hidden)"]) {
      const el = $(s);
      if (el && shown(el)) return el;
    }
    return document.body;
  }
  function items(root) {
    return [...root.querySelectorAll(ITEMS)].filter((el) => !el.closest(".usp-seek") && shown(el) && (root !== document.body || !el.closest(".usp.hidden,.dk-cats:not(.on),.dk-srcpanel:not(.on)")));
  }
  function focus(el) {
    if (!el) return false;
    if (!NATIVE.test(el.tagName) && !el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
    el.focus({ preventScroll: true });
    try {
      el.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
    } catch (_) {
      el.scrollIntoView(false);
    }
    last = el;
    return true;
  }
  /* the nearest item in a direction: the gap along it, plus how far off to the side */
  function nearest(from, list, dir) {
    const a = from.getBoundingClientRect();
    let best = null, score = Infinity;
    for (const el of list) {
      if (el === from || el.contains(from) || from.contains(el)) continue;
      const b = el.getBoundingClientRect();
      const slack = 0.3;
      let gap, side, ok;
      if (dir === "right" || dir === "left") {
        const m = Math.min(a.width, b.width) * slack;
        ok = dir === "right" ? b.left >= a.right - m && b.left + b.width / 2 > a.left + a.width / 2 : b.right <= a.left + m && b.left + b.width / 2 < a.left + a.width / 2;
        gap = dir === "right" ? b.left - a.right : a.left - b.right;
        side = Math.max(0, Math.max(a.top, b.top) - Math.min(a.bottom, b.bottom));
        side += Math.abs(a.top + a.height / 2 - (b.top + b.height / 2)) * 0.05;
      } else {
        const m = Math.min(a.height, b.height) * slack;
        ok = dir === "down" ? b.top >= a.bottom - m && b.top + b.height / 2 > a.top + a.height / 2 : b.bottom <= a.top + m && b.top + b.height / 2 < a.top + a.height / 2;
        gap = dir === "down" ? b.top - a.bottom : a.top - b.bottom;
        side = Math.max(0, Math.max(a.left, b.left) - Math.min(a.right, b.right));
        side += Math.abs(a.left + a.width / 2 - (b.left + b.width / 2)) * 0.05;
      }
      if (!ok) continue;
      const s = Math.max(0, gap) + side * 2.5;
      if (s < score) {
        score = s;
        best = el;
      }
    }
    return best;
  }
  /* something to start from: the last place, the playing channel, the first item on screen */
  function start(list) {
    if (last && list.includes(last)) return last;
    const playing = list.find((el) => el.matches(".live-card.dk-on"));
    if (playing) return playing;
    const onScreen = list.filter((el) => {
      const r = el.getBoundingClientRect();
      return r.bottom > 60 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
    });
    const main = onScreen.filter((el) => !el.closest("#dkBar"));
    return (main.length ? main : onScreen)[0] || list[0];
  }
  function move(dir) {
    const root = scope();
    const list = items(root);
    if (!list.length) return false;
    const cur = document.activeElement;
    if (!cur || cur === document.body || !root.contains(cur) || !list.includes(cur)) return focus(start(list));
    const next = nearest(cur, list, dir);
    if (next) return focus(next);
    // nothing further on screen: let long lists load more
    if (root === document.body && (dir === "down" || dir === "up")) window.scrollBy({ top: (dir === "down" ? 1 : -1) * innerHeight * 0.4, behavior: "smooth" });
    return true;
  }

  /* ------------------------------------------------------------ the player */
  function wake() {
    const s = stage();
    if (s) s.dispatchEvent(new MouseEvent("mousemove", { bubbles: true }));
  }
  function controls() {
    const b = box();
    if (!b) return [];
    const s = stage();
    if (s) s.classList.remove("idle");
    return items(b.querySelector(".usp-bar")).filter((el) => !el.closest(".usx-strip") || el.matches("button"));
  }
  function showControls() {
    wake();
    const list = controls();
    const pp = list.find((el) => el.matches(".pp"));
    const strip = list.find((el) => el.closest(".usx-strip"));
    focus(strip || pp || list[0]);
  }
  function hideControls() {
    const s = stage();
    if (document.activeElement && document.activeElement.closest(".usp")) document.activeElement.blur();
    if (s) s.classList.add("idle");
  }
  function playerKey(e, dir) {
    const b = box();
    const inBar = document.activeElement && document.activeElement.closest(".usp-bar");
    const live = b && b.querySelector(".usp-live") && b.querySelector(".usp-live").style.display !== "none";
    if (inBar) {
      const s = stage();
      if (s && s.classList.contains("idle")) return wake(), true; // first press only shows them
      wake();
      if (dir === "up") {
        const next = nearest(document.activeElement, controls(), "up");
        return next ? focus(next) : (hideControls(), true);
      }
      return dir ? move(dir) : false;
    }
    // just watching
    if (dir === "left" || dir === "right") {
      if (live) return showControls(), true;
      return false; // the player seeks 10 seconds
    }
    if (dir === "up" || dir === "down") {
      if (live) return false; // the player changes the channel
      return showControls(), true;
    }
    return false;
  }

  /* ------------------------------------------------------------ keys */
  window.addEventListener(
    "keydown",
    (e) => {
      const k = e.key;
      const dir = ARROW[k];
      const el = document.activeElement;
      // typing: ← → move the cursor until its end
      if (el && /^(INPUT|TEXTAREA)$/.test(el.tagName) && !/^(checkbox|radio|button|submit|range)$/.test(el.type)) {
        if (k === "ArrowLeft" && el.selectionStart > 0) return;
        if (k === "ArrowRight" && el.selectionEnd < String(el.value || "").length) return;
        if (k === "Enter") return;
      }
      if (/^Media(PlayPause|Play|Pause)$/.test(k) && box()) {
        const pp = $(".usp:not(.hidden) .usp-bar .pp");
        if (pp) pp.click();
        wake();
        e.preventDefault();
        return;
      }
      if (!dir && k !== "Enter") return;
      let done = false;
      if (watching() && !$(".usp:not(.hidden) .usp-menu.on")) {
        if (k === "Enter") {
          const inBar = el && el.closest(".usp-bar");
          if (inBar) {
            wake();
            return; // the button's own click
          }
          const live = $(".usp:not(.hidden) .usp-live");
          if (live && live.style.display === "none") {
            const pp = $(".usp:not(.hidden) .usp-bar .pp");
            if (pp && !pp.hidden) pp.click();
          }
          showControls();
          done = true;
        } else done = playerKey(e, dir);
        if (!done) return; // the player's own keys
      } else if (k === "Enter") {
        if (!el || el === document.body) return;
        // the playing channel again: the picture fills the screen
        if (el.matches(".live-card.dk-on") && box()) {
          window.USPlayer.fullscreen();
          setTimeout(showControls, 150);
          done = true;
        } else if (!NATIVE.test(el.tagName)) {
          el.click();
          done = true;
        } else return; // buttons and links open themselves
      } else done = move(dir);
      if (done) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    },
    true
  );

  /* ------------------------------------------------------------ Back (asked by the app) */
  const OPEN = () =>
    [".usp:not(.hidden)", ".usp-menu.on", ".dk-cats.on", ".dk-srcpanel.on", "#dkBar.searching", "body.dk-drawer-open", "#playerSheet:not(.hidden)", "dialog[open]", ".usp.expanded"]
      .map((s) => ($(s) ? 1 : 0))
      .join("");
  window.usTvBack = function () {
    const menu = $(".usp:not(.hidden) .usp-menu.on");
    if (menu) {
      menu.classList.remove("on");
      showControls();
      return true;
    }
    const b = box();
    if (b && watching()) {
      const a = document.activeElement;
      if (a && a.closest(".usp-bar") && !stage().classList.contains("idle")) {
        hideControls();
        return true;
      }
      if (document.body.classList.contains("us-mini")) return false;
      if (b.classList.contains("docked")) {
        window.USPlayer.fullscreen(); // back to the Live TV screen, still playing
        setTimeout(() => focus($("#browseItems .live-card.dk-on")), 100);
      } else window.USPlayer.close();
      setTimeout(() => last && document.contains(last) && focus(last), 120);
      return true;
    }
    if (document.body.classList.contains("dk-drawer-open")) {
      const m = $("#dkMenuBtn");
      if (m) m.click();
      return true;
    }
    // panels close on Escape
    const before = OPEN();
    const ev = { key: "Escape", code: "Escape", keyCode: 27, which: 27, bubbles: true, cancelable: true };
    (document.activeElement || document.body).dispatchEvent(new KeyboardEvent("keydown", ev));
    if (OPEN() !== before) {
      setTimeout(() => {
        if (!document.activeElement || document.activeElement === document.body) move("down");
      }, 80);
      return true;
    }
    return false; // the app goes back a page, or leaves
  };

  // a first focus as soon as there is something to focus
  let tries = 0;
  const first = setInterval(() => {
    if (++tries > 40 || (document.activeElement && document.activeElement !== document.body)) return clearInterval(first);
    const list = items(document.body);
    if (list.length > 3) {
      clearInterval(first);
      focus(start(list));
    }
  }, 250);
  // when the focused thing disappears (a list redrawn), carry on from the screen
  document.addEventListener("focusout", () => {
    setTimeout(() => {
      if ((!document.activeElement || document.activeElement === document.body) && last && !document.contains(last)) last = null;
    }, 0);
  });
})();
