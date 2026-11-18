/* What the page may ask of the program: only VLC playback (window.usNative.vlc). */
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
  },
  openLogs: () => ipcRenderer.send("app:logs"),
  win: {
    cmd: (c) => ipcRenderer.send("win:cmd", c),
    state: () => ipcRenderer.sendSync("win:state"),
    onState: (cb) => ipcRenderer.on("win:state", (_, s) => cb(s)),
  },
});
