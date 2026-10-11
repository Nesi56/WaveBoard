import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
const source = (await readFile(new URL('../web/hands.js', import.meta.url), 'utf8')).replace(/^import .*projection\.js.*;$/m, '');
const mapping = await import(`data:text/javascript;base64,${Buffer.from(await readFile(new URL('../web/projection.js', import.meta.url), 'utf8')).toString('base64')}`);
async function trackerFixture(preferences = { mirrored: false }) {
  let now = 1000, receive;
  const frames = [], intervals = [], inputs = [], elements = [], arcs = [], keys = [], listeners = {};
  const context2d = new Proxy({}, { get: (_, key) => (...args) => { if (key === 'arc') arcs.push(args); } });
  const element = tag => {
    const el = { tag, style: {}, dataset: {}, hidden: false, parentElement: null,
      setAttribute() {}, append(...children) { for (const child of children) child.parentElement = this; },
      getContext: () => context2d };
    elements.push(el);
    return el;
  };
  const doc = { head: element('head'), body: element('body'), hidden: false, fullscreenElement: null,
    createElement: element, querySelector: () => null, addEventListener() {}, dispatchEvent(event) { keys.push(event.key); } };
  const win = { innerWidth: 1000, innerHeight: 600, devicePixelRatio: 1,
    WaveBoardDesktop: true,
    WaveBoardNative: Promise.resolve({ hands: { connect(callback) { receive = callback; } }, startHands() {} }),
    WaveBoardInput: { pointer(event) { inputs.push(event); return true; }, hover() {}, suspend() {} },
    addEventListener(type, callback) { listeners[type] = callback; }, dispatchEvent() {} };
  vm.runInNewContext(source, { document: doc, window: win, location: { search: '' }, URLSearchParams,
    ...mapping, localStorage: { getItem: () => JSON.stringify(preferences), setItem() {} },
    performance: { now: () => now }, requestAnimationFrame: cb => frames.push(cb),
    setInterval: cb => intervals.push(cb), setTimeout() {},
    CustomEvent: class {}, KeyboardEvent: class { constructor(type, data) { Object.assign(this, data); } }, console });
  await Promise.resolve();
  const emit = (patch, frame = {}) => receive(JSON.stringify({ type: 'frame', ...frame, pointer: {
    visible: true, down: false, hand: 'right', x: 0.1, y: 0.5, swipe_id: 0, hands: [], ...patch,
  } }));
  const tick = (milliseconds = 16) => { now += milliseconds; const pending = frames.splice(0); pending.forEach(cb => cb(now)); };
  const cursor = elements.find(el => el.className === 'hand-cursor');
  return { emit, tick, inputs, cursor, arcs, keys, listeners, controls: win.WaveBoardHands,
    expire(ms = 600) { now += ms; intervals.forEach(cb => cb()); } };
}
test('cursor eases between inference frames at display cadence', async () => {
  const f = await trackerFixture();
  f.emit({ x: 0.1 }); f.tick();
  f.emit({ x: 0.8 }); f.tick();
  const first = Number(f.cursor.style.transform.match(/translate\(([\d.]+)px/)[1]);
  assert.ok(first > 100 && first < 800);
  f.tick();
  const second = Number(f.cursor.style.transform.match(/translate\(([\d.]+)px/)[1]);
  assert.ok(second > first && second < 800, 'moves smoothly without another detector packet');
});
test('flow can move a drag but cannot start or release; prediction cannot drag', async () => {
  const f = await trackerFixture();
  f.emit({}); f.tick();
  f.emit({ down: true, observed: false, motion_tracked: true, x: 0.2 }); f.tick();
  assert.equal(f.inputs.length, 0);
  f.emit({ down: true, observed: true, x: 0.2 }); f.tick();
  assert.equal(f.inputs.filter(e => e.type === 'down').length, 1);
  f.emit({ down: false, observed: false, motion_tracked: true, x: 0.3 }); f.tick();
  assert.equal(f.inputs.filter(e => e.type === 'up').length, 0);
  const before = f.inputs.length;
  f.emit({ down: true, observed: false, predicted: true, x: 0.3 }); f.tick();
  assert.equal(f.inputs.length, before);
});
test('cancelled and stale tracking never synthesize a click release and need rearming', async () => {
  const f = await trackerFixture();
  f.emit({}); f.tick();
  f.emit({ down: true }); f.tick();
  f.emit({ down: false, cancelled: true }); f.tick();
  assert.equal(f.inputs.filter(e => e.type === 'cancel').length, 1);
  assert.equal(f.inputs.filter(e => e.type === 'up').length, 0);
  f.emit({ down: true }); f.tick();
  assert.equal(f.inputs.filter(e => e.type === 'down').length, 1);
  f.emit({ down: false }); f.emit({ down: true }); f.tick();
  assert.equal(f.inputs.filter(e => e.type === 'down').length, 2);
  f.expire();
  assert.equal(f.inputs.filter(e => e.type === 'cancel').length, 2);
  assert.equal(f.cursor.hidden, true);
});
test('batched hover, pinch and release act at packet coordinates before repaint', async () => {
  const f = await trackerFixture();
  f.emit({ x: 0.1 }); f.tick();
  f.emit({ x: 0.8 });
  f.emit({ x: 0.8, down: true });
  f.emit({ x: 0.8, down: false });
  assert.deepEqual(f.inputs.filter(e => e.type === 'down' || e.type === 'up').map(e => [e.type, e.x]),
    [['down', 800], ['up', 800]]);
});
test('batched drag excursion is consumed before release returns to start', async () => {
  const f = await trackerFixture();
  f.emit({ x: 0.1 }); f.tick();
  f.emit({ x: 0.1, down: true });
  f.emit({ x: 0.8, down: true, observed: false, motion_tracked: true });
  f.emit({ x: 0.1, down: false });
  const excursion = f.inputs.findIndex(e => e.type === 'move' && e.x === 800);
  const release = f.inputs.findIndex(e => e.type === 'up');
  assert.ok(excursion > 0 && excursion < release);
  assert.equal(f.inputs[release].x, 100);
});

test('default mirror reverses skeleton, click and swipe together', async () => {
  const f = await trackerFixture(null);
  const hand = { id: 'right', primary: true, points: Array.from({ length: 21 }, () => [0.2, 0.4]) };
  f.emit({ x: 0.2, y: 0.4, hands: [hand] }); f.tick();
  assert.equal(f.arcs[0][0], 800);
  f.emit({ x: 0.2, y: 0.4, down: true });
  assert.equal(f.inputs.find(e => e.type === 'down').x, 800);
  f.emit({ swipe_id: 1, swipe: 1 });
  assert.deepEqual(f.keys, ['ArrowRight']);
});

test('changing alignment during a pinch cancels and requires an open hand', async () => {
  const f = await trackerFixture();
  f.emit({ down: true });
  f.controls.configure({ mirrored: true });
  assert.equal(f.inputs.at(-1).type, 'cancel');
  f.emit({ down: true });
  assert.equal(f.inputs.filter(e => e.type === 'down').length, 1);
  f.emit({ down: false }); f.emit({ down: true, x: 0.2 });
  assert.equal(f.inputs.at(-1).x, 800);
});

function calibrate(f, patch = {}) {
  for (let i = 0; i < 3; i++) {
    f.tick(500);
    const timestamp = 1500 + i * 500;
    f.emit({ camera_x: 0.25, camera_y: 0.4, ...patch }, { timestamp, projection: {
      timestamp, markers: mapping.MARKER_CENTERS.map(([x, y], id) => ({ id, center: [1 - x, y] })),
    } });
  }
}

test('corner calibration uses raw coordinates for both skeleton and cursor with no extra mirror', async () => {
  const f = await trackerFixture({ mirrored: true, enabled: true });
  calibrate(f);
  assert.equal(f.controls.getSettings().status, 'Aligned to projection');
  f.emit({ x: 0.01, y: 0.01, camera_x: 0.25, camera_y: 0.4, hands: [{
    id: 'right', primary: true, points: Array.from({ length: 21 }, () => [0.01, 0.01]),
    camera_points: Array.from({ length: 21 }, () => [0.25, 0.4]),
  }] });
  f.tick();
  assert.ok(Math.abs(f.arcs.at(-1)[0] - 750) < 1e-6);
  f.emit({ down: true, camera_x: 0.25, camera_y: 0.4 });
  const down = f.inputs.find(e => e.type === 'down');
  assert.ok(Math.abs(down.x - 750) < 1e-6);
  assert.ok(Math.abs(down.y - 240) < 1e-6);
  f.emit({ down: true, camera_x: 1.2, camera_y: 0.4 });
  assert.equal(f.inputs.at(-1).type, 'cancel');
  assert.equal(f.cursor.hidden, true);
});

test('locking corners and losing calibration cancel presses without a click', async () => {
  const f = await trackerFixture({ enabled: true, mirrored: false });
  f.emit({ down: true });
  calibrate(f, { down: true });
  assert.equal(f.inputs.filter(e => e.type === 'cancel').length, 1);
  f.emit({ down: false, camera_x: 0.25, camera_y: 0.4 });
  f.emit({ down: true, camera_x: 0.25, camera_y: 0.4 });
  f.expire(2600);
  assert.equal(f.inputs.filter(e => e.type === 'cancel').length, 2);
  assert.equal(f.inputs.filter(e => e.type === 'up').length, 0);
  assert.match(f.controls.getSettings().status, /manual alignment/);
});

test('outside primary cannot swipe or hide an inside secondary skeleton', async () => {
  const f = await trackerFixture({ enabled: true });
  calibrate(f);
  f.emit({ camera_x: 1.2, camera_y: 0.4, swipe_id: 1, swipe: 1,
    camera_swipe: [[1.1, 0.4], [1.2, 0.4]], hands: [{
      id: 'left', primary: false, points: Array.from({ length: 21 }, () => [0.2, 0.4]),
      camera_points: Array.from({ length: 21 }, () => [0.25, 0.4]),
    }] });
  f.tick();
  assert.equal(f.cursor.hidden, true);
  assert.ok(Math.abs(f.arcs.at(-1)[0] - 750) < 1e-6);
  assert.deepEqual(f.keys, []);
  f.emit({ camera_x: 0.2, camera_y: 0.4, swipe_id: 1, swipe: 1,
    camera_swipe: [[0.1, 0.4], [0.2, 0.4]] });
  assert.deepEqual(f.keys, [], 'suppressed swipe cannot replay after re-entry');
});
