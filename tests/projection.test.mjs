import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../web/projection.js', import.meta.url), 'utf8');
const { ProjectionMap, homography, transform, MARKER_CENTERS, MARKER_CODES, markerSVG } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const packet = (timestamp, centers = MARKER_CENTERS) => ({ timestamp, markers: centers.map((center, id) => ({ id, center })) });
const close = (actual, expected) => actual.forEach((v, i) => assert.ok(Math.abs(v - expected[i]) < 1e-8));

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
