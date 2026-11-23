/* Ultra Stalker for TV — what the page may ask of the app (window.usNative), before the
   player loads. The app's object (window.USTV) answers synchronously; the page expects
   promises, as from the Windows program. */
(function () {
  "use strict";
  const N = window.USTV;
  // The TV app is always full screen: the player fills the page instead of asking for
  // the browser's full screen (which a TV's web view doesn't offer).
  try {
    Object.defineProperty(document, "fullscreenEnabled", { get: () => false });
    Element.prototype.requestFullscreen = function () {
      return Promise.reject(new Error("full screen is the page itself on the TV"));
    };
  } catch (_) {}
  // Saving a file (a backup, a cleaned server list): the TV saves it and offers it to a
  // phone (tv.js), also for links the page clicks without showing them.
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (this.hasAttribute("download") && window.USTVFiles && /^(blob|data):/.test(this.href) && window.usTvSave) return window.usTvSave(this.href, this.getAttribute("download"));
    return click.call(this);
  };
  if (!N) return;
  const parse = (s, d) => {
    try {
      return JSON.parse(s);
    } catch (_) {
      return d;
    }
  };
  window.usNative = {
    vlc: {
      available: !!N.vlcAvailable(),
      play: (o) => Promise.resolve(parse(N.vlcPlay(JSON.stringify(o || {})), { ok: false, error: "VLC didn't answer" })),
      stop: () => N.vlcStop(),
      cmd: (name, arg) => Promise.resolve(!!N.vlcCmd(String(name), arg == null ? "" : String(arg))),
      status: () => Promise.resolve(parse(N.vlcStatus(), { state: "stopped", time: 0, length: 0 })),
      tracks: () => Promise.resolve(parse(N.vlcTracks(), { audio: [], subs: [] })),
      // page coordinates; the app turns them into the screen's pixels
      place: (r) => N.vlcPlace(r ? JSON.stringify({ x: r.x, y: r.y, w: r.w, h: r.h, vw: window.innerWidth, vh: window.innerHeight }) : ""),
      fit: (f) => N.vlcFit(String(f || "fit")),
    },
    tv: {
      version: () => N.version(),
      exit: () => N.exitApp(),
    },
  };
  // VLC plays everything on a TV box (graphics-card decoding, every codec): first choice.
  try {
    if (!localStorage.getItem("us-player-engine")) localStorage.setItem("us-player-engine", "vlc");
  } catch (_) {}
})();
