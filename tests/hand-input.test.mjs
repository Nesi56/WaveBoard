import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source = await readFile(new URL('../web/hand-input.js', import.meta.url), 'utf8');
const { createHandInput } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
globalThis.PointerEvent = class { constructor(type, init) { this.type = type; Object.assign(this, init); } };
function fixture(kind = 'button') {
  const classes = new Set();
  const control = {
    tagName: 'BUTTON', isConnected: true, events: [], clicks: 0,
    classList: { add: c => classes.add(c), remove: c => classes.delete(c) },
    getBoundingClientRect: () => ({ left: 100, right: 240, top: 100, bottom: 170, width: 140 }),
    closest(selector) {
      if (selector.startsWith('[inert]')) return this.disabled ? this : null;
      if (selector === 'label') return null;
      if (selector.startsWith('canvas')) return kind === 'range' ? this : null;
      return this;
    },
    matches: selector => selector === 'input[type="range"]' && kind === 'range',
    focus() {}, dispatchEvent(event) { this.events.push(event.type); }, click() { this.clicks++; },
    parentElement: null,
    min: '0', max: '1000', step: '10', value: '0',
  };
  const doc = {
    body: {}, querySelector: () => null,
    elementFromPoint: (x, y) => (x >= 100 && x <= 240 && y >= 100 && y <= 170) ? control : null,
    defaultView: { getComputedStyle: () => ({ overflowY: 'visible', direction: 'ltr' }) },
  };
  return { control, doc, input: createHandInput(doc), classes };
}
test('button tolerates natural movement within target and clicks exactly once', () => {
  const { control, input, classes } = fixture();
  input.pointer({ type: 'down', x: 120, y: 120 });
  input.pointer({ type: 'move', x: 180, y: 135 });
  assert.ok(classes.has('hand-pressed'));
  input.pointer({ type: 'up', x: 180, y: 135 });
  assert.equal(control.clicks, 1);
  assert.deepEqual(control.events, ['pointerdown', 'pointermove', 'pointerup']);
  assert.ok(!classes.has('hand-pressed'));
});
test('tracking cancellation, hidden controls and leaving target never click', () => {
  for (const reason of ['cancel', 'hidden', 'leave']) {
    const { control, input } = fixture();
    input.pointer({ type: 'down', x: 120, y: 120 });
    if (reason === 'hidden') control.isConnected = false;
    if (reason === 'leave') input.pointer({ type: 'move', x: 400, y: 400 });
    input.pointer({ type: reason === 'cancel' ? 'cancel' : 'up', x: 120, y: 120 });
    assert.equal(control.clicks, 0, reason);
  }
});
test('small release jitter outside button is accepted, different control is not', () => {
  const { control, input } = fixture();
  input.pointer({ type: 'down', x: 235, y: 120 });
  input.pointer({ type: 'up', x: 248, y: 120 });
  assert.equal(control.clicks, 1);
  const f = fixture();
  f.input.pointer({ type: 'down', x: 120, y: 120 });
  f.doc.elementFromPoint = () => control;
  f.input.pointer({ type: 'up', x: 130, y: 120 });
  assert.equal(f.control.clicks, 0);
});
test('pinch dragging slider updates stepped values and emits input/change', () => {
  const { control, input } = fixture('range');
  input.pointer({ type: 'down', x: 100, y: 120 });
  input.pointer({ type: 'move', x: 170, y: 120 });
  assert.equal(control.value, '500');
  input.pointer({ type: 'up', x: 240, y: 120 });
  assert.equal(control.value, '1000');
  assert.ok(control.events.includes('input'));
  assert.equal(control.events.filter(e => e === 'change').length, 1);
  assert.equal(control.clicks, 0);
});
test('dragging file rows scrolls container and cancels click/long press', () => {
  const { control, input, doc } = fixture();
  const scroller = { scrollHeight: 800, clientHeight: 200, scrollTop: 100, parentElement: doc.body };
  control.parentElement = scroller;
  doc.defaultView.getComputedStyle = el => ({ overflowY: el === scroller ? 'auto' : 'visible' });
  input.pointer({ type: 'down', x: 160, y: 150 });
  input.pointer({ type: 'move', x: 161, y: 110 });
  input.pointer({ type: 'up', x: 161, y: 100 });
  assert.equal(scroller.scrollTop, 150);
  assert.ok(control.events.includes('pointercancel'));
  assert.equal(control.clicks, 0);
});
test('suspension stops hold timers without creating a release', () => {
  const { control, input } = fixture();
  input.pointer({ type: 'down', x: 120, y: 120 });
  input.suspend();
  assert.deepEqual(control.events, ['pointerdown', 'pointerleave']);
  assert.equal(control.clicks, 0);
});
