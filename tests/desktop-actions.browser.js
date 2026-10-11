// Native-action regression: actual exports/imports, rendered 3D zoom, and quit.
window.desktopActions = { checks: [], error: null, capture: null, readyToQuit: false };
(async () => {
  const result = window.desktopActions;
  const check = (condition, name) => { if (!condition) throw Error(name); result.checks.push(name); };
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const until = async (predicate, name) => {
    for (let n = 0; n < 320; n++) { if (predicate()) return; await wait(25); }
    throw Error('Timed out: ' + name);
  };
  const gesture = selector => {
    const element = typeof selector === 'string' ? document.querySelector(selector) : selector;
    if (!element) throw Error('Missing control ' + selector);
    element.scrollIntoView({ block: 'center', inline: 'nearest' });
    const box = element.getBoundingClientRect();
    const at = { x: box.left + box.width / 2, y: box.top + box.height / 2, pointerId: 902, isPrimary: true };
    WaveBoardInput.pointer({ type: 'down', ...at });
    WaveBoardInput.pointer({ type: 'up', ...at });
  };
  const entry = (selector, text) => [...document.querySelectorAll(selector)].find(button => (button.querySelector('.file-name') || button).textContent.trim() === text);
  const capture = async name => {
    await wait(350);
    const bounds = document.querySelector('#viewer-host canvas').getBoundingClientRect();
    result.captureBounds = { x: bounds.left, y: bounds.top, width: bounds.width, height: bounds.height };
    result.capture = name;
    await until(() => window.desktopCaptureAcknowledged === name, name + ' screenshot');
  };
  try {
    await until(() => window.WaveBoardInput, 'workspace');
    await WaveBoardInput.navigate('whiteboard');
    const canvas = document.querySelector('#drawing-canvas');
    const bounds = canvas.getBoundingClientRect();
    const at = { x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2, pointerId: 902, isPrimary: true };
    WaveBoardInput.pointer({ type: 'down', ...at });
    WaveBoardInput.pointer({ type: 'move', ...at, x: at.x + 90 });
    WaveBoardInput.pointer({ type: 'up', ...at, x: at.x + 90 });
    await wait(100);
    const exported = [];
    (await WaveBoardNative).saved.connect(message => exported.push(message));
    gesture('#menu-toggle');
    gesture('#export-board');
    await until(() => exported.length === 1, 'first PNG save');
    check(exported[0].startsWith('Saved to '), 'first PNG saved through native bridge');
    await until(() => document.querySelector('#toast').textContent === exported[0], 'first saved toast');
    check(true, 'save toast reports actual destination');
    gesture('#menu-toggle');
    gesture('#export-board');
    await until(() => exported.length === 2, 'second PNG save');
    check(exported[1].startsWith('Saved to ') && exported[1] !== exported[0], 'duplicate save gets a unique path');
    result.exports = exported;

    await WaveBoardInput.navigate('files');
    await until(() => entry('[data-file]', 'Destination'), 'destination folder');
    gesture(entry('[data-file]', 'Destination'));
    await until(() => document.querySelector('#file-path').textContent.includes('Destination'), 'destination loaded');
    gesture('#upload-file');
    await until(() => entry('[data-pick-file]', 'Source'), 'source picker');
    gesture(entry('[data-pick-file]', 'Source'));
    await until(() => entry('[data-pick-file]', 'lesson-source.txt'), 'source file');
    gesture(entry('[data-pick-file]', 'lesson-source.txt'));
    await until(() => entry('[data-file]', 'lesson-source.txt'), 'copied file listed');
    check(document.querySelector('#toast').textContent === 'File imported.', 'hand-only picker imports into selected folder');

    await WaveBoardInput.navigate('models');
    await until(() => document.querySelector('#viewer-host canvas'), '3D model renderer');
    await capture('before');
    gesture('#zoom-model-in');
    check(document.querySelector('#workspace-menu').hidden, 'hand selects Zoom in');
    await capture('zoom_in');
    gesture('#zoom-model-out');
    check(document.querySelector('#workspace-menu').hidden, 'hand selects Zoom out');
    await capture('zoom_out');

    gesture('#menu-toggle');
    gesture('#settings-button');
    await until(() => document.querySelector('#quit-app'), 'settings');
    gesture('#quit-app');
    check(!!document.querySelector('#confirm-quit'), 'hand opens quit confirmation');
    result.readyToQuit = true;
    await until(() => window.desktopQuitAcknowledged, 'native quit test acknowledgement');
    gesture('#confirm-quit');
  } catch (error) { result.error = String(error.stack || error); result.done = true; }
})();
