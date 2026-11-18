/* Ultra Stalker for Windows: the window's own buttons in the gold top bar
   (minimise · full screen / window · close). The program has no Windows frame. */
(function () {
  const W = window.usNative && window.usNative.win;
  if (!W) return;
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
