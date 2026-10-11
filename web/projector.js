/** Large, direct controls for the projected workspace. */
// Keep these indices in step with app.js; the home carousel has its own visual order.
const tools = [
  { page: "whiteboard", label: "Whiteboard", icon: "pen", color: "coral", description: "Draw, write and sketch" },
  { page: "models", label: "3D studio", icon: "cube", color: "blue", description: "Explore every angle" },
  { page: "files", label: "Files", icon: "folder", color: "yellow", description: "Browse and open your work" },
  { page: "video", label: "Video", icon: "play", color: "mint", description: "Watch and learn together" },
  { page: "slides", label: "Slides", icon: "slides", color: "violet", description: "Present, swipe, discover" },
];
const homeOrder = [0, 4, 2, 3, 1];

export function renderProjectorHome({ main, icon, navigate, index = 0, onIndexChange }) {
  let current = Number.isInteger(index) ? ((index % tools.length) + tools.length) % tools.length : 0;
  main.innerHTML = `
    <section class="home-screen" aria-label="Choose a tool">
      <header class="home-heading">
        <div class="home-meta"><time class="home-time"></time><span class="home-hand-status" role="status"><i aria-hidden="true"></i><span></span></span></div>
        <h1 class="home-brand">What shall we open?</h1>
      </header>
      <div class="home-carousel" role="group" aria-roledescription="carousel" aria-label="Tools"></div>
      <div class="carousel-dots" role="status" aria-live="polite" aria-atomic="true"></div>
      <footer class="home-footer">
        <div class="home-paging">
          <button type="button" id="previous-tool" class="round-control carousel-arrow" aria-label="Previous tool">${icon("left")}</button>
          <button type="button" id="next-tool" class="round-control carousel-arrow" aria-label="Next tool">${icon("right")}</button>
          <span class="home-swipe-hint">Swipe for more</span>
        </div>
        <div class="home-shortcuts">
          <button type="button" id="home-fullscreen" class="round-control" aria-label="Full screen">${icon("expand")}</button>
          <button type="button" id="home-settings" class="home-shortcut">${icon("settings")}<span>Settings</span></button>
          <button type="button" id="home-calibrate" class="home-shortcut calibrate-shortcut">${icon("target")}<span>Calibrate</span></button>
        </div>
      </footer>
    </section>`;
  const carousel = main.querySelector(".home-carousel");
  const previous = main.querySelector("#previous-tool");
  const next = main.querySelector("#next-tool");
  const dots = main.querySelector(".carousel-dots");
  const time = main.querySelector(".home-time");
  const status = main.querySelector(".home-hand-status");
  const calibrate = main.querySelector("#home-calibrate");
  const fullscreen = main.querySelector("#home-fullscreen");
  const settingsButton = main.querySelector("#home-settings");

  function update() {
    const position = homeOrder.indexOf(current);
    carousel.innerHTML = homeOrder.map((_, offset) => {
      const toolIndex = homeOrder[(position + offset) % homeOrder.length];
      const tool = tools[toolIndex];
      return `<button type="button" ${offset === 0 ? 'id="launch-tool"' : ""} class="launch-card ${offset === 0 ? "selected" : ""}" data-tool-index="${toolIndex}" data-accent="${tool.color}" aria-label="Open ${tool.label}">
        <span class="launch-icon">${icon(tool.icon)}</span>
        <span class="launch-label">${tool.label}</span>
        <span class="launch-description">${tool.description}</span>
        <span class="launch-prompt">${offset === 0 ? "Pinch to open" : "Open " + tool.label}</span>
      </button>`;
    }).join("");
    dots.setAttribute("aria-label", `${tools[current].label}, ${position + 1} of ${tools.length}`);
    dots.innerHTML = homeOrder.map((_, i) => `<span class="carousel-dot${i === position ? " active" : ""}" aria-hidden="true"></span>`).join("");
  }
  function advance(delta) {
    current = homeOrder[(homeOrder.indexOf(current) + delta + tools.length) % tools.length];
    update();
    onIndexChange?.(current);
  }
  function updateTime() {
    const now = new Date();
    time.dateTime = now.toISOString();
    time.textContent = `${now.toLocaleDateString(undefined, { weekday: "long" })} · ${now.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
  }
  function updateStatus(event) {
    const tracking = event?.detail || window.WaveBoardHands?.getTrackingStatus?.() || {};
    status.dataset.visible = String(tracking.visible === true);
    status.querySelector("span").textContent = tracking.visible ? "Hands detected" : tracking.connected ? "Looking for hands" : "Hand controls offline";
  }
  function updateSettings() {
    const enabled = window.WaveBoardHands?.getSettings?.().enabled === true;
    calibrate.disabled = !enabled;
    calibrate.title = enabled ? "Align your hands with the projection" : "Turn on Projector mode in Settings to calibrate";
  }
  function updateFullscreen() {
    const label = document.querySelector("#fullscreen-button")?.textContent?.trim() || "Full screen";
    fullscreen.setAttribute("aria-label", label);
    fullscreen.title = label;
  }
  function keyboard(event) {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey ||
      document.querySelector('dialog[open], [aria-modal="true"]:not([hidden])') ||
      event.target.closest?.('input, textarea, select, [contenteditable="true"], [role="menu"]')) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      advance(event.key === "ArrowLeft" ? -1 : 1);
    }
  }
  const goPrevious = () => advance(-1);
  const goNext = () => advance(1);
  const open = event => {
    const card = event.target.closest("[data-tool-index]");
    if (card) navigate(tools[Number(card.dataset.toolIndex)].page);
  };
  const settings = () => document.querySelector("#settings-button")?.click();
  const calibration = () => document.querySelector("#calibrate-hands-button")?.click();
  const toggleFullscreen = () => document.querySelector("#fullscreen-button")?.click();
  previous.addEventListener("click", goPrevious);
  next.addEventListener("click", goNext);
  carousel.addEventListener("click", open);
  settingsButton.addEventListener("click", settings);
  calibrate.addEventListener("click", calibration);
  fullscreen.addEventListener("click", toggleFullscreen);
  document.addEventListener("keydown", keyboard);
  document.addEventListener("fullscreenchange", updateFullscreen);
  window.addEventListener("waveboard-hand-status", updateStatus);
  window.addEventListener("waveboard-alignment-status", updateSettings);
  update(); updateTime(); updateStatus(); updateSettings(); updateFullscreen();
  const clock = window.setInterval(updateTime, 15000);
  return () => {
    window.clearInterval(clock);
    previous.removeEventListener("click", goPrevious);
    next.removeEventListener("click", goNext);
    carousel.removeEventListener("click", open);
    settingsButton.removeEventListener("click", settings);
    calibrate.removeEventListener("click", calibration);
    fullscreen.removeEventListener("click", toggleFullscreen);
    document.removeEventListener("keydown", keyboard);
    document.removeEventListener("fullscreenchange", updateFullscreen);
    window.removeEventListener("waveboard-hand-status", updateStatus);
    window.removeEventListener("waveboard-alignment-status", updateSettings);
  };
}

const colors = [["#26374d", "Navy"], ["#ff7858", "Coral"], ["#8f9fff", "Violet"], ["#78d7c8", "Mint"], ["#ffda60", "Yellow"]];
const sizes = [3, 8, 18];
const nearestSize = value => sizes.reduce((closest, size) => Math.abs(size - value) < Math.abs(closest - value) ? size : closest, sizes[0]);

export function renderProjectorBoard({ main, icon, createWhiteboard, setMenu, toast, downloadBlob }) {
  const drawingTools = [["pen", "Pen"], ["highlighter", "Marker"], ["eraser", "Eraser"]];
  main.innerHTML = `
    <section class="drawing-workspace" aria-label="Whiteboard">
      <div class="board-wrap"><canvas id="drawing-canvas" aria-label="Drawing surface"></canvas><span class="board-label">Whiteboard</span></div>
      <footer class="workspace-footer drawing-footer">
        <button type="button" class="round-control workspace-home" data-page="home" aria-label="Home">${icon("home")}</button>
        <div class="control-dock drawing-dock" role="group" aria-label="Drawing tools">
          ${drawingTools.map(([tool, label]) => `<button type="button" class="round-control" data-drawing-tool="${tool}" aria-label="${label}" title="${label}" aria-pressed="false">${icon(tool)}</button>`).join("")}
          <button type="button" id="undo-board-dock" class="round-control" aria-label="Undo" title="Undo">${icon("undo")}</button>
          <button type="button" id="ink-options" class="round-control ink-options" aria-label="Ink color and brush size" title="Ink color and brush size" aria-expanded="false" aria-controls="drawing-palette"><span aria-hidden="true"></span></button>
        </div>
      </footer>
      <div id="drawing-palette" class="drawing-palette" role="group" aria-label="Ink color and brush size" hidden>
        <div class="palette-heading"><strong>Ink &amp; size</strong><button type="button" class="round-control" id="close-palette" aria-label="Close ink options">${icon("close")}</button></div>
        <div class="palette-colors">${colors.map(([color, name]) => `<button type="button" class="swatch" data-color="${color}" style="--swatch:${color}" aria-label="${name} ink" aria-pressed="false"></button>`).join("")}</div>
        <div class="palette-sizes">${sizes.map((size, i) => `<button type="button" class="size-dot" data-size="${size}" aria-label="${["Small", "Medium", "Large"][i]} brush" aria-pressed="false"><span style="--dot-size:${[5, 12, 22][i]}px" aria-hidden="true"></span><b>${["Small", "Medium", "Large"][i]}</b></button>`).join("")}</div>
      </div>
    </section>`;
  const menuButton = (id, label, symbol) => `<button type="button" id="${id}" class="menu-tool">${icon(symbol)}<span>${label}</span></button>`;
  setMenu(`${drawingTools.map(([tool, label]) => `<button type="button" class="menu-tool" data-drawing-tool="${tool}" aria-pressed="false">${icon(tool)}<span>${label}</span></button>`).join("")}
    ${menuButton("undo-board", "Undo", "undo")}${menuButton("redo-board", "Redo", "redo")}${menuButton("export-board", "Save", "download")}${menuButton("clear-board", "Clear", "trash")}`);
  const menu = document.querySelector("#menu-tools");
  const colorButtons = [...main.querySelectorAll("[data-color]")];
  const sizeButtons = [...main.querySelectorAll("[data-size]")];
  const toolButtons = [...main.querySelectorAll("[data-drawing-tool]"), ...menu.querySelectorAll("[data-drawing-tool]")];
  const undoButtons = [menu.querySelector("#undo-board"), main.querySelector("#undo-board-dock")];
  const redo = menu.querySelector("#redo-board");
  const save = menu.querySelector("#export-board");
  const palette = main.querySelector("#drawing-palette");
  const inkOptions = main.querySelector("#ink-options");
  let disposed = false;
  const listeners = [];
  function pressed(button, active) {
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  // The initial notification occurs before createWhiteboard returns its controller.
  function sync(snapshot) {
    if (disposed) return;
    undoButtons.forEach(button => { button.disabled = !snapshot.canUndo; });
    redo.disabled = !snapshot.canRedo;
    colorButtons.forEach(button => pressed(button, button.dataset.color === snapshot.color.toLowerCase()));
    sizeButtons.forEach(button => pressed(button, Number(button.dataset.size) === nearestSize(snapshot.size)));
    toolButtons.forEach(button => pressed(button, button.dataset.drawingTool === snapshot.tool));
    inkOptions.style.setProperty("--selected-ink", snapshot.color);
    main.querySelector(".drawing-workspace").dataset.tool = snapshot.tool;
  }
  const board = createWhiteboard(main.querySelector("#drawing-canvas"), {
    paperColor: "#f7f6ef",
    onChange: sync,
    onStorageError: () => toast("Drawing could not be saved on this device. Use Save to keep an image."),
  });
  const restored = board.getState();
  const brushSizes = { pen: 8, highlighter: 24, eraser: 32, [restored.tool]: restored.size };
  function listen(element, handler) {
    element.addEventListener("click", handler);
    listeners.push(() => element.removeEventListener("click", handler));
  }
  function selectTool(tool) {
    const snapshot = board.getState();
    if (snapshot.tool === tool) return;
    brushSizes[snapshot.tool] = snapshot.size;
    board.setTool(tool);
    board.setSize(brushSizes[tool]);
  }
  function setPalette(open, returnFocus = false) {
    palette.hidden = !open;
    inkOptions.setAttribute("aria-expanded", String(open));
    if (returnFocus) inkOptions.focus();
  }
  const closeOutside = event => {
    if (!palette.hidden && !palette.contains(event.target) && !inkOptions.contains(event.target)) setPalette(false);
  };
  const escapePalette = event => {
    if (event.key === "Escape" && !palette.hidden) {
      event.preventDefault();
      setPalette(false, true);
    }
  };
  listen(inkOptions, () => setPalette(palette.hidden));
  listen(main.querySelector("#close-palette"), () => setPalette(false, true));
  document.addEventListener("pointerdown", closeOutside);
  document.addEventListener("keydown", escapePalette);
  colorButtons.forEach(button => listen(button, () => {
    if (board.getState().tool === "eraser") selectTool("pen");
    board.setColor(button.dataset.color);
  }));
  sizeButtons.forEach(button => listen(button, () => {
    const size = Number(button.dataset.size);
    brushSizes[board.getState().tool] = size;
    board.setSize(size);
  }));
  toolButtons.forEach(button => listen(button, () => selectTool(button.dataset.drawingTool)));
  undoButtons.forEach(button => listen(button, () => board.undo()));
  listen(redo, () => board.redo());
  listen(menu.querySelector("#clear-board"), () => { board.clear(); toast("Board cleared. Undo brings it back."); });
  listen(save, async () => {
    save.disabled = true;
    try {
      downloadBlob(await board.exportPNG(), `WaveBoard-${new Date().toISOString().slice(0, 10)}.png`);
      toast(window.WaveBoardDesktop ? "Saving drawing…" : "Drawing saved to Downloads.");
    } catch (error) { toast(error.message || "Drawing could not be saved."); }
    finally { save.disabled = false; }
  });
  return {
    board,
    dispose() {
      if (disposed) return;
      listeners.forEach(remove => remove());
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", escapePalette);
      board.dispose();
      disposed = true;
    },
  };
}
