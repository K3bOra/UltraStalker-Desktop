import test from "node:test";
import assert from "node:assert/strict";
import { createSeekController } from "../app/seek-controller.js";
import { singleFlight } from "../app/single-flight.js";

function fixture(apply) {
  let actual = 100, clock = 0, next = 0;
  const timers = new Map(), calls = [];
  const seeks = createSeekController({
    read: () => actual, duration: () => 1000, now: () => clock,
    apply: (n) => { calls.push(n); return apply?.(n); },
    schedule: (fn) => { timers.set(++next, fn); return next; },
    cancel: (id) => timers.delete(id),
  });
  const run = async () => {
    for (const [id, fn] of [...timers]) { timers.delete(id); fn(); }
    for (let i = 0; i < 8; i++) await Promise.resolve();
  };
  return { seeks, calls, run, position: (n) => { actual = n; }, clock: (n) => { clock = n; } };
}

test("five rapid presses advance 50 seconds, not 10", async () => {
  const f = fixture();
  for (let i = 0; i < 5; i++) f.seeks.by(10);
  assert.equal(f.seeks.time(), 150);
  await f.run();
  assert.deepEqual(f.calls, [150]);
  // The VLC status sample can still contain the pre-seek position.
  f.position(101);
  f.seeks.by(10);
  await f.run();
  assert.deepEqual(f.calls, [150, 160]);
});

test("presses during an in-flight seek are accumulated and sent after it", async () => {
  let finish;
  const f = fixture(() => new Promise((r) => { finish = r; }));
  f.seeks.by(10);
  await f.run();
  for (let i = 0; i < 4; i++) f.seeks.by(10);
  await f.run();
  assert.deepEqual(f.calls, [110]);
  finish();
  await f.run();
  await f.run();
  assert.deepEqual(f.calls, [110, 150]);
  finish();
});

test("back/forward, slider overrides, limits and acknowledged playback", async () => {
  const f = fixture();
  f.seeks.by(-10); f.seeks.by(-10); f.seeks.by(10);
  assert.equal(f.seeks.time(), 90);
  f.seeks.to(500);
  f.seeks.by(10);
  await f.run();
  assert.deepEqual(f.calls, [510]);
  f.position(511);
  assert.equal(f.seeks.time(), 511);
  f.position(520);
  assert.equal(f.seeks.time(), 520);
  f.seeks.to(-100);
  assert.equal(f.seeks.time(), 0);
  f.seeks.to(9000);
  assert.equal(f.seeks.time(), 1000);
  await f.run();
  assert.equal(f.calls.at(-1), 1000);
});

test("closing/changing the video discards unsent seeks", async () => {
  const f = fixture();
  f.seeks.by(10);
  f.seeks.reset();
  await f.run();
  assert.deepEqual(f.calls, []);
  f.position(20);
  f.seeks.by(10);
  await f.run();
  assert.deepEqual(f.calls, [30]);
});

test("a rejected backend seek restores the actual position", async () => {
  const f = fixture(() => Promise.reject(new Error("cannot seek")));
  f.seeks.by(10);
  await f.run();
  assert.equal(f.seeks.time(), 100);
});

test("a new video cancels a scheduled backend call from the previous video", async () => {
  const f = fixture();
  f.seeks.by(10);
  const pending = f.run();
  f.seeks.reset();
  f.position(20);
  f.seeks.by(10);
  await pending;
  await f.run();
  assert.deepEqual(f.calls, [30]);
});

test("slow native status reads share one pending request", async () => {
  let finish, calls = 0;
  const status = singleFlight(() => { calls++; return new Promise((r) => { finish = r; }); });
  const a = status(), b = status();
  assert.equal(a, b);
  await Promise.resolve();
  assert.equal(calls, 1);
  finish({ time: 100 });
  assert.deepEqual(await b, { time: 100 });
  const c = status();
  await Promise.resolve();
  assert.equal(calls, 2);
  finish({ time: 101 });
  await c;
});
