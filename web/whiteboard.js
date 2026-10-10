/**
 * Touch-first vector whiteboard. All points and widths are normalised so a
 * drawing survives changes to the size and pixel density of its canvas.
 */
export function createWhiteboard(canvas, options = {}) {
  if (!(canvas instanceof HTMLCanvasElement)) {
    throw new TypeError('createWhiteboard requires a canvas element.');
  }

  const context = canvas.getContext('2d');
  const layer = document.createElement('canvas');
  const layerContext = layer.getContext('2d');
  if (!context || !layerContext) throw new Error('Canvas drawing is unavailable.');

  const storageKey = options.storageKey || 'waveboard.whiteboard.v1';
  const storageLimit = 2_000_000;
  const paperColor = options.paperColor || '#fbfaf7';
  const previousTouchAction = canvas.style.touchAction;
  canvas.style.touchAction = 'none';

  let actions = [];
  let future = [];
  let current = null;
  let pointerId = null;
  let tool = 'pen';
  let color = '#26374d';
  let size = 4;
  let cssWidth = 1;
  let cssHeight = 1;
  let ratio = 1;
  let frame = 0;
  let saveTimer = 0;
  let disposed = false;
  let layerDirty = true;
  const validColor = value => typeof value === 'string' && /^#(?:[\da-f]{3}|[\da-f]{4}|[\da-f]{6}|[\da-f]{8})$/i.test(value);
  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

  function visibleActions() {
    let start = 0;
    for (let index = actions.length - 1; index >= 0; index--) {
      if (actions[index].kind === 'clear') {
        start = index + 1;
        break;
      }
    }
    return actions.slice(start);
  }

  function getState() {
    return {
      canUndo: actions.length > 0,
      canRedo: future.length > 0,
      tool,
      color,
      size,
      strokeCount: visibleActions().filter(action => action.kind === 'stroke').length,
    };
  }

  function notify() {
    options.onChange?.(getState());
  }

  function isValidAction(action) {
    if (!action || typeof action !== 'object') return false;
    if (action.kind === 'clear') return true;
    return action.kind === 'stroke'
      && ['pen', 'highlighter', 'eraser'].includes(action.tool)
      && validColor(action.color)
      && Number.isFinite(action.width) && action.width > 0 && action.width <= 1
      && Array.isArray(action.points) && action.points.length > 0 && action.points.length <= 12_000
      && action.points.every(point => Array.isArray(point) && point.length === 2
        && point.every(value => Number.isFinite(value) && value >= 0 && value <= 1));
  }

  function restore() {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return;
      if (raw.length > storageLimit) throw new Error('Saved drawing exceeds the storage limit.');
      const saved = JSON.parse(raw);
      if (saved.version !== 1 || !Array.isArray(saved.actions) || saved.actions.length > 5_000
        || !saved.actions.every(isValidAction)) throw new Error('Invalid saved drawing.');
      actions = saved.actions;
      if (['pen', 'highlighter', 'eraser'].includes(saved.tool)) tool = saved.tool;
      if (validColor(saved.color)) color = saved.color;
      if (Number.isFinite(saved.size)) size = clamp(saved.size, 1, 96);
    } catch {
      // A corrupt save or unavailable local storage must never block drawing.
      try { localStorage.removeItem(storageKey); } catch { /* Storage can be disabled. */ }
    }
  }

  function persist() {
    window.clearTimeout(saveTimer);
    saveTimer = 0;
    try {
      // Keep history in memory, but do not spend storage on strokes hidden by a clear.
      let savedActions = visibleActions();
      let saved = JSON.stringify({ version: 1, actions: savedActions, tool, color, size });
      // Downsample the stored copy if needed; the live drawing retains its detail.
      for (let attempt = 0; saved.length > storageLimit && attempt < 10; attempt++) {
        savedActions = savedActions.map(action => {
          if (action.points.length <= 8) return action;
          const points = action.points.filter((_, index) => index % 2 === 0);
          if (points.at(-1) !== action.points.at(-1)) points.push(action.points.at(-1));
          return { ...action, points };
        });
        saved = JSON.stringify({ version: 1, actions: savedActions, tool, color, size });
      }
      if (saved.length > storageLimit || savedActions.length > 5_000) {
        // Do not silently restore a stale version after a drawing has outgrown storage.
        localStorage.removeItem(storageKey);
        options.onStorageError?.(new Error('This drawing is too large to save locally. Export it as a PNG.'));
        return;
      }
      localStorage.setItem(storageKey, saved);
    } catch (error) {
      options.onStorageError?.(error);
    }
  }

  function scheduleSave() {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(persist, 300);
  }

  function paintStroke(target, stroke) {
    const points = stroke.points;
    if (!points.length) return;
    const width = stroke.width * Math.min(cssWidth, cssHeight);
    target.save();
    target.globalCompositeOperation = stroke.tool === 'eraser' ? 'destination-out' : 'source-over';
    target.globalAlpha = stroke.tool === 'highlighter' ? 0.3 : 1;
    target.strokeStyle = stroke.color;
    target.fillStyle = stroke.color;
    target.lineWidth = width;
    target.lineCap = 'round';
    target.lineJoin = 'round';
    target.beginPath();
    const firstX = points[0][0] * cssWidth;
    const firstY = points[0][1] * cssHeight;
    if (points.length === 1) {
      target.arc(firstX, firstY, width / 2, 0, Math.PI * 2);
      target.fill();
    } else {
      target.moveTo(firstX, firstY);
      for (let index = 1; index < points.length - 1; index++) {
        const point = points[index];
        const next = points[index + 1];
        target.quadraticCurveTo(point[0] * cssWidth, point[1] * cssHeight,
          (point[0] + next[0]) * cssWidth / 2, (point[1] + next[1]) * cssHeight / 2);
      }
      const last = points[points.length - 1];
      target.lineTo(last[0] * cssWidth, last[1] * cssHeight);
      target.stroke();
    }
    target.restore();
  }

  function render() {
    frame = 0;
    if (disposed) return;
    if (layerDirty) {
      layerContext.setTransform(1, 0, 0, 1, 0, 0);
      layerContext.clearRect(0, 0, layer.width, layer.height);
      layerContext.setTransform(ratio, 0, 0, ratio, 0, 0);
      for (const action of visibleActions()) paintStroke(layerContext, action);
      layerDirty = false;
    }
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(layer, 0, 0);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    if (current) paintStroke(context, current);
  }

  function requestRender() {
    if (!frame && !disposed) frame = requestAnimationFrame(render);
  }

  function finishStroke() {
    if (!current) return;
    actions.push(current);
    future = [];
    current = null;
    const releasedPointer = pointerId;
    pointerId = null;
    if (releasedPointer !== null && canvas.hasPointerCapture?.(releasedPointer)) {
      canvas.releasePointerCapture(releasedPointer);
    }
    layerDirty = true;
    requestRender();
    scheduleSave();
    notify();
  }

  function pointFrom(event) {
    const bounds = canvas.getBoundingClientRect();
    return [
      Math.round(clamp((event.clientX - bounds.left) / Math.max(bounds.width, 1), 0, 1) * 100_000) / 100_000,
      Math.round(clamp((event.clientY - bounds.top) / Math.max(bounds.height, 1), 0, 1) * 100_000) / 100_000,
    ];
  }

  function addPoint(event, force = false) {
    const point = pointFrom(event);
    const last = current.points[current.points.length - 1];
    const distance = Math.hypot((point[0] - last[0]) * cssWidth, (point[1] - last[1]) * cssHeight);
    if (distance < (force ? 0.05 : 0.7)) return;
    current.points.push(point);
    // Keep exceptionally long, uninterrupted gestures bounded in memory.
    if (current.points.length > 10_000) {
      const lastPoint = current.points.at(-1);
      current.points = current.points.filter((_, index) => index % 2 === 0);
      if (current.points.at(-1) !== lastPoint) current.points.push(lastPoint);
    }
  }

  function pointerDown(event) {
    if (disposed || current || event.isPrimary === false || (event.pointerType === 'mouse' && event.button !== 0)) return;
    event.preventDefault();
    resize();
    pointerId = event.pointerId;
    current = {
      kind: 'stroke', tool, color,
      width: Math.min(1, size / Math.max(1, Math.min(cssWidth, cssHeight))),
      points: [pointFrom(event)],
    };
    try { canvas.setPointerCapture(pointerId); } catch { /* Synthetic input may not support capture. */ }
    requestRender();
  }

  function pointerMove(event) {
    if (!current || event.pointerId !== pointerId) return;
    event.preventDefault();
    const samples = event.getCoalescedEvents?.();
    for (const sample of samples?.length ? samples : [event]) addPoint(sample);
    requestRender();
  }

  function pointerUp(event) {
    if (!current || event.pointerId !== pointerId) return;
    event.preventDefault();
    addPoint(event, true);
    finishStroke();
  }

  function pointerCancel(event) {
    if (!current || event.pointerId !== pointerId) return;
    // Preserve the part already drawn if the browser cancels a gesture.
    finishStroke();
  }

  function resize() {
    if (disposed) return;
    const bounds = canvas.getBoundingClientRect();
    // Hidden panels keep their last useful drawing size until shown again.
    if (bounds.width < 1 || bounds.height < 1) return;
    const nextRatio = Math.min(window.devicePixelRatio || 1, 3);
    const width = Math.max(1, Math.round(bounds.width * nextRatio));
    const height = Math.max(1, Math.round(bounds.height * nextRatio));
    if (canvas.width === width && canvas.height === height && cssWidth === bounds.width
      && cssHeight === bounds.height && ratio === nextRatio) return;
    cssWidth = bounds.width;
    cssHeight = bounds.height;
    ratio = nextRatio;
    canvas.width = layer.width = width;
    canvas.height = layer.height = height;
    layerDirty = true;
    requestRender();
  }

  function setTool(nextTool) {
    if (!['pen', 'highlighter', 'eraser'].includes(nextTool)) return;
    finishStroke();
    tool = nextTool;
    notify();
    scheduleSave();
  }

  function setColor(nextColor) {
    if (!validColor(nextColor)) return;
    finishStroke();
    color = nextColor;
    notify();
    scheduleSave();
  }

  function setSize(nextSize) {
    if (!Number.isFinite(Number(nextSize))) return;
    finishStroke();
    size = clamp(Number(nextSize), 1, 96);
    notify();
    scheduleSave();
  }

  function undo() {
    finishStroke();
    if (!actions.length) return;
    future.push(actions.pop());
    layerDirty = true;
    requestRender();
    scheduleSave();
    notify();
  }

  function redo() {
    finishStroke();
    if (!future.length) return;
    actions.push(future.pop());
    layerDirty = true;
    requestRender();
    scheduleSave();
    notify();
  }

  function clear() {
    finishStroke();
    if (!visibleActions().length) return;
    actions.push({ kind: 'clear' });
    future = [];
    layerDirty = true;
    requestRender();
    scheduleSave();
    notify();
  }

  async function exportPNG() {
    finishStroke();
    if (frame) cancelAnimationFrame(frame);
    render();
    const output = document.createElement('canvas');
    output.width = canvas.width;
    output.height = canvas.height;
    const outputContext = output.getContext('2d');
    outputContext.fillStyle = paperColor;
    outputContext.fillRect(0, 0, output.width, output.height);
    outputContext.drawImage(canvas, 0, 0);
    return new Promise((resolve, reject) => output.toBlob(blob => {
      if (blob) resolve(blob);
      else reject(new Error('The drawing could not be exported.'));
    }, 'image/png'));
  }

  function onPageHide() {
    finishStroke();
    persist();
  }

  function dispose() {
    if (disposed) return;
    finishStroke();
    persist();
    disposed = true;
    cancelAnimationFrame(frame);
    resizeObserver?.disconnect();
    canvas.style.touchAction = previousTouchAction;
    canvas.removeEventListener('pointerdown', pointerDown);
    canvas.removeEventListener('pointermove', pointerMove);
    canvas.removeEventListener('pointerup', pointerUp);
    canvas.removeEventListener('pointercancel', pointerCancel);
    canvas.removeEventListener('lostpointercapture', pointerCancel);
    window.removeEventListener('resize', resize);
    window.removeEventListener('pagehide', onPageHide);
  }

  restore();
  canvas.addEventListener('pointerdown', pointerDown, { passive: false });
  canvas.addEventListener('pointermove', pointerMove, { passive: false });
  canvas.addEventListener('pointerup', pointerUp, { passive: false });
  canvas.addEventListener('pointercancel', pointerCancel);
  canvas.addEventListener('lostpointercapture', pointerCancel);
  window.addEventListener('resize', resize);
  window.addEventListener('pagehide', onPageHide);
  const resizeObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(resize) : null;
  resizeObserver?.observe(canvas);
  resize();
  notify();

  return { setTool, setColor, setSize, undo, redo, clear, exportPNG, resize, dispose, getState };
}
