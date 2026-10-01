const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync('h5p/H5P.LumTrackedVideo-1.0/tracked-video.js', 'utf8');

function harness({duration = 10, previousState, resume = true, saveEnabled = true} = {}) {
  let clock = 0, failSave = false, timer;
  const events = {}, documentEvents = {}, statements = [], saves = [];
  const video = {currentTime: 0, duration, readyState: 1, paused: true, ended: false, seeking: false, playbackRate: 1,
    addEventListener(name, callback) { events[name] = callback; }};
  class Element {
    constructor() { this.value = ''; this.properties = {}; }
    addClass() { return this; } appendTo() { return this; } on() { return this; }
    text(value) { this.value = value; return this; }
    toggleClass(_, value) { this.error = value; return this; }
    prop(key, value) { this.properties[key] = value; return this; }
    find() { return [video]; }
  }
  const $ = () => new Element();
  $.inArray = (item, list) => list.indexOf(item);
  function Dispatcher() {}
  Dispatcher.prototype.on = function () {};
  Dispatcher.prototype.trigger = function (event) { statements.push(event.data.statement); };
  Dispatcher.prototype.createXAPIEventTemplate = function (verb) {
    return {data: {statement: {verb: {id: 'http://adlnet.gov/expapi/verbs/' + verb},
      object: {id: 'https://moodle.invalid/video', definition: {}}}}};
  };
  const integration = {saveFreq: saveEnabled ? 30 : false, user: {name: 'Test', mail: 'test@example.invalid'},
    contents: {'cid-1': {url: 'https://moodle.invalid/video', metadata: {title: 'Prova'}, contentUserData: {0: {}}}}};
  const H5P = {jQuery: $, EventDispatcher: Dispatcher,
    Video: function () { this.attach = () => {}; this.trigger = () => {}; },
    Event: function (type, data) { this.type = type; this.data = data; },
    getContentForInstance: id => integration.contents['cid-' + id],
    createTitle: text => text,
    setUserData(id, key, state, options) {
      const cache = integration.contents['cid-' + id].contentUserData[0];
      const json = JSON.stringify(state);
      if (cache[key] === json) return;
      cache[key] = json;
      saves.push(JSON.parse(json));
      if (failSave) options.errorCallback('Network failure');
      // Official API has no success callback.
    }};
  const window = {H5P, addEventListener() {}};
  const context = vm.createContext({H5P, H5PIntegration: integration, window,
    document: {visibilityState: 'visible', addEventListener(name, callback) { documentEvents[name] = callback; }},
    performance: {now: () => clock}, setInterval(callback) { timer = callback; }, setTimeout() {}, btoa, atob});
  const index = process.argv.indexOf('--core-dir');
  if (index !== -1) {
    for (const file of ['h5p-x-api-event.js', 'h5p-x-api.js']) {
      vm.runInContext(fs.readFileSync(path.join(process.argv[index + 1], file), 'utf8'), context);
    }
  }
  vm.runInContext(source, context);
  const instance = new H5P.LumTrackedVideo({lessonTitle: 'Titolo è corretto', duration, checkpointSeconds: '30',
    resume, video: [{path: 'videos/video.mp4', mime: 'video/mp4'}]}, 1, {previousState});
  instance.attach(new Element());
  return {instance, video, events, documentEvents, statements, saves,
    advance(position, event = 'timeupdate') {
      clock += Math.max(0, position - video.currentTime) * 1000 / video.playbackRate;
      video.currentTime = position;
      if (event === 'ended') video.ended = true;
      events[event]();
    }, tick() { timer(); }, failSave(value) { failSave = value; }};
}

{
  const p = harness();
  p.video.paused = false;
  p.events.play();
  p.advance(3);
  p.documentEvents.visibilitychange();
  p.advance(10, 'ended');
  assert.equal(p.statements.length, 1);
  assert.equal(p.statements[0].verb.id, 'http://adlnet.gov/expapi/verbs/completed');
  assert.equal(p.statements[0].result.completion, true);
  assert.equal(p.statements[0].result.duration, 'PT10.00S');
  assert.equal(p.statements[0].result.score, undefined);
  assert.equal(p.statements[0].result.success, undefined);
  assert.equal(p.instance.$coverage.value, '100% visto');
  p.events.ended(); p.tick();
  assert.equal(p.statements.length, 1, 'No automatic duplicate completion');
  const restored = harness({previousState: JSON.parse(JSON.stringify(p.instance.getCurrentState()))});
  assert.equal(restored.instance.completed, true);
  assert.equal(restored.statements.length, 0, 'Opening completed content must not create another attempt');
  restored.instance.sendCompletion(true);
  assert.equal(restored.statements.length, 1, 'Manual retry is available when platform receipt is uncertain');
}
{
  const p = harness();
  p.video.paused = false; p.events.play(); p.advance(2);
  p.events.seeking(); p.video.currentTime = 9; p.events.seeked(); p.events.playing();
  p.advance(10, 'ended');
  assert.equal(p.instance.$coverage.value, '30% visto');
  assert.equal(p.statements.length, 0, 'Seeking to the end is not completion');
}
{
  const p = harness();
  p.video.paused = false; p.advance(0.24, 'playing'); p.advance(5); p.events.pause();
  const state = JSON.parse(JSON.stringify(p.instance.getCurrentState()));
  assert.equal(p.instance.$coverage.value, '50% visto');
  const resumed = harness({previousState: state});
  assert.equal(resumed.video.currentTime, 5);
  resumed.events.seeking(); resumed.events.seeked(); resumed.video.paused = false; resumed.events.play();
  resumed.advance(10, 'ended');
  assert.equal(resumed.instance.$coverage.value, '100% visto');
  assert.equal(resumed.statements.length, 1);
  const noResume = harness({previousState: state, resume: false});
  assert.equal(noResume.video.currentTime, 0);
  assert.equal(noResume.instance.$coverage.value, '50% visto');
}
{
  const p = harness();
  p.video.paused = false; p.events.play(); p.advance(3);
  p.failSave(true); p.tick();
  assert.equal(p.instance.$state.error, true);
  const requests = p.saves.length;
  p.failSave(false); p.tick();
  assert.equal(p.saves.length, requests + 1, 'An unchanged failed state must be retried');
  assert.equal(p.instance.$state.error, false);
  p.tick();
  assert.equal(p.saves.length, requests + 1, 'An unchanged successful request is not flooded');
}
{
  const p = harness({saveEnabled: false});
  assert.equal(p.instance.$state.error, true);
  p.tick(); assert.equal(p.saves.length, 0);
}
{
  const p = harness({previousState: {version: 1, coverage: 'bad', emitted: true}});
  assert.equal(p.instance.completed, false);
  assert.equal(p.instance.emitted, false);
  assert.equal(p.statements.length, 0);
}
{
  const p = harness();
  p.video.duration = 11;
  p.events.loadedmetadata(); p.video.paused = false; p.events.play(); p.advance(11, 'ended');
  assert.equal(p.statements.length, 0, 'Invalid metadata must not count as playback');
}
console.log('H5P tracking: 7 scenarios passed' + (process.argv.includes('--core-dir') ? ' with real Moodle H5P xAPI core' : ''));
