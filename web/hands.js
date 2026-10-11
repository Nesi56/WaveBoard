// Hand control for the WaveBoard workspace.
//
// Receives hand packets from the desktop Qt bridge (legacy browser mode uses a WebSocket),
// draws every tracked hand as a skeleton over the workspace (the camera image is
// never shown), and turns the primary hand into window.WaveBoardInput events:
// a thumb + index pinch presses, drags and releases like a finger on a touch
// screen, and an open-palm swipe acts as the left / right arrow keys (Home cards,
// slides). Without the tracker this module stays idle and quietly retries.

import { ProjectionMap, HandCalibration, HAND_TARGETS, MARKER_CENTERS, markerSVG } from "./projection.js";

let handPreferences = {};
try { handPreferences = JSON.parse(localStorage.getItem("waveboard-hand-alignment") || "{}"); } catch {}
const projection = new ProjectionMap({
  // Migrate an explicitly enabled alignment or saved fit, not the old default mirror.
  enabled: typeof handPreferences?.projectorMode === 'boolean' ? handPreferences.projectorMode :
    handPreferences?.enabled === true || Boolean(handPreferences?.calibration),
});
const savedCalibration = handPreferences?.calibration;
if (savedCalibration?.width === window.innerWidth && savedCalibration?.height === window.innerHeight)
  projection.setHandCalibration(savedCalibration.source, savedCalibration.target);

const params = new URLSearchParams(location.search);
const PORT = Number(params.get("hands-port")) || 8766;
const STALE_MS = 500;
const RETRY_MS = 3000;
// Joints glide toward each new tracking result, so the skeleton moves at the
// display's frame rate even when the tracker updates 15-25 times a second.
const GLIDE_MS = 30;
const BONES = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11],
  [11, 12], [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [0, 17], [17, 18], [18, 19], [19, 20]];
const PALM = [0, 1, 5, 9, 13, 17];
// Chromium gives the real mouse pointerId 1; a separate id keeps mouse movement
// out of hand strokes. The hand is still the primary pointer.
const HAND_POINTER_ID = 0x48414e44;
const TIPS = new Set([4, 8, 12, 16, 20]);
// The workspace palette (web/styles.css and the welcome slides).
const DEEP = "#304b3b";
const PAPER = "#fffefa";
const SAGE = "#bed1ab";

const style = document.createElement("style");
style.textContent = `
.hand-layer { position: fixed; inset: 0; pointer-events: none; z-index: 2147483647; }
.hand-skeletons { position: absolute; inset: 0; width: 100%; height: 100%; }
.hand-cursor {
  position: fixed; left: 0; top: 0; width: 38px; height: 38px; margin: -19px 0 0 -19px;
  border: 4px solid var(--deep, ${DEEP}); border-radius: 50%;
  background: rgb(255 255 255 / 0.35); box-shadow: 0 0 0 3px rgb(255 255 255 / 0.85);
  transition: background 0.08s;
}
.hand-cursor[data-down="true"] { background: var(--deep, ${DEEP}); }
.hand-cursor[data-tracking="recovering"] { opacity: 0.55; border-style: dashed; }
.projection-marker { position: absolute; width: min(10vw, 14vh); height: min(10vw, 14vh); transform: translate(-50%, -50%); }
.projection-marker svg { display: block; width: 100%; height: 100%; }
body[data-projection-alignment="true"][data-page="home"] .menu-toggle { right: 12%; }
.projection-status { position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%); max-width: 75vw;
  padding: 6px 14px; border-radius: 12px; color: ${DEEP}; background: ${PAPER}; font: 26px/1.2 sans-serif; text-align: center; }
dialog.hand-calibration { position: fixed; inset: 0; width: 100vw; height: 100vh; max-width: none; max-height: none;
  margin: 0; padding: 0; border: 0; border-radius: 0; background: ${PAPER}; color: ${DEEP}; overflow: hidden; }
.hand-calibration h2 { position: absolute; top: 16px; left: 20px; right: 140px; margin: 0; font: bold 30px/1.2 sans-serif; }
.calibration-cancel { position: absolute; top: 12px; right: 12px; min-height: 60px; font-size: 26px; }
.calibration-target { position: absolute; width: 72px; height: 72px; margin: -36px 0 0 -36px;
  border: 5px solid ${DEEP}; border-radius: 50%; box-shadow: 0 0 0 7px #bed1ab; background: white; }
.calibration-target::before, .calibration-target::after { content: ''; position: absolute; background: ${DEEP}; }
.calibration-target::before { width: 4px; height: 20px; left: calc(50% - 2px); top: calc(50% - 10px); }
.calibration-target::after { height: 4px; width: 20px; top: calc(50% - 2px); left: calc(50% - 10px); }
.calibration-help { position: absolute; top: 32%; left: 23%; right: 23%; margin: 0; text-align: center; font: 600 26px/1.25 sans-serif; }
.hand-calibration[data-step="4"] .calibration-help { top: 82px; left: 15%; right: 15%; }
.calibration-progress { position: absolute; left: 25%; width: 50%; bottom: 28px; height: 22px; accent-color: ${DEEP}; }
.calibration-retry { position: absolute; left: 50%; bottom: 24px; transform: translateX(-50%); font-size: 28px; }
.hand-calibration[data-error="true"] .calibration-help { top: 28%; left: 12%; right: 12%; }`;
document.head.append(style);
const layer = document.createElement("div");
layer.className = "hand-layer";
layer.setAttribute("aria-hidden", "true");
const canvas = document.createElement("canvas");
canvas.className = "hand-skeletons";
const cursor = document.createElement("div");
cursor.className = "hand-cursor";
cursor.hidden = true;
const markers = document.createElement("div");
markers.innerHTML = MARKER_CENTERS.map(([x, y], id) =>
  `<div class="projection-marker" style="left:${x * 100}%;top:${y * 100}%">${markerSVG(id)}</div>`).join("");
