// Marker IDs are shared with gesture-lab/projection.py. One white quiet cell,
// one black border cell, then a 4x4 payload (1 = white), in an 8x8 square.
export const MARKER_CODES = [0x0f34, 0xf1a0, 0x393b, 0xc704];
export const MARKER_CENTERS = [[0.06, 0.08], [0.94, 0.08], [0.94, 0.92], [0.06, 0.92]];
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
export class ProjectionMap {
  constructor({ mirrored = true, enabled = false } = {}) {
    this.mirrored = mirrored;
    this.enabled = enabled;
    this.revision = 0;
    this.reset();
  }
  reset() {
    this.matrix = null;
    this.centers = null;
    this.pending = null;
    this.stable = 0;
    this.lastScan = null;
    this.lastSeen = -Infinity;
    this.found = 0;
    this.revision++;
  }
  configure({ mirrored = this.mirrored, enabled = this.enabled }) {
    if (mirrored === this.mirrored && enabled === this.enabled) return;
    this.mirrored = mirrored;
    this.enabled = enabled;
    this.reset();
  }
  update(packet, now, frameTimestamp) {
    if (!this.enabled) return;
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
      this.revision++;
    }
  }
  expire(now) {
    if (this.matrix && now - this.lastSeen > 2500) {
      this.matrix = null; this.centers = null; this.pending = null; this.stable = 0; this.revision++;
    }
  }
  get calibrated() { return this.enabled && this.matrix !== null; }
  get status() {
    if (!this.enabled) return 'Manual alignment';
    if (this.calibrated) return this.found === 4 && this.stable >= 3 ? 'Aligned to projection' : 'Corners obscured — holding alignment';
    return `Finding corners (${this.found}/4) — manual alignment`;
  }
  point(x, y, cameraX, cameraY) {
    if (this.calibrated) return transform(this.matrix, cameraX, cameraY);
    return Number.isFinite(x) && Number.isFinite(y) ? [this.mirrored ? 1 - x : x, y] : null;
  }
  swipe(pointer) {
    if (this.calibrated) {
      const ends = pointer.camera_swipe;
      if (!Array.isArray(ends) || ends.length !== 2 || !ends.every(pair)) return 0;
      const a = transform(this.matrix, ...ends[0]), b = transform(this.matrix, ...ends[1]);
      if (!a || !b || Math.abs(b[0] - a[0]) < Math.abs(b[1] - a[1])) return 0;
      if ([...a, ...b].some(value => value < 0 || value > 1)) return 0;
      return Math.sign(b[0] - a[0]);
    }
    return pointer.swipe * (this.mirrored ? -1 : 1);
  }
}
