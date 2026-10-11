// Synthetic PointerEvents do not perform native click, range, or scrolling
// defaults. Supply those defaults once for hand input, while real mouse/touch
// continue to use the browser normally.
const CONTROL = 'button, a[href], input, textarea, select, [role="button"], label';
const DRAG_THRESHOLD = 18;
const RELEASE_MARGIN = 18;

export function createHandInput(doc = document) {
  const pointers = new Map();
  let hovered = null;
  const usable = element => element && !element.closest('[inert], [hidden], :disabled, [aria-disabled="true"]');
  const controlAt = element => {
    const candidate = element?.closest(CONTROL);
    if (!usable(candidate)) return null;
    // A settings label is one large, easy-to-hit checkbox target.
    return candidate.tagName === 'LABEL' ? candidate.control || candidate.querySelector('input') : candidate;
  };
  const inside = (element, x, y, margin = 0) => {
    const r = element.getBoundingClientRect();
    return x >= r.left - margin && x <= r.right + margin && y >= r.top - margin && y <= r.bottom + margin;
  };
  function hover(x, y) {
    const target = Number.isFinite(x) && Number.isFinite(y) ? controlAt(doc.elementFromPoint(x, y)) : null;
    if (target !== hovered) {
      hovered?.classList.remove('hand-hover');
      hovered = target;
      hovered?.classList.add('hand-hover');
    }
    return target;
  }
  function scrollParent(element) {
    // Drawing and 3D surfaces own their drags even if a page ancestor scrolls.
    if (element.closest('canvas, input[type="range"], textarea')) return null;
    for (let parent = element; parent && parent !== doc.body; parent = parent.parentElement) {
      const style = doc.defaultView.getComputedStyle(parent);
      if (/(auto|scroll)/.test(style.overflowY) && parent.scrollHeight > parent.clientHeight + 1) return parent;
    }
    return null;
  }
  function dispatch(active, type, x, y, pointerId, isPrimary) {
    active.target.dispatchEvent(new PointerEvent('pointer' + type, {
      bubbles: true, cancelable: true, clientX: x, clientY: y,
      pointerId, pointerType: 'touch', isPrimary: Boolean(isPrimary), button: 0,
      buttons: type === 'up' || type === 'cancel' || type === 'leave' ? 0 : 1,
      pressure: type === 'up' || type === 'cancel' ? 0 : 0.5,
    }));
  }
  function updateRange(element, x) {
    const r = element.getBoundingClientRect();
    const min = Number(element.min || 0), max = Number(element.max || 100);
    const step = element.step === 'any' ? 0 : Number(element.step || 1);
    let ratio = Math.min(1, Math.max(0, (x - r.left) / Math.max(1, r.width)));
    if (doc.defaultView.getComputedStyle(element).direction === 'rtl') ratio = 1 - ratio;
    let value = min + ratio * (max - min);
    if (step > 0) value = min + Math.round((value - min) / step) * step;
    const next = String(Math.min(max, Math.max(min, Number(value.toFixed(8)))));
    if (element.value !== next) {
      element.value = next;
      element.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }
  function pointer({ type, x, y, pointerId = 1, isPrimary = pointerId === 1 }) {
    if (!['down', 'move', 'up', 'cancel'].includes(type) || !Number.isFinite(x) || !Number.isFinite(y)) return false;
    let active = pointers.get(pointerId);
    if (type === 'down') {
      if (active) pointer({ type: 'cancel', x, y, pointerId, isPrimary });
      const hit = doc.elementFromPoint(x, y);
      if (!usable(hit)) return false;
      const control = controlAt(hit);
      const target = control || hit;
      const label = hit.closest('label');
      const region = label && (label.control === control || label.querySelector('input') === control) ? label : target;
      active = { target, control, region, startX: x, startY: y, scroll: scrollParent(target), scrolling: false, leftControl: false };
      active.scrollTop = active.scroll?.scrollTop || 0;
      active.range = control?.matches('input[type="range"]');
      active.rangeValue = active.range ? control.value : null;
      pointers.set(pointerId, active);
      control?.focus?.({ preventScroll: true });
      control?.classList.add('hand-pressed');
    }
    if (!active) { if (type === 'move') hover(x, y); return false; }
    if (!active.target.isConnected || !usable(active.target)) type = 'cancel';
    if (active.control && !inside(active.region, x, y, RELEASE_MARGIN)) active.leftControl = true;
    if (type === 'move' && !active.scrolling && active.scroll && Math.abs(y - active.startY) > DRAG_THRESHOLD && Math.abs(y - active.startY) > Math.abs(x - active.startX)) {
      active.scrolling = true;
      dispatch(active, 'cancel', x, y, pointerId, isPrimary);
      active.control?.classList.remove('hand-pressed');
    }
    if (active.scrolling) {
      if (type === 'move' || type === 'up') active.scroll.scrollTop = active.scrollTop + active.startY - y;
    } else {
      dispatch(active, type, x, y, pointerId, isPrimary);
      if (active.range && type !== 'cancel') updateRange(active.control, x);
    }
    if (type === 'up' || type === 'cancel') {
      pointers.delete(pointerId);
      active.control?.classList.remove('hand-pressed');
      if (type === 'up' && !active.scrolling && usable(active.control) && active.control.isConnected) {
        if (active.range) {
          if (active.rangeValue !== active.control.value) active.control.dispatchEvent(new Event('change', { bubbles: true }));
        } else if (!active.leftControl && inside(active.region, x, y, RELEASE_MARGIN)) {
          const release = controlAt(doc.elementFromPoint(x, y));
          // A little air-hand jitter can leave the edge, but cannot activate a
          // different button or a control hidden under a newly opened dialog.
          const modal = doc.querySelector('dialog[open]');
          if ((!modal || modal.contains(active.control)) && (release === active.control || !release)) active.control.click();
        }
      }
    }
    return true;
  }
  function suspend() {
    hover(NaN, NaN);
    // Stop long-press timers during uncertain tracking without discarding a
    // drawing stroke that can safely resume at the retained point.
    for (const [id, active] of pointers) dispatch(active, 'leave', active.startX, active.startY, id, true);
  }
  return { pointer, hover, suspend };
}