const projectionStatus = document.createElement("div");
projectionStatus.className = "projection-status";
layer.append(canvas, markers, projectionStatus, cursor);
document.body.append(layer);
const ctx = canvas.getContext("2d");

let pressed = false;
let pressHand = null;
// A press may only start after the tracker has reported an open pinch, so a pinch
// that failed to press (or was cancelled) cannot turn into a press somewhere else.
let armed = true;
let last = { x: 0, y: 0 };
let cursorTarget = null;
let motionAllowed = false;
let pendingMove = false;
let pointerDown = false;
let lastSwipe = null;
let lastFrameAt = 0;
const targets = new Map(); // hand id -> { points (CSS px), primary, pinch }
const shown = new Map();   // hand id -> points currently drawn
let painting = false;
let mappingRevision = projection.revision;
let cameraGeometry = projection.handCalibration ? savedCalibration?.camera || null : null;
let lastProjectionStatus = null;
let calibrationSession = null;

function savePreferences() {
  const calibration = projection.handCalibration ? { ...projection.handCalibration,
    width: window.innerWidth, height: window.innerHeight, camera: cameraGeometry } : null;
  try { localStorage.setItem("waveboard-hand-alignment", JSON.stringify({
    projectorMode: projection.enabled, calibration,
  })); } catch {}
}

function alignmentStatus() {
  const borders = projection.enabled && !projection.handCalibration && !calibrationSession;
  const menu = document.querySelector('#workspace-menu');
  const covered = Boolean(openModal() || (menu && !menu.hidden));
  projection.setBordersPaused(covered || Boolean(calibrationSession), performance.now());
  document.body.dataset.projectionAlignment = String(borders);
  markers.hidden = projectionStatus.hidden = !borders || covered;
  projectionStatus.textContent = projection.status;
  if (lastProjectionStatus !== projection.status) {
    lastProjectionStatus = projection.status;
    window.dispatchEvent(new CustomEvent("waveboard-alignment-status", { detail: projection.status }));
  }
}
function mappingChanged() {
  if (mappingRevision === projection.revision) return;
  mappingRevision = projection.revision;
  // A mapping change must never bend a held stroke or release onto a new button.
  hide();
  shown.clear();
}
window.WaveBoardHands = Object.freeze({
  getSettings: () => ({ mirrored: projection.mirrored, enabled: projection.enabled, status: projection.status,
    handCalibrated: projection.handCalibrated }),
  configure(options) {
    projection.configure(options);
    if (!projection.enabled) finishCalibration();
    mappingChanged();
    alignmentStatus();
    placeLayer();
    savePreferences();
  },
  realign() { projection.reset(); mappingChanged(); alignmentStatus(); },
  startCalibration,
  clearCalibration() { projection.clearHandCalibration(); mappingChanged(); alignmentStatus(); savePreferences(); },
});
alignmentStatus();

