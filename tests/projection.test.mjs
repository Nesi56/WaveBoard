import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../web/projection.js', import.meta.url), 'utf8');
const { ProjectionMap, HandCalibration, HAND_TARGETS, homography, transform, MARKER_CENTERS, MARKER_CODES, markerSVG } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const packet = (timestamp, centers = MARKER_CENTERS) => ({ timestamp, markers: centers.map((center, id) => ({ id, center })) });
const close = (actual, expected) => actual.forEach((v, i) => assert.ok(Math.abs(v - expected[i]) < 1e-8));

test('projector mode alone controls fallback mirroring and swipes, with the original behavior by default', () => {
  const map = new ProjectionMap();
  assert.equal(map.enabled, false);
  assert.equal(map.mirrored, false);
  close(map.point(0.2, 0.4, 0.9, 0.8), [0.2, 0.4]);
  assert.equal(map.swipe({ swipe: 1 }), 1);
  map.configure({ enabled: true });
  assert.equal(map.mirrored, true);
  close(map.point(0.2, 0.4, 0.9, 0.8), [0.8, 0.4]);
  assert.equal(map.swipe({ swipe: 1 }), -1);
  map.configure({ mirrored: false });
  assert.equal(map.mirrored, true, 'the removed independent mirror option cannot override the mode');
  map.configure({ enabled: false });
  close(map.point(0.2, 0.4), [0.2, 0.4]);
  assert.equal(map.swipe({ swipe: 1 }), 1);
  for (const t of [0, 500, 1000]) map.update(packet(t), t, t);
  assert.equal(map.calibrated, false, 'marker observations are inactive outside projector mode');
});

test('four known correspondences undo an angled camera view and reflection', () => {
  const projection = [-0.65, 0.08, 0.85, 0.03, 0.68, 0.1, 0.12, 0.09];
  const camera = MARKER_CENTERS.map(p => transform(projection, ...p));
  const inverse = homography(camera);
  for (const point of [...MARKER_CENTERS, [0.5, 0.5], [0.2, 0.7], [1, 0]])
    close(transform(inverse, ...transform(projection, ...point)), point);
});

test('invalid, crossed and collapsed quadrilaterals do not calibrate', () => {
  assert.equal(homography([[0, 0], [1, 1], [1, 0], [0, 1]]), null);
  assert.equal(homography([[0, 0], [1, 0], [1, 0.001], [0, 0.001]]), null);
  assert.equal(homography([[0, 0], [1, 0], [NaN, 1], [0, 1]]), null);
});

test('lock requires three distinct stable scans, not repeated frame packets', () => {
  const map = new ProjectionMap({ enabled: true });
  for (let i = 0; i < 10; i++) map.update(packet(0), i * 20, i * 20);
  assert.equal(map.calibrated, false);
  map.update(packet(500), 500, 500);
  assert.equal(map.calibrated, false);
  map.update(packet(1000), 1000, 1000);
  assert.equal(map.calibrated, true);
  close(map.point(0.1, 0.1, 0.7, 0.6), [0.7, 0.6]);
});

test('missing corners hold briefly, expire and require a new stable lock', () => {
  const map = new ProjectionMap({ enabled: true });
  for (const t of [0, 500, 1000]) map.update(packet(t), t, t);
  map.update({ timestamp: 1500, markers: [] }, 1500, 1500);
  assert.match(map.status, /holding/);
  map.expire(3501);
  assert.equal(map.calibrated, false);
  close(map.point(0.2, 0.4, 0.6, 0.6), [0.8, 0.4]);
  map.update(packet(4000), 4000, 4000);
  assert.equal(map.calibrated, false);
});

test('intentionally hidden borders retain alignment and preserve remaining grace after menus close', () => {
  const map = new ProjectionMap({ enabled: true });
  for (const t of [0, 500, 1000]) map.update(packet(t), t, t);
  const revision = map.revision;
  map.setBordersPaused(true, 1500);
  map.setBordersPaused(true, 2000); // Repeated UI checks must not restart the pause.
  assert.equal(map.status, 'Screen alignment held');
  const reflected = MARKER_CENTERS.map(([x, y]) => [1 - x, y]);
  for (const t of [2000, 2500, 3000]) map.update(packet(t, reflected), t, t);
  map.expire(101500);
  assert.equal(map.revision, revision);
  close(map.cameraPoint(0.2, 0.5), [0.2, 0.5]);
  map.setBordersPaused(false, 101500);
  assert.equal(map.lastSeen, 101000);
  assert.equal(map.pending, null);
  assert.equal(map.stable, 0);
  assert.equal(map.lastScan, null);
  map.setBordersPaused(false, 102000); // Repeated resume checks cannot extend grace.
  map.expire(103500);
  assert.equal(map.calibrated, true);
  assert.equal(map.revision, revision);
  map.expire(103501);
  assert.equal(map.calibrated, false);
});

