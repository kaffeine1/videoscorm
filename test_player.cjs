const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { Coverage, timeString } = require('./player.js');

const coverage = new Coverage(10);
assert.equal(coverage.count, 10);
assert.equal(coverage.addContinuous(0, 3.2), true);
assert.equal(coverage.watched, 3);
assert.equal(coverage.addContinuous(8, 10), true);
assert.equal(coverage.watched, 5);
const restored = new Coverage(10);
restored.restore(coverage.serialize());
assert.equal(restored.watched, 5);
restored.addContinuous(3, 8);
assert.equal(restored.watched, 10);
const differentVideo = new Coverage(11);
differentVideo.restore(coverage.serialize());
assert.equal(differentVideo.watched, 0);
assert.equal(new Coverage(20000).serialize().length < 4096, true);
assert.equal(timeString(3661250), '01:01:01.25');

async function integration() {
  const values = { 'cmi.core.lesson_status': '', 'cmi.suspend_data': '', 'cmi.core.lesson_location': '' };
  const listeners = {};
  const videoListeners = {};
  const elements = {
    video: {
      currentTime: 0, duration: 10, readyState: 1, playbackRate: 1, paused: false, seeking: false,
      addEventListener(name, fn) { videoListeners[name] = fn; },
    },
    title: { textContent: '' }, coverage: { textContent: '' }, state: { textContent: '', className: '' },
  };
  let clock = 0;
  let commits = 0;
  const api = {
    LMSInitialize() { return 'true'; },
    LMSGetValue(key) { return values[key] || ''; },
    LMSSetValue(key, value) { values[key] = value; return 'true'; },
    LMSCommit() { commits += 1; return 'true'; },
    LMSFinish() { return 'true'; },
  };
  const window = { API: api, addEventListener(name, fn) { listeners[name] = fn; } };
  window.parent = window;
  const document = { visibilityState: 'visible', title: '',
    getElementById(id) { return elements[id]; }, addEventListener(name, fn) { listeners[name] = fn; } };
  const context = { window, document, fetch: async () => ({ ok: true,
    json: async () => ({ title: 'Prova', duration: 10, checkpointSeconds: 30, resume: true }) }),
    performance: { now: () => clock }, setInterval() {}, btoa, atob, Date };
  vm.runInNewContext(fs.readFileSync('./player.js', 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements.video.controls, true);
  videoListeners.playing();
  for (let i = 1; i <= 2; i += 1) {
    clock += 1000; elements.video.currentTime = i; videoListeners.timeupdate();
  }
  clock += 500; elements.video.currentTime = 2.5; videoListeners.timeupdate();
  videoListeners.pause();
  clock += 10000;
  videoListeners.playing();
  for (let i = 3; i <= 5; i += 1) {
    clock += 1000; elements.video.currentTime = i; videoListeners.timeupdate();
  }
  assert.equal(elements.coverage.textContent, '50% visto');
  videoListeners.seeking();
  elements.video.currentTime = 9;
  videoListeners.seeked();
  clock += 1000;
  elements.video.currentTime = 10;
  videoListeners.ended();
  assert.equal(values['cmi.core.lesson_status'], 'incomplete');
  assert.equal(elements.coverage.textContent, '60% visto');
  videoListeners.seeking();
  elements.video.currentTime = 5;
  videoListeners.seeked();
  for (let i = 6; i <= 9; i += 1) {
    clock += 1000; elements.video.currentTime = i; videoListeners.timeupdate();
  }
  assert.equal(values['cmi.core.lesson_status'], 'completed');
  assert.ok(commits >= 2);
  assert.equal(elements.coverage.textContent, '100% visto');
}

async function harness({ duration = 10, savedData = '', initialStatus = '' } = {}) {
  const values = { 'cmi.core.lesson_status': initialStatus, 'cmi.suspend_data': savedData,
    'cmi.core.lesson_location': '' };
  const videoListeners = {}, documentListeners = {}, windowListeners = {};
  const video = { currentTime: 0, duration, readyState: 1, playbackRate: 1, paused: true, seeking: false,
    addEventListener(name, callback) { videoListeners[name] = callback; } };
  const elements = { video, title: {}, coverage: {}, state: {} };
  let clock = 0, interval = null, failCommit = false;
  const api = {
    LMSInitialize() { return 'true'; },
    LMSGetValue(key) { return values[key] || ''; },
    LMSSetValue(key, value) { values[key] = value; return 'true'; },
    LMSCommit() { return failCommit ? 'false' : 'true'; },
    LMSFinish() { return 'true'; },
  };
  const window = { API: api, addEventListener(name, callback) { windowListeners[name] = callback; } };
  window.parent = window;
  const document = { visibilityState: 'visible',
    getElementById(id) { return elements[id]; },
    addEventListener(name, callback) { documentListeners[name] = callback; } };
  vm.runInNewContext(fs.readFileSync('./player.js', 'utf8'), {
    window, document, fetch: async () => ({ ok: true,
      json: async () => ({ title: 'Prova', duration, checkpointSeconds: 30, resume: true }) }),
    performance: { now: () => clock }, setInterval(callback) { interval = callback; }, btoa, atob, Date,
  });
  await new Promise(resolve => setImmediate(resolve));
  return { video, elements, values, document, videoListeners, documentListeners, windowListeners,
    advance(position, event = 'timeupdate') {
      clock += Math.max(0, position - video.currentTime) * 1000 / video.playbackRate;
      video.currentTime = position;
      videoListeners[event]();
    },
    tick() { interval(); },
    commitFailure(value) { failCommit = value; },
  };
}

async function backgroundPlayback() {
  const p = await harness({ duration: 600.066033 });
  p.video.paused = false;
  p.videoListeners.playing();
  p.advance(6);
  p.document.visibilityState = 'hidden';
  p.documentListeners.visibilitychange();
  for (const position of [54, 85, 137]) p.advance(position);
  p.document.visibilityState = 'visible';
  p.documentListeners.visibilitychange();
  p.advance(600.066033, 'ended');
  assert.equal(p.values['cmi.core.lesson_status'], 'completed', 'Actual background playback must count');
  assert.equal(p.elements.coverage.textContent, '100% visto');
}

async function delayedFirstFrame() {
  const p = await harness();
  p.video.paused = false;
  p.advance(0.24, 'playing');
  for (let second = 1; second <= 10; second += 1) p.advance(second);
  p.videoListeners.ended();
  assert.equal(p.values['cmi.core.lesson_status'], 'completed', 'A delayed playing event must not lose the first second');
}

async function backgroundSeekIsNotPlayback() {
  const p = await harness();
  p.video.paused = false;
  p.videoListeners.playing();
  p.advance(2);
  p.document.visibilityState = 'hidden';
  p.documentListeners.visibilitychange();
  p.videoListeners.seeking();
  p.video.currentTime = 9;
  p.videoListeners.seeked();
  p.advance(10, 'ended');
  assert.equal(p.values['cmi.core.lesson_status'], 'incomplete');
  assert.equal(p.elements.coverage.textContent, '30% visto');
}

async function priorProgressIsPreserved() {
  const data = 'V1:600066:1:PwAAAAAAIAAAACAAAAAAAAD+////////////////////////////////////////////////////////////////////////////AQ==';
  const p = await harness({ duration: 600.066033, savedData: data, initialStatus: 'incomplete' });
  const prior = new Coverage(600.066033);
  prior.restore(p.values['cmi.suspend_data']);
  assert.equal(prior.watched, 472);
  p.video.paused = false;
  p.videoListeners.playing();
  p.advance(138);
  assert.equal(p.values['cmi.core.lesson_status'], 'completed');
  assert.equal(p.elements.coverage.textContent, '100% visto');
}

async function commitFailureIsRetriedAndCompletedStatusIsNotDowngraded() {
  const p = await harness({ initialStatus: 'passed' });
  p.video.paused = false;
  p.videoListeners.playing();
  p.commitFailure(true);
  p.advance(2);
  p.tick();
  assert.equal(p.elements.state.className, 'error');
  p.commitFailure(false);
  p.tick();
  assert.equal(p.elements.state.className, '');
  assert.equal(p.values['cmi.core.lesson_status'], 'passed');
}

Promise.allSettled([integration(), backgroundPlayback(), delayedFirstFrame(), backgroundSeekIsNotPlayback(),
  priorProgressIsPreserved(), commitFailureIsRetriedAndCompletedStatusIsNotDowngraded()]).then(results => {
  const failed = results.filter(result => result.status === 'rejected');
  for (const result of failed) console.error(result.reason);
  if (failed.length) process.exitCode = 1;
  else console.log('Player coverage and 6 SCORM integration scenarios passed');
});