const input = (packet) =>
  window.WaveBoardInput?.pointer({ ...packet, pointerId: HAND_POINTER_ID, isPrimary: true }) === true;

function release(type) {
  if (pressed) input({ type, x: last.x, y: last.y });
  pressed = false;
  pressHand = null;
  pendingMove = false;
}

function hideCursor() {
  release("cancel");
  cursor.hidden = true;
  cursorTarget = null;
  motionAllowed = false;
  armed = false;
  window.WaveBoardInput?.suspend();
}

function hide() {
  hideCursor();
  targets.clear();
  paintSoon();
}

function arrowKey(key) {
  document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
}

function openModal() {
  try {
    return document.querySelector("dialog:modal");
  } catch {
    return document.querySelector("dialog[open]"); // browsers without :modal
  }
}

function placeLayer() {
  // Modal dialogs, then full-screen elements, are drawn above everything else. A dialog
  // opened during full screen is above the full-screen element, so it comes first.
  const host = openModal() || document.fullscreenElement || document.body;
  if (layer.parentElement !== host) host.append(layer);
}

function calibrationView() {
  const session = calibrationSession;
  if (!session) return;
  const fit = session.fit;
  session.dialog.dataset.step = String(fit.index);
  session.dialog.dataset.error = String(Boolean(fit.error));
  session.title.textContent = fit.error ? 'Try the targets again' : `Match your hand · ${fit.index + 1} of 5`;
  session.help.textContent = fit.error ? `${fit.error} Open, then pinch to retry.` : fit.message;
  session.retry.hidden = !fit.error;
  session.progress.hidden = Boolean(fit.error);
  session.progress.value = fit.progress;
  session.target.hidden = Boolean(fit.error);
  const target = HAND_TARGETS[Math.min(fit.index, 4)];
  session.target.style.left = `${target[0] * 100}%`;
  session.target.style.top = `${target[1] * 100}%`;
}

function finishCalibration() {
  if (!calibrationSession) return;
  const { dialog } = calibrationSession;
  calibrationSession = null;
  lastSwipe = null; // Open-hand moves between targets are not workspace swipes.
  hide();
  shown.clear();
  dialog.close();
  // Move the overlay out before removing the dialog that owns it.
  placeLayer();
  dialog.remove();
  alignmentStatus();
}

function startCalibration() {
  if (!projection.enabled || calibrationSession) return;
  hide();
  const dialog = document.createElement('dialog');
  dialog.className = 'hand-calibration';
  dialog.setAttribute('aria-label', 'Match your hand position');
  const title = document.createElement('h2');
  const help = document.createElement('p');
  help.className = 'calibration-help';
  help.setAttribute('role', 'status');
  const target = document.createElement('div');
  target.className = 'calibration-target';
  target.setAttribute('aria-hidden', 'true');
  const progress = document.createElement('progress');
  progress.className = 'calibration-progress';
  progress.max = 1;
  progress.setAttribute('aria-label', 'Hold your pinch steady');
  const cancel = document.createElement('button');
  cancel.className = 'button secondary calibration-cancel';
  cancel.textContent = 'Cancel';
  cancel.onclick = finishCalibration;
  const retry = document.createElement('button');
  retry.className = 'button calibration-retry';
  retry.textContent = 'Try again';
  retry.onclick = () => { calibrationSession.fit = new HandCalibration(); calibrationView(); };
  dialog.append(title, help, target, progress, cancel, retry);
  dialog.addEventListener('cancel', event => { event.preventDefault(); finishCalibration(); });
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Enter' && calibrationSession?.fit.error) { event.preventDefault(); retry.onclick(); }
  });
  document.body.append(dialog);
  calibrationSession = { dialog, title, help, target, progress, retry, fit: new HandCalibration(), retryArmed: false };
  dialog.showModal();
  alignmentStatus();
  calibrationView();
  placeLayer();
}