test('resumed border scans require three fresh observations and never replace a hand calibration', () => {
  const map = new ProjectionMap({ enabled: true });
  for (const t of [0, 500, 1000]) map.update(packet(t), t, t);
  const reflected = MARKER_CENTERS.map(([x, y]) => [1 - x, y]);
  map.setBordersPaused(true, 1000);
  map.setBordersPaused(false, 10000);
  for (const t of [10000, 10500]) map.update(packet(t, reflected), t, t);
  close(map.cameraPoint(0.2, 0.5), [0.2, 0.5]);
  map.update(packet(11000, reflected), 11000, 11000);
  close(map.cameraPoint(0.2, 0.5), [0.8, 0.5]);
  map.setHandCalibration(HAND_TARGETS.slice(0, 4));
  map.setBordersPaused(true, 11500);
  assert.equal(map.status, 'Hand position calibrated');
  map.expire(100000);
  close(map.cameraPoint(0.2, 0.5), [0.2, 0.5]);
  map.reset();
  assert.equal(map.bordersPaused, false);
  assert.equal(map.bordersPausedAt, null);
  assert.equal(map.calibrated, true);
});

test('bad marker packets and old scans cannot establish calibration', () => {
  const map = new ProjectionMap({ enabled: true });
  for (const markers of [[null], [{ id: 0, center: [NaN, 0.3] }], [packet(0).markers[0], packet(0).markers[0]]])
    assert.doesNotThrow(() => map.update({ timestamp: Math.random(), markers }, 10, 10));
  for (const t of [500, 1000, 1500]) map.update(packet(t), t + 2000, t + 2000);
  assert.equal(map.calibrated, false);
});

test('calibrated swipes use actual transformed endpoints', () => {
  const map = new ProjectionMap({ enabled: true });
  const reflected = MARKER_CENTERS.map(([x, y]) => [1 - x, y]);
  for (const t of [0, 500, 1000]) map.update(packet(t, reflected), t, t);
  assert.equal(map.swipe({ swipe: 1, camera_swipe: [[0.2, 0.5], [0.8, 0.5]] }), -1);
  assert.equal(map.swipe({ swipe: 1 }), 0);
});

test('projected marker payloads match the detector protocol', async () => {
  const backend = await readFile(new URL('../gesture-lab/projection.py', import.meta.url), 'utf8');
  for (let id = 0; id < 4; id++) {
    assert.ok(backend.toLowerCase().includes(`0x${MARKER_CODES[id].toString(16).padStart(4, '0')}`));
    const svg = markerSVG(id);
    assert.match(svg, /viewBox="0 0 8 8"/);
    const bits = [...svg.matchAll(/<rect x="(\d)" y="(\d)" width="1" height="1" fill="white"/g)]
      .reduce((code, [, col, row]) => code | (1 << (15 - (Number(row) - 2) * 4 - Number(col) + 2)), 0);
    assert.equal(bits, MARKER_CODES[id]);
  }
});

const calibrationPointer = (point, pinch = false, extra = {}) => ({
  visible: true, observed: true, predicted: false, hand: 1,
  hands: [{ id: 1, observed: true, predicted: false, pinch, camera_points: Array.from({ length: 21 }, () => [...point]) }],
  ...extra,
});
function captureTarget(calibration, point, start = 0) {
  calibration.update(calibrationPointer(point), start);
  for (const offset of [100, 300, 500, 700]) calibration.update(calibrationPointer(point, true), start + offset);
  return start + 800;
}

