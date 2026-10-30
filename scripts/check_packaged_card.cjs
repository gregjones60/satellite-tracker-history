// Smoke-test the exact JavaScript bytes from a release ZIP without a browser.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const registry = new Map();
const frames = new Map();let frameId = 0;
const nodes = new Map();
const node = selector=>{
  if (!nodes.has(selector)) nodes.set(selector, {
    value:'', textContent:'', clientWidth:0, clientHeight:0, children:[],
    addEventListener(){}, replaceChildren(){this.children=[]},
    append(child){this.children.push(child)},
  });
  return nodes.get(selector);
};
const context = {
  HTMLElement: class {
    attachShadow(){this.shadowRoot={innerHTML:'',querySelector:node};}
  },
  ResizeObserver: class {observe(){} disconnect(){}},
  requestAnimationFrame: fn=>{const id=++frameId;frames.set(id,fn);return id;},
  cancelAnimationFrame: id=>frames.delete(id),
  document: {createElement:()=>({textContent:''})},
  window: {},
  customElements: {
    get: name=>registry.get(name),
    define: (name, constructor)=>{
      assert.equal(registry.has(name), false, `Duplicate registration: ${name}`);
      registry.set(name, constructor);
    },
  },
};
const source = fs.readFileSync(0, 'utf8');
vm.runInNewContext(source, context, {filename:'packaged-spot-trace-history-card.js', timeout:1000});
const Card = registry.get('spot-trace-history-card');
assert.equal(typeof Card, 'function', 'Packaged card did not register its custom element');
for (const method of ['renderPlayback', 'scrubPlayback', 'togglePlayback', 'playbackPoint', 'startPlayback', 'pausePlayback', 'playbackTick']) {
  assert.equal(typeof Card.prototype[method], 'function', `Packaged card is missing ${method}`);
}
const card = new Card();
card.setConfig({type:'custom:spot-trace-history-card'});
assert.ok(card.shadowRoot.innerHTML.includes('class="playback-enabled"'), 'Packaged card is missing the timeline control');
assert.ok(card.shadowRoot.innerHTML.includes('class="playback-slider"'), 'Packaged card is missing the timeline slider');
assert.equal(typeof node('.playback-slider').oninput, 'function', 'Timeline slider is not wired');
const points = [{time:100}, {time:200}];
card.playbackTime = 150;
assert.equal(card.playbackPoint(points), points[0], 'Playback must use the last recorded fix');
card.playbackTime = 50;
assert.equal(card.playbackPoint(points), null, 'Playback must not show a future fix');
card.trips = [{id:'trip'}];
node('.trip-select').value = 'trip';
card.tracks = [{d:{entry_id:'entry',device:'vehicle'},points}];
card.playbackRange = {start:50,end:300};
card.renderPlayback();
assert.equal(node('.timeline-toggle').disabled, false, 'A selected trip must enable the timeline button');
node('.timeline-toggle').onclick();
assert.equal(node('.playback').hidden, false, 'The timeline button must reveal playback controls');
node('.playback-enabled').checked = true;
card.togglePlayback();
assert.equal(node('.playback-slider').disabled, false, 'Timeline should be enabled');
card.scrubPlayback(150);
assert.equal(card.playbackPoint(points), points[0], 'Scrubbing did not update the marker position');
assert.equal(typeof node('.playback-play').onclick, 'function', 'Play button is not wired');
node('.playback-speed').value='600';node('.playback-speed').onchange();
assert.equal(card.playbackRate,600,'Speed selector did not change playback speed');
card.startPlayback();
assert.equal(frames.size,1,'Play did not schedule animation');
function advance(time){for(const [id,fn] of [...frames]){frames.delete(id);fn(time);}}
advance(0);advance(100);
assert.equal(card.playbackTime,210,'Automatic playback did not advance at the selected speed');
card.pausePlayback();
assert.equal(frames.size,0,'Pause did not cancel animation');
console.log('Packaged JavaScript registration and playback smoke test passed');
