// Qt's bridge stays inside the desktop process: no HTTP or WebSocket transport.
window.WaveBoardDesktop = location.protocol === "waveboard:";
if (window.WaveBoardDesktop) {
  // Ubuntu 22.04's Qt WebEngine predates Array.at and import maps.
  if (!Array.prototype.at) Object.defineProperty(Array.prototype, "at", {
    value(index) { index = Math.trunc(index) || 0; return this[index < 0 ? this.length + index : index]; },
  });
  // Qt 5 handles custom resources through XHR but not Chromium's Fetch API.
  // Three.js uses fetch; preserve its Response/stream contract for local assets.
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, options = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    if (url.protocol !== "waveboard:") return originalFetch(input, options);
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      const signal = options.signal || (input instanceof Request ? input.signal : null);
      const abort = () => request.abort();
      const cleanup = () => signal?.removeEventListener("abort", abort);
      if (signal?.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }
      request.open(options.method || (input instanceof Request ? input.method : "GET"), url.href);
      request.responseType = "arraybuffer";
      request.onload = () => {
        cleanup();
        // Qt's custom scheme has no HTTP status, so a successful load is 200.
        if (request.status && request.status >= 400) { reject(new Error("Local file could not be read.")); return; }
        resolve(new Response(request.response, { status: 200, headers: {
          "Content-Type": request.getResponseHeader("Content-Type") || "application/octet-stream",
        } }));
      };
      request.onerror = () => { cleanup(); reject(new Error("Local file could not be read.")); };
      request.onabort = () => { cleanup(); reject(new DOMException("Aborted", "AbortError")); };
      signal?.addEventListener("abort", abort, { once: true });
      request.send();
    });
  };
  window.WaveBoardNative = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "qrc:///qtwebchannel/qwebchannel.js";
    script.onerror = () => reject(new Error("The desktop connection could not start. Reopen WaveBoard."));
    script.onload = () => new QWebChannel(qt.webChannelTransport, channel => resolve(channel.objects.workspace));
    document.head.appendChild(script);
  });
}