test('hand-depth mapping corrects increasing rightward scale error and ignores border updates', () => {
  const map = new ProjectionMap({ enabled: true });
  for (const t of [0, 500, 1000]) map.update(packet(t), t, t);
  const camera = ([x, y]) => [0.15 + 1.1 * (x - 0.15), y];
  close(map.cameraPoint(...camera([0.15, 0.5])), [0.15, 0.5]);
  assert.ok(Math.abs(map.cameraPoint(...camera([0.85, 0.5]))[0] - 0.85) > 0.06);
  const source = HAND_TARGETS.slice(0, 4).map(camera);
  assert.equal(map.setHandCalibration(source), true);
  assert.equal(map.status, 'Hand position calibrated');
  for (const point of [[0.15, 0.5], [0.5, 0.5], [0.85, 0.5], [0.4, 0.7]])
    close(map.point(0, 0, ...camera(point)), point);
  const revision = map.revision;
  const reflected = MARKER_CENTERS.map(([x, y]) => [1 - x, y]);
  for (const t of [1500, 2000, 2500]) map.update(packet(t, reflected), t, t);
  map.expire(10000);
  assert.equal(map.revision, revision);
  close(map.cameraPoint(...camera([0.85, 0.5])), [0.85, 0.5]);
  assert.equal(map.swipe({ camera_swipe: [camera([0.2, 0.5]), camera([0.8, 0.5])] }), 1);
  map.reset();
  assert.equal(map.calibrated, true);
  map.configure({ enabled: false });
  assert.equal(map.calibrated, false);
  assert.equal(map.cameraPoint(0.5, 0.5), null);
  close(map.point(0.2, 0.4, ...camera([0.85, 0.5])), [0.2, 0.4]);
  assert.equal(map.swipe({ swipe: -1, camera_swipe: [camera([0.2, 0.5]), camera([0.8, 0.5])] }), -1);
  assert.deepEqual(map.handCalibration, { source, target: HAND_TARGETS.slice(0, 4) });
  map.configure({ enabled: true });
  assert.equal(map.calibrated, true);
  close(map.point(0.2, 0.4, ...camera([0.85, 0.5])), [0.85, 0.5]);
  map.reset({ clearHand: true });
  assert.equal(map.calibrated, false);
  assert.equal(map.handCalibration, null);
});

test('invalid replacement calibration preserves the previous mapping and clear restores manual mode', () => {
  const map = new ProjectionMap({ enabled: true });
  assert.equal(map.setHandCalibration(HAND_TARGETS.slice(0, 4)), true);
  assert.equal(map.setHandCalibration([[0, 0], [1, 1], [1, 0], [0, 1]]), false);
  assert.equal(map.calibrated, true);
  close(map.cameraPoint(0.2, 0.6), [0.2, 0.6]);
  map.clearHandCalibration();
  assert.equal(map.calibrated, false);
  close(map.point(0.2, 0.6, 0.9, 0.9), [0.8, 0.6]);
});

test('calibration collects four stable fingertip pinches then independently validates center', () => {
  const calibration = new HandCalibration();
  const camera = [-0.65, 0.08, 0.85, 0.03, 0.68, 0.1, 0.12, 0.09];
  let start = 0;
  for (let index = 0; index < HAND_TARGETS.length; index++) {
    const point = transform(camera, ...HAND_TARGETS[index]);
    start = captureTarget(calibration, point, start);
    assert.equal(calibration.done, index === 4);
    assert.equal(calibration.error, null);
  }
  assert.equal(calibration.source.length, 4);
  for (const point of [[0.5, 0.5], [0.3, 0.4], [0.8, 0.7]])
    close(transform(calibration.matrix, ...transform(camera, ...point)), point);
});

test('calibration requires an observed release before each capture', () => {
  const calibration = new HandCalibration();
  for (const t of [0, 200, 400, 600, 800]) calibration.update(calibrationPointer(HAND_TARGETS[0], true), t);
  assert.equal(calibration.index, 0);
  const next = captureTarget(calibration, HAND_TARGETS[0], 1000);
  assert.equal(calibration.index, 1);
  for (const t of [next, next + 200, next + 400, next + 600])
    calibration.update(calibrationPointer(HAND_TARGETS[1], true), t);
  assert.equal(calibration.index, 1);
  captureTarget(calibration, HAND_TARGETS[1], next + 800);
  assert.equal(calibration.index, 2);
});

test('capture uses only the primary hand index fingertip, independent of the cursor and other joints', () => {
  const calibration = new HandCalibration();
  const point = HAND_TARGETS[0];
  const pointer = pinch => {
    const data = calibrationPointer([0.9, 0.9], pinch);
    data.x = data.camera_x = 0.8;
    data.y = data.camera_y = 0.8;
    data.hands[0].camera_points[8] = point;
    data.hands.unshift({ id: 2, observed: true, predicted: false, pinch,
      camera_points: Array.from({ length: 21 }, () => [0.05, 0.05]) });
    return data;
  };
  calibration.update(pointer(false), 0);
  for (const t of [100, 300, 500, 700]) calibration.update(pointer(true), t);
  assert.equal(calibration.index, 1);
  close(calibration.source[0], point);
});

