(function () {
  "use strict";

  // Bounded parent walk: Moodle places the SCO in a frame and exposes API above it.
  function findApi(start) {
    let current = start;
    for (let depth = 0; depth < 10 && current; depth += 1) {
      try {
        if (current.API && typeof current.API.LMSInitialize === "function") return current.API;
        if (current === current.parent) break;
        current = current.parent;
      } catch (_) { break; }
    }
    return null;
  }

  function locateApi() {
    return findApi(window) || (window.opener ? findApi(window.opener) : null);
  }

  function timeString(elapsedMs) {
    const cs = Math.floor(Math.max(0, elapsedMs) / 10);
    const hours = Math.floor(cs / 360000);
    const minutes = Math.floor(cs / 6000) % 60;
    const seconds = Math.floor(cs / 100) % 60;
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(cs % 100).padStart(2, "0")}`;
  }

  class Coverage {
    constructor(duration) {
      this.duration = duration;
      this.unit = Math.max(1, Math.ceil(duration / 16000));
      this.count = Math.ceil(duration / this.unit);
      this.bits = new Uint8Array(Math.ceil(this.count / 8));
      this.watched = 0;
    }
    has(i) { return Boolean(this.bits[i >> 3] & (1 << (i & 7))); }
    mark(i) {
      if (!this.has(i)) {
        this.bits[i >> 3] |= 1 << (i & 7);
        this.watched += 1;
        return true;
      }
      return false;
    }
    addContinuous(start, end) {
      let changed = false;
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return false;
      const first = Math.max(0, Math.floor(start / this.unit));
      const last = Math.min(this.count - 1, Math.floor(end / this.unit));
      for (let i = first; i <= last; i += 1) {
        const left = i * this.unit;
        const right = Math.min(this.duration, left + this.unit);
        if (start <= left + 0.05 && end >= right - 0.05) changed = this.mark(i) || changed;
      }
      return changed;
    }
    serialize() {
      let binary = "";
      for (const byte of this.bits) binary += String.fromCharCode(byte);
      return `V1:${Math.round(this.duration * 1000)}:${this.unit}:${btoa(binary)}`;
    }
    restore(value) {
      if (!value) return;
      const parts = value.split(":");
      if (parts.length !== 4 || parts[0] !== "V1" ||
          Number(parts[1]) !== Math.round(this.duration * 1000) || Number(parts[2]) !== this.unit) return;
      try {
        const bytes = atob(parts[3]);
        if (bytes.length !== this.bits.length) return;
        for (let i = 0; i < bytes.length; i += 1) this.bits[i] = bytes.charCodeAt(i);
        this.watched = 0;
        for (let i = 0; i < this.count; i += 1) if (this.has(i)) this.watched += 1;
      } catch (_) { /* Invalid prior state is ignored, never treated as completed. */ }
    }
  }

  function start(config) {
    const video = document.getElementById("video");
    const status = document.getElementById("state");
    const coverageText = document.getElementById("coverage");
    document.getElementById("title").textContent = config.title;
    document.title = config.title;
    video.controls = false;
    const api = locateApi();
    let initialized = false;
    try { initialized = api && api.LMSInitialize("") === "true"; } catch (_) { initialized = false; }
    if (!initialized) {
      status.textContent = "Tracciamento non disponibile. Apri la lezione dalla piattaforma Moodle.";
      status.className = "error";
      return;
    }
    const coverage = new Coverage(config.duration);
    let initialStatus, savedData, savedPosition;
    try {
      initialStatus = api.LMSGetValue("cmi.core.lesson_status");
      savedData = api.LMSGetValue("cmi.suspend_data");
      savedPosition = Number(api.LMSGetValue("cmi.core.lesson_location"));
    } catch (_) {
      status.textContent = "Impossibile leggere il tentativo SCORM. Riapri la lezione dalla piattaforma.";
      status.className = "error";
      return;
    }
    let complete = initialStatus === "completed" || initialStatus === "passed";
    coverage.restore(savedData);
    if (coverage.watched === coverage.count) complete = true;
    let dirty = true;
    let lastMedia = null;
    let lastWall = null;
    let runStart = null;
    let finished = false;
    const sessionStart = Date.now();

    function report(message, error = false) {
      status.textContent = message;
      status.className = error ? "error" : "";
    }
    function updateCoverage() {
      coverageText.textContent = `${Math.floor(coverage.watched * 100 / coverage.count)}% visto`;
    }
    function resetRun() {
      lastMedia = null;
      lastWall = null;
      runStart = null;
    }
    function recordContinuous(position) {
      if (runStart === null || !coverage.addContinuous(runStart, position)) return;
      dirty = true;
      updateCoverage();
      if (!complete && coverage.watched === coverage.count) {
        complete = true;
        sync(true);
      }
    }
    function observe() {
      if (video.seeking) return;
      const now = performance.now();
      const position = Math.min(video.currentTime, coverage.duration);
      if (lastMedia === null) {
        lastMedia = position;
        lastWall = now;
        if (runStart === null) runStart = position;
        return;
      }
      const delta = position - lastMedia;
      const elapsed = (now - lastWall) / 1000;
      if (delta < -0.1 || delta > elapsed * Math.max(1, video.playbackRate) + 0.8) {
        resetRun();
        lastMedia = position;
        lastWall = now;
        runStart = position;
        return;
      }
      if (delta > 0) recordContinuous(position);
      lastMedia = position;
      lastWall = now;
    }
    function setValue(key, value) {
      try { return api.LMSSetValue(key, String(value)) === "true"; }
      catch (_) { return false; }
    }
    function sync(force = false) {
      if (finished || (!dirty && !force)) return true;
      const data = coverage.serialize();
      let good = data.length <= 4096 &&
        setValue("cmi.core.lesson_location", Math.floor(video.currentTime || 0)) &&
        setValue("cmi.suspend_data", data) &&
        setValue("cmi.core.lesson_status", complete ? (initialStatus === "passed" ? "passed" : "completed") : "incomplete") &&
        setValue("cmi.core.exit", "suspend") &&
        setValue("cmi.core.session_time", timeString(Date.now() - sessionStart));
      if (good) {
        try { good = api.LMSCommit("") === "true"; } catch (_) { good = false; }
      }
      dirty = !good;
      report(good ? (complete ? "Lezione completata e salvata." : "Avanzamento salvato.") :
        "Salvataggio non riuscito. Mantieni aperta la lezione e verifica la connessione.", !good);
      return good;
    }
    function close() {
      if (finished) return;
      observe();
      if (sync(true)) {
        try { api.LMSFinish(""); } catch (_) { /* The commit has already succeeded. */ }
        finished = true;
      }
    }

    function onMetadata() {
      if (!Number.isFinite(video.duration) || Math.abs(video.duration - config.duration) > 0.25) {
        report("Durata video non coerente con il pacchetto. Contatta l'assistenza.", true);
        return;
      }
      if (config.resume && !video._resumed && Number.isFinite(savedPosition) && savedPosition > 0 &&
          savedPosition < video.duration - 2 && !complete) {
        video.currentTime = savedPosition;
      }
      video._resumed = true;
      // Anchor before playback starts: the first playing event may arrive after the first frame.
      if (runStart === null && lastMedia === null) runStart = Math.min(video.currentTime, coverage.duration);
      video.controls = true;
      updateCoverage();
      sync(true);
    }
    video.addEventListener("loadedmetadata", onMetadata);
    if (video.readyState >= 1) onMetadata();
    video.addEventListener("play", observe);
    video.addEventListener("playing", observe);
    video.addEventListener("timeupdate", observe);
    video.addEventListener("pause", () => {
      observe();
      lastMedia = null;
      lastWall = null;
      sync();
    });
    video.addEventListener("seeking", () => { resetRun(); });
    video.addEventListener("seeked", () => {
      resetRun();
      runStart = Math.min(video.currentTime, coverage.duration);
      if (!video.paused) observe();
      dirty = true;
    });
    video.addEventListener("ended", () => {
      observe();
      if (runStart !== null) recordContinuous(Math.min(video.currentTime, coverage.duration));
      resetRun();
      sync(true);
    });
    video.addEventListener("error", () => report("Video non riproducibile. Verifica la rete o il file MP4.", true));
    document.addEventListener("visibilitychange", () => {
      // Browser visibility is not playback: audio/video can continue in a background tab.
      observe();
      sync();
    });
    window.addEventListener("pagehide", close);
    window.addEventListener("beforeunload", close);
    setInterval(() => { if (!video.paused && !video.seeking) observe(); sync(); }, config.checkpointSeconds * 1000);
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { Coverage, timeString };
  if (typeof document !== "undefined") {
    fetch("config.json", { cache: "no-store" }).then(response => {
      if (!response.ok) throw new Error("config");
      return response.json();
    }).then(start).catch(() => {
      const status = document.getElementById("state");
      status.textContent = "Configurazione della lezione non disponibile.";
      status.className = "error";
    });
  }
})();
