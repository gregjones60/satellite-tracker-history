const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const src = fs.readFileSync(path.join(__dirname, '../custom_components/spot_trace_history/www/spot-trace-history-card.js'), 'utf8');

test('card source retains a tile cache and removes obsolete tiles', () => {
  assert.match(src, /tileNodes=new Map\(\)/);
  assert.match(src, /this\.tileNodes\.get\(key\)/);
  assert.match(src, /!needed\.has\(key\)/);
});
test('tile requests use a safe referrer policy and configurable provider', () => {
  assert.match(src, /strict-origin-when-cross-origin/);
  assert.match(src, /tile_url/);
});
test('multi-device configuration and route display remain available', () => {
  assert.match(src, /deviceSettings/);
  assert.match(src, /entry_id/);
});

function cardContext(existing) {
  const registered = new Map(existing ? [['spot-trace-history-card', existing]] : []);
  let definitions = 0;
  const context = vm.createContext({
    HTMLElement: class {}, window: {},
    customElements: {
      get: name=>registered.get(name),
      define: (name, cls)=>{
        assert.equal(registered.has(name), false, 'duplicate element definition');
        definitions++;
        registered.set(name, cls);
      },
    },
  });
  return {context, registered, definitions: ()=>definitions};
}

test('loading the card twice in the same page registers it only once', () => {
  const c=cardContext();
  vm.runInContext(src,c.context);
  const first=c.registered.get('spot-trace-history-card');
  vm.runInContext(src,c.context);
  assert.equal(c.definitions(),1);
  assert.equal(c.registered.get('spot-trace-history-card'),first);
  assert.equal(c.context.window.customCards.length,1);
});

test('an existing card definition and picker entry are preserved', () => {
  const existing=class {};
  const c=cardContext(existing);
  const pickerEntry={type:'spot-trace-history-card',name:'Existing card'};
  c.context.window.customCards=[pickerEntry];
  vm.runInContext(src,c.context);
  assert.equal(c.definitions(),0);
  assert.equal(c.registered.get('spot-trace-history-card'),existing);
  assert.equal(c.context.window.customCards.length,1);
  assert.equal(c.context.window.customCards[0],pickerEntry);
});

test('zoom buttons and wheel change scale, respect bounds, and do not drag the map', () => {
  const c=cardContext();
  c.context.ResizeObserver=class {observe() {} disconnect() {}};
  vm.runInContext(src,c.context);
  const Card=c.registered.get('spot-trace-history-card');
  const card=new Card();
  const nodes=new Map();
  const node=selector=>{
    if(!nodes.has(selector)) nodes.set(selector,{
      clientWidth:0, clientHeight:0, listeners:{},
      addEventListener(name,handler){this.listeners[name]=handler},
    });
    return nodes.get(selector);
  };
  card.attachShadow=()=>{card.shadowRoot={querySelector:node}};
  card.setConfig({type:'custom:spot-trace-history-card'});
  // A zero-size map lets the real draw() update controls without tile rendering.
  node('.zoom-in').onclick();
  assert.equal(card.zoom,7);
  node('.zoom-out').onclick();
  assert.equal(card.zoom,6);
  let prevented=false;
  node('.map').listeners.wheel({deltaY:-1,preventDefault(){prevented=true}});
  assert.equal(card.zoom,7);
  assert.equal(prevented,true);
  card.zoom=17;
  node('.zoom-in').onclick();
  assert.equal(card.zoom,17);
  assert.equal(node('.zoom-in').disabled,true);
  assert.equal(node('.zoom-out').disabled,false);
  card.zoom=1;
  node('.zoom-out').onclick();
  assert.equal(card.zoom,1);
  assert.equal(node('.zoom-out').disabled,true);
  let stopped=false;
  node('.zoom-controls').listeners.pointerdown({stopPropagation(){stopped=true}});
  assert.equal(stopped,true);
  assert.equal(card.drag,undefined);
});
