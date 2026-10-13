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

function tripCard() {
  const c=cardContext();
  c.context.ResizeObserver=class {observe() {} disconnect() {}};
  c.context.document={createElement:()=>({})};
  vm.runInContext(src,c.context);
  const card=new (c.registered.get('spot-trace-history-card'))();
  const nodes=new Map();
  const node=selector=>{
    if(!nodes.has(selector)) nodes.set(selector,{
      value:'', clientWidth:0, clientHeight:0, children:[],
      addEventListener(){},replaceChildren(){this.children=[]},append(child){this.children.push(child)},
    });
    return nodes.get(selector);
  };
  card.attachShadow=()=>{card.shadowRoot={querySelector:node}};
  card.setConfig({type:'custom:spot-trace-history-card'});
  card.fit=()=>{};card.draw=()=>{};
  return {card,node,window:c.context.window};
}

test('saving dates persists a named trip and selecting it filters device queries', async () => {
  const {card,node}=tripCard();
  const trip={id:'trip-1',name:'Camping',start_date:'2026-01-01',end_date:'2026-01-03'};
  const calls=[];
  card._hass={callWS:async msg=>{calls.push(msg);return msg.type==='spot_trace_history/create_trip' ? trip : []}};
  node('.from').value=trip.start_date;node('.to').value=trip.end_date;
  node('.trip-name').value=' Camping ';
  await card.saveTrip();
  assert.equal(calls[0].name,'Camping');
  assert.equal(calls[0].start_date,trip.start_date);
  assert.equal(node('.trip-select').value,'trip-1');
  assert.equal(node('.trip-name').value,'');
  assert.equal(node('.save-trip').disabled,false);
  card.devices=[{entry_id:'feed-a',device:'vehicle'},{entry_id:'feed-b',device:'trailer'}];
  card.selected={'feed-a:vehicle':true,'feed-b:trailer':false};
  node('.from').value='2026-02-01';node('.to').value='2026-02-02';
  await card.selectTrip();
  const trackQueries=calls.filter(msg=>msg.type==='spot_trace_history/track');
  assert.equal(trackQueries.length,1);
  assert.equal(trackQueries[0].device,'vehicle');
  assert.equal(trackQueries[0].start,Date.parse('2026-01-01T00:00:00')/1000);
  assert.equal(trackQueries[0].end,Date.parse('2026-01-03T23:59:59')/1000);
  node('.from').onchange();
  assert.equal(node('.trip-select').value,'');
});

test('save errors retain user input and restore the save button', async () => {
  const {card,node}=tripCard();
  node('.trip-name').value='Camping';
  card._hass={callWS:async ()=>{throw new Error('Trip already exists')}};
  await card.saveTrip();
  assert.equal(node('.trip-name').value,'Camping');
  assert.equal(node('.save-trip').disabled,false);
  assert.match(node('.note').textContent,/Trip already exists/);
  assert.equal(card.trips.length,0);
});

test('trip list loads saved dates and treats names as plain text', async () => {
  const {card,node}=tripCard();
  const trip={id:'saved',name:'<img onerror=bad()>',start_date:'2025-01-01',end_date:'2025-01-02'};
  card._hass={callWS:async msg=>{
    assert.equal(msg.type,'spot_trace_history/trips');return [trip];
  }};
  await card.loadTrips();
  assert.equal(node('.trip-select').children[0].textContent,'Custom dates');
  assert.match(node('.trip-select').children[1].textContent,/<img onerror=bad\(\)>/);
  assert.equal(node('.trip-select').children[1].innerHTML,undefined);
});

test('editing updates the selected trip without creating a second definition', async () => {
  const {card,node}=tripCard();
  const trip={id:'1',name:'Camping',start_date:'2026-01-01',end_date:'2026-01-02'};
  card.trips=[trip];card.renderTrips('1');card.editTrip();
  assert.equal(node('.trip-name').value,'Camping');
  assert.equal(node('.save-trip').textContent,'Save changes');
  node('.trip-name').value='Summer';node('.to').value='2026-01-03';
  node('.to').onchange();
  assert.equal(node('.trip-select').value,'1');
  card._hass={callWS:async msg=>{
    assert.equal(msg.type,'spot_trace_history/update_trip');
    assert.equal(msg.trip_id,'1');
    return {...trip,name:msg.name,end_date:msg.end_date};
  }};
  await card.saveTrip();
  assert.equal(card.trips.length,1);
  assert.equal(card.trips[0].name,'Summer');
  assert.equal(card.trips[0].end_date,'2026-01-03');
  assert.equal(card.editingTrip,null);
});

test('cancelling an edit restores saved dates without a mutation request', async () => {
  const {card,node}=tripCard();
  card.trips=[{id:'1',name:'Camping',start_date:'2026-01-01',end_date:'2026-01-02'}];
  card.renderTrips('1');card.editTrip();
  node('.to').value='2026-01-20';node('.trip-name').value='Changed';
  card._hass={callWS:async ()=>{throw new Error('unexpected mutation')}};
  await card.cancelTripEdit();
  assert.equal(card.editingTrip,null);
  assert.equal(node('.to').value,'2026-01-02');
  assert.equal(node('.trip-name').value,'');
  assert.equal(card.trips[0].name,'Camping');
});

test('failed edits keep the editable values and selected trip intact', async () => {
  const {card,node}=tripCard();
  card.trips=[{id:'1',name:'Camping',start_date:'2026-01-01',end_date:'2026-01-02'}];
  card.renderTrips('1');card.editTrip();node('.trip-name').value='Duplicate';
  card._hass={callWS:async ()=>{throw new Error('name already exists')}};
  await card.saveTrip();
  assert.equal(card.editingTrip,'1');
  assert.equal(card.trips[0].name,'Camping');
  assert.equal(node('.trip-name').value,'Duplicate');
  assert.equal(node('.save-trip').disabled,false);
});

test('deleting requires confirmation and retains displayed dates as custom dates', async () => {
  const {card,node,window}=tripCard();
  card.trips=[{id:'1',name:'Camping',start_date:'2026-01-01',end_date:'2026-01-02'}];
  card.renderTrips('1');await card.selectTrip();
  const calls=[];
  card._hass={callWS:async msg=>{calls.push(msg);return {deleted:'1'}}};
  window.confirm=()=>false;
  await card.deleteTrip();
  assert.equal(calls.length,0);
  assert.equal(card.trips.length,1);
  window.confirm=message=>{assert.match(message,/GPS records will be kept/);return true};
  await card.deleteTrip();
  assert.equal(calls[0].type,'spot_trace_history/delete_trip');
  assert.equal(calls[0].trip_id,'1');
  assert.equal(card.trips.length,0);
  assert.equal(node('.trip-select').value,'');
  assert.equal(node('.from').value,'2026-01-01');
  assert.equal(node('.to').value,'2026-01-02');
  assert.equal(node('.delete-trip').disabled,true);
});
