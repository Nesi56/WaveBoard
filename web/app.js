import { createHandInput } from "./hand-input.js";
import { createWhiteboard } from "./whiteboard.js";
import { renderProjectorHome, renderProjectorBoard } from "./projector.js";

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const escapeHTML = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const paths = {
  home: '<path d="m3 10 9-8 9 8v11h-6v-8H9v8H3z"/>',
  pen: '<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14z"/>',
  cube: '<path d="m12 3 9 5v9l-9 5-9-5V8zM3 8l9 5 9-5M12 13v9M7.5 5.5l9 5"/>',
  folder:
    '<path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  play: '<path d="m7 4 13 8-13 8z"/>',
  slides:
    '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="m10 7 5 3-5 3zM8 21h8"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4 2c-1.5 1-1.5 1.5-1.5 2M12 17h.01"/>',
  settings:
    '<path d="M3 6h9m4 0h5M3 12h3m4 0h11M3 18h11m4 0h3"/><circle cx="14" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="18" r="2"/>',
  target: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><circle cx="12" cy="12" r="4"/>',
  plus: '<path d="M12 4v16M4 12h16"/>',
  minus: '<path d="M4 12h16"/>',
  expand: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  touch:
    '<path d="M9 12V5a2 2 0 0 1 4 0v6l2-1 5 2-1 7-3 3h-5l-6-7a2 2 0 0 1 3-2l1 1"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  left: '<path d="m14 6-6 6 6 6"/>',
  right: '<path d="m10 6 6 6-6 6"/>',
  back: '<path d="m9 5-7 7 7 7M2 12h19"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  upload: '<path d="M12 16V3M7 8l5-5 5 5M4 16v5h16v-5"/>',
  undo: '<path d="M3 10h10a7 7 0 0 1 0 14M3 10l6-6m-6 6 6 6" transform="translate(0 -3)"/>',
  redo: '<path d="M21 10H11a7 7 0 0 0 0 14m10-14-6-6m6 6-6 6" transform="translate(0 -3)"/>',
  eraser:
    '<path d="m4 13 9-9a2 2 0 0 1 3 0l5 5a2 2 0 0 1 0 3l-9 9H7l-3-4a3 3 0 0 1 0-4m4-4 9 9M12 21h10"/>',
  highlighter: '<path d="m8 15 8-12 5 4-8 12-5-4zm0 0-4 5h7M3 22h15"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  grid: '<path d="M3 3h18v18H3zM9 3v18m6-18v18M3 9h18M3 15h18"/>',
  rotate: '<path d="M20 8a8 8 0 1 0 0 8m0-13v5h-5"/>',
  usb: '<path d="M12 21V3m-3 3 3-3 3 3M12 16l-6-4V8m6 5 6-4V6"/><circle cx="6" cy="6" r="2"/><path d="M16 3h4v3h-4z"/>',
  device:
    '<rect x="3" y="3" width="18" height="14" rx="2"/><path d="M8 22h8m-4-5v5"/>',
  file: '<path d="M14 2H5v20h14V7zM14 2v6h5M8 13h8m-8 4h5"/>',
  image:
    '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m3 17 5-5 4 4 4-6 5 6"/><circle cx="8" cy="8" r="1"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  spark:
    '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5zM20 2v4m-2-2h4"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  pause: '<path d="M8 5v14M16 5v14" stroke-width="5"/>',
  volume: '<path d="M11 4 6 8H3v8h3l5 4zM15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
  muted: '<path d="M11 4 6 8H3v8h3l5 4zM16 9l6 6m0-6-6 6"/>',
  list: '<path d="M7 6h14M7 12h14M7 18h14M3 6h.01M3 12h.01M3 18h.01"/>',
  up: '<path d="M12 21V3m-7 7 7-7 7 7"/>',
  search: '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
};
const icon = (name) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`;
const pages = [
  { id: "home", name: "Home", icon: "home" },
  { id: "whiteboard", name: "Whiteboard", icon: "pen" },
  { id: "models", name: "3D studio", icon: "cube" },
  { id: "files", name: "Files", icon: "folder" },
  { id: "video", name: "Video", icon: "play" },
  { id: "slides", name: "Slides", icon: "slides" },
];
const state = {
  page: "home",
  status: null,
  roots: [],
  root: "home",
  path: "",
  entries: [],
  board: null,
  viewer: null,
  cleanup: null,
  videoURL: null,
  slidePages: null,
  slideIndex: 0,
  slideTitle: "A little introduction",
  loadToken: 0,
  navToken: 0,
};
let toastTimer,
  latestFile = null;
try {
  latestFile = JSON.parse(localStorage.getItem("waveboard-recent") || "null");
} catch {}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("#toast").classList.remove("visible"), 3800);
}
window.addEventListener("waveboard-tracker-error", event => toast(event.detail || "The camera could not start."));
let nativeFullscreen = false;
let wasFullscreenBeforePresent = false;
let trackingStats = null;
window.addEventListener("waveboard-tracking-stats", event => {
  trackingStats = event.detail;
  updateTrackingStats();
});
window.addEventListener("waveboard-alignment-status", () => updateAlignmentSettings());
function updateAlignmentSettings() {
  const settings = window.WaveBoardHands?.getSettings();
  if ($("#projector-mode")) $("#projector-mode").checked = settings?.enabled === true;
  for (const id of ["#align-hands", "#calibrate-hands-button"])
    if ($(id)) $(id).disabled = !settings?.enabled;
  if ($("#projection-alignment-status")) $("#projection-alignment-status").textContent = settings?.status || "Waiting for hand controls";
  if ($("#recheck-projection")) $("#recheck-projection").disabled = !settings?.enabled || settings?.handCalibrated;
  if ($("#reset-hand-calibration")) $("#reset-hand-calibration").disabled = !settings?.handCalibrated;
}
window.addEventListener("waveboard-calibration-complete", () => toast("Hands aligned. Open your hand, then point and pinch."));
function updateTrackingStats() {
  const rate = value => Number.isFinite(value) ? `${value.toFixed(1)} fps` : "Waiting for camera";
  if ($("#hand-update-rate")) $("#hand-update-rate").textContent = rate(trackingStats?.tracking_fps);
  if ($("#hand-detection-rate")) $("#hand-detection-rate").textContent = rate(trackingStats?.inference_fps);
}
function isFullscreen() { return window.WaveBoardDesktop ? nativeFullscreen : Boolean(document.fullscreenElement); }
async function setFullscreen(enabled, element = document.documentElement) {
  if (window.WaveBoardDesktop) {
    const bridge = await window.WaveBoardNative;
    nativeFullscreen = await new Promise(resolve => bridge.setFullscreen(enabled, resolve));
  } else if (enabled) await element.requestFullscreen();
  else if (document.fullscreenElement) await document.exitFullscreen();
}
async function exitPresentation() {
  const stage = $("#slide-stage");
  stage?.classList.remove("presenting");
  await setFullscreen(window.WaveBoardDesktop && wasFullscreenBeforePresent);
}
if (window.WaveBoardDesktop) {
  window.WaveBoardNative.then(bridge => {
    bridge.isFullscreen(value => { nativeFullscreen = value; document.dispatchEvent(new Event("fullscreenchange")); });
    bridge.fullscreenChanged.connect(value => {
      nativeFullscreen = value;
      document.dispatchEvent(new Event("fullscreenchange"));
      if (!value) $("#slide-stage")?.classList.remove("presenting");
    });
    bridge.saved.connect(message => toast(message));
  }).catch(error => toast(error.message));
}

async function api(url, options) {
  if (window.WaveBoardDesktop) {
    const bridge = await window.WaveBoardNative;
    const request = { url, method: options?.method || "GET" };
    if (typeof options?.body === "string") request.body = JSON.parse(options.body);
    const encoded = await new Promise(resolve => bridge.request(JSON.stringify(request), resolve));
    const result = JSON.parse(encoded);
    if (result.error) throw new Error(result.error);
    return result.result;
  }
  const response = await fetch(url, options);
  const result = await response.json();
  if (!response.ok)
    throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}
const fileURL = (root, path) =>
  `/api/file?${new URLSearchParams({ root, path })}`;
const sizeLabel = (bytes) =>
  bytes < 1024
    ? `${bytes} B`
    : bytes < 1048576
      ? `${(bytes / 1024).toFixed(0)} KB`
      : `${(bytes / 1048576).toFixed(1)} MB`;
const extension = (name) => name.split(".").pop().toLowerCase();
const fileIcon = (entry) =>
  entry.is_dir
    ? "folder"
    : ["glb", "gltf", "obj", "stl"].includes(extension(entry.name))
      ? "cube"
      : ["mp4", "webm", "ogv", "mov", "m4v"].includes(extension(entry.name))
        ? "play"
        : ["ppt", "pptx", "pdf"].includes(extension(entry.name))
          ? "slides"
          : ["png", "jpg", "jpeg", "webp", "gif", "svg"].includes(
                extension(entry.name),
              )
            ? "image"
            : "file";
function remember(root, entry) {
  latestFile = { root, ...entry };
  try {
    localStorage.setItem("waveboard-recent", JSON.stringify(latestFile));
  } catch {}
}
const button = (id, label, ico, kind = "") =>
  `<button id="${id}" class="button ${kind}">${ico ? icon(ico) : ""}${label}</button>`;
const roundButton = (id, label, ico, extra = "") =>
  `<button id="${id}" class="round-control" aria-label="${label}" title="${label}" ${extra}>${icon(ico)}</button>`;
const homeButton = () => `<button class="round-control workspace-home" data-page="home" aria-label="Home" title="Home">${icon("home")}</button>`;
function modal(title, body, actions = "") {
  closeMenu();
  $("#dialog-content").innerHTML =
    `<div class="dialog-heading"><h2>${title}</h2><button class="icon-button" id="dialog-close" aria-label="Close dialog">${icon("close")}</button></div>${body}${actions ? `<div class="dialog-actions">${actions}</div>` : ""}`;
  $("#dialog-close").onclick = () => $("#dialog").close();
  if (!$("#dialog").open) $("#dialog").showModal();
}
$("#dialog").addEventListener("click", (e) => {
  if (e.target === $("#dialog")) {
    const r = e.target.getBoundingClientRect();
    if (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      e.target.close();
  }
});
let homeIndex = 0;
function setMenu(html = "") {
  $("#menu-tools").innerHTML = html;
}
function closeMenu() {
  $("#workspace-menu").hidden = true;
  $("#menu-backdrop").hidden = true;
  $("#menu-toggle").setAttribute("aria-expanded", "false");
  $("#main").inert = false;
}
function openMenu() {
  $("#workspace-menu").hidden = false;
  $("#menu-backdrop").hidden = false;
  $("#menu-toggle").setAttribute("aria-expanded", "true");
  $("#main").inert = true;
  $("#menu-close").focus();
}
$("#menu-toggle").onclick = () =>
  $("#workspace-menu").hidden ? openMenu() : closeMenu();
$("#menu-close").onclick = () => {
  closeMenu();
  $("#menu-toggle").focus();
};
$("#menu-backdrop").onclick = closeMenu;
$("#workspace-menu").addEventListener("click", (event) => {
  if (event.target.closest("button")) closeMenu();
});
$("#workspace-menu").addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const buttons = $$("button:not(:disabled)", $("#workspace-menu")),
    first = buttons[0],
    last = buttons.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});
$$("[data-icon]").forEach((el) => (el.innerHTML = icon(el.dataset.icon)));
document.addEventListener("click", (event) => {
  const target = event.target.closest("button[data-page]");
  if (target) navigate(target.dataset.page);
});
document.addEventListener("fullscreenchange", () => {
  $("#fullscreen-button").innerHTML = `${icon("expand")}${isFullscreen() ? "Exit full screen" : "Full screen"}`;
});
$("#fullscreen-button").onclick = async () => {
  try {
    await setFullscreen(!isFullscreen());
  } catch {
    toast("Full screen could not be changed. Try again.");
  }
};
function renderHome() {
  state.cleanup = renderProjectorHome({
    main: $("#main"),
    icon,
    navigate,
    index: homeIndex,
    onIndexChange: (index) => (homeIndex = index),
  });
}
async function navigate(page) {
  if (!pages.some((p) => p.id === page)) page = "home";
  closeMenu();
  if ($("#dialog").open) $("#dialog").close();
  setMenu();
  ++state.navToken;
  ++state.loadToken;
  state.cleanup?.();
  state.cleanup = null;
  if (state.board) {
    state.board.dispose();
    state.board = null;
  }
  if (state.viewer) {
    state.viewer.dispose();
    state.viewer = null;
  }
  const previousVideo = $("video");
  if (previousVideo) {
    previousVideo.pause();
    previousVideo.removeAttribute("src");
    previousVideo.load();
  }
  if (state.videoURL) {
    URL.revokeObjectURL(state.videoURL);
    state.videoURL = null;
  }
  state.page = page;
  history.replaceState(null, "", `#${page}`);
  document.body.dataset.page = page;
  if (page !== "home")
    homeIndex = Math.max(0, pages.findIndex((p) => p.id === page) - 1);
  try {
    await {
      home: renderHome,
      whiteboard: renderWhiteboard,
      models: renderModels,
      files: renderFiles,
      video: renderVideo,
      slides: renderSlides,
    }[page]();
  } catch (e) {
    toast(e.message);
  }
}
function renderWhiteboard() {
  const surface = renderProjectorBoard({
    main: $("#main"),
    icon,
    createWhiteboard,
    setMenu,
    toast,
    downloadBlob,
  });
  state.board = surface.board;
  state.cleanup = surface.dispose;
}
function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
async function renderModels() {
  const token = state.navToken;
  $("#main").innerHTML =
    `<section class="model-workspace"><div class="model-heading"><span class="model-dot"></span><span>3D Viewer · <span id="model-name">Wave sculpture</span></span>${button("open-model", "Open", "folder", "secondary")}</div><div class="viewer-wrap"><div id="viewer-host" class="viewer-host"></div><div class="model-zoom">${roundButton("zoom-model-in", "Zoom in", "plus")}${roundButton("zoom-model-out", "Zoom out", "minus")}</div><p class="gesture-hint model-hint">Pinch and drag to rotate</p></div><footer class="workspace-footer">${homeButton()}<div class="control-dock">${roundButton("reset-model", "Reset view", "rotate")}${roundButton("auto-rotate", "Auto rotate", "spark", 'aria-pressed="false"')}${roundButton("wire-mode", "Wireframe", "cube", 'aria-pressed="false"')}${roundButton("model-fullscreen", "Full screen", "expand")}</div></footer></section>`;
  setMenu(
    `${button("solid-mode", "Solid surfaces", "cube", "menu-tool")}<p id="model-status" class="menu-note" role="status">Loading…</p>`,
  );
  $("#model-fullscreen").onclick = () => setFullscreen(!isFullscreen()).catch(() => toast("Full screen could not be changed."));
  $("#open-model").onclick = () =>
    pickFile(
      "Open a 3D model",
      ["glb", "gltf", "obj", "stl"],
      async (root, entry) => {
        remember(root, entry);
        await loadModel(fileURL(root, entry.path), entry.name);
      },
      async (file) => {
        const url = URL.createObjectURL(file);
        try {
          await loadModel(url, file.name);
        } finally {
          URL.revokeObjectURL(url);
        }
      },
    );
  try {
    const { createModelViewer } = await import("./viewer3d.js");
    if (token !== state.navToken) return;
    const viewer = await createModelViewer($("#viewer-host"), {
      onStatus: (t) => {
        if (token === state.navToken && $("#model-status"))
          $("#model-status").textContent = t;
      },
      onError: (e) => {
        if (token === state.navToken) toast(e.message);
      },
    });
    if (token !== state.navToken) {
      viewer.dispose();
      return;
    }
    state.viewer = viewer;
    let rotate = false, wireframe = false;
    const setWireframe = (enabled) => {
      wireframe = enabled;
      state.viewer.setMode(wireframe ? "wireframe" : "solid");
      $("#wire-mode").setAttribute("aria-pressed", String(wireframe));
    };
    $("#solid-mode").onclick = () => setWireframe(false);
    $("#wire-mode").onclick = () => setWireframe(!wireframe);
    $("#reset-model").onclick = () => state.viewer.reset();
    $("#zoom-model-in").onclick = () => state.viewer.zoom(0.8);
    $("#zoom-model-out").onclick = () => state.viewer.zoom(1.25);
    $("#auto-rotate").onclick = () => {
      rotate = !rotate;
      state.viewer.setAutoRotate(rotate);
      $("#auto-rotate").setAttribute("aria-pressed", String(rotate));
      $("#auto-rotate").setAttribute("aria-label", rotate ? "Stop rotation" : "Auto rotate");
      $("#auto-rotate").title = rotate ? "Stop rotation" : "Auto rotate";
    };
  } catch (e) {
    if (token === state.navToken)
      $("#viewer-host").innerHTML =
        `<div class="empty-state"><h2>3D needs WebGL</h2><p>${escapeHTML(e.message)}. Check the device graphics drivers and reopen WaveBoard.</p></div>`;
  }
}
async function loadModel(url, name) {
  const viewer = state.viewer,
    token = state.navToken;
  if (!viewer) {
    toast("The 3D viewer is still starting.");
    return;
  }
  const loaded = await viewer.load(url, name);
  if (loaded && viewer === state.viewer && token === state.navToken)
    $("#model-name").textContent = name;
}
async function refreshRoots() {
  const result = await api("/api/status");
  state.status = result;
  state.roots = result.roots;
  if (!state.roots.some((r) => r.id === state.root)) {
    state.root = state.roots[0]?.id;
    state.path = "";
  }
  return result;
}
function searchKeyboard() {
  const rows = ["1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm.-_"];
  return `<div class="hand-keyboard" aria-label="File name keyboard">${rows.map(row => `<div class="keyboard-row">${[...row].map(key => `<button type="button" data-key="${key}" aria-label="Type ${key}">${key}</button>`).join("")}</div>`).join("")}<div class="keyboard-row keyboard-actions"><button type="button" data-key="space">Space</button><button type="button" data-key="backspace" aria-label="Delete last character">Delete</button><button type="button" data-key="clear">Clear</button></div></div>`;
}
function bindSearchKeyboard(input) {
  $$("[data-key]").forEach(key => {
    key.onclick = () => {
      const action = key.dataset.key;
      const start = input.selectionStart ?? input.value.length;
      const end = input.selectionEnd ?? start;
      if (action === "clear") input.value = "";
      else if (action === "backspace") input.setRangeText("", start === end ? Math.max(0, start - 1) : start, end, "end");
      else input.setRangeText(action === "space" ? " " : action, start, end, "end");
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus({ preventScroll: true });
    };
  });
}
let fileQuery = "";
let fileView = "grid";
async function renderFiles() {
  $("#main").innerHTML =
    `<section class="files-workspace"><div class="files-body"><aside class="file-sidebar" aria-label="File locations"><h1>Files</h1><div id="file-locations"></div><div id="usb-status"></div></aside><div class="file-browser"><div class="file-toolbar">${button("choose-location", "Location", "folder", "secondary")}<span class="breadcrumb" id="file-path">Loading…</span></div><div class="file-content"><div id="file-list" class="file-list file-cards"><div class="empty-state"><div class="loading-dot"></div></div></div></div></div></div><footer class="workspace-footer">${homeButton()}<div class="control-dock">${roundButton("parent-folder", "Parent folder", "up")}${roundButton("file-grid", "Grid view", "grid", 'aria-pressed="true"')}${roundButton("file-lines", "List view", "list", 'aria-pressed="false"')}</div>${button("upload-file", "Import", "upload", "files-import")}</footer></section>`;
  setMenu(
    `${button("upload-file-menu", "Import", "upload", "menu-tool")}${button("find-file", "Find file", "search", "menu-tool")}${button("refresh-files", "Refresh", "rotate", "menu-tool")}`,
  );
  $("#upload-file-menu").onclick = () => $("#upload-file").click();
  for (const [id, view] of [["#file-grid", "grid"], ["#file-lines", "list"]]) $(id).onclick = () => {
    fileView = view;
    renderFileRows();
  };
  $("#choose-location").onclick = async () => {
    try {
      await refreshRoots();
    } catch (e) {
      toast(e.message);
      return;
    }
    if (state.page !== "files") return;
    modal(
      "Choose a location",
      `<div class="location-list">${state.roots.map((r) => `<button class="picker-entry" data-root="${escapeHTML(r.id)}">${icon(r.kind === "usb" ? "usb" : r.id === "demo" ? "spark" : "device")}<span>${escapeHTML(r.label)}</span></button>`).join("")}</div>`,
    );
    $$("[data-root]").forEach(
      (b) =>
        (b.onclick = () => {
          state.root = b.dataset.root;
          state.path = "";
          fileQuery = "";
          $("#dialog").close();
          listFiles();
        }),
    );
  };
  $("#refresh-files").onclick = async () => {
    try {
      await refreshRoots();
      if (state.page === "files") await listFiles();
    } catch (e) {
      toast(e.message);
    }
  };
  $("#parent-folder").onclick = () => {
    state.path = state.path.split("/").slice(0, -1).join("/");
    fileQuery = "";
    listFiles();
  };
  $("#find-file").onclick = () => {
    modal(
      "Find a file",
      `<input class="search" id="file-search" placeholder="File name" aria-label="File name" value="${escapeHTML(fileQuery)}">${searchKeyboard()}`,
      button("apply-search", "Find", "file"),
    );
    const apply = () => {
      fileQuery = $("#file-search").value;
      $("#dialog").close();
      renderFileRows();
    };
    $("#apply-search").onclick = apply;
    $("#file-search").onkeydown = (e) => {
      if (e.key === "Enter") apply();
    };
    bindSearchKeyboard($("#file-search"));
    $("#file-search").focus();
  };
  $("#upload-file").onclick = () => {
    const root = state.root,
      path = state.path;
    if (window.WaveBoardDesktop) {
      pickFile("Import into this folder", [], async (sourceRoot, entry) => {
        await api("/api/import", { method: "POST", body: JSON.stringify({ source_root: sourceRoot, source_path: entry.path, root, path }) });
        toast("File imported.");
        if (state.page === "files") await listFiles();
      });
      return;
    }
    chooseLocal("", async (file) => {
      toast("Importing…");
      await api(
        `/api/upload?${new URLSearchParams({ root, path, name: file.name })}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/octet-stream" },
          body: file,
        },
      );
      toast("File imported.");
      if (state.page === "files") await listFiles();
    });
  };
  try {
    await refreshRoots();
    if (state.page === "files") await listFiles();
  } catch (e) {
    if ($("#file-list"))
      $("#file-list").innerHTML =
        `<div class="empty-state"><h2>Files unavailable</h2><p>${escapeHTML(e.message)}</p></div>`;
  }
}
function renderFileLocations() {
  const host = $("#file-locations");
  if (!host) return;
  host.innerHTML = state.roots.map(root => `<button class="location-pill ${state.root === root.id ? "active" : ""}" data-location="${escapeHTML(root.id)}" aria-current="${state.root === root.id ? "location" : "false"}">${icon(root.kind === "usb" ? "usb" : root.id === "demo" ? "spark" : "folder")}<span>${escapeHTML(root.label)}</span></button>`).join("");
  $$("[data-location]").forEach(element => element.onclick = () => {
    state.root = element.dataset.location;
    state.path = "";
    fileQuery = "";
    listFiles();
  });
  const usb = state.roots.find(root => root.kind === "usb");
  $("#usb-status").innerHTML = usb ? `<div class="usb-card"><strong>● USB drive connected</strong><span>${escapeHTML(usb.label)}</span><button class="button" id="browse-usb">Browse drive</button></div>` : "";
  if (usb) $("#browse-usb").onclick = () => { state.root = usb.id; state.path = ""; fileQuery = ""; listFiles(); };
}
let fileRequest = 0;
async function listFiles() {
  const req = ++fileRequest;
  try {
    const result = await api(
      `/api/files?${new URLSearchParams({ root: state.root, path: state.path })}`,
    );
    if (req !== fileRequest || state.page !== "files") return;
    state.entries = result.entries;
    $("#file-path").textContent = [state.roots.find((r) => r.id === state.root)?.label || "Files", ...state.path.split("/").filter(Boolean)].join(" › ");
    $("#parent-folder").disabled = !state.path;
    $("#upload-file").disabled = state.root === "demo";
    $("#upload-file-menu").disabled = state.root === "demo";
    renderFileLocations();
    renderFileRows();
  } catch (e) {
    if (req === fileRequest) toast(e.message);
  }
}
function renderFileRows() {
  const entries = state.entries.filter((e) =>
    e.name.toLowerCase().includes(fileQuery.toLowerCase()),
  );
  $("#file-list").classList.toggle("file-cards", fileView === "grid");
  $("#file-list").classList.toggle("file-lines", fileView === "list");
  $("#file-grid").setAttribute("aria-pressed", String(fileView === "grid"));
  $("#file-lines").setAttribute("aria-pressed", String(fileView === "list"));
  $("#file-list").innerHTML = entries.length
    ? entries
        .map(
          (e, i) =>
            `<div class="file-row file-kind-${fileIcon(e)}"><button class="file-open" data-file="${i}"><span class="file-art">${icon(fileIcon(e))}</span><span class="file-caption"><span class="file-name">${escapeHTML(e.name)}</span><span class="file-meta">${e.is_dir ? "Folder" : `${escapeHTML(extension(e.name).toUpperCase())} · ${sizeLabel(e.size || 0)}`}</span></span></button><button class="file-details icon-button" data-details="${i}" aria-label="Details for ${escapeHTML(e.name)}">${icon("more")}</button></div>`,
        )
        .join("")
    : `<div class="empty-state">${icon("folder")}<h2>${fileQuery ? "No matching files" : "Empty folder"}</h2>${fileQuery ? button("reset-search", "Show all files", "folder") : ""}</div>`;
  if ($("#reset-search"))
    $("#reset-search").onclick = () => {
      fileQuery = "";
      renderFileRows();
    };
  $$("[data-file]").forEach((b) => {
    const e = entries[Number(b.dataset.file)];
    b.onclick = () => {
      if (e.is_dir) {
        state.path = e.path;
        fileQuery = "";
        listFiles();
      } else openEntry(state.root, e).catch((err) => toast(err.message));
    };
    bindHold(b, () => showDetails(state.root, e));
  });
  $$("[data-details]").forEach(
    (b) =>
      (b.onclick = () =>
        showDetails(state.root, entries[Number(b.dataset.details)])),
  );
}
function bindHold(element, action) {
  let timer,
    start,
    held = false;
  const cancel = () => clearTimeout(timer);
  element.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    held = false;
    start = [e.clientX, e.clientY];
    timer = setTimeout(() => {
      if (!element.isConnected) return;
      held = true;
      action();
    }, 600);
  });
  element.addEventListener("pointermove", (e) => {
    if (start && Math.hypot(e.clientX - start[0], e.clientY - start[1]) > 12)
      cancel();
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((n) =>
    element.addEventListener(n, cancel),
  );
  element.addEventListener(
    "click",
    (e) => {
      if (held) {
        e.stopImmediatePropagation();
        e.preventDefault();
        held = false;
      }
    },
    true,
  );
  element.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    cancel();
    action();
  });
}
function showDetails(root, entry) {
  modal(
    "A closer look",
    `<dl class="file-detail"><dt>Name</dt><dd>${escapeHTML(entry.name)}</dd><dt>Location</dt><dd>${escapeHTML(state.roots.find((r) => r.id === root)?.label || root)} / ${escapeHTML(entry.path)}</dd><dt>Size</dt><dd>${entry.is_dir ? "Folder" : sizeLabel(entry.size)}</dd><dt>Modified</dt><dd>${new Date(entry.modified).toLocaleString()}</dd></dl>`,
    entry.is_dir ? "" : button("detail-download", "Download", "download"),
  );
  if (!entry.is_dir)
    $("#detail-download").onclick = () => {
      const a = document.createElement("a");
      a.href = fileURL(root, entry.path);
      a.download = entry.name;
      a.click();
    };
}
async function openEntry(root, entry) {
  const ext = extension(entry.name);
  remember(root, entry);
  if (["glb", "gltf", "obj", "stl"].includes(ext)) {
    const navigation = navigate("models"),
      token = state.navToken;
    await navigation;
    if (token !== state.navToken || state.page !== "models") return;
    await loadModel(fileURL(root, entry.path), entry.name);
  } else if (["mp4", "webm", "ogv", "mov", "m4v", "mkv"].includes(ext)) {
    await navigate("video");
    setVideo(fileURL(root, entry.path), entry.name);
  } else if (["ppt", "pptx", "pdf"].includes(ext)) {
    await navigate("slides");
    await loadPresentation(root, entry);
  } else if (["png", "jpg", "jpeg", "webp", "gif", "svg"].includes(ext))
    modal(
      escapeHTML(entry.name),
      `<img class="file-preview" src="${escapeHTML(fileURL(root, entry.path))}" alt="${escapeHTML(entry.name)}">`,
    );
  else if (
    ["txt", "md", "csv", "json", "log", "py"].includes(ext) &&
    entry.size < 300000
  ) {
    const response = await fetch(fileURL(root, entry.path));
    if (!response.ok) throw new Error("This file could not be opened.");
    modal(
      escapeHTML(entry.name),
      `<pre class="text-preview">${escapeHTML(await response.text())}</pre>`,
    );
  } else showDetails(root, entry);
}
function chooseLocal(accept, onFile) {
  const input = $("#local-file");
  const navigation = state.navToken;
  input.value = "";
  input.accept = accept;
  input.onchange = async () => {
    if (input.files[0] && navigation === state.navToken) {
      try {
        await onFile(input.files[0]);
      } catch (e) {
        if (navigation === state.navToken) toast(e.message);
      }
    }
  };
  input.click();
}
async function pickFile(title, extensions, onPick, onLocal) {
  // Every desktop file is available through a device/USB root. Native OS
  // choosers cannot receive the camera cursor, so stay inside this picker.
  if (window.WaveBoardDesktop) onLocal = null;
  // One picker owns this shared dialog. Closing it also invalidates pending
  // requests, so a slow folder or disconnected drive cannot reopen it later.
  pickFile.cancelActive?.();
  const dialog = $("#dialog");
  const navigation = state.navToken;
  let root = state.root || "home",
    path = "",
    request = 0,
    canceled = false;
  const active = () =>
    !canceled &&
    navigation === state.navToken &&
    pickFile.cancelActive === cancel &&
    dialog.open;
  function cancel() {
    canceled = true;
    ++request;
    dialog.removeEventListener("close", onClose);
    if (pickFile.cancelActive === cancel) pickFile.cancelActive = null;
  }
  function onClose() {
    // A close event from an earlier dialog can be delivered after reopening.
    if (!dialog.open) cancel();
  }
  function finish() {
    cancel();
    dialog.close();
  }
  function openLocal() {
    if (!active()) return;
    finish();
    chooseLocal(extensions.map((e) => "." + e).join(","), onLocal);
  }
  pickFile.cancelActive = cancel;
  dialog.addEventListener("close", onClose);
  async function draw() {
    if (canceled || navigation !== state.navToken) return;
    const n = ++request;
    modal(
      title,
      '<div class="picker-empty" role="status">Loading files…</div>',
    );
    try {
      if (!state.roots.length) await refreshRoots();
      if (!active() || n !== request) return;
      if (!state.roots.some((r) => r.id === root)) root = state.roots[0]?.id;
      const result = await api(
        `/api/files?${new URLSearchParams({ root, path })}`,
      );
      if (!active() || n !== request) return;
      const list = result.entries.filter(
        (e) => e.is_dir || !extensions.length || extensions.includes(extension(e.name)),
      );
      modal(
        title,
        `<div class="picker-roots">${state.roots.map((r) => `<button class="button ${r.id === root ? "" : "secondary"}" data-pick-root="${escapeHTML(r.id)}">${escapeHTML(r.label)}</button>`).join("")}</div><div class="file-toolbar"><button class="icon-button" id="picker-up" aria-label="Parent folder" ${!path ? "disabled" : ""}>${icon("back")}</button><span class="breadcrumb">${escapeHTML(path || "Choose a file")}</span></div><div class="picker-list">${list.length ? list.map((e, i) => `<button class="picker-entry" data-pick-file="${i}">${icon(fileIcon(e))}<span>${escapeHTML(e.name)}</span></button>`).join("") : '<p class="picker-empty">No supported files in this folder.</p>'}</div>`,
        onLocal
          ? button("picker-local", "Import a file", "upload", "secondary")
          : "",
      );
      $$("[data-pick-root]").forEach(
        (b) =>
          (b.onclick = () => {
            if (!active()) return;
            root = b.dataset.pickRoot;
            path = "";
            draw();
          }),
      );
      $("#picker-up").onclick = () => {
        if (!active()) return;
        path = path.split("/").slice(0, -1).join("/");
        draw();
      };
      $$("[data-pick-file]").forEach(
        (b) =>
          (b.onclick = async () => {
            if (!active()) return;
            const e = list[Number(b.dataset.pickFile)];
            if (e.is_dir) {
              path = e.path;
              draw();
            } else {
              finish();
              try {
                await onPick(root, e);
              } catch (err) {
                if (navigation === state.navToken) toast(err.message);
              }
            }
          }),
      );
      if (onLocal) $("#picker-local").onclick = openLocal;
    } catch (e) {
      if (!active() || n !== request) return;
      toast(e.message);
      if (onLocal) openLocal();
      else {
        modal(title, `<p class="picker-empty">${escapeHTML(e.message)}</p>`, button("picker-retry", "Try again", "rotate"));
        $("#picker-retry").onclick = draw;
      }
    }
  }
  await draw();
}
function renderVideo() {
  $("#main").innerHTML =
    `<section class="video-workspace"><header class="video-heading"><h1 id="video-title">Video</h1>${button("open-video", "Open", "folder", "secondary")}</header><div class="media-stage" id="media-stage"><svg class="video-landscape" viewBox="0 0 900 510" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><defs><linearGradient id="video-sky" x2="0" y2="1"><stop stop-color="#244d63"/><stop offset="1" stop-color="#112b3a"/></linearGradient></defs><path fill="url(#video-sky)" d="M0 0h900v510H0z"/><circle cx="715" cy="123" r="52" fill="#ffda60"/><path d="M0 320 150 215 320 318 530 172 760 339 900 271V510H0" fill="#1b3e50"/><path d="m0 389 220-83 240 91 225-73 215 80v106H0" fill="#0b232f"/></svg><button id="video-empty-open" class="video-poster-open" aria-label="Open a video"><span>${icon("play")}</span><strong>Open a video</strong></button></div><div class="media-controls" id="video-controls"><span id="video-time">0:00</span><input id="video-seek" type="range" min="0" max="1000" value="0" aria-label="Video position" disabled><span id="video-duration">0:00</span></div><footer class="workspace-footer">${homeButton()}<div class="control-dock">${roundButton("video-back", "Back 10 seconds", "undo", "disabled")}${roundButton("video-play", "Play", "play", "disabled")}${roundButton("video-forward", "Forward 10 seconds", "redo", "disabled")}${roundButton("mute-video", "Mute", "volume", "disabled")}</div><button id="video-speed" class="round-control video-speed" aria-label="Playback speed: 1 times" disabled>1×</button></footer></section>`;
  setMenu(
    `${button("video-fullscreen", "Full screen video", "expand", "menu-tool")}<p class="menu-note" id="video-info">Open an MP4 or WebM.</p>`,
  );
  const pick = () =>
    pickFile(
      "Open a video",
      ["mp4", "webm", "ogv", "mov", "m4v", "mkv"],
      (root, entry) => {
        remember(root, entry);
        setVideo(fileURL(root, entry.path), entry.name);
      },
      (file) => setVideo(URL.createObjectURL(file), file.name),
    );
  $("#open-video").onclick = pick;
  $("#video-empty-open").onclick = pick;
  $("#mute-video").disabled = true;
  $("#video-fullscreen").onclick = () => setFullscreen(!isFullscreen()).catch(() => toast("Full screen could not be changed."));
}
const mediaTime = (seconds) =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
function setVideo(url, name) {
  const stage = $("#media-stage");
  if (!stage) {
    if (url.startsWith("blob:")) URL.revokeObjectURL(url);
    return;
  }
  const previous = $("video", stage);
  if (previous) {
    previous.pause();
    previous.removeAttribute("src");
    previous.load();
  }
  if (state.videoURL && state.videoURL !== url)
    URL.revokeObjectURL(state.videoURL);
  state.videoURL = url.startsWith("blob:") ? url : null;
  stage.innerHTML =
    '<video playsinline preload="metadata" aria-label="Video player"></video>';
  const video = $("video", stage);
  video.src = url;
  $("#video-controls").hidden = false;
  $("#video-info").textContent = name;
  $("#video-title").textContent = name;
  for (const id of ["#mute-video", "#video-play", "#video-back", "#video-forward", "#video-speed"]) $(id).disabled = false;
  const sync = () => {
    if (!video.isConnected) return;
    const playing = !video.paused && !video.ended;
    $("#video-play").innerHTML = icon(playing ? "pause" : "play");
    $("#video-play").setAttribute("aria-label", playing ? "Pause" : "Play");
    $("#video-play").title = playing ? "Pause" : "Play";
    $("#video-time").textContent = mediaTime(video.currentTime);
    const seekable = Number.isFinite(video.duration) && video.duration > 0;
    $("#video-duration").textContent = seekable ? mediaTime(video.duration) : "0:00";
    $("#video-seek").disabled = !seekable;
    $("#video-back").disabled = !seekable;
    $("#video-forward").disabled = !seekable;
    $("#video-seek").value = seekable
      ? String((video.currentTime / video.duration) * 1000)
      : "0";
    $("#video-seek").style.setProperty("--played", `${Number($("#video-seek").value) / 10}%`);
    $("#mute-video").innerHTML = icon(video.muted ? "muted" : "volume");
    $("#mute-video").setAttribute("aria-label", video.muted ? "Unmute" : "Mute");
    $("#mute-video").title = video.muted ? "Unmute" : "Mute";
    $("#mute-video").setAttribute("aria-pressed", String(video.muted));
    $("#video-speed").textContent = `${video.playbackRate}×`;
    $("#video-speed").setAttribute("aria-label", `Playback speed: ${video.playbackRate} times`);
    $("#video-speed").title = `Playback speed: ${video.playbackRate}×`;
  };
  for (const event of [
    "loadedmetadata",
    "timeupdate",
    "play",
    "pause",
    "ended",
    "durationchange",
    "volumechange",
    "ratechange",
  ])
    video.addEventListener(event, sync);
  $("#video-play").onclick = () =>
    video.paused
      ? video.play().catch(() => toast("This video could not play."))
      : video.pause();
  $("#video-seek").oninput = (e) => {
    if (Number.isFinite(video.duration))
      video.currentTime = (Number(e.target.value) / 1000) * video.duration;
  };
  $("#mute-video").onclick = () => {
    video.muted = !video.muted;
  };
  const skip = seconds => { if (Number.isFinite(video.duration)) video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + seconds)); };
  $("#video-back").onclick = () => skip(-10);
  $("#video-forward").onclick = () => skip(10);
  $("#video-speed").onclick = () => {
    const speeds = [1, 1.25, 1.5, 2, 0.5, 0.75];
    video.playbackRate = speeds[(speeds.indexOf(video.playbackRate) + 1) % speeds.length];
  };
  $("#video-fullscreen").onclick = async () => {
    try {
      await setFullscreen(!isFullscreen());
    } catch {
      toast("Use the menu for full screen.");
    }
  };
  const onFullscreen = () => {
    $("#video-fullscreen")?.setAttribute(
      "aria-label",
      isFullscreen() ? "Exit full screen" : "Full screen video",
    );
  };
  document.addEventListener("fullscreenchange", onFullscreen);
  state.cleanup?.();
  state.cleanup = () =>
    document.removeEventListener("fullscreenchange", onFullscreen);
  onFullscreen();
  video.onerror = () => {
    if (!video.isConnected) return;
    toast("Cannot play this video. Try MP4 or WebM.");
    $("#video-info").textContent = "Unsupported format or disconnected drive.";
  };
  sync();
}
const demoSlides = [
  { title: "WaveBoard", copy: "Your ideas, in reach." },
  { title: "Tap. Draw. Explore.", copy: "Five tools. One board." },
  { title: "Make it yours.", copy: "Open a presentation to begin." },
];
function renderSlides() {
  state.slidePages = null;
  state.slideIndex = 0;
  state.slideTitle = "Meet your new workspace";
  $("#main").innerHTML =
    `<section class="slides-workspace"><div class="slide-deck">${roundButton("prev-slide", "Previous slide", "left")}<div class="slide-stage" id="slide-stage"></div>${roundButton("next-slide", "Next slide", "right")}</div><footer class="workspace-footer">${homeButton()}<div class="control-dock">${roundButton("open-slides", "Open slides", "folder")}${roundButton("present-slides", "Present slides", "expand")}<span class="slide-counter" id="slide-counter"></span></div><p class="gesture-hint slide-hint">Swipe palm to turn</p></footer></section>`;
  setMenu(
    `<p id="slide-note" class="menu-note">Sample slides · Open a presentation using the folder button.</p>`,
  );
  showSlide();
  $("#prev-slide").onclick = () => advanceSlide(-1);
  $("#next-slide").onclick = () => advanceSlide(1);
  $("#present-slides").onclick = async () => {
    try {
      wasFullscreenBeforePresent = isFullscreen();
      await setFullscreen(true, $("#slide-stage"));
      if (window.WaveBoardDesktop) $("#slide-stage").classList.add("presenting");
    } catch {
      toast("Presentation could not enter full screen. Try again.");
    }
  };
  $("#open-slides").onclick = () =>
    pickFile(
      "Open slides",
      ["ppt", "pptx", "pdf"],
      async (root, entry) => {
        remember(root, entry);
        await loadPresentation(root, entry);
      },
      async (file) => {
        const pageToken = state.navToken;
        const target =
          state.roots.find((r) => r.id === "home") ||
          state.roots.find((r) => r.id !== "demo");
        if (!target)
          throw new Error(
            "Choose a writable device folder in Files to import presentations.",
          );
        toast("Importing presentation to " + target.label + "…");
        const result = await api(
          `/api/upload?${new URLSearchParams({ root: target.id, path: "", name: file.name })}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/octet-stream" },
            body: file,
          },
        );
        if (pageToken !== state.navToken) return;
        await loadPresentation(target.id, result.entry);
      },
    );
}
function showSlide() {
  const stage = $("#slide-stage");
  if (!stage) return;
  const count = state.slidePages?.length || demoSlides.length;
  if (state.slidePages) {
    stage.innerHTML = `<img src="${escapeHTML(state.slidePages[state.slideIndex])}" alt="Slide ${state.slideIndex + 1}">`;
  } else {
    const s = demoSlides[state.slideIndex];
    stage.innerHTML = `<div class="demo-slide demo-slide-${state.slideIndex}"><div class="slide-orbits" aria-hidden="true"><span class="planet-large"></span><span class="planet-small"></span><span class="planet-tiny"></span></div><h2>${s.title}</h2><p>${s.copy}</p><div class="slide-progress" aria-hidden="true"><span style="width:${((state.slideIndex + 1) / count) * 100}%"></span></div></div>`;
  }
  stage.insertAdjacentHTML(
    "beforeend",
    `<div class="present-overlay"><button class="icon-button" id="present-prev" aria-label="Previous slide">${icon("left")}</button><span class="slide-counter">${state.slideIndex + 1} / ${count}</span><button class="icon-button" id="present-next" aria-label="Next slide">${icon("right")}</button><button class="icon-button" id="present-exit" aria-label="Exit presentation">${icon("close")}</button></div>`,
  );
  $("#present-prev").onclick = () => advanceSlide(-1);
  $("#present-next").onclick = () => advanceSlide(1);
  $("#present-prev").disabled = state.slideIndex === 0;
  $("#present-next").disabled = state.slideIndex === count - 1;
  $("#present-exit").onclick = () => exitPresentation().catch(error => toast(error.message));
  $("#slide-counter").textContent =
    `${String(state.slideIndex + 1).padStart(2, "0")} / ${String(count).padStart(2, "0")}`;
  $("#prev-slide").disabled = state.slideIndex === 0;
  $("#next-slide").disabled = state.slideIndex === count - 1;
}
function advanceSlide(delta) {
  state.slideIndex = Math.max(
    0,
    Math.min(
      (state.slidePages?.length || demoSlides.length) - 1,
      state.slideIndex + delta,
    ),
  );
  showSlide();
}
async function loadPresentation(root, entry) {
  if (state.page !== "slides" || !$("#slide-stage")) return;
  const token = ++state.loadToken;
  state.slideTitle = entry.name;
  $("#slide-stage").innerHTML =
    '<div class="empty-state"><div class="loading-dot"></div><h2>Loading slides…</h2></div>';
  $("#prev-slide").disabled = true;
  $("#next-slide").disabled = true;
  $("#slide-note").textContent = entry.name;
  try {
    let job = await api("/api/presentations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ root, path: entry.path }),
    });
    while (!["ready", "error"].includes(job.status)) {
      await new Promise((r) => setTimeout(r, 1000));
      if (token !== state.loadToken || state.page !== "slides") return;
      job = await api(`/api/presentations/${job.id}`);
    }
    if (token !== state.loadToken || state.page !== "slides") return;
    if (job.status === "error")
      throw new Error(job.error || "Could not render this presentation.");
    if (!job.pages.length) throw new Error("This presentation has no pages.");
    state.slidePages = job.pages;
    state.slideIndex = 0;
    showSlide();
    $("#slide-note").textContent =
      entry.name +
      " · Static slides · Use the arrows to move through your presentation.";
  } catch (e) {
    if (token !== state.loadToken) return;
    $("#slide-stage").innerHTML =
      `<div class="empty-state">${icon("slides")}<h2>Cannot open slides</h2><p>${escapeHTML(e.message)}</p><button class="button secondary" id="restore-demo">Back to the sample</button></div>`;
    $("#restore-demo").onclick = renderSlides;
    $("#slide-note").textContent =
      "On Ubuntu: sudo apt install libreoffice-impress poppler-utils";
  }
}
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("#workspace-menu").hidden) {
    closeMenu();
    $("#menu-toggle").focus();
    return;
  }
  if (!$("#workspace-menu").hidden) return;
  if (
    $("#dialog").open ||
    ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)
  )
    return;
  if (
    state.page === "slides" &&
    $("#slide-stage .demo-slide, #slide-stage > img")
  ) {
    if (["ArrowRight", "PageDown", " "].includes(event.key)) {
      event.preventDefault();
      advanceSlide(1);
    }
    if (["ArrowLeft", "PageUp"].includes(event.key)) {
      event.preventDefault();
      advanceSlide(-1);
    }
  }
  if (
    state.page === "whiteboard" &&
    (event.ctrlKey || event.metaKey) &&
    event.key.toLowerCase() === "z"
  ) {
    event.preventDefault();
    event.shiftKey ? state.board.redo() : state.board.undo();
  }
});
$("#help-button").onclick = () =>
  modal(
    "Simple by design",
    `<div class="dialog-copy"><p><strong>Hands:</strong> Move your index finger to point. Pinch thumb and index, then release to select. The highlighted control shows your target. Keep pinching and move up or down to scroll lists. Pinch and drag the video bar to seek.</p><p><strong>Home:</strong> Tap a tool card to open it.</p><p><strong>Whiteboard:</strong> Pick a pen and color, then drag to draw.</p><p><strong>More:</strong> The bottom-right button opens extra tools and settings. The home button returns to your tools.</p><p><strong>Files:</strong> Pinch to open. Use the three-dot button for details.</p><p><strong>3D:</strong> Pinch and drag to rotate. Use the + and − buttons to zoom.</p></div>`,
  );
