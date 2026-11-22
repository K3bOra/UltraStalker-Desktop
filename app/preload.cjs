/* What the page may ask of the program: VLC playback, the window, pictures,
   recordings and updates (window.usNative). */
const { contextBridge, ipcRenderer } = require("electron");

let available = false;
try {
  available = !!ipcRenderer.sendSync("vlc:available");
} catch (_) {}

contextBridge.exposeInMainWorld("usNative", {
  vlc: {
    available,
    play: (o) => ipcRenderer.invoke("vlc:play", o),
    stop: () => ipcRenderer.send("vlc:stop"),
    cmd: (name, arg) => ipcRenderer.invoke("vlc:cmd", name, arg),
    status: () => ipcRenderer.invoke("vlc:status"),
    tracks: () => ipcRenderer.invoke("vlc:tracks"),
    place: (r) => ipcRenderer.send("vlc:place", r || null),
    fit: (f) => ipcRenderer.send("vlc:fit", f),
    // the mouse moved over VLC's picture (a window of its own)
    onPointer: (cb) => ipcRenderer.on("vlc:pointer", () => cb()),
  },
  snap: (o) => ipcRenderer.invoke("app:snap", o),
  showFile: (f) => ipcRenderer.send("app:show", f),
  rec: {
    start: (o) => ipcRenderer.invoke("rec:start", o),
    stop: () => ipcRenderer.invoke("rec:stop"),
    status: () => ipcRenderer.invoke("rec:status"),
  },
  update: {
    state: () => ipcRenderer.invoke("upd:state"),
    onState: (cb) => ipcRenderer.on("upd:state", (_, s) => cb(s)),
    install: () => ipcRenderer.send("upd:install"),
  },
  openLogs: () => ipcRenderer.send("app:logs"),
  win: {
    cmd: (c) => ipcRenderer.send("win:cmd", c),
    state: () => ipcRenderer.sendSync("win:state"),
    onState: (cb) => ipcRenderer.on("win:state", (_, s) => cb(s)),
  },
});
