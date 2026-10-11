import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
const source = (await readFile(new URL('../web/hands.js', import.meta.url), 'utf8')).replace(/^import .*projection\.js.*;$/m, '');
const mapping = await import(`data:text/javascript;base64,${Buffer.from(await readFile(new URL('../web/projection.js', import.meta.url), 'utf8')).toString('base64')}`);
async function trackerFixture(preferences = null) {
  let now = 1000, receive;
  let saved = preferences;
  const frames = [], intervals = [], inputs = [], elements = [], arcs = [], keys = [], events = [], listeners = {};
  const context2d = new Proxy({}, { get: (_, key) => (...args) => { if (key === 'arc') arcs.push(args); } });
  const element = tag => {
    const el = { tag, style: {}, dataset: {}, hidden: false, parentElement: null, open: false,
      setAttribute() {}, append(...children) { for (const child of children) child.parentElement = this; },
      addEventListener() {}, showModal() { this.open = true; }, close() { this.open = false; }, remove() { this.parentElement = null; },
      getContext: () => context2d };
    elements.push(el);
    return el;
  };
  const doc = { head: element('head'), body: element('body'), hidden: false, fullscreenElement: null,
    createElement: element, querySelector: selector => selector.startsWith('dialog') ? elements.find(el => el.tag === 'dialog' && el.open) || null : null,
    addEventListener() {}, dispatchEvent(event) { keys.push(event.key); } };
  const win = { innerWidth: 1000, innerHeight: 600, devicePixelRatio: 1,
    WaveBoardDesktop: true,
    WaveBoardNative: Promise.resolve({ hands: { connect(callback) { receive = callback; } }, startHands() {} }),
    WaveBoardInput: { pointer(event) { inputs.push(event); return true; }, hover() {}, suspend() {} },
    addEventListener(type, callback) { listeners[type] = callback; }, dispatchEvent(event) { events.push(event); } };
  vm.runInNewContext(source, { document: doc, window: win, location: { search: '' }, URLSearchParams,
    ...mapping, localStorage: { getItem: () => JSON.stringify(preferences), setItem(key, value) { saved = JSON.parse(value); } },
    performance: { now: () => now }, requestAnimationFrame: cb => frames.push(cb),
    setInterval: cb => intervals.push(cb), setTimeout() {},
    CustomEvent: class { constructor(type, data) { this.type = type; Object.assign(this, data); } },
    KeyboardEvent: class { constructor(type, data) { Object.assign(this, data); } }, console });
  await Promise.resolve();
  const emit = (patch, frame = {}) => receive(JSON.stringify({ type: 'frame', ...frame, pointer: {
    visible: true, down: false, hand: 'right', x: 0.1, y: 0.5, swipe_id: 0, hands: [], ...patch,
  } }));
  const tick = (milliseconds = 16) => { now += milliseconds; const pending = frames.splice(0); pending.forEach(cb => cb(now)); };
  const cursor = elements.find(el => el.className === 'hand-cursor');
  return { emit, tick, inputs, cursor, arcs, keys, events, listeners, elements, controls: win.WaveBoardHands, saved: () => saved,
    status: patch => receive(JSON.stringify({ type: 'status', ...patch })),
    expire(ms = 600) { now += ms; intervals.forEach(cb => cb()); } };
}

test('hand status reports fresh observations and only announces changes', async () => {
  const f = await trackerFixture();
  const states = () => f.events.filter(event => event.type === 'waveboard-hand-status').map(event =>
    [event.detail.connected, event.detail.visible]);
  assert.equal(f.controls.getTrackingStatus().connected, false);
  assert.equal(f.controls.getTrackingStatus().visible, false);
  f.emit({ observed: true });
  f.emit({ observed: true });
  assert.deepEqual(states(), [[true, true]]);
  f.emit({ observed: false, predicted: true });
  f.expire(501);
  assert.deepEqual(states(), [[true, true], [false, false]]);
  f.emit({ visible: false, observed: false });
  assert.deepEqual(states().at(-1), [true, false]);
  f.emit({ observed: true });
  f.status({ level: 'error', message: 'Camera unavailable' });
  assert.deepEqual(states().at(-1), [false, false]);
});

test('lost-hand notice requires a real hand, waits two seconds, and clears on return', async () => {
  const f = await trackerFixture();
  const notice = f.elements.find(element => element.className === 'hand-notice');
  f.expire(3000);
  assert.equal(notice.hidden, true, 'mouse-only users are never prompted to show a hand');
  f.emit({ observed: false, predicted: true });
  f.expire(3000);
  assert.equal(notice.hidden, true, 'predicted positions cannot establish a real hand');
  f.emit({ observed: true });
  f.emit({ visible: false, observed: false });
  f.expire(1900);
  assert.equal(notice.hidden, true);
  f.expire(100);
  assert.equal(notice.hidden, false);
  assert.equal(notice.textContent, 'Show your hand to continue');
  f.emit({ observed: true });
  assert.equal(notice.hidden, true);
});

