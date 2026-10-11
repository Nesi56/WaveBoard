// Hand control for the WaveBoard workspace.
//
// Connects to the hand tracker in gesture-lab/ (python gesture-lab/server.py),
// draws every tracked hand as a skeleton over the workspace (the camera image is
// never shown), and turns the primary hand into window.WaveBoardInput events:
// a thumb + index pinch presses, drags and releases like a finger on a touch
// screen, and an open-palm swipe acts as the left / right arrow keys (Home cards,
// slides). Without the tracker this module stays idle and quietly retries.

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
  transition: scale 0.08s, background 0.08s;
}
.hand-cursor[data-down="true"] { scale: 0.75; background: var(--deep, ${DEEP}); }`;
document.head.append(style);
const layer = document.createElement("div");
layer.className = "hand-layer";
layer.setAttribute("aria-hidden", "true");
const canvas = document.createElement("canvas");
canvas.className = "hand-skeletons";
const cursor = document.createElement("div");
cursor.className = "hand-cursor";
cursor.hidden = true;
layer.append(canvas, cursor);
document.body.append(layer);
const ctx = canvas.getContext("2d");

let pressed = false;
let last = { x: 0, y: 0 };
let lastSwipe = null;
let lastFrameAt = 0;
const targets = new Map(); // hand id -> { points (CSS px), primary, pinch }
const shown = new Map();   // hand id -> points currently drawn
let painting = false;

const input = (packet) => window.WaveBoardInput?.pointer({ ...packet, pointerId: 1 }) === true;

function release(type) {
  if (pressed) input({ type, x: last.x, y: last.y });
  pressed = false;
}

function hide() {
  release("cancel");
  cursor.hidden = true;
  targets.clear();
  paintSoon();
}

function arrowKey(key) {
  document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
}

function placeLayer() {
  // Full-screen slides and open dialogs are drawn above everything else.
  const host = document.fullscreenElement || document.querySelector("dialog[open]") || document.body;
  if (layer.parentElement !== host) host.append(layer);
}

function apply(pointer) {
  lastFrameAt = performance.now();
  if (pointer.swipe_id !== lastSwipe) {
    // Like a touch screen: push the page left to see the next one.
    if (lastSwipe !== null && pointer.swipe) arrowKey(pointer.swipe < 0 ? "ArrowRight" : "ArrowLeft");
    lastSwipe = pointer.swipe_id;
  }
  if (!pointer.visible || document.hidden) return hide();
  placeLayer();
  targets.clear();
  for (const hand of pointer.hands || []) {
    targets.set(hand.id, {
      points: hand.points.map(([x, y]) => [x * window.innerWidth, y * window.innerHeight]),
      primary: hand.primary, pinch: hand.pinch,
    });
  }
  paintSoon();
  last = { x: pointer.x * window.innerWidth, y: pointer.y * window.innerHeight };
  cursor.hidden = false;
  // The translate property (not transform) so the pressed-state scale cannot scale the position.
  cursor.style.translate = `${last.x}px ${last.y}px`;
  cursor.dataset.down = String(pointer.down);
  if (pointer.down && !pressed) pressed = input({ type: "down", ...last });
  else if (pointer.down) input({ type: "move", ...last });
  else release("up");
}

function paintSoon() {
  if (!painting) {
    painting = true;
    requestAnimationFrame(paint);
  }
}

let lastPaint = performance.now();
function paint(now) {
  const dt = Math.min(100, Math.max(0, now - lastPaint));
  lastPaint = now;
  const ratio = window.devicePixelRatio || 1;
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

function drawHand(points, { primary, pinch }) {
  // Sized for a 480p projector and scaled up on larger screens.
  const unit = Math.max(0.75, Math.min(window.innerWidth, window.innerHeight) / 480);
  ctx.save();
  ctx.globalAlpha = primary ? 1 : 0.55;
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
        hand.points.length === 21 && hand.points.every(finitePair))));
}

function connect() {
  let socket;
  try {
    socket = new WebSocket(`ws://127.0.0.1:${PORT}`);
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
    if (data?.type === "frame" && validPointer(data.pointer)) apply(data.pointer);
    else if (data?.type === "status" && data.level === "error") hide();
  });
  socket.addEventListener("close", () => {
    hide();
    lastSwipe = null;
    setTimeout(connect, RETRY_MS);
  });
}

// The tracker only sends while it sees frames; treat silence as a lost hand.
setInterval(() => {
  if ((!cursor.hidden || targets.size) && performance.now() - lastFrameAt > STALE_MS) hide();
}, 200);
document.addEventListener("visibilitychange", () => document.hidden && hide());
window.addEventListener("resize", paintSoon);
connect();
