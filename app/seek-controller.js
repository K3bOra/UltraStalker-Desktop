/* Accumulate relative seeks while a backend is still reporting the old position.
   The bundle embeds this small, dependency-free controller in the shared player. */
export function createSeekController({ read, duration, apply, changed = () => {}, delay = 120,
  now = Date.now, schedule = setTimeout, cancel = clearTimeout }) {
  let target = null, dirty = false, timer = null, flight = null, revision = 0, generation = 0, expires = 0;

  function time() {
    const actual = Number(read()) || 0;
    if (target !== null && !dirty && !flight && (Math.abs(actual - target) < 1.5 || now() > expires)) target = null;
    return target === null ? actual : target;
  }
  function arm(ms = delay) {
    if (timer !== null) cancel(timer);
    timer = schedule(flush, ms);
  }
  function flush() {
    timer = null;
    if (flight || !dirty || target === null) return;
    dirty = false;
    const value = target, sent = revision, session = generation;
    const pending = Promise.resolve().then(() => {
      if (session === generation) return apply(value);
    }).then(() => {
      if (sent === revision) expires = now() + 6000;
    }).catch(() => {
      if (sent === revision) target = null;
    }).finally(() => {
      if (flight !== pending) return;
      flight = null;
      if (dirty) arm(0);
      changed();
    });
    flight = pending;
  }
  function to(value) {
    const end = Number(duration());
    if (!Number.isFinite(value) || !(end > 0)) return;
    target = Math.max(0, Math.min(end, value));
    revision++;
    dirty = true;
    expires = now() + 6000;
    arm();
    changed();
  }
  function reset() {
    generation++;
    revision++;
    target = null;
    dirty = false;
    expires = 0;
    if (timer !== null) cancel(timer);
    timer = null;
  }
  return { time, to, by: (seconds) => to(time() + seconds), reset };
}