test('calibration supplies its own hand guidance and suppresses the lost-hand notice', async () => {
  const f = await trackerFixture({ projectorMode: true });
  const notice = f.elements.find(element => element.className === 'hand-notice');
  f.emit({ observed: true });
  f.expire(2000);
  assert.equal(notice.hidden, false);
  f.controls.startCalibration();
  f.expire(2000);
  assert.equal(notice.hidden, true);
  f.elements.find(element => element.className === 'button secondary calibration-cancel').onclick();
  assert.equal(notice.hidden, false);
  assert.equal(notice.parentElement.tag, 'body', 'notice survives closing the calibration dialog');
});
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

test('default mode preserves the original skeleton, click and swipe orientation', async () => {
  const f = await trackerFixture();
  assert.equal(f.controls.getSettings().enabled, false);
  const hand = { id: 'right', primary: true, points: Array.from({ length: 21 }, () => [0.2, 0.4]) };
  f.emit({ x: 0.2, y: 0.4, hands: [hand] }); f.tick();
  assert.equal(f.arcs[0][0], 200);
  f.emit({ x: 0.2, y: 0.4, down: true });
  assert.equal(f.inputs.find(e => e.type === 'down').x, 200);
  f.emit({ swipe_id: 1, swipe: 1 });
  assert.deepEqual(f.keys, ['ArrowLeft']);
});

