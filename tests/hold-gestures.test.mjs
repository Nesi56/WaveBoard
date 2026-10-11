import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const { HoldGestures } = await import(`data:text/javascript;base64,${Buffer.from(await readFile(new URL('../web/hold-gestures.js', import.meta.url))).toString('base64')}`);
const point = { visible: true, observed: true, down: false, hand: 'one', pose: 'point' };
const slides = { page: 'slides' };
const peace = { ...point, pose: 'peace' };
function feed(gestures, pointer, from, to, context = slides, position = [0.95, 0.5]) {
  const actions = [];
  for (let now = from; now <= to; now += 50) {
    const action = gestures.update(pointer, position, context, now);
    if (action) actions.push([now, action]);
  }
  return actions;
}
test('index hold waits then repeats while held, and stops on moving away', () => {
  const g = new HoldGestures();
  assert.deepEqual(feed(g, point, 0, 1600), [[650, { direction: 1 }], [1550, { direction: 1 }]]);
  g.update(point, [0.5, 0.5], slides, 1650);
  assert.equal(g.progress(1650), null);
  assert.deepEqual(feed(g, point, 1700, 2300), []);
});
test('peace requires three continuous seconds and fires once until released', () => {
  const g = new HoldGestures();
  assert.deepEqual(feed(g, peace, 0, 1500), []);
  assert.equal(g.progress(1500).value, 0.5);
  assert.deepEqual(feed(g, peace, 1550, 2950), []);
  assert.deepEqual(feed(g, peace, 3000, 6000), [[3000, { home: true }]]);
  assert.equal(g.progress(6000), null);
  g.update({ ...peace, pose: null }, [0.5, 0.5], slides, 6050);
  assert.deepEqual(feed(g, peace, 6100, 9100), [[9100, { home: true }]]);
});
test('brief flow frames keep feedback but cannot finish either hold', () => {
  const g = new HoldGestures();
  feed(g, peace, 0, 2900);
  assert.equal(g.update({ ...peace, observed: false, pose: null, motion_tracked: true }, [0.5, 0.5], slides, 3100), null);
  assert.equal(g.progress(3100).value, 1);
  assert.deepEqual(g.update(peace, [0.5, 0.5], slides, 3150), { home: true });
});
test('loss, stale observations, pinch, identity, and cancelled tracking reset holds', () => {
  for (const patch of [{ visible: false }, { down: true }, { hand: 'two' }, { cancelled: true }, { pose: null }]) {
    const g = new HoldGestures();
    feed(g, peace, 0, 2900);
    assert.equal(g.update({ ...peace, ...patch }, [0.5, 0.5], slides, 2950), null);
    assert.deepEqual(feed(g, peace, 3000, 3500), []);
  }
  const g = new HoldGestures();
  feed(g, peace, 0, 2900);
  assert.equal(g.progress(3400), null);
  assert.equal(g.update(peace, [0.5, 0.5], slides, 3400), null);
  assert.equal(g.progress(3400).value, 0);
});
test('open palms never navigate; edges only work on Home/Slides with no menu or dialog', () => {
  for (const context of [{ page: 'files' }, { page: 'whiteboard' }, { ...slides, blocked: true }, { ...slides, hidden: true }]) {
    assert.deepEqual(feed(new HoldGestures(), point, 0, 3500, context), []);
  }
  assert.deepEqual(feed(new HoldGestures(), { ...point, pose: null, swipe_id: 99, swipe: 1 }, 0, 3500), []);
  assert.deepEqual(feed(new HoldGestures(), peace, 0, 3000, { ...slides, blocked: true }), [[3000, { home: true }]]);
  assert.deepEqual(feed(new HoldGestures(), peace, 0, 4000, { page: 'home' }), []);
});
test('edge hysteresis tolerates small jitter; changing side or page starts a new hold', () => {
  const g = new HoldGestures();
  feed(g, point, 0, 400, slides, [0.14, 0.5]);
  assert.deepEqual(feed(g, point, 450, 650, slides, [0.19, 0.5]), [[650, { direction: -1 }]]);
  assert.deepEqual(feed(g, point, 700, 1300, slides, [0.95, 0.5]), []);
  assert.deepEqual(feed(g, point, 1350, 1950, { page: 'home' }), []);
  assert.deepEqual(feed(g, point, 2000, 2000, { page: 'home' }), [[2000, { direction: 1 }]]);
});
test('duplicate evidence, stale frames and camera-time gaps cannot finish a hold', () => {
  const g = new HoldGestures();
  for (let now = 0; now <= 3500; now += 50) {
    assert.equal(g.update({ ...peace, observation_timestamp: 100 }, [0.5, 0.5], slides, now), null);
  }
  assert.equal(g.progress(3500), null);
  const h = new HoldGestures();
  for (let now = 0; now <= 2900; now += 50) h.update({ ...peace, observation_timestamp: now }, [0.5, 0.5], slides, now);
  assert.equal(h.update({ ...peace, observation_timestamp: 4000 }, [0.5, 0.5], slides, 3000), null);
  assert.equal(h.progress(3000).value, 0);
  assert.equal(h.update({ ...peace, observation_timestamp: 4050, tracking_age_ms: 500 }, [0.5, 0.5], slides, 3050), null);
  assert.equal(h.progress(3050), null);
});
