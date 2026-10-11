/** Simple, generous controls for a low-resolution projected workspace. */
const tools = [
  { page: "whiteboard", label: "Draw", icon: "pen" },
  { page: "models", label: "3D", icon: "cube" },
  { page: "files", label: "Files", icon: "folder" },
  { page: "video", label: "Video", icon: "play" },
  { page: "slides", label: "Slides", icon: "slides" },
];

export function renderProjectorHome({
  main,
  icon,
  navigate,
  index = 0,
  onIndexChange,
}) {
  let current = Number.isInteger(index)
    ? ((index % tools.length) + tools.length) % tools.length
    : 0;
  main.innerHTML = `
    <section class="home-screen" aria-label="Choose a tool">
      <h1 class="home-brand">WaveBoard</h1>
      <div class="home-carousel" role="group" aria-roledescription="carousel" aria-label="Tools">
        <button type="button" id="previous-tool" class="carousel-arrow" aria-label="Previous tool">${icon("left")}</button>
        <button type="button" id="launch-tool" class="launch-card"></button>
        <button type="button" id="next-tool" class="carousel-arrow" aria-label="Next tool">${icon("right")}</button>
      </div>
      <div class="carousel-dots" role="status" aria-live="polite" aria-atomic="true"></div>
    </section>`;

  const launch = main.querySelector("#launch-tool");
  const previous = main.querySelector("#previous-tool");
  const next = main.querySelector("#next-tool");
  const dots = main.querySelector(".carousel-dots");

  function update() {
    const tool = tools[current];
    launch.innerHTML = `<span class="launch-icon">${icon(tool.icon)}</span><span class="launch-label">${tool.label}</span>`;
    launch.setAttribute("aria-label", `Open ${tool.label}`);
    dots.setAttribute(
      "aria-label",
      `${tool.label}, ${current + 1} of ${tools.length}`,
    );
    dots.innerHTML = tools
      .map(
        (_, i) =>
          `<span class="carousel-dot${i === current ? " active" : ""}" aria-hidden="true"></span>`,
      )
      .join("");
  }

  function advance(delta) {
    current = (current + delta + tools.length) % tools.length;
    update();
    onIndexChange?.(current);
  }

  const goPrevious = () => advance(-1);
  const goNext = () => advance(1);
  const open = () => navigate(tools[current].page);
  function keyboard(event) {
    if (
      event.defaultPrevented ||
      event.altKey ||
      event.ctrlKey ||
      event.metaKey ||
      document.querySelector(
        'dialog[open], [aria-modal="true"]:not([hidden])',
      ) ||
      event.target.closest?.(
        'input, textarea, select, [contenteditable="true"], [role="menu"]',
      )
    )
      return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      advance(event.key === "ArrowLeft" ? -1 : 1);
    }
  }

  previous.addEventListener("click", goPrevious);
  next.addEventListener("click", goNext);
  launch.addEventListener("click", open);
  document.addEventListener("keydown", keyboard);
  update();

  return () => {
    previous.removeEventListener("click", goPrevious);
    next.removeEventListener("click", goNext);
    launch.removeEventListener("click", open);
    document.removeEventListener("keydown", keyboard);
  };
}

const colors = [
  ["#334b3b", "Dark green"],
  ["#819e59", "Green"],
  ["#d89d6a", "Orange"],
  ["#a6b8cf", "Blue"],
  ["#c78d9a", "Pink"],
];
const sizes = [3, 8, 18];
const nearestSize = (value) =>
  sizes.reduce(
    (closest, size) =>
      Math.abs(size - value) < Math.abs(closest - value) ? size : closest,
    sizes[0],
  );