function alignHands() {
  closeMenu();
  $("#dialog").close();
  if (window.WaveBoardHands) window.WaveBoardHands.startCalibration();
  else toast("Hand controls are still loading. Try again.");
}
$("#calibrate-hands-button").onclick = alignHands;
$("#settings-button").onclick = async () => {
  try {
    await refreshRoots();
  } catch {}
  const presentation = state.status?.presentation;
  const handSettings = window.WaveBoardHands?.getSettings();
  modal(
    "Settings",
    `<label class="settings-row"><span>Projector mode</span><input type="checkbox" id="projector-mode" ${handSettings?.enabled ? "checked" : ""}></label>
    <p class="dialog-copy">Mirror hands and align them to the projection. Turn off to use the original hand controls.</p>
    <div class="dialog-actions">${button("align-hands", "Align hands", "touch")}${button("reset-hand-calibration", "Reset alignment", "rotate", "secondary")}</div>
    <p class="dialog-copy">Match your index fingertip to 5 targets. Stay at your usual distance from the screen.</p>
    <p id="projection-alignment-status" class="dialog-copy" role="status"></p>
    <p class="dialog-copy">Corner markers align hands at the screen surface. For hands in the air, use Align hands.</p>
    <div class="dialog-actions">${button("recheck-projection", "Recheck corners", "rotate", "secondary")}</div>
    <label class="settings-row"><span>Extra contrast</span><input type="checkbox" id="contrast-setting" ${document.body.classList.contains("high-contrast") ? "checked" : ""}></label>
    <div class="settings-row"><span>Hand updates</span><span id="hand-update-rate" class="status-badge"></span></div>
    <div class="settings-row"><span>AI detection</span><span id="hand-detection-rate" class="status-badge"></span></div>
    <div class="settings-row"><span>PowerPoint</span><span class="status-badge">${presentation?.available ? "Ready" : "Setup needed"}</span></div>${presentation?.available ? "" : '<p class="dialog-copy">On Ubuntu, install LibreOffice Impress and poppler-utils.</p>'}`,
  );
  updateTrackingStats();
  $("#align-hands").onclick = alignHands;
  $("#reset-hand-calibration").onclick = () => { window.WaveBoardHands?.clearCalibration(); updateAlignmentSettings(); };
  $("#projector-mode").onchange = event => window.WaveBoardHands?.configure({ enabled: event.target.checked });
  $("#recheck-projection").onclick = () => window.WaveBoardHands?.realign();
  updateAlignmentSettings();
  if (window.WaveBoardDesktop) {
    $("#dialog-content").insertAdjacentHTML("beforeend", `<div class="dialog-actions">${button("quit-app", "Close WaveBoard", "close", "secondary")}</div>`);
    $("#quit-app").onclick = () => {
      modal("Close WaveBoard?", '<p class="dialog-copy">End this classroom session?</p>', `${button("cancel-quit", "Keep working", "", "secondary")}${button("confirm-quit", "Close WaveBoard", "close")}`);
      $("#cancel-quit").onclick = () => $("#dialog").close();
      $("#confirm-quit").onclick = () => window.WaveBoardNative.then(bridge => bridge.quit());
    };
  }
  $("#contrast-setting").onchange = (e) => {
    document.body.classList.toggle("high-contrast", e.target.checked);
    try {
      localStorage.setItem("waveboard-contrast", String(e.target.checked));
    } catch {}
  };
};
try {
  document.body.classList.toggle(
    "high-contrast",
    localStorage.getItem("waveboard-contrast") === "true",
  );
} catch {}
// Hand events share the normal workspace actions and add browser defaults that
// untrusted synthetic events do not trigger (click, range, and drag scrolling).
window.WaveBoardInput = Object.freeze({ navigate, ...createHandInput() });

navigate(location.hash.slice(1) || "home")
  .then(() => refreshRoots())
  .catch(() => {
    toast("The workspace could not open device files. Reopen WaveBoard.");
  });
