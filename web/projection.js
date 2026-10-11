// Marker IDs are shared with gesture-lab/projection.py. One white quiet cell,
// one black border cell, then a 4x4 payload (1 = white), in an 8x8 square.
export const MARKER_CODES = [0x0f34, 0xf1a0, 0x393b, 0xc704];
export const MARKER_CENTERS = [[0.06, 0.08], [0.94, 0.08], [0.94, 0.92], [0.06, 0.92]];
// Four correspondences at the user's working hand depth, then an independent
// center check. Camera border markers alone describe the screen's depth.
export const HAND_TARGETS = [[0.15, 0.22], [0.85, 0.22], [0.85, 0.78], [0.15, 0.78], [0.5, 0.5]];
export function markerSVG(id) {
  let cells = '';
  for (let row = 0; row < 4; row++) for (let col = 0; col < 4; col++) {
    if ((MARKER_CODES[id] >> (15 - row * 4 - col)) & 1)
      cells += `<rect x="${col + 2}" y="${row + 2}" width="1" height="1" fill="white"/>`;
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8" shape-rendering="crispEdges" aria-hidden="true"><rect width="8" height="8" fill="white"/><rect x="1" y="1" width="6" height="6" fill="black"/>${cells}</svg>`;
}

const pair = p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite);
function validQuad(points) {
  if (!Array.isArray(points) || points.length !== 4 || !points.every(pair)) return false;
  let sign = 0, area = 0;
  for (let i = 0; i < 4; i++) {
    const a = points[i], b = points[(i + 1) % 4], c = points[(i + 2) % 4];
    if (a.some(v => v < 0 || v > 1)) return false;
    const cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]);
    if (Math.abs(cross) < 0.005 || (sign && Math.sign(cross) !== sign)) return false;
    sign = Math.sign(cross);
    area += a[0] * b[1] - a[1] * b[0];
  }
  return Math.abs(area) / 2 >= 0.04;
}

export function transform(matrix, x, y) {
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  const w = matrix[6] * x + matrix[7] * y + 1;
  if (Math.abs(w) < 1e-8) return null;
  const p = [(matrix[0] * x + matrix[1] * y + matrix[2]) / w,
    (matrix[3] * x + matrix[4] * y + matrix[5]) / w];
  return p.every(Number.isFinite) ? p : null;
}

export function homography(source, destination = MARKER_CENTERS) {
  if (!validQuad(source) || !validQuad(destination)) return null;
  // Solve the eight projective coefficients with partial-pivot elimination.
  const rows = [];
  source.forEach(([x, y], i) => {
    const [u, v] = destination[i];
    rows.push([x, y, 1, 0, 0, 0, -u * x, -u * y, u]);
    rows.push([0, 0, 0, x, y, 1, -v * x, -v * y, v]);
  });
  for (let col = 0; col < 8; col++) {
    let pivot = col;
    for (let row = col + 1; row < 8; row++) if (Math.abs(rows[row][col]) > Math.abs(rows[pivot][col])) pivot = row;
    if (Math.abs(rows[pivot][col]) < 1e-9) return null;
    [rows[col], rows[pivot]] = [rows[pivot], rows[col]];
    const divisor = rows[col][col];
    for (let j = col; j <= 8; j++) rows[col][j] /= divisor;
    for (let row = 0; row < 8; row++) if (row !== col) {
      const factor = rows[row][col];
      for (let j = col; j <= 8; j++) rows[row][j] -= factor * rows[col][j];
    }
  }
  const result = rows.map(row => row[8]);
  // A projective horizon through the screen would make points jump to infinity.
  const denominators = source.map(([x, y]) => result[6] * x + result[7] * y + 1);
  if (denominators.some(w => Math.abs(w) < 1e-6 || Math.sign(w) !== Math.sign(denominators[0]))) return null;
  return result;
}

