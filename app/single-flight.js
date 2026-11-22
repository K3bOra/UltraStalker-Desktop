/* One native status read at a time, even when the renderer is ahead of VLC. */
export function singleFlight(read) {
  let pending = null;
  return () => {
    if (!pending) pending = Promise.resolve().then(read).finally(() => { pending = null; });
    return pending;
  };
}