test('duplicate, flow and predicted frames cannot provide capture evidence', () => {
  const calibration = new HandCalibration();
  const point = HAND_TARGETS[0];
  calibration.update(calibrationPointer(point), 0);
  calibration.update(calibrationPointer(point, true), 100);
  for (let i = 0; i < 20; i++) calibration.update(calibrationPointer(point, true), 100);
  assert.equal(calibration.samples.length, 1);
  for (const t of [200, 300, 400, 500, 600, 700])
    calibration.update(calibrationPointer(point, true, { observed: false, tracking_source: 'flow' }), t);
  assert.equal(calibration.index, 0);
  assert.equal(calibration.armed, false);
  calibration.update(calibrationPointer(point, true), 800);
  assert.equal(calibration.progress, 0);
  calibration.update(calibrationPointer(point), 900);
  calibration.update(calibrationPointer(point, true), 1000);
  calibration.update(calibrationPointer(point, true, { predicted: true, observed: false }), 1100);
  assert.equal(calibration.armed, false);
  assert.equal(calibration.progress, 0);
});

test('identity changes and observation gaps discard a partly captured hold', () => {
  for (const loss of ['identity', 'gap']) {
    const calibration = new HandCalibration();
    const point = HAND_TARGETS[0];
    calibration.update(calibrationPointer(point), 0);
    calibration.update(calibrationPointer(point, true), 100);
    calibration.update(calibrationPointer(point, true), 300);
    const changed = calibrationPointer(point, true);
    if (loss === 'identity') { changed.hand = 2; changed.hands[0].id = 2; }
    calibration.update(changed, loss === 'identity' ? 500 : 800);
    assert.equal(calibration.index, 0);
    assert.equal(calibration.progress, 0);
    assert.equal(calibration.armed, false);
  }
});

test('moving during a hold restarts stability timing instead of averaging across a drag', () => {
  const calibration = new HandCalibration();
  const point = HAND_TARGETS[0];
  calibration.update(calibrationPointer(point), 0);
  calibration.update(calibrationPointer(point, true), 100);
  calibration.update(calibrationPointer(point, true), 300);
  const moved = [point[0] + 0.05, point[1]];
  for (const t of [500, 700, 900]) calibration.update(calibrationPointer(moved, true), t);
  assert.equal(calibration.index, 0);
  calibration.update(calibrationPointer(moved, true), 1100);
  assert.equal(calibration.index, 1);
  close(calibration.source[0], moved);
});

test('explicit interruption requires a new observed release after packet silence', () => {
  const calibration = new HandCalibration();
  const point = HAND_TARGETS[0];
  calibration.update(calibrationPointer(point), 0);
  calibration.update(calibrationPointer(point, true), 100);
  calibration.update(calibrationPointer(point, true), 300);
  calibration.interrupt('Tracker paused.');
  assert.equal(calibration.message, 'Tracker paused.');
  assert.equal(calibration.progress, 0);
  for (const t of [500, 700, 900, 1100]) calibration.update(calibrationPointer(point, true), t);
  assert.equal(calibration.index, 0);
  captureTarget(calibration, point, 1200);
  assert.equal(calibration.index, 1);
});

test('inconsistent center and collapsed corner captures fail without accepting a map', () => {
  const centerFailure = new HandCalibration();
  let start = 0;
  for (const point of HAND_TARGETS.slice(0, 4)) start = captureTarget(centerFailure, point, start);
  assert.ok(centerFailure.matrix);
  captureTarget(centerFailure, [0.62, 0.5], start);
  assert.equal(centerFailure.done, false);
  assert.equal(centerFailure.matrix, null);
  assert.match(centerFailure.error, /Center did not line up/);

  const collapsed = new HandCalibration();
  start = 0;
  for (let i = 0; i < 4; i++) start = captureTarget(collapsed, [0.5, 0.5], start);
  assert.equal(collapsed.done, false);
  assert.equal(collapsed.matrix, null);
  assert.match(collapsed.error, /usable shape/);
});