const delta = (a, b) => Math.max(...a.map((p, i) => Math.hypot(p[0] - b[i][0], p[1] - b[i][1])));
export class HandCalibration {
  constructor() {
    this.index = 0;
    this.progress = 0;
    this.message = 'Open your hand, then pinch and hold your index fingertip at the target.';
    this.done = false;
    this.error = null;
    this.source = [];
    this.matrix = null;
    this.identity = null;
    this.armed = false;
    this.samples = [];
    this.lastTimestamp = -Infinity;
    this.lastObserved = -Infinity;
  }
  resetHold(message) {
    this.samples = [];
    this.progress = 0;
    this.armed = false;
    this.message = message;
  }
  fail(message) {
    this.error = this.message = message;
    this.matrix = null;
    this.resetHold(message);
  }
  interrupt(message = 'Hand tracking lost. Open your hand, then pinch again at the target.') {
    if (!this.done && !this.error) {
      this.resetHold(message);
      this.lastObserved = -Infinity;
    }
    return this;
  }
  update(pointer, timestamp) {
    if (this.done || this.error || !Number.isFinite(timestamp) || timestamp <= this.lastTimestamp) return this;
    this.lastTimestamp = timestamp;
    const hand = Array.isArray(pointer?.hands) ? pointer.hands.find(hand => hand && hand.id === pointer.hand) : null;
    const point = hand?.camera_points?.[8];
    if (!pointer?.visible || pointer.cancelled || !hand || typeof hand.pinch !== 'boolean' || !pair(point) || point.some(v => v < 0 || v > 1) ||
        pointer.predicted || hand.predicted) {
      this.resetHold('Hand tracking lost. Open your hand, then pinch again at the target.');
      return this;
    }
    if (this.identity !== null && this.identity !== hand.id) {
      this.resetHold('Hand changed. Open your hand, then pinch again at the target.');
    }
    this.identity = hand.id;
    if (timestamp - this.lastObserved > 300) {
      this.resetHold('Open your hand, then pinch and hold at the target.');
    }
    // Flow can keep visuals moving between detector results, but must never
    // supply evidence for capture, release, or a new pinch.
    if (pointer.observed !== true || hand.observed !== true || pointer.tracking_source === 'flow') return this;
    this.lastObserved = timestamp;
    if (!hand.pinch) {
      this.samples = [];
      this.progress = 0;
      this.armed = true;
      this.message = 'Pinch and hold your index fingertip at the target.';
      return this;
    }
    if (!this.armed) {
      this.message = 'Open your hand before capturing the next target.';
      return this;
    }
    if (this.samples.length && Math.hypot(point[0] - this.samples[0].point[0], point[1] - this.samples[0].point[1]) > 0.015) {
      this.samples = [];
    }
    this.samples.push({ point: [...point], timestamp });
    const elapsed = timestamp - this.samples[0].timestamp;
    this.progress = Math.min(1, elapsed / 600);
    this.message = 'Hold still…';
    if (elapsed < 600 || this.samples.length < 4) return this;
    const measured = [0, 1].map(axis => this.samples.reduce((sum, sample) => sum + sample.point[axis], 0) / this.samples.length);
    if (this.index < 4) {
      this.source.push(measured);
      this.index++;
      this.resetHold('Target saved. Open your hand and move to the next target.');
      if (this.index === 4) {
        this.matrix = homography(this.source, HAND_TARGETS.slice(0, 4));
        if (!this.matrix) this.fail('Targets did not form a usable shape. Restart and keep your hand at the same depth.');
      }
      return this;
    }
    const center = transform(this.matrix, ...measured);
    if (!center || Math.hypot(center[0] - 0.5, center[1] - 0.5) > 0.04) {
      this.fail('Center did not line up. Restart and hold your hand at the same depth for all five targets.');
      return this;
    }
    this.done = true;
    this.progress = 1;
    this.message = 'Hand position calibrated';
    return this;
  }
}

