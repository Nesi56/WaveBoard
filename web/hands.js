// Hand control for the WaveBoard workspace.
//
// Connects to the hand tracker in gesture-lab/ (python gesture-lab/server.py)
// and turns its pointer into window.WaveBoardInput events: a thumb + index pinch
// presses, drags and releases like a finger on a touch screen, and an open-palm
// swipe acts as the left / right arrow keys (Home cards, slides). Without the
// tracker this module stays idle and quietly retries.

const params = new URLSearchParams(location.search);
const PORT = Number(params.get("hands-port")) || 8766;
const STALE_MS = 500;
const RETRY_MS = 3000;

const style = document.createElement("style");
style.textContent = `
.hand-cursor {
  position: fixed; left: 0; top: 0; width: 38px; height: 38px; margin: -19px 0 0 -19px;
  border: 4px solid var(--deep, #304b3b); border-radius: 50%;
  background: rgb(255 255 255 / 0.35); box-shadow: 0 0 0 3px rgb(255 255 255 / 0.85);
  pointer-events: none; z-index: 2147483647; transition: scale 0.08s, background 0.08s;
}
.hand-cursor[data-down="true"] { scale: 0.75; background: var(--deep, #304b3b); }`;
document.head.append(style);
const cursor = document.createElement("div");
cursor.className = "hand-cursor";
cursor.hidden = true;
cursor.setAttribute("aria-hidden", "true");
document.body.append(cursor);

let pressed = false;
let last = { x: 0, y: 0 };
let lastSwipe = null;
let lastFrameAt = 0;

const input = (packet) => window.WaveBoardInput?.pointer({ ...packet, pointerId: 1 }) === true;

function release(type) {
  if (pressed) input({ type, x: last.x, y: last.y });
  pressed = false;
}

function hide() {
  release("cancel");
  cursor.hidden = true;
}

function arrowKey(key) {
  document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
}

function apply(pointer) {
  lastFrameAt = performance.now();
  if (pointer.swipe_id !== lastSwipe) {
    // Like a touch screen: push the page left to see the next one.
    if (lastSwipe !== null && pointer.swipe) arrowKey(pointer.swipe < 0 ? "ArrowRight" : "ArrowLeft");
    lastSwipe = pointer.swipe_id;
  }
  if (!pointer.visible || document.hidden) return hide();
  last = { x: pointer.x * window.innerWidth, y: pointer.y * window.innerHeight };
  // Full-screen slides and open dialogs are drawn above everything else.
  const layer = document.fullscreenElement || document.querySelector("dialog[open]") || document.body;
  if (cursor.parentElement !== layer) layer.append(cursor);
  cursor.hidden = false;
  // The translate property (not transform) so the pressed-state scale cannot scale the position.
  cursor.style.translate = `${last.x}px ${last.y}px`;
  cursor.dataset.down = String(pointer.down);
  if (pointer.down && !pressed) pressed = input({ type: "down", ...last });
  else if (pointer.down) input({ type: "move", ...last });
  else release("up");
}

function validPointer(pointer) {
  return pointer && typeof pointer.visible === "boolean" && typeof pointer.down === "boolean" &&
    Number.isSafeInteger(pointer.swipe_id) &&
    (!pointer.visible || (Number.isFinite(pointer.x) && Number.isFinite(pointer.y)));
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
  if (!cursor.hidden && performance.now() - lastFrameAt > STALE_MS) hide();
}, 200);
document.addEventListener("visibilitychange", () => document.hidden && hide());
connect();
