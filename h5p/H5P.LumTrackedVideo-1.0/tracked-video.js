/* global H5P, H5PIntegration */
H5P.LumTrackedVideo = (function ($) {
  "use strict";

  // Keep the V1 coverage format compatible with our SCORM player, not its LMS transport.
  class Coverage {
    constructor(duration) {
      this.duration = duration;
      this.unit = Math.max(1, Math.ceil(duration / 16000));
      this.count = Math.ceil(duration / this.unit);
      this.bits = new Uint8Array(Math.ceil(this.count / 8));
      this.watched = 0;
    }
    has(i) { return Boolean(this.bits[i >> 3] & (1 << (i & 7))); }
    addContinuous(start, end) {
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return false;
      let changed = false;
      for (let i = Math.max(0, Math.floor(start / this.unit)); i <= Math.min(this.count - 1, Math.floor(end / this.unit)); i += 1) {
        const left = i * this.unit, right = Math.min(this.duration, left + this.unit);
        if (start <= left + 0.05 && end >= right - 0.05 && !this.has(i)) {
          this.bits[i >> 3] |= 1 << (i & 7);
          this.watched += 1;
          changed = true;
        }
      }
      return changed;
    }
    serialize() {
      return `V1:${Math.round(this.duration * 1000)}:${this.unit}:${btoa(String.fromCharCode(...this.bits))}`;
    }
    restore(value) {
      if (typeof value !== "string") return;
      const parts = value.split(":");
      if (parts.length !== 4 || parts[0] !== "V1" || Number(parts[1]) !== Math.round(this.duration * 1000) || Number(parts[2]) !== this.unit) return;
      try {
        const data = atob(parts[3]);
        if (data.length !== this.bits.length) return;
        for (let i = 0; i < data.length; i += 1) this.bits[i] = data.charCodeAt(i);
        this.watched = 0;
        for (let i = 0; i < this.count; i += 1) if (this.has(i)) this.watched += 1;
      } catch (_) { /* Malformed state is not evidence of completed playback. */ }
    }
  }

  function TrackedVideo(params, contentId, extras = {}) {
    H5P.EventDispatcher.call(this);
    this.contentId = contentId;
    this.params = params;
    const duration = Number(params.duration);
    if (!Number.isFinite(duration) || duration < 1) throw new Error("Durata video non valida.");
    this.coverage = new Coverage(duration);
    const previous = extras.previousState || {};
    if (previous.version === 1) this.coverage.restore(previous.coverage);
    this.completed = this.coverage.watched === this.coverage.count;
    this.emitted = this.completed && previous.emitted === true;
    this.position = previous.version === 1 && Number.isFinite(previous.position) ? Math.max(0, Math.min(previous.position, duration)) : 0;
    this.playedSeconds = previous.version === 1 && Number.isFinite(previous.playedSeconds) ? Math.max(0, previous.playedSeconds) : 0;
    this.lastMedia = this.lastWall = this.runStart = null;
    this.saveEnabled = typeof H5PIntegration !== "undefined" && H5PIntegration.saveFreq !== false &&
      typeof H5P.setUserData === "function";
    this.saveFailed = false;
    this.validVideo = false;
  }

  TrackedVideo.prototype = Object.create(H5P.EventDispatcher.prototype);
  TrackedVideo.prototype.constructor = TrackedVideo;

  TrackedVideo.prototype.getTitle = function () { return this.params.lessonTitle; };
  TrackedVideo.prototype.getCurrentState = function () {
    return { version: 1, coverage: this.coverage.serialize(), position: this.position,
      playedSeconds: this.playedSeconds, emitted: this.emitted };
  };
  TrackedVideo.prototype.resetRun = function () { this.lastMedia = this.lastWall = this.runStart = null; };
  TrackedVideo.prototype.report = function (text, error = false) {
    this.$state.text(text).toggleClass("error", error);
  };
  TrackedVideo.prototype.refresh = function () {
    this.$coverage.text(`${Math.floor(this.coverage.watched * 100 / this.coverage.count)}% visto`);
    this.$retry.prop("hidden", !this.completed);
  };

  TrackedVideo.prototype.observe = function (ended = false) {
    const video = this.video;
    if (!this.validVideo || video.seeking) return;
    const now = performance.now();
    // A genuine ended event tolerates the small container/stream duration difference.
    const position = ended && video.ended ? this.coverage.duration : Math.min(video.currentTime, this.coverage.duration);
    this.position = position;
    if (this.lastMedia === null) {
      this.lastMedia = position;
      this.lastWall = now;
      if (this.runStart === null) this.runStart = position;
      return;
    }
    const delta = position - this.lastMedia, elapsed = (now - this.lastWall) / 1000;
    if (delta < -0.1 || delta > elapsed * Math.max(1, video.playbackRate) + 0.8) {
      this.resetRun();
      this.runStart = position;
    } else if (delta > 0) {
      this.playedSeconds += delta / Math.max(0.1, video.playbackRate);
      if (this.coverage.addContinuous(this.runStart, position)) this.refresh();
      if (!this.completed && this.coverage.watched === this.coverage.count) {
        this.completed = true;
        this.refresh();
        this.sendCompletion();
      }
    }
    this.lastMedia = position;
    this.lastWall = now;
  };

  TrackedVideo.prototype.save = function () {
    if (!this.saveEnabled) {
      this.report("Ripresa non disponibile: il salvataggio dello stato H5P è disattivato in piattaforma.", true);
      return;
    }
    const state = this.getCurrentState(), serialized = JSON.stringify(state);
    // Core only calls errorCallback on failure, not on success or unchanged-state skips.
    if (serialized === this.lastRequestedState && !this.saveFailed) return;
    this.lastRequestedState = serialized;
    this.saveFailed = false;
    this.report(this.completed ? "Visione completata. Completamento comunicato alla piattaforma." : "Salvataggio richiesto alla piattaforma.");
    H5P.setUserData(this.contentId, "state", state, {deleteOnChange: true,
      errorCallback: (error) => {
        if (!error) return;
        this.saveFailed = true;
        // Failed requests remain in core's optimistic cache. Remove only our unchanged snapshot for retry.
        const content = H5PIntegration.contents && H5PIntegration.contents[`cid-${this.contentId}`];
        const cache = content && content.contentUserData && content.contentUserData[0];
        if (cache && cache.state === serialized) delete cache.state;
        this.report("Salvataggio non riuscito. Verifica la connessione e mantieni aperta la lezione.", true);
      }});
  };

  TrackedVideo.prototype.sendCompletion = function (manual = false) {
    if (!this.completed || (this.emitted && !manual)) return;
    const event = this.createXAPIEventTemplate("completed");
    const statement = event.data.statement;
    statement.object.definition.name = {"it": this.params.lessonTitle};
    statement.object.definition.description = {"it": this.params.lessonTitle};
    statement.object.definition.type = "http://id.tincanapi.com/activitytype/video";
    statement.object.definition.extensions = Object.assign({}, statement.object.definition.extensions,
      {"https://arcapuglia.it/xapi/video-coverage": 1});
    // No score or success grade: completion is viewing, not an academic assessment.
    statement.result = {completion: true, duration: `PT${Math.max(0, this.playedSeconds).toFixed(2)}S`};
    this.trigger(event);
    this.emitted = true;
    this.report("Visione completata. Completamento comunicato alla piattaforma.");
    this.save();
  };

  TrackedVideo.prototype.attach = function ($container) {
    $container.addClass("lum-tracked-video");
    $("<h2>").text(this.params.lessonTitle).appendTo($container);
    const $player = $("<div>", {class: "lum-video-player"}).appendTo($container);
    const $footer = $("<div>", {class: "lum-video-footer"}).appendTo($container);
    this.$coverage = $("<span>").appendTo($footer);
    this.$state = $("<span>", {class: "lum-video-state", role: "status", "aria-live": "polite"}).appendTo($footer);
    this.$retry = $("<button>", {type: "button", text: "Reinvia completamento", hidden: true}).appendTo($footer);
    this.$retry.on("click", () => {
      this.$retry.prop("disabled", true);
      this.sendCompletion(true);
      setTimeout(() => this.$retry.prop("disabled", false), 10000);
    });
    this.player = new H5P.Video({sources: this.params.video,
      visuals: {controls: true, fit: false}, playback: {autoplay: false, loop: false}, a11y: []}, this.contentId);
    this.player.attach($player);
    this.video = $player.find("video")[0];
    if (!this.video) { this.report("Il player non ha creato un video HTML5 compatibile.", true); return; }
    const video = this.video;
    const metadata = () => {
      if (!Number.isFinite(video.duration) || Math.abs(video.duration - this.coverage.duration) > 0.25) {
        this.validVideo = false;
        this.report("Durata video non coerente con il pacchetto. Contatta l'assistenza.", true);
        return;
      }
      this.validVideo = true;
      if (!this.metadataLoaded && this.params.resume && this.position > 0 && this.position < video.duration - 2 && !this.completed) {
        video.currentTime = this.position;
      }
      this.metadataLoaded = true;
      if (this.runStart === null) this.runStart = video.currentTime;
      this.refresh();
      this.report(this.completed ? "Visione già completata." : "Lezione pronta.");
      if (!this.saveEnabled) this.save();
      if (this.completed && !this.emitted) this.sendCompletion();
    };
    video.addEventListener("loadedmetadata", metadata);
    if (video.readyState >= 1) metadata();
    for (const name of ["play", "playing", "timeupdate"]) video.addEventListener(name, () => this.observe());
    video.addEventListener("pause", () => { this.observe(); this.lastMedia = this.lastWall = null; this.save(); });
    video.addEventListener("seeking", () => this.resetRun());
    video.addEventListener("seeked", () => { this.resetRun(); this.runStart = video.currentTime; this.position = video.currentTime; });
    video.addEventListener("ended", () => { this.observe(true); this.save(); });
    video.addEventListener("error", () => this.report("Errore di riproduzione del video. Verifica la connessione.", true));
    this.onVisibility = () => { this.observe(); this.save(); };
    this.onPageHide = () => { this.observe(); this.save(); };
    document.addEventListener("visibilitychange", this.onVisibility);
    window.addEventListener("pagehide", this.onPageHide);
    this.timer = setInterval(() => { this.observe(); this.save(); }, Number(this.params.checkpointSeconds) * 1000);
    this.on("resize", () => this.player.trigger("resize"));
  };
  return TrackedVideo;
})(H5P.jQuery);