export class ProjectionMap {
  constructor({ enabled = false } = {}) {
    this.enabled = enabled;
    this.revision = 0;
    this.handMatrix = null;
    this.handCalibration = null;
    this.reset();
  }
  reset({ clearHand = false } = {}) {
    if (clearHand) {
      this.handMatrix = null;
      this.handCalibration = null;
    }
    this.matrix = null;
    this.centers = null;
    this.pending = null;
    this.stable = 0;
    this.lastScan = null;
    this.lastSeen = -Infinity;
    this.found = 0;
    this.bordersPaused = false;
    this.bordersPausedAt = null;
    this.revision++;
  }
  setBordersPaused(paused, now) {
    paused = Boolean(paused);
    if (paused === this.bordersPaused) return;
    if (paused) {
      this.bordersPausedAt = Number.isFinite(now) ? now : null;
    } else {
      // Menus deliberately hide the markers. Preserve the remaining grace
      // period while they are hidden, then require fresh stable scans.
      if (Number.isFinite(this.lastSeen) && Number.isFinite(this.bordersPausedAt) && Number.isFinite(now))
        this.lastSeen += Math.max(0, now - this.bordersPausedAt);
      this.bordersPausedAt = null;
      this.pending = null;
      this.stable = 0;
      this.lastScan = null;
    }
    this.bordersPaused = paused;
  }
  setHandCalibration(source, target = HAND_TARGETS.slice(0, 4)) {
    const matrix = homography(source, target);
    if (!matrix) return false;
    this.handMatrix = matrix;
    this.handCalibration = { source: source.map(p => [...p]), target: target.map(p => [...p]) };
    this.revision++;
    return true;
  }
  clearHandCalibration() {
    if (!this.handMatrix) return;
    this.handMatrix = null;
    this.handCalibration = null;
    this.revision++;
  }
  configure({ enabled = this.enabled }) {
    enabled = Boolean(enabled);
    if (enabled === this.enabled) return;
    this.enabled = enabled;
    this.reset();
  }
  update(packet, now, frameTimestamp) {
    if (!this.enabled || this.bordersPaused) return;
    this.expire(now);
    if (!packet || !Number.isFinite(packet.timestamp) || packet.timestamp === this.lastScan) return;
    this.lastScan = packet.timestamp;
    if (!Number.isFinite(frameTimestamp) || frameTimestamp - packet.timestamp < 0 || frameTimestamp - packet.timestamp > 1200) return;
    const markers = packet.markers;
    const points = new Array(4);
    if (Array.isArray(markers) && markers.length <= 4) for (const marker of markers) {
      if (!marker || typeof marker !== 'object' || !Number.isInteger(marker.id) || marker.id < 0 || marker.id > 3 || points[marker.id] || !pair(marker.center)) {
        this.found = 0; this.pending = null; this.stable = 0; return;
      }
      points[marker.id] = marker.center;
    }
    this.found = points.filter(Boolean).length;
    if (this.found !== 4 || !validQuad(points)) { this.pending = null; this.stable = 0; return; }
    if (this.pending && delta(points, this.pending) < 0.012) this.stable++;
    else { this.pending = points; this.stable = 1; }
    if (this.stable < 3) return;
    const matrix = homography(points);
    if (!matrix) return;
    this.lastSeen = now;
    if (!this.centers || delta(points, this.centers) > 0.004) {
      this.matrix = matrix;
      this.centers = points;
      if (!this.handMatrix) this.revision++;
    }
  }
  expire(now) {
    if (this.bordersPaused) return;
    if (this.matrix && now - this.lastSeen > 2500) {
      this.matrix = null; this.centers = null; this.pending = null; this.stable = 0;
      if (!this.handMatrix) this.revision++;
    }
  }
  get mirrored() { return this.enabled; }
  get handCalibrated() { return this.enabled && this.handMatrix !== null; }
  get calibrated() { return this.enabled && (this.handMatrix !== null || this.matrix !== null); }
  get status() {
    if (!this.enabled) return 'Projector mode off';
    if (this.handMatrix) return 'Hand position calibrated';
    if (this.matrix && this.bordersPaused) return 'Screen alignment held';
    if (this.calibrated) return this.found === 4 && this.stable >= 3 ? 'Aligned to projection' : 'Corners obscured — holding alignment';
    return `Finding corners (${this.found}/4) — manual alignment`;
  }
  cameraPoint(x, y) {
    const matrix = this.enabled ? this.handMatrix || this.matrix : null;
    return matrix ? transform(matrix, x, y) : null;
  }
  point(x, y, cameraX, cameraY) {
    if (this.calibrated) return this.cameraPoint(cameraX, cameraY);
    return Number.isFinite(x) && Number.isFinite(y) ? [this.mirrored ? 1 - x : x, y] : null;
  }
  swipe(pointer) {
    if (this.calibrated) {
      const ends = pointer.camera_swipe;
      if (!Array.isArray(ends) || ends.length !== 2 || !ends.every(pair)) return 0;
      const a = this.cameraPoint(...ends[0]), b = this.cameraPoint(...ends[1]);
      if (!a || !b || Math.abs(b[0] - a[0]) < Math.abs(b[1] - a[1])) return 0;
      if ([...a, ...b].some(value => value < 0 || value > 1)) return 0;
      return Math.sign(b[0] - a[0]);
    }
    return pointer.swipe * (this.mirrored ? -1 : 1);
  }
}
