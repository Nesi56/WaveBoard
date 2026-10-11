// Run inside the local Qt WebEngine app (with a root containing many files).
// Exercises the real DOM with camera-style pointer packets, no mouse clicks.
window.handUIResults = { checks: [], error: null };
(async () => {
  const result = window.handUIResults;
  const check = (condition, name) => { if (!condition) throw Error(name); result.checks.push(name); };
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const until = async predicate => {
    for (let n = 0; n < 120; n++) { if (predicate()) return; await wait(25); }
    throw Error('Timed out waiting for UI');
  };
  const point = (selector, offset = 0) => {
    const element = typeof selector === 'string' ? document.querySelector(selector) : selector;
    if (!element) throw Error('Missing control ' + selector);
    // Large 480p controls may be below the fold in a scrollable menu/dialog.
    element.scrollIntoView({ block: 'center', inline: 'nearest' });
    const box = element.getBoundingClientRect();
    return { x: box.left + box.width / 2 + offset, y: box.top + box.height / 2 };
  };
  const gesture = (selector, jitter = 0) => {
    const at = point(selector);
    WaveBoardInput.pointer({ type: 'down', ...at, pointerId: 901, isPrimary: true });
    if (jitter) WaveBoardInput.pointer({ type: 'move', x: at.x + jitter, y: at.y, pointerId: 901, isPrimary: true });
    WaveBoardInput.pointer({ type: 'up', x: at.x + jitter, y: at.y, pointerId: 901, isPrimary: true });
  };
  try {
    await until(() => window.WaveBoardInput);
    await WaveBoardInput.navigate('whiteboard');
    gesture('#menu-toggle', 20);
    check(!document.querySelector('#workspace-menu').hidden, 'hand opens menu with 20px jitter');
    gesture('#settings-button');
    await until(() => document.querySelector('#contrast-setting'));
    const checkbox = document.querySelector('#contrast-setting');
    const before = checkbox.checked;
    gesture(checkbox.closest('label'));
    check(checkbox.checked !== before, 'whole checkbox label selects by hand');
    check(!!document.querySelector('#quit-app'), 'close app available in settings');
    gesture('#dialog-close');
    check(!document.querySelector('#dialog').open, 'hand closes modal');
    await WaveBoardInput.navigate('files');
    await until(() => document.querySelector('[data-file]'));
    gesture('#menu-toggle');
    gesture('#find-file');
    gesture('[data-key="q"]');
    gesture('[data-key="w"]');
    gesture('[data-key="backspace"]');
    check(document.querySelector('#file-search').value === 'q', 'file search keyboard works with hands');
    gesture('[data-key="clear"]');
    gesture('#apply-search');
    check(!document.querySelector('#dialog').open, 'hand applies search');
    const list = document.querySelector('#file-list');
    const first = document.querySelector('[data-file]');
    const start = point(first);
    WaveBoardInput.pointer({ type: 'down', ...start, pointerId: 901, isPrimary: true });
    WaveBoardInput.pointer({ type: 'move', x: start.x, y: start.y - 70, pointerId: 901, isPrimary: true });
    WaveBoardInput.pointer({ type: 'up', x: start.x, y: start.y - 90, pointerId: 901, isPrimary: true });
    check(list.scrollTop > 0 || list.parentElement.scrollTop > 0, 'hand drag scrolls file list');
    check(!document.querySelector('#dialog').open, 'scroll does not open file');
    await WaveBoardInput.navigate('slides');
    gesture('#present-slides');
    await until(() => document.querySelector('#slide-stage').classList.contains('presenting'));
    check(!!document.querySelector('.presenting .present-overlay'), 'hand enters presentation');
    gesture('#present-next');
    check(document.querySelector('.demo-slide h2').textContent === 'Tap. Draw. Explore.', 'hand advances presentation');
    gesture('#present-exit');
    await until(() => !document.querySelector('#slide-stage').classList.contains('presenting'));
    check(true, 'hand exits presentation');
    gesture('#open-slides');
    await until(() => document.querySelector('.picker-list'));
    check(!document.querySelector('#picker-local'), 'desktop picker stays in app');
    gesture('#dialog-close');
    await WaveBoardInput.navigate('whiteboard');
    const canvas = document.querySelector('#drawing-canvas');
    const at = point(canvas);
    WaveBoardInput.pointer({ type: 'down', ...at, pointerId: 901, isPrimary: true });
    WaveBoardInput.pointer({ type: 'move', x: at.x + 70, y: at.y + 20, pointerId: 901, isPrimary: true });
    WaveBoardInput.pointer({ type: 'cancel', x: at.x + 70, y: at.y + 20, pointerId: 901, isPrimary: true });
    await wait(80);
    // Native fullscreen may finish resizing after its bridge reply. The stroke
    // starts at normalized canvas center and must survive that resize too.
    const pixels = canvas.getContext('2d').getImageData(Math.round(canvas.width / 2), Math.round(canvas.height / 2), 1, 1).data;
    check(pixels.some(v => v > 0), 'hand drawing survives cancellation');
    // A real range input checks browser value sanitization and events.
    const range = document.createElement('input');
    range.type = 'range'; range.min = '0'; range.max = '1000'; range.value = '0';
    range.style.cssText = 'position:fixed;left:100px;top:200px;width:400px;height:50px;z-index:100';
    document.body.append(range);
    let inputs = 0, changes = 0;
    range.addEventListener('input', () => inputs++);
    range.addEventListener('change', () => changes++);
    WaveBoardInput.pointer({ type: 'down', x: 120, y: 225, pointerId: 901, isPrimary: true });
    WaveBoardInput.pointer({ type: 'move', x: 300, y: 225, pointerId: 901, isPrimary: true });
    WaveBoardInput.pointer({ type: 'up', x: 470, y: 225, pointerId: 901, isPrimary: true });
    check(Number(range.value) > 850 && inputs > 0 && changes === 1, 'hand slider drag emits input and one change');
    range.remove();
  } catch (error) { result.error = String(error.stack || error); }
  result.done = true;
})();