export function renderProjectorBoard({
  main,
  icon,
  createWhiteboard,
  setMenu,
  toast,
  downloadBlob,
}) {
  main.innerHTML = `
    <section class="drawing-workspace" aria-label="Whiteboard">
      <div class="board-wrap"><canvas id="drawing-canvas" aria-label="Drawing surface"></canvas></div>
      <div class="drawing-palette" role="group" aria-label="Drawing color and size">
        ${colors.map(([color, name]) => `<button type="button" class="swatch" data-color="${color}" style="--swatch:${color}" aria-label="${name} ink" aria-pressed="false"></button>`).join("")}
        <span class="palette-divider" aria-hidden="true"></span>
        ${sizes.map((size, i) => `<button type="button" class="size-dot" data-size="${size}" aria-label="${["Small", "Medium", "Large"][i]} brush" aria-pressed="false"><span style="--dot-size:${[5, 12, 22][i]}px" aria-hidden="true"></span></button>`).join("")}
      </div>
    </section>`;

  const menuButton = (id, label, symbol) =>
    `<button type="button" id="${id}" class="menu-tool">${icon(symbol)}<span>${label}</span></button>`;
  setMenu(`
    ${[
      ["pen", "Pen"],
      ["highlighter", "Marker"],
      ["eraser", "Eraser"],
    ]
      .map(
        ([tool, label]) =>
          `<button type="button" class="menu-tool" data-drawing-tool="${tool}" aria-pressed="false">${icon(tool)}<span>${label}</span></button>`,
      )
      .join("")}
    ${menuButton("undo-board", "Undo", "undo")}
    ${menuButton("redo-board", "Redo", "redo")}
    ${menuButton("export-board", "Save", "download")}
    ${menuButton("clear-board", "Clear", "trash")}`);

  const menu = document.querySelector("#menu-tools");
  const colorButtons = [...main.querySelectorAll("[data-color]")];
  const sizeButtons = [...main.querySelectorAll("[data-size]")];
  const toolButtons = [...menu.querySelectorAll("[data-drawing-tool]")];
  const undo = menu.querySelector("#undo-board");
  const redo = menu.querySelector("#redo-board");
  const save = menu.querySelector("#export-board");
  let disposed = false;
  const listeners = [];

  function pressed(button, active) {
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }

  // createWhiteboard calls onChange while it initializes, before board exists.
  function sync(snapshot) {
    if (disposed) return;
    undo.disabled = !snapshot.canUndo;
    redo.disabled = !snapshot.canRedo;
    colorButtons.forEach((button) =>
      pressed(button, button.dataset.color === snapshot.color.toLowerCase()),
    );
    sizeButtons.forEach((button) =>
      pressed(
        button,
        Number(button.dataset.size) === nearestSize(snapshot.size),
      ),
    );
    toolButtons.forEach((button) =>
      pressed(button, button.dataset.drawingTool === snapshot.tool),
    );
    main.querySelector(".drawing-workspace").dataset.tool = snapshot.tool;
  }

  const board = createWhiteboard(main.querySelector("#drawing-canvas"), {
    onChange: sync,
    onStorageError: () =>
      toast(
        "Drawing could not be saved on this device. Use Save to keep an image.",
      ),
  });
  const restored = board.getState();
  const brushSizes = { pen: 8, highlighter: 24, eraser: 32 };
  brushSizes[restored.tool] =
    restored.tool === "pen" ? nearestSize(restored.size) : restored.size;
  const restoredColor = restored.color.toLowerCase();
  const paletteColor = colors.some(([color]) => color === restoredColor)
    ? restoredColor
    : colors[0][0];
  if (restored.color !== paletteColor) board.setColor(paletteColor);
  if (restored.size !== brushSizes[restored.tool])
    board.setSize(brushSizes[restored.tool]);

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

  colorButtons.forEach((button) =>
    listen(button, () => {
      if (board.getState().tool === "eraser") selectTool("pen");
      board.setColor(button.dataset.color);
    }),
  );
  sizeButtons.forEach((button) =>
    listen(button, () => {
      const size = Number(button.dataset.size);
      brushSizes[board.getState().tool] = size;
      board.setSize(size);
    }),
  );
  toolButtons.forEach((button) =>
    listen(button, () => selectTool(button.dataset.drawingTool)),
  );
  listen(undo, () => board.undo());
  listen(redo, () => board.redo());
  listen(menu.querySelector("#clear-board"), () => {
    board.clear();
    toast("Board cleared. Undo brings it back.");
  });
  listen(save, async () => {
    save.disabled = true;
    try {
      downloadBlob(
        await board.exportPNG(),
        `WaveBoard-${new Date().toISOString().slice(0, 10)}.png`,
      );
      toast(window.WaveBoardDesktop ? "Saving drawing…" : "Drawing saved to Downloads.");
    } catch (error) {
      toast(error.message || "Drawing could not be saved.");
    } finally {
      save.disabled = false;
    }
  });

  return {
    board,
    dispose() {
      if (disposed) return;
      listeners.forEach((remove) => remove());
      board.dispose();
      disposed = true;
    },
  };
}
