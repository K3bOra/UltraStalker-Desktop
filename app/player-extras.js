/* Ultra Stalker for Windows — extra player features.
   The bundle embeds this file inside the shared player (bundle/web/player.js), so it
   sees the player's own state: A (one API over every engine), current, opts, box, bar,
   stage, menu, refresh(), openMenu(), halt(), close(), fullscreen(), store, esc …

   - next episode: a button, the N key, and a 10-second countdown when an episode ends
   - playback speed, sleep timer (Settings)
   - shortcuts: N, S, R, P, [ ], 0-9, mouse wheel = volume
   - snapshot (S) and recording live channels (R) — saved by the program
   - mini player: a small window above every other window (P)
   - controls hide in VLC too (the program reports mouse moves over VLC's picture) */
const usX = (() => {
  const XN = window.usNative || {};
  const IC = {
    nextEp: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5.5v13a.8.8 0 0 0 1.2.7l9.2-6.5a.8.8 0 0 0 0-1.4L7.2 4.8A.8.8 0 0 0 6 5.5z" fill="currentColor" stroke="none"/><path d="M19 5v14"/></svg>',
    snap: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2.2l1.4-2h5.8l1.4 2h2.2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z"/><circle cx="12" cy="12.8" r="3.4"/></svg>',
    rec: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4.2" fill="currentColor" stroke="none"/></svg>',
    mini: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><rect x="11.5" y="11.5" width="7" height="5" rx="1" fill="currentColor" stroke="none"/></svg>',
    big: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7"/></svg>',
    x: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  };
  // VLC steps through its own speeds; the other engines play any speed
  const speeds = () => (isVlc() ? [0.5, 1, 1.5, 2] : [0.5, 0.75, 1, 1.25, 1.5, 2]);
  const SLEEP = [0, 15, 30, 60, 90];
  let wakeFn = null, lastSeen = { t: 0, d: 0 }, endedFor = -1, countdown = null;
  let sleepAt = 0, sleepTimer = 0, rec = null, recPoll = false, mini = false, toastT = 0;

  const isLive = () => !!(current && current.live);
  const playing = () => !!(current && (current.stream || current.url) && !current._halted);
  // the cards remember how far a movie or an episode got
  window.usxState = () => (playing() ? { t: A.time() || 0, d: A.duration() || 0, live: isLive() } : null);
  const nextInfo = () => {
    if (isLive() || !window.usDesktopNext) return null;
    try {
      return window.usDesktopNext.info();
    } catch (_) {
      return null;
    }
  };
  const ar = (en, a) => `${esc(en)}<span class="usx-ar">${esc(a)}</span>`;

  /* ------------------------------------------------------------ style */
  function style() {
    if (document.getElementById("usxStyle")) return;
    const s = document.createElement("style");
    s.id = "usxStyle";
    s.textContent = `
.usp-ic.usx-rec.on{color:#ff5a5a}
.usp-ic.usx-rec.on svg circle:last-child{animation:uspBlink 1.2s ease-in-out infinite}
.usx-pill{display:inline-flex;align-items:center;gap:6px;margin:0 4px;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.06em;color:#ffd9d9;background:rgba(255,70,70,.16);border:1px solid rgba(255,90,90,.4);font-variant-numeric:tabular-nums;white-space:nowrap}
.usx-pill[hidden]{display:none}
.usx-pill.sleep{color:#f3e2b4;background:rgba(240,222,180,.1);border-color:rgba(240,222,180,.28)}
.usx-strip{display:flex;flex-direction:column;gap:8px;margin:0 6px 10px}
.usx-strip:empty{display:none}
.usx-card{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:10px 12px 10px 14px;border-radius:14px;background:rgba(20,15,8,.94);border:1px solid rgba(240,222,180,.3);color:#f3e7c7;font-size:13px;line-height:1.45;box-shadow:0 14px 30px -18px #000}
.usx-card b{color:#fff6dc}
.usx-card .usx-grow{flex:1;min-width:160px}
.usx-card button{appearance:none;border:1px solid rgba(240,222,180,.3);background:rgba(255,240,210,.06);color:#f6e7b8;border-radius:999px;padding:7px 14px;font:inherit;font-size:12.5px;font-weight:700;cursor:pointer}
.usx-card button.gold{background:var(--foil);color:#1a1306;border-color:transparent}
.usx-card button:hover{filter:brightness(1.12)}
.usx-ring{flex:none;width:34px;height:34px;border-radius:50%;display:grid;place-items:center;font-weight:800;color:#1a1306;background:conic-gradient(#e2c07c var(--p,100%),rgba(240,222,180,.15) 0)}
.usx-ring i{font-style:normal;width:26px;height:26px;border-radius:50%;display:grid;place-items:center;background:#171108;color:#f6e7b8;font-size:12px}
.usx-ar{display:block;direction:rtl;text-align:left;font-size:11.5px;color:#cdb98a;margin-top:2px}
.usp-menu button[data-xl]{display:block;text-align:left;line-height:1.45}
.usx-keys{display:grid;grid-template-columns:auto 1fr;gap:5px 12px;padding:2px 6px 4px;font-size:12px;color:#d9ccaa}
.usx-keys kbd{font:inherit;font-size:11px;font-weight:700;color:#1a1306;background:#e9d29d;border-radius:6px;padding:1px 7px;justify-self:start;white-space:nowrap}
.usx-sleepnow{margin:6px 4px 0;font-size:12px;color:#e9d29d}
.usx-toast{position:fixed;right:22px;bottom:22px;z-index:2147483000;max-width:420px}
.usx-minibar{display:none}
.usp-ic.usx-gone{display:none!important}
html.us-mini,body.us-mini{overflow:hidden!important}
body.us-mini #dkBar{display:none!important}
body.us-mini .usp{position:fixed!important;inset:0!important;z-index:2147482000!important;padding:0!important;margin:0!important;background:#000!important;display:flex!important;align-items:stretch!important;justify-content:stretch!important;width:auto!important;height:auto!important}
body.us-mini .usp-card{width:100%!important;max-width:none!important;height:100%!important;max-height:none!important;border:0!important;border-radius:0!important;margin:0!important;display:flex!important;flex-direction:column!important;box-shadow:none!important}
body.us-mini .usp-head{display:none!important}
body.us-mini .usx-minibar{display:flex;align-items:center;gap:6px;height:32px;flex:none;padding:0 4px 0 12px;background:#0d0a06;border-bottom:1px solid rgba(240,222,180,.18);color:#f3e2b4;font-size:12px;font-weight:700;-webkit-app-region:drag;app-region:drag}
body.us-mini .usx-minibar b{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
body.us-mini .usx-minibar button{-webkit-app-region:no-drag;app-region:no-drag;appearance:none;border:0;background:none;color:#f6e7b8;width:30px;height:28px;border-radius:8px;display:grid;place-items:center;cursor:pointer}
body.us-mini .usx-minibar button:hover{background:rgba(240,222,180,.14)}
body.us-mini .usx-minibar svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
body.us-mini .usp-stage{flex:1!important;min-height:0!important;height:auto!important;max-height:none!important;aspect-ratio:auto!important}
body.us-mini .usp-bar{padding:30px 8px 6px}
body.us-mini .usp-vol input,body.us-mini .usp-ic.prev,body.us-mini .usp-ic.next,body.us-mini .usp-ic.stop,body.us-mini .usp-ic.usx-snap,body.us-mini .usp-ic.trk,body.us-mini .usp-ic.gear,body.us-mini .usp-ic.full,body.us-mini .usp-osd,body.us-mini .usp-live,body.us-mini .usp-tag,body.us-mini .usx-pill.sleep,body.us-mini .usx-card .usx-ar{display:none!important}
body.us-mini .usp-row{gap:2px}
body.us-mini .usx-card{padding:6px 8px 6px 10px;gap:8px;font-size:12px}
body.us-mini .usx-card button{padding:5px 10px}
body.us-mini .usp-ic{width:34px;height:34px}
body.us-mini .usp-ic.pp{width:38px;height:38px}
body.us-mini .usp-menu{max-height:calc(100% - 80px)}
`;
    document.head.appendChild(s);
  }

  /* ------------------------------------------------------------ build */
  function button(cls, label, title, icon) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "usp-ic " + cls;
    b.setAttribute("aria-label", label);
    b.title = title;
    b.innerHTML = icon;
    return b;
  }
  function build(wake) {
    style();
    wakeFn = wake;
    const q = (s) => bar.querySelector(s);
    const row = q(".usp-row");
    // next episode, right after "forward 10"
    const nx = button("usx-nextep", "Next episode", "Next episode (N) · الحلقة اللي بعدها", IC.nextEp);
    nx.hidden = true;
    nx.onclick = () => playNext();
    q(".skip-forward").after(nx);
    // REC / sleep pills next to LIVE
    const recPill = document.createElement("span");
    recPill.className = "usx-pill rec";
    recPill.hidden = true;
    const sleepPill = document.createElement("span");
    sleepPill.className = "usx-pill sleep";
    sleepPill.hidden = true;
    q(".usp-live").after(recPill, sleepPill);
    // record · snapshot · mini, before audio & subtitles
    const rc = button("usx-rec", "Record", "Record this channel (R) · تسجيل القناة", IC.rec);
    rc.onclick = () => toggleRec();
    const sn = button("usx-snap", "Snapshot", "Save a picture (S) · صورة من الفيديو", IC.snap);
    sn.onclick = () => snapshot();
    const mn = button("usx-mini", "Mini player", "Mini player (P) · شاشة صغيرة فوق كل البرامج", IC.mini);
    mn.onclick = () => setMini(!mini);
    q(".trk").before(rc, sn, mn);
    q(".pip").classList.add("usx-gone"); // the mini player works with every engine, VLC included
    // strip above the seek bar: next-episode countdown, messages
    const strip = document.createElement("div");
    strip.className = "usx-strip";
    bar.prepend(strip);
    // mini window's own title bar (drag to move)
    const mb = document.createElement("div");
    mb.className = "usx-minibar";
    mb.innerHTML = `<b></b><button type="button" class="usx-big" aria-label="Back to the big window" title="Back to the big window (P)">${IC.big}</button><button type="button" class="usx-close" aria-label="Close" title="Close">${IC.x}</button>`;
    mb.querySelector(".usx-big").onclick = () => setMini(false);
    mb.querySelector(".usx-close").onclick = () => {
      setMini(false);
      halt();
    };
    stage.before(mb);
    // mouse wheel over the picture: volume
    stage.addEventListener("wheel", (e) => {
      if (e.target.closest(".usp-menu")) return;
      e.preventDefault();
      A.setVol(A.vol() + (e.deltaY < 0 ? 0.05 : -0.05));
      wake();
      refresh();
    }, { passive: false });
    // VLC's picture is a window of its own: the program tells us when the mouse moves over it
    if (NV && NV.onPointer) NV.onPointer(() => box && !box.classList.contains("hidden") && wakeFn && wakeFn());
    if (XN.win && XN.win.onState) XN.win.onState((s) => s && typeof s.mini === "boolean" && s.mini !== mini && miniClass(s.mini));
  }

  /* ------------------------------------------------------------ refresh (every second + on changes) */
  function refreshX() {
    if (!bar) return;
    const q = (s) => bar.querySelector(s);
    const live = isLive();
    const on = playing();
    if (on && started && !live) {
      const d = A.duration(), t = A.time();
      if (d > 0) lastSeen = { t, d };
    }
    q(".usx-nextep").hidden = live || !on || !nextInfo();
    const rc = q(".usx-rec");
    rc.hidden = !live || !on || !XN.rec;
    rc.classList.toggle("on", !!rec);
    rc.title = rec ? "Stop recording (R) · وقّف التسجيل" : "Record this channel (R) · تسجيل القناة";
    q(".usx-snap").hidden = !on || !XN.snap;
    q(".usx-mini").hidden = !XN.win;
    const mb = box.querySelector(".usx-minibar b");
    if (mb) mb.textContent = (current && current.title) || "Ultra Stalker";
    const sp = q(".usx-pill.sleep");
    sp.hidden = !sleepAt;
    if (sleepAt) sp.textContent = "☾ " + Math.max(1, Math.ceil((sleepAt - Date.now()) / 60000)) + " min";
    if (rec) recStatus();
    // something to read in the strip: keep the controls showing
    if (q(".usx-strip").children.length) stage.classList.remove("idle");
  }
  async function recStatus() {
    if (recPoll || !XN.rec) return;
    recPoll = true;
    try {
      const s = await XN.rec.status();
      const pill = bar.querySelector(".usx-pill.rec");
      if (!s || !s.on) {
        pill.hidden = true;
        if (rec) recDone(s);
        return;
      }
      pill.hidden = false;
      pill.textContent = "● REC " + fmtClock(s.seconds || 0) + " · " + size(s.bytes);
    } catch (_) {
    } finally {
      recPoll = false;
    }
  }
  const size = (n) => (n > 1 << 30 ? (n / (1 << 30)).toFixed(2) + " GB" : Math.round((n || 0) / (1 << 20)) + " MB");

  /* ------------------------------------------------------------ messages */
  function strip() {
    return bar && bar.querySelector(".usx-strip");
  }
  function toast(html, ms = 6000, actions = []) {
    const card = document.createElement("div");
    card.className = "usx-card";
    card.innerHTML = `<div class="usx-grow">${html}</div>`;
    for (const [label, fn, gold] of actions) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      if (gold) b.className = "gold";
      b.onclick = (e) => {
        e.stopPropagation();
        card.remove();
        fn();
      };
      card.appendChild(b);
    }
    // inside the control bar while the player is open (VLC's picture never covers it)
    const s = box && !box.classList.contains("hidden") ? strip() : null;
    if (s) {
      s.querySelectorAll(".usx-card.toast").forEach((c) => c.remove());
      card.classList.add("toast");
      s.appendChild(card);
      stage.classList.remove("idle");
    } else {
      let holder = document.querySelector(".usx-toast");
      if (!holder) {
        holder = document.createElement("div");
        holder.className = "usx-toast";
        document.body.appendChild(holder);
      }
      holder.replaceChildren(card);
    }
    clearTimeout(toastT);
    if (ms) toastT = setTimeout(() => card.remove(), ms);
    return card;
  }
  function saved(kind, r) {
    if (!r || !r.ok) return toast(ar("Couldn't save the " + kind + ". " + ((r && r.error) || ""), "ما اتحفظش."), 7000);
    const name = String(r.file || "").split(/[\\/]/).pop();
    toast(`<b>${kind === "picture" ? "Picture saved" : "Recording saved"}</b> · ${esc(name)}` + `<span class="usx-ar">${kind === "picture" ? "الصورة اتحفظت" : "التسجيل اتحفظ"} في ${esc(r.folder || "")}</span>`, 9000, [["Show in folder", () => XN.showFile && XN.showFile(r.file)]]);
  }

  /* ------------------------------------------------------------ next episode */
  async function playNext() {
    cancelCountdown();
    const n = nextInfo();
    if (!n || !window.usDesktopNext) return;
    try {
      await window.usDesktopNext.play();
    } catch (_) {}
  }
  function cancelCountdown() {
    if (!countdown) return;
    clearInterval(countdown.timer);
    countdown.card.remove();
    countdown = null;
  }
  function ended() {
    if (!current || isLive() || endedFor === alive) return;
    // only a real end (not a dropped line in the middle of the film)
    const { t, d } = lastSeen;
    if (!(d > 0) || t < d - Math.max(45, d * 0.03)) return;
    endedFor = alive;
    if (sleepAt && Date.now() >= sleepAt - 1000) return;
    const n = nextInfo();
    if (!n) return;
    const s = strip();
    if (!s) return;
    cancelCountdown();
    const card = document.createElement("div");
    card.className = "usx-card";
    let left = 10;
    card.innerHTML = `<span class="usx-ring" style="--p:100%"><i>${left}</i></span><div class="usx-grow"><b>Next episode</b> · ${esc(n.label || "")}<span class="usx-ar">الحلقة اللي بعدها هتشتغل لوحدها</span></div>`;
    const go = document.createElement("button");
    go.type = "button";
    go.className = "gold";
    go.textContent = "Play now";
    go.onclick = (e) => (e.stopPropagation(), playNext());
    const no = document.createElement("button");
    no.type = "button";
    no.textContent = "Cancel";
    no.onclick = (e) => (e.stopPropagation(), cancelCountdown());
    card.append(go, no);
    s.appendChild(card);
    stage.classList.remove("idle");
    const my = alive;
    countdown = {
      card,
      timer: setInterval(() => {
        if (my !== alive) return cancelCountdown();
        left--;
        card.querySelector(".usx-ring").style.setProperty("--p", (left / 10) * 100 + "%");
        card.querySelector(".usx-ring i").textContent = String(Math.max(0, left));
        if (left <= 0) playNext();
      }, 1000),
    };
  }

  /* ------------------------------------------------------------ speed */
  function rate() {
    return (current && current._rate) || 1;
  }
  function setRate(r) {
    if (!current || isLive()) return;
    const list = speeds();
    r = list.reduce((a, b) => (Math.abs(b - r) < Math.abs(a - r) ? b : a), 1);
    current._rate = r;
    applyRate();
    toast(`Speed <b>${r}×</b><span class="usx-ar">سرعة التشغيل</span>`, 1800);
  }
  function applyRate() {
    const r = rate();
    try {
      if (isVlc()) NV.cmd("rate", r.toFixed(2));
      else if (isEngine() && eng && eng.setPlaybackRate) eng.setPlaybackRate(r);
      else if (video) video.playbackRate = r;
    } catch (_) {}
  }
  function startedX() {
    if (isLive() || rate() === 1) return;
    // another engine may not have the same speeds: the nearest one it has
    current._rate = speeds().reduce((a, b) => (Math.abs(b - rate()) < Math.abs(a - rate()) ? b : a), 1);
    setTimeout(applyRate, isVlc() ? 600 : 0);
  }

  /* ------------------------------------------------------------ sleep timer */
  function setSleep(min) {
    clearTimeout(sleepTimer);
    sleepAt = min ? Date.now() + min * 60000 : 0;
    if (min) {
      sleepTimer = setTimeout(() => {
        sleepAt = 0;
        if (current) {
          setMini(false);
          if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
          halt();
        }
        toast(ar("Sleep timer: playback stopped.", "مؤقت النوم وقّف التشغيل."), 0);
      }, min * 60000);
      toast(`Sleep timer · <b>${min} min</b><span class="usx-ar">التشغيل هيقف بعد ${min} دقيقة</span>`, 2500);
    }
    refresh();
  }

  /* ------------------------------------------------------------ snapshot */
  async function snapshot() {
    if (!XN.snap || !playing()) return;
    const title = (current && current.title) || "Ultra Stalker";
    let r;
    try {
      if (isVlc()) r = await XN.snap({ vlc: true, title });
      else if (!isEngine() && video && video.videoWidth) {
        const c = document.createElement("canvas");
        c.width = video.videoWidth;
        c.height = video.videoHeight;
        c.getContext("2d").drawImage(video, 0, 0);
        r = await XN.snap({ dataUrl: c.toDataURL("image/png"), title });
      } else {
        // the Ultra engine draws on its own canvas: take the picture from the window
        stage.classList.add("idle");
        await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
        const b = stage.getBoundingClientRect();
        r = await XN.snap({ rect: { x: Math.round(b.left), y: Math.round(b.top), width: Math.round(b.width), height: Math.round(b.height) }, title });
        stage.classList.remove("idle");
      }
    } catch (e) {
      r = { ok: false, error: String((e && e.message) || e) };
    }
    saved("picture", r);
  }

  /* ------------------------------------------------------------ recording */
  async function toggleRec() {
    if (!XN.rec) return;
    if (rec) return stopRec();
    if (!isLive() || !playing()) return;
    const r = await XN.rec.start({ title: (current && current.title) || "Channel" });
    if (!r || !r.ok) return toast(ar("Recording didn't start. " + ((r && r.error) || ""), "التسجيل مابدأش."), 7000);
    rec = { file: r.file, folder: r.folder, alive };
    toast(`<b>Recording</b> · ${esc((current && current.title) || "")}<span class="usx-ar">بيسجّل القناة… دوس R أو الزرار تاني عشان توقّف</span>`, 4000);
    refresh();
  }
  async function stopRec() {
    if (!rec || !XN.rec) return;
    const r = await XN.rec.stop();
    recDone(r);
  }
  function recDone(r) {
    if (!rec) return;
    const was = rec;
    rec = null;
    const pill = bar && bar.querySelector(".usx-pill.rec");
    if (pill) pill.hidden = true;
    if (r && r.bytes > 0) saved("recording", { ok: true, file: r.file || was.file, folder: r.folder || was.folder });
    else toast(ar("Nothing was recorded.", "مفيش حاجة اتسجّلت."), 5000);
    refresh();
  }

  /* ------------------------------------------------------------ mini player */
  function miniClass(on) {
    mini = on;
    document.documentElement.classList.toggle("us-mini", on);
    document.body.classList.toggle("us-mini", on);
    if (!box) return;
    if (on) {
      if (box.parentNode !== document.body) document.body.appendChild(box);
    } else if (box.classList.contains("docked") && opts.host && box.parentNode !== opts.host) opts.host.appendChild(box);
    const b = bar && bar.querySelector(".usx-mini");
    if (b) {
      b.innerHTML = on ? IC.big : IC.mini;
      b.title = on ? "Back to the big window (P)" : "Mini player (P) · شاشة صغيرة فوق كل البرامج";
    }
  }
  async function setMini(on) {
    if (!XN.win || on === mini) return;
    if (on && (!box || box.classList.contains("hidden"))) return;
    if (on) {
      if (document.fullscreenElement) await document.exitFullscreen().catch(() => {});
      box.classList.remove("expanded");
      if (menu) menu.classList.remove("on");
    }
    miniClass(on);
    XN.win.cmd(on ? "mini" : "unmini");
  }

  /* ------------------------------------------------------------ keys */
  function key(e) {
    if (e.ctrlKey || e.altKey || e.metaKey) return false;
    const k = e.key, live = isLive();
    if (k === "n" || k === "N") return !live && nextInfo() ? (playNext(), true) : false;
    if (k === "s" || k === "S") return snapshot(), true;
    if (k === "r" || k === "R") return live ? (toggleRec(), true) : false;
    if (k === "p" || k === "P") return setMini(!mini), true;
    if (k === "Escape" && mini) return setMini(false), true;
    if (live) return false;
    if (k === "]" || k === ">") return setRate(speeds().find((s) => s > rate() + 0.01) || 2), true;
    if (k === "[" || k === "<") return setRate([...speeds()].reverse().find((s) => s < rate() - 0.01) || 0.5), true;
    if (k === "=" ) return setRate(1), true;
    if (/^[0-9]$/.test(k) && A.duration() > 0) return A.seek((A.duration() * +k) / 10), true;
    if (k === "Home" && A.duration() > 0) return A.seek(0), true;
    return false;
  }

  /* ------------------------------------------------------------ Settings menu */
  function menuHtml() {
    let h = "";
    if (current && !isLive()) {
      h += '<h4>Speed · السرعة</h4><div class="usp-seg">' + speeds().map((s) => `<button type="button" data-xr="${s}" class="${Math.abs(rate() - s) < 0.01 ? "on" : ""}">${s === 1 ? "1×" : s}</button>`).join("") + "</div>";
    }
    const left = sleepAt ? Math.max(1, Math.ceil((sleepAt - Date.now()) / 60000)) : 0;
    h += '<h4>Sleep timer · مؤقت النوم</h4><div class="usp-seg">' + SLEEP.map((m) => `<button type="button" data-xs="${m}" class="${(!m && !sleepAt) ? "on" : ""}">${m ? m + "m" : "Off"}</button>`).join("") + "</div>";
    if (left) h += `<div class="usx-sleepnow">Stops in ${left} min · هيقف بعد ${left} دقيقة</div>`;
    return h;
  }
  function menuEnd() {
    let h = "";
    const resume = store.get("us-desk-last-live", "1") === "1";
    h += `<h4>Program</h4><button type="button" data-xl="1" class="${resume ? "on" : ""}">${resume ? "✓ " : ""}Open the last channel at start<span class="usx-ar">يفتح آخر قناة كانت شغالة أول ما البرنامج يفتح</span></button>`;
    h += '<h4>Shortcuts · الاختصارات</h4><div class="usx-keys">' + [
      ["Space", "Play / pause · تشغيل وإيقاف"],
      ["← →", "10 seconds · عشر ثواني"],
      ["↑ ↓", "Volume (live: channel) · الصوت"],
      ["Wheel", "Volume · الصوت"],
      ["PgUp PgDn", "Channel · القناة"],
      ["F · F11", "Full screen · ملء الشاشة"],
      ["M", "Mute · كتم الصوت"],
      ["N", "Next episode · الحلقة اللي بعدها"],
      ["[ ]", "Speed · السرعة"],
      ["0 – 9", "Jump to 0–90% · تنقّل في الفيلم"],
      ["S", "Picture · صورة"],
      ["R", "Record live · تسجيل"],
      ["P", "Mini player · الشاشة الصغيرة"],
    ].map(([k, l]) => `<kbd>${k}</kbd><span>${l}</span>`).join("") + "</div>";
    return h;
  }
  function menuClick(b) {
    if (b.dataset.xr !== undefined) {
      setRate(+b.dataset.xr);
      openMenu();
      return true;
    }
    if (b.dataset.xs !== undefined) {
      setSleep(+b.dataset.xs);
      openMenu();
      return true;
    }
    if (b.dataset.xl !== undefined) {
      store.set("us-desk-last-live", store.get("us-desk-last-live", "1") === "1" ? "0" : "1");
      openMenu();
      return true;
    }
    return false;
  }

  /* ------------------------------------------------------------ the player stops (new stream, close) */
  function stopX() {
    cancelCountdown();
    lastSeen = { t: 0, d: 0 };
    if (rec) stopRec();
  }
  function closed() {
    if (mini) setMini(false);
  }

  return {
    build,
    refresh: refreshX,
    ended,
    started: startedX,
    key,
    menuHtml,
    menuEnd,
    menuClick,
    stop: stopX,
    closed,
    wake: () => wakeFn && wakeFn(),
    get mini() {
      return mini;
    },
    toast,
  };
})();