function calibrateFrame(pointer, timestamp) {
  const session = calibrationSession;
  if (!session) return;
  lastFrameAt = performance.now();
  // Calibration pinches never press workspace buttons or draw on the board.
  hide();
  if (session.fit.error) {
    if (pointer.visible && pointer.observed !== false && !pointer.predicted && !pointer.cancelled) {
      if (!pointer.down) session.retryArmed = true;
      else if (session.retryArmed) { session.fit = new HandCalibration(); session.retryArmed = false; }
    }
  } else {
    session.fit.update(pointer, timestamp);
  }
  if (session.fit.done && projection.setHandCalibration(session.fit.source)) {
    mappingChanged();
    savePreferences();
    finishCalibration();
    window.dispatchEvent(new CustomEvent('waveboard-calibration-complete'));
    return;
  }
  calibrationView();
}

function apply(pointer) {
  lastFrameAt = performance.now();
  // QProcess can deliver several camera frames before the display repaints.
  // Consume an unpainted drag point before replacing it so excursions outside
  // a control (or around a stroke corner) are not erased by frame batching.
  if (pressed && pendingMove && cursorTarget) {
    last = { ...cursorTarget };
    input({ type: "move", ...last });
  }
  pendingMove = false;
  const observed = pointer.observed !== false && !pointer.predicted;
  // Optical flow supplies measured camera movement between full landmark
  // detections. It can continue a drag, but cannot invent a pinch or release.
  motionAllowed = !pointer.predicted && (observed || pointer.motion_tracked === true);
  if (pointer.cancelled) {
    release("cancel");
    armed = false;
  }
  const newSwipe = observed && !pointer.cancelled && pointer.swipe_id !== lastSwipe;
  const canSwipe = newSwipe && lastSwipe !== null;
  // Consume even suppressed swipes so they cannot replay on re-entry.
  if (newSwipe) lastSwipe = pointer.swipe_id;
  if (!pointer.visible || document.hidden) return hide();
  const fingertip = pointer.hands?.find(hand => hand.id === pointer.hand)?.camera_points?.[8];
  const mapped = projection.handCalibrated ? (fingertip ? projection.cameraPoint(...fingertip) : null) :
    projection.point(pointer.x, pointer.y, pointer.camera_x, pointer.camera_y);
  placeLayer();
  targets.clear();
  for (const hand of pointer.hands || []) {
    const points = hand.points.map(([x, y], i) => projection.point(x, y, ...(hand.camera_points?.[i] || [])));
    if (points.some(p => !p || p.some(value => Math.abs(value) > 8))) continue;
    if (projection.calibrated && [0, 1].some(axis => points.every(p => p[axis] < 0) || points.every(p => p[axis] > 1))) continue;
    targets.set(hand.id, {
      points: points.map(([x, y]) => [x * window.innerWidth, y * window.innerHeight]),
      primary: hand.primary, pinch: hand.pinch, predicted: hand.predicted,
    });
  }
  // Outside the actual projection is outside the workspace, not an edge click.
  // The other hand can still be visible inside it.
  if (!mapped || (projection.calibrated && mapped.some(value => value < 0 || value > 1))) {
    hideCursor();
    paintSoon();
    return;
  }
  if (canSwipe) {
    const direction = projection.swipe(pointer);
    if (direction) arrowKey(direction < 0 ? "ArrowRight" : "ArrowLeft");
  }
  if (pressed && pointer.hand !== pressHand) {
    release("cancel");
    armed = false;
  }
  cursorTarget = {
    x: Math.min(Math.max(mapped[0] * window.innerWidth, 0), window.innerWidth - 1),
    y: Math.min(Math.max(mapped[1] * window.innerHeight, 0), window.innerHeight - 1),
  };
  if (cursor.hidden) last = { ...cursorTarget };
  cursor.hidden = false;
  cursor.dataset.tracking = pointer.predicted ? "recovering" : "tracked";
  pointerDown = pointer.down;
  if (!observed) window.WaveBoardInput?.suspend();
  if (observed && !pointer.cancelled) {
    if (!pointer.down) {
      if (pressed) {
        last = { ...cursorTarget };
        input({ type: "move", ...last });
      }
      release("up");
      armed = true;
    } else if (!pressed && armed) {
      // Gesture edges use their packet's coordinates, even if hover, press and
      // release all arrived in one bridge read before requestAnimationFrame.
      last = { ...cursorTarget };
      armed = false;
      pressed = input({ type: "down", ...last });
      pressHand = pressed ? pointer.hand : null;
    }
  }
  pendingMove = pressed && motionAllowed;
  paintSoon();
}

