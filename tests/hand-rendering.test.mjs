import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../web/hands.js', import.meta.url), 'utf8');
async function trackerFixture() {
  let now = 1000, receive;
  const frames = [], intervals = [], inputs = [], elements = [];
  const context2d = new Proxy({}, { get: () => () => {} });
  const element = tag => {
    const el = { tag, style: {}, dataset: {}, hidden: false, parentElement: null,
      setAttribute() {}, append(...children) { for (const child of children) child.parentElement = this; },
      getContext: () => context2d };
    elements.push(el);
    return el;
  };
  const doc = { head: element('head'), body: element('body'), hidden: false, fullscreenElement: null,
    createElement: element, querySelector: () => null, addEventListener() {}, dispatchEvent() {} };
  const win = { innerWidth: 1000, innerHeight: 600, devicePixelRatio: 1,
    WaveBoardDesktop: true,
    WaveBoardNative: Promise.resolve({ hands: { connect(callback) { receive = callback; } }, startHands() {} }),
    WaveBoardInput: { pointer(event) { inputs.push(event); return true; }, hover() {}, suspend() {} },
    addEventListener() {}, dispatchEvent() {} };
  vm.runInNewContext(source, { document: doc, window: win, location: { search: '' }, URLSearchParams,
    performance: { now: () => now }, requestAnimationFrame: cb => frames.push(cb),
    setInterval: cb => intervals.push(cb), setTimeout() {},
    CustomEvent: class {}, KeyboardEvent: class {}, console });
  await Promise.resolve();
  const emit = patch => receive(JSON.stringify({ type: 'frame', pointer: {
    visible: true, down: false, hand: 'right', x: 0.1, y: 0.5, swipe_id: 0, hands: [], ...patch,
  } }));
  const tick = (milliseconds = 16) => { now += milliseconds; const pending = frames.splice(0); pending.forEach(cb => cb(now)); };
  const cursor = elements.find(el => el.className === 'hand-cursor');
  return { emit, tick, inputs, cursor, expire() { now += 600; intervals.forEach(cb => cb()); } };
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