test('projector mode reverses skeleton, click and swipe together', async () => {
  const f = await trackerFixture({ projectorMode: true });
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
  f.controls.configure({ enabled: true });
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
  const f = await trackerFixture({ projectorMode: true });
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
  const f = await trackerFixture({ projectorMode: true });
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
  const f = await trackerFixture({ projectorMode: true });
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

function fingertipPacket(point, down) {
  return { down, observed: true, camera_x: 0.01, camera_y: 0.01, hands: [{
    id: 'right', primary: true, observed: true, pinch: down,
    points: Array.from({ length: 21 }, () => [0.01, 0.01]),
    camera_points: Array.from({ length: 21 }, () => point),
  }] };
}
const handCamera = ([x, y]) => [0.15 + 1.1 * (x - 0.15), y];
function fitHand(f) {
  let timestamp = 1000;
  f.controls.configure({ enabled: true });
  f.controls.startCalibration();
  for (const point of mapping.HAND_TARGETS) {
    f.emit(fingertipPacket(handCamera(point), false), { timestamp });
    for (const offset of [100, 300, 500, 700]) {
      f.tick(200);
      f.emit(fingertipPacket(handCamera(point), true), { timestamp: timestamp + offset });
    }
    timestamp += 800;
  }
}

test('guided fit consumes pinches, persists map, and uses the calibrated fingertip for input and skeleton', async () => {
  const f = await trackerFixture();
  fitHand(f);
  assert.equal(f.controls.getSettings().handCalibrated, true);
  assert.equal(f.inputs.length, 0, 'target captures cannot click workspace');
  assert.equal(f.elements.some(el => el.tag === 'dialog' && el.open), false);
  assert.equal(f.saved().calibration.source.length, 4);
  // The last capture is still pinched. Require a release before normal input.
  f.emit(fingertipPacket(handCamera([0.85, 0.5]), true));
  assert.equal(f.inputs.length, 0);
  f.emit(fingertipPacket(handCamera([0.85, 0.5]), false)); f.tick();
  f.emit(fingertipPacket(handCamera([0.85, 0.5]), true)); f.tick();
  assert.ok(Math.abs(f.inputs.find(e => e.type === 'down').x - 850) < 1e-6);
  assert.ok(Math.abs(f.arcs.at(-1)[0] - 850) < 1e-6);
  const restored = await trackerFixture(f.saved());
  assert.equal(restored.controls.getSettings().handCalibrated, true);
  restored.listeners.resize();
  assert.equal(restored.controls.getSettings().handCalibrated, false);
  assert.equal(restored.saved().calibration, null);
});

test('cancelled calibration keeps prior fit and camera geometry changes invalidate it', async () => {
  const f = await trackerFixture();
  fitHand(f);
  f.controls.startCalibration();
  f.elements.find(el => el.className === 'button secondary calibration-cancel' && el.parentElement.open).onclick();
  assert.equal(f.controls.getSettings().handCalibrated, true);
  f.emit(fingertipPacket(handCamera([0.5, 0.5]), false), { camera: { width: 1280, height: 720 } });
  f.emit(fingertipPacket(handCamera([0.5, 0.5]), false), { camera: { width: 640, height: 480 } });
  assert.equal(f.controls.getSettings().handCalibrated, false);
  assert.equal(f.saved().calibration, null);
});

test('open-hand swipes during calibration never replay into the workspace', async () => {
  const f = await trackerFixture({ projectorMode: true });
  f.emit({ swipe_id: 0 });
  f.controls.startCalibration();
  f.emit({ ...fingertipPacket([0.2, 0.2], false), swipe_id: 1, swipe: 1 }, { timestamp: 1000 });
  f.elements.find(el => el.className === 'button secondary calibration-cancel' && el.parentElement.open).onclick();
  f.emit({ swipe_id: 1, swipe: 1 });
  assert.deepEqual(f.keys, []);
});

test('turning projector mode off restores original coordinates and retains the fit for later', async () => {
  const f = await trackerFixture();
  fitHand(f);
  const fitted = f.saved().calibration;
  f.controls.configure({ enabled: false });
  assert.equal(f.controls.getSettings().handCalibrated, false);
  assert.equal(f.saved().projectorMode, false);
  assert.deepEqual(f.saved().calibration, fitted);
  const hand = { id: 'right', primary: true, points: Array.from({ length: 21 }, () => [0.2, 0.4]),
    camera_points: Array.from({ length: 21 }, () => handCamera([0.85, 0.5])) };
  f.emit({ x: 0.3, y: 0.6, camera_x: 0.99, camera_y: 0.99, hands: [hand] }); f.tick();
  assert.equal(f.arcs.at(-1)[0], 200);
  f.emit({ x: 0.3, y: 0.6, down: true, hands: [hand] });
  assert.equal(f.inputs.find(e => e.type === 'down').x, 300, 'off uses the original midpoint cursor instead of calibrated fingertip');
  f.emit({ swipe_id: 1, swipe: 1 });
  assert.deepEqual(f.keys, ['ArrowLeft']);
  const restoredOff = await trackerFixture(f.saved());
  assert.equal(restoredOff.controls.getSettings().enabled, false);
  assert.equal(restoredOff.controls.getSettings().handCalibrated, false);
  restoredOff.controls.configure({ enabled: true });
  assert.equal(restoredOff.controls.getSettings().handCalibrated, true);
  restoredOff.emit(fingertipPacket(handCamera([0.85, 0.5]), false)); restoredOff.tick();
  restoredOff.emit(fingertipPacket(handCamera([0.85, 0.5]), true));
  assert.ok(Math.abs(restoredOff.inputs.find(e => e.type === 'down').x - 850) < 1e-6);
});

test('legacy preferences migrate projection intent but never enable mode for an old mirror setting alone', async () => {
  for (const mirrored of [true, false]) {
    const original = await trackerFixture({ mirrored });
    assert.equal(original.controls.getSettings().enabled, false);
  }
  const legacy = await trackerFixture({ enabled: true, mirrored: false });
  assert.equal(legacy.controls.getSettings().enabled, true);
  assert.equal(legacy.controls.getSettings().mirrored, true);
  const fitted = await trackerFixture();
  fitHand(fitted);
  const calibration = fitted.saved().calibration;
  const legacyFit = await trackerFixture({ enabled: false, mirrored: false, calibration });
  assert.equal(legacyFit.controls.getSettings().enabled, true);
  assert.equal(legacyFit.controls.getSettings().handCalibrated, true);
  const explicitlyOff = await trackerFixture({ projectorMode: false, enabled: true, mirrored: true, calibration });
  assert.equal(explicitlyOff.controls.getSettings().enabled, false);
  assert.equal(explicitlyOff.controls.getSettings().handCalibrated, false);
});

test('calibration cannot start outside projector mode and disabling mode cancels an active pass', async () => {
  const f = await trackerFixture();
  f.controls.startCalibration();
  assert.equal(f.elements.some(el => el.tag === 'dialog' && el.open), false);
  fitHand(f);
  const fitted = f.saved().calibration;
  f.controls.startCalibration();
  assert.equal(f.elements.some(el => el.tag === 'dialog' && el.open), true);
  f.controls.configure({ enabled: false });
  assert.equal(f.elements.some(el => el.tag === 'dialog' && el.open), false);
  assert.equal(f.controls.getSettings().handCalibrated, false);
  assert.deepEqual(f.saved().calibration, fitted);
  f.emit({ down: true, x: 0.3 });
  assert.equal(f.inputs.length, 0, 'held calibration pinch cannot activate the normal workspace');
  f.emit({ down: false, x: 0.3 });
  f.emit({ down: true, x: 0.3 });
  assert.equal(f.inputs.find(e => e.type === 'down').x, 300);
});