function paintSoon() {
  if (!painting) {
    painting = true;
    requestAnimationFrame(paint);
  }
}

let lastPaint = performance.now();
function paint(now) {
  const dt = Math.min(32, Math.max(0, now - lastPaint));
  lastPaint = now;
  // A 4K projector should not quadruple skeleton rasterization work.
  const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
  const width = Math.round(window.innerWidth * ratio);
  const height = Math.round(window.innerHeight * ratio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
  for (const id of shown.keys()) if (!targets.has(id)) shown.delete(id);
  const glide = 1 - Math.exp(-dt / GLIDE_MS);
  let moving = false;
  if (cursorTarget && !cursor.hidden) {
    last.x += (cursorTarget.x - last.x) * glide;
    last.y += (cursorTarget.y - last.y) * glide;
    moving = Math.hypot(cursorTarget.x - last.x, cursorTarget.y - last.y) > 0.3;
    cursor.style.transform = `translate(${last.x}px, ${last.y}px) scale(${pointerDown ? 0.75 : 1})`;
    cursor.dataset.down = String(pointerDown);
    if (motionAllowed) {
      window.WaveBoardInput?.hover(last.x, last.y);
      if (pressed) input({ type: "move", ...last });
      pendingMove = false;
    }
  }
  // Draw the secondary hand first so the primary hand stays on top.
  const hands = [...targets.entries()].sort(([, a], [, b]) => Number(a.primary) - Number(b.primary));
  for (const [id, target] of hands) {
    let points = shown.get(id);
    if (!points) {
      points = target.points.map((p) => p.slice());
      shown.set(id, points);
    }
    for (let i = 0; i < points.length; i++) {
      const [tx, ty] = target.points[i];
      points[i][0] += (tx - points[i][0]) * glide;
      points[i][1] += (ty - points[i][1]) * glide;
      moving ||= Math.abs(tx - points[i][0]) + Math.abs(ty - points[i][1]) > 0.3;
    }
    drawHand(points, target);
  }
  painting = moving;
  if (painting) requestAnimationFrame(paint);
}

// Joints and bones follow the hand's own size on screen: wrist to middle knuckle, or
// across the knuckles when the palm is tilted. 80 px of palm is the reference size.
function handScale(points) {
  const length = (a, b) => Math.hypot(points[a][0] - points[b][0], points[a][1] - points[b][1]);
  const palm = Math.max(length(0, 9), 1.3 * length(5, 17));
  return Math.min(3, Math.max(0.35, palm / 80));
}

function drawHand(points, { primary, pinch, predicted }) {
  const unit = handScale(points);
  ctx.save();
  ctx.globalAlpha = (primary ? 1 : 0.55) * (predicted ? 0.55 : 1);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  PALM.forEach((index, i) => (i ? ctx.lineTo : ctx.moveTo).call(ctx, ...points[index]));
  ctx.closePath();
  ctx.fillStyle = "rgb(190 209 171 / 0.35)";
  ctx.fill();
  for (const [color, width] of [["rgb(255 254 250 / 0.85)", 11 * unit], [DEEP, 5 * unit]]) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    for (const [a, b] of BONES) {
      ctx.moveTo(...points[a]);
      ctx.lineTo(...points[b]);
    }
    ctx.stroke();
  }
  points.forEach(([x, y], i) => {
    const tip = TIPS.has(i);
    ctx.beginPath();
    ctx.arc(x, y, (tip ? 8 : 4.5) * unit, 0, Math.PI * 2);
    ctx.fillStyle = pinch && (i === 4 || i === 8) ? DEEP : tip ? SAGE : PAPER;
    ctx.fill();
    ctx.lineWidth = (tip ? 3 : 2.5) * unit;
    ctx.strokeStyle = DEEP;
    ctx.stroke();
  });
  ctx.restore();
}

const finitePair = (p) => Array.isArray(p) && p.length === 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]);

function validPointer(pointer) {
  return pointer && typeof pointer.visible === "boolean" && typeof pointer.down === "boolean" &&
    Number.isSafeInteger(pointer.swipe_id) &&
    (!pointer.visible || (Number.isFinite(pointer.x) && Number.isFinite(pointer.y))) &&
    (pointer.hands === undefined || (Array.isArray(pointer.hands) && pointer.hands.length <= 2 &&
      pointer.hands.every((hand) => typeof hand.id === "string" && Array.isArray(hand.points) &&
        hand.points.length === 21 && hand.points.every(finitePair) &&
        (hand.camera_points === undefined || (Array.isArray(hand.camera_points) &&
          hand.camera_points.length === 21 && hand.camera_points.every(finitePair))))));
}

let lastStatsAt = 0;
function trackingFrame(data) {
  if (!validPointer(data.pointer)) return;
  const geometry = data.camera ? `${data.camera.width}:${data.camera.height}` : null;
  if (cameraGeometry && geometry && cameraGeometry !== geometry) {
    projection.reset({ clearHand: true });
    finishCalibration();
    savePreferences();
  }
  if (geometry) cameraGeometry = geometry;
  alignmentStatus();
  projection.update(data.projection, performance.now(), data.timestamp);
  mappingChanged();
  alignmentStatus();
  if (calibrationSession) calibrateFrame(data.pointer, data.timestamp);
  else apply(data.pointer);
  if (performance.now() - lastStatsAt > 500) {
    lastStatsAt = performance.now();
    window.dispatchEvent(new CustomEvent("waveboard-tracking-stats", { detail: {
      tracking_fps: data.tracking_fps, inference_fps: data.inference_fps,
    } }));
  }
}

function connect() {
  let socket;
  try {
    socket = new WebSocket(`ws://localhost:${PORT}`);
  } catch {
    setTimeout(connect, RETRY_MS);
    return;
  }
  socket.addEventListener("message", (event) => {
    if (typeof event.data !== "string" || event.data.length > 65536) return;
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (data?.type === "frame") trackingFrame(data);
    else if (data?.type === "status" && data.level === "error") hide();
  });
  socket.addEventListener("close", () => {
    hide();
    projection.reset();
    alignmentStatus();
    lastSwipe = null;
    setTimeout(connect, RETRY_MS);
  });
}

// The tracker only sends while it sees frames; treat silence as a lost hand.
setInterval(() => {
  if ((!cursor.hidden || targets.size) && performance.now() - lastFrameAt > STALE_MS) hide();
  if (calibrationSession && performance.now() - lastFrameAt > STALE_MS) {
    calibrationSession.fit.interrupt('Waiting for your hand. Open your pinch, then try the target.');
    calibrationView();
  }
  alignmentStatus();
  projection.expire(performance.now());
  mappingChanged();
  alignmentStatus();
  if (projection.enabled || calibrationSession) placeLayer();
}, 200);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { finishCalibration(); projection.reset(); mappingChanged(); hide(); }
});
window.addEventListener("resize", () => {
  finishCalibration(); projection.reset({ clearHand: true }); mappingChanged();
  alignmentStatus(); savePreferences(); paintSoon();
});
if (window.WaveBoardDesktop) {
  window.WaveBoardNative.then(bridge => {
    bridge.hands.connect(encoded => {
      let data;
      try { data = JSON.parse(encoded); } catch { return; }
      if (data?.type === "frame") trackingFrame(data);
      else if (data?.type === "status" && data.level === "error") {
        hide();
        projection.reset();
        alignmentStatus();
        window.dispatchEvent(new CustomEvent("waveboard-tracker-error", { detail: data.message }));
      }
    });
    bridge.startHands();
  }).catch(() => hide());
} else {
  connect();
}
