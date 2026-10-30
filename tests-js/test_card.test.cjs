const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const src = fs.readFileSync(path.join(__dirname, '../custom_components/spot_trace_history/www/spot-trace-history-card.js'), 'utf8');

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
    HTMLElement: class {}, window: {}, document:{hidden:false},
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

function tripCard() {
  const c=cardContext();
  c.context.ResizeObserver=class {observe() {} disconnect() {}};
  const listeners=new Map(),frames=new Map();let nextFrame=0;
  c.context.requestAnimationFrame=fn=>{const id=++nextFrame;frames.set(id,fn);return id};
  c.context.cancelAnimationFrame=id=>frames.delete(id);
  c.context.document={hidden:false,addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name),createElement:()=>({style:{},children:[],append(...children){this.children.push(...children)}}),createTextNode:text=>({textContent:text})};
  vm.runInContext(src,c.context);
  const card=new (c.registered.get('spot-trace-history-card'))();
  const nodes=new Map();let focused=null;
  const node=selector=>{
    if(!nodes.has(selector)) nodes.set(selector,{
      value:'', clientWidth:0, clientHeight:0, children:[], attrs:{}, listeners:{},
      addEventListener(name,fn){this.listeners[name]=fn},replaceChildren(){this.children=[]},append(child){this.children.push(child)},
      setAttribute(name,value){this.attrs[name]=value},focus(){focused=selector},
      showModal(){this.open=true},close(){this.open=false},
    });
    return nodes.get(selector);
  };
  card.attachShadow=()=>{card.shadowRoot={querySelector:node}};
  card.setConfig({type:'custom:spot-trace-history-card'});
  card.fit=()=>{};card.draw=()=>{};
  card.allDevices=[{entry_id:'feed-a',feed_id:'feed-a-id',device:'vehicle',name:'Vehicle'},{entry_id:'feed-b',feed_id:'feed-b-id',device:'trailer',name:'Trailer'}];
  return {card,node,focused:()=>focused,window:c.context.window,frames,document:c.context.document,listeners,advance:time=>{for(const [id,fn] of [...frames]){frames.delete(id);fn(time)}}};
}

test('saving dates persists a named trip and selecting it filters device queries', async () => {
  const {card,node}=tripCard();
  const trip={id:'trip-1',name:'Camping',start_date:'2026-01-01',end_date:'2026-01-03'};
  const calls=[];
  card._hass={callWS:async msg=>{calls.push(msg);return msg.type==='spot_trace_history/create_trip' ? trip : []}};
  node('.from').value=trip.start_date;node('.to').value=trip.end_date;
  card.openTripDialog();
  assert.equal(node('.trip-dialog').open,true);
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
  card.openTripDialog();
  node('.trip-name').value='Camping';
  card._hass={callWS:async ()=>{throw new Error('Trip already exists')}};
  await card.saveTrip();
  assert.equal(node('.trip-name').value,'Camping');
  assert.equal(node('.save-trip').disabled,false);
  assert.match(node('.trip-error').textContent,/Trip already exists/);
  assert.equal(node('.trip-dialog').open,true);
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

test('dialog saves changed dates with the original name without creating another trip', async () => {
  const {card,node}=tripCard();
  const trip={id:'1',name:'Camping',start_date:'2026-01-01',end_date:'2026-01-02'};
  card.trips=[trip];card.renderTrips('1');card.editTrip();
  assert.equal(node('.trip-name').value,'Camping');
  assert.equal(node('.save-trip').textContent,'Save changes');
  assert.equal(node('.trip-dialog').open,true);
  assert.equal(node('.trip-dialog-title').textContent,'Edit trip');
  node('.trip-to').value='2026-01-03';
  assert.equal(node('.trip-select').value,'1');
  card._hass={callWS:async msg=>{
    assert.equal(msg.type,'spot_trace_history/update_trip');
    assert.equal(msg.trip_id,'1');
    assert.equal(msg.name,'Camping');
    return {...trip,name:msg.name,end_date:msg.end_date};
  }};
  await card.saveTrip();
  assert.equal(card.trips.length,1);
  assert.equal(card.trips[0].name,'Camping');
  assert.equal(node('.trip-dialog').open,false);
  assert.equal(card.trips[0].end_date,'2026-01-03');
  assert.equal(card.editingTrip,null);
});

test('cancelling an edit restores saved dates without a mutation request', async () => {
  const {card,node}=tripCard();
  card.trips=[{id:'1',name:'Camping',start_date:'2026-01-01',end_date:'2026-01-02'}];
  card.renderTrips('1');await card.selectTrip();card.editTrip();
  node('.trip-to').value='2026-01-20';node('.trip-name').value='Changed';
  card._hass={callWS:async ()=>{throw new Error('unexpected mutation')}};
  await card.cancelTripEdit();
  assert.equal(card.editingTrip,null);
  assert.equal(node('.to').value,'2026-01-02');
  assert.equal(node('.trip-dialog').open,false);
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

test('trip dialog saves vehicle participants and filtering excludes the trailer', async () => {
  const {card,node}=tripCard();
  card.devices=card.allDevices;
  card.selected={'feed-a:vehicle':true,'feed-b:trailer':true};
  card.openTripDialog();
  assert.equal(card.tripVehicleChecks.length,2);
  card.tripVehicleChecks[1].checkbox.checked=false;
  node('.trip-name').value='Vehicle weekend';
  const queries=[];
  card._hass={callWS:async msg=>{
    queries.push(msg);
    if(msg.type==='spot_trace_history/create_trip')return {...msg,id:'weekend'};
    return [];
  }};
  await card.saveTrip();
  const participants=queries[0].devices;
  assert.equal(participants.length,1);
  assert.equal(participants[0].feed_id,'feed-a-id');
  assert.equal(participants[0].device,'vehicle');
  assert.equal(queries.filter(msg=>msg.type==='spot_trace_history/track').length,1);
  assert.equal(queries.find(msg=>msg.type==='spot_trace_history/track').device,'vehicle');
  assert.equal(card.tripDevices().length,1);
  node('.trip-select').value='';await card.selectTrip();
  assert.equal(card.tripDevices().length,2);
});

test('same messenger ID in different feeds and unavailable participants remain distinct', () => {
  const {card,node}=tripCard();
  card.allDevices=[{entry_id:'new-entry',feed_id:'feed-one',device:'same',name:'Vehicle'},
                   {entry_id:'other-entry',feed_id:'feed-two',device:'same',name:'Vehicle'}];
  card.devices=card.allDevices;
  const trip={id:'1',name:'Camping',start_date:'2026-01-01',end_date:'2026-01-02',
              devices:[{feed_id:'feed-one',device:'same'},{feed_id:'removed-feed',device:'old'}]};
  card.trips=[trip];card.renderTrips('1');card.editTrip();
  assert.equal(card.tripVehicleChecks.length,3);
  assert.equal(card.tripVehicleChecks[0].checkbox.checked,true);
  assert.equal(card.tripVehicleChecks[1].checkbox.checked,false);
  assert.equal(card.tripVehicleChecks[2].checkbox.checked,true);
  assert.equal(card.tripDevices()[0].entry_id,'new-entry');
  assert.equal(card.tripDevices().length,1);
  assert.match(node('.trip-vehicles').children[2].children[1].textContent,/unavailable/);
});

test('legacy trips allow all vehicles and explicit empty selections cannot be saved', async () => {
  const {card,node}=tripCard();
  const trip={id:'1',name:'Old trip',start_date:'2026-01-01',end_date:'2026-01-02'};
  card.trips=[trip];card.renderTrips('1');card.editTrip();
  assert.equal(node('.trip-all-devices').checked,true);
  assert.equal(card.tripVehicleChecks[0].checkbox.disabled,true);
  node('.trip-all-devices').checked=false;node('.trip-all-devices').onchange();
  for(const item of card.tripVehicleChecks)item.checkbox.checked=false;
  let requests=0;
  card._hass={callWS:async ()=>{requests++;throw new Error('unexpected request')}};
  await card.saveTrip();
  assert.equal(requests,0);
  assert.match(node('.trip-error').textContent,/Select at least one vehicle/);
  assert.equal(node('.save-trip').disabled,false);
});

test('year filter offers archive years and queries the full leap year without trip restrictions', async () => {
  const {card,node}=tripCard();
  card.devices=[{entry_id:'feed-a',feed_id:'feed-a-id',device:'vehicle',
                 first:Date.parse('2019-06-01T00:00:00')/1000,last:Date.parse('2025-06-01T00:00:00')/1000}];
  card.selected={'feed-a:vehicle':true};
  card.renderYears();
  assert.equal(node('.year-select').children.some(o=>o.value==='2019'),true);
  assert.equal(node('.year-select').children.some(o=>o.value==='2024'),true);
  const queries=[];
  card._hass={callWS:async msg=>{queries.push(msg);return []}};
  node('.trip-select').value='old-trip';node('.year-select').value='2024';
  await card.selectYear();
  assert.equal(node('.trip-select').value,'');
  assert.equal(node('.from').value,'2024-01-01');
  assert.equal(node('.to').value,'2024-12-31');
  assert.equal(queries[0].start,Date.parse('2024-01-01T00:00:00')/1000);
  assert.equal(queries[0].end,Date.parse('2024-12-31T23:59:59')/1000);
  node('.to').value='2024-11-30';node('.to').onchange();
  assert.equal(node('.year-select').value,'');
});

test('year options use only devices included by the card and tolerate missing metadata', () => {
  const {card,node}=tripCard();
  card.devices=[];card.allDevices=[{first:Date.parse('2000-01-01')/1000,last:Date.parse('2001-01-01')/1000}];
  card.renderYears();
  assert.equal(node('.year-select').children.length,2);
  assert.equal(node('.year-select').children.some(o=>o.value==='2000'),false);
  card.devices=[{}];card.renderYears();
  assert.equal(node('.year-select').children.length,2);
});

test('trip timeline scrubs to the last known fix without interpolating gaps or future positions', () => {
  const {card,node}=tripCard();
  card.trips=[{id:'trip',name:'Camping'}];node('.trip-select').value='trip';
  const points=[{time:100,lat:-37,lon:145},{time:200,lat:-38,lon:146}];
  card.tracks=[{d:card.allDevices[0],points},{d:card.allDevices[1],points:[{time:250,lat:-39,lon:147}]}];
  card.playbackRange={start:50,end:300};card.renderPlayback();
  assert.equal(node('.playback').hidden,true,'the timeline stays closed until asked for');
  node('.timeline-toggle').onclick();
  assert.equal(node('.playback').hidden,false);
  assert.equal(node('.playback-slider').disabled,true);
  node('.playback-enabled').checked=true;card.togglePlayback();
  assert.equal(card.playbackTime,50);
  assert.equal(card.playbackPoint(points),null);
  assert.match(node('.playback-positions').children[0].textContent,/no recorded fix yet/);
  node('.playback-slider').value='150';node('.playback-slider').oninput();
  assert.equal(card.playbackPoint(points),points[0]);
  assert.equal(card.playbackPoint(card.tracks[1].points),null);
  assert.match(node('.playback-positions').children[0].textContent,/last recorded fix/);
  card.scrubPlayback(200);assert.equal(card.playbackPoint(points),points[1]);
  card.scrubPlayback(999);assert.equal(card.playbackTime,300);
  card.scrubPlayback(-1);assert.equal(card.playbackTime,50);
  node('.playback-enabled').checked=false;card.togglePlayback();
  assert.equal(card.playbackTime,null);
  assert.equal(card.playbackPoint(points),points[1]);
});

test('leaving a trip clears playback and empty trips cannot start it', () => {
  const {card,node}=tripCard();
  card.trips=[{id:'trip'}];node('.trip-select').value='trip';
  card.tracks=[];card.playbackRange={start:50,end:300};card.renderPlayback();
  assert.equal(node('.playback-enabled').disabled,true);
  assert.match(node('.playback-time').textContent,/No loaded positions/);
  card.tracks=[{d:card.allDevices[0],points:[{time:100}]}];card.renderPlayback();
  node('.playback-enabled').checked=true;card.togglePlayback();
  assert.equal(card.playbackTime,50);
  node('.trip-select').value='';card.syncTripControls();
  assert.equal(card.playbackTime,null);
  assert.equal(node('.playback').hidden,true);
});

test('new range queries reset playback and late responses cannot replace the latest tracks', async () => {
  const {card,node}=tripCard();
  card.devices=[card.allDevices[0]];card.selected={'feed-a:vehicle':true};
  const pending=[];
  card._hass={callWS:()=>new Promise(resolve=>pending.push(resolve))};
  card.playbackTime=100;
  const first=card.loadTracks();
  assert.equal(card.playbackTime,null);
  node('.from').value='2026-06-01';node('.to').value='2026-06-02';
  const second=card.loadTracks();
  const recent=[{time:200,lat:-37,lon:145}];
  pending[1](recent);await second;
  pending[0]([{time:100,lat:-38,lon:146}]);await first;
  assert.equal(card.tracks[0].points,recent);
  assert.equal(card.playbackRange.start,Date.parse('2026-06-01T00:00:00')/1000);
});

function playbackCard() {
  const c=tripCard();
  c.card.trips=[{id:'trip',name:'Camping'}];c.node('.trip-select').value='trip';
  c.card.tracks=[{d:c.card.allDevices[0],points:[{time:100,lat:-37,lon:145},{time:800,lat:-38,lon:146}]}];
  c.card.playbackRange={start:0,end:1000};c.card.renderPlayback();
  return c;
}

test('Play/Pause resumes position, applies selected speed, and never starts duplicate loops', () => {
  const {card,node,advance,frames}=playbackCard();
  node('.playback-play').onclick();card.startPlayback();
  assert.equal(frames.size,1);
  assert.equal(card.playbackTime,0);
  assert.equal(node('.playback-play').textContent,'Pause');
  advance(0);advance(100);
  assert.equal(card.playbackTime,360);
  node('.playback-play').onclick();
  assert.equal(frames.size,0);
  assert.equal(node('.playback-play').textContent,'Play');
  advance(900);assert.equal(card.playbackTime,360);
  node('.playback-play').onclick();advance(1000);advance(1100);
  assert.equal(card.playbackTime,720);
  node('.playback-speed').value='600';node('.playback-speed').onchange();advance(1200);
  assert.equal(card.playbackTime,780);
  node('.playback-speed').value='invalid';node('.playback-speed').onchange();
  assert.equal(card.playbackRate,600);
  card.scrubPlayback(100);
  assert.equal(frames.size,0);
  assert.equal(card.playbackPlaying,false);
  assert.equal(card.playbackTime,100);
});

test('playback stops exactly at the end and Replay starts at the beginning', () => {
  const {card,node,advance,frames}=playbackCard();
  card.playbackRange.end=500;
  card.startPlayback();advance(0);advance(250);
  assert.equal(card.playbackTime,500);
  assert.equal(card.playbackPlaying,false);
  assert.equal(frames.size,0);
  assert.equal(node('.playback-play').textContent,'Replay');
  node('.playback-play').onclick();
  assert.equal(card.playbackTime,0);
  assert.equal(frames.size,1);
});

test('hiding or detaching the card pauses playback and removes animation work', () => {
  const {card,document,listeners,frames}=playbackCard();
  card.startPlayback();document.hidden=true;listeners.get('visibilitychange')();
  assert.equal(card.playbackPlaying,false);assert.equal(frames.size,0);
  document.hidden=false;card.startPlayback();
  assert.equal(frames.size,1);
  card.disconnectedCallback();
  assert.equal(frames.size,0);
  assert.equal(listeners.has('visibilitychange'),false);
});

test('trip changes, disabling timeline, and new history requests stop playback', async () => {
  const {card,node,frames}=playbackCard();
  card.startPlayback();node('.playback-enabled').checked=false;card.togglePlayback();
  assert.equal(frames.size,0);assert.equal(card.playbackTime,null);
  card.startPlayback();node('.trip-select').value='';card.syncTripControls();
  assert.equal(frames.size,0);
  node('.trip-select').value='trip';card.startPlayback();
  card.devices=[card.allDevices[0]];card.selected={'feed-a:vehicle':true};
  card._hass={callWS:async ()=>[]};
  await card.loadTracks();
  assert.equal(frames.size,0);assert.equal(card.playbackTime,null);
  assert.equal(node('.playback-play').disabled,true);
});

test('a delayed animation frame cannot jump minutes of wall-clock time', () => {
  const {card,advance}=playbackCard();
  card.playbackRange.end=100000;
  card.startPlayback();advance(0);advance(10000);
  assert.equal(card.playbackTime,900);
});

// Arrays built inside the card's VM context are not deepEqual to this realm's arrays.
const sameJSON=(actual,expected,message)=>assert.equal(JSON.stringify(actual),JSON.stringify(expected),message);

function fakeLeaflet() {
  const made={maps:[],tiles:[],polylines:[],markers:[],icons:[]};
  const group=()=>({layers:new Set(),addTo(){return this},addLayer(layer){this.layers.add(layer);return this},
    removeLayer(layer){this.layers.delete(layer);return this},clearLayers(){this.layers.clear();return this}});
  const layer=props=>({...props,addTo(target){target.addLayer?.(this);return this}});
  const L={
    map:(container,options)=>{const map={container,options,fitted:[],resized:0,
      setView(){return this},fitBounds(bounds,opts){this.fitted.push([bounds,opts]);return this},invalidateSize(){this.resized++;return this}};
      made.maps.push(map);return map},
    tileLayer:(url,options)=>{const tiles={...layer({url,options}),handlers:{},on(name,fn){this.handlers[name]=fn;return this}};made.tiles.push(tiles);return tiles},
    layerGroup:group,
    polyline:(latlngs,options)=>{const line=layer({latlngs,options});made.polylines.push(line);return line},
    marker:(latlng,options)=>{const marker={...layer({latlng,options}),moves:0,setLatLng(next){this.latlng=next;this.moves++;return this}};made.markers.push(marker);return marker},
    divIcon:options=>{made.icons.push(options);return {options}},
  };
  return {L,made};
}

function leafletCard(config={}) {
  const c=cardContext();
  const resize=[];
  c.context.ResizeObserver=class {constructor(fn){resize.push(fn)} observe() {} disconnect() {}};
  const element=tag=>({tag,style:{},attrs:{},children:[],setAttribute(name,value){this.attrs[name]=value},append(...children){this.children.push(...children)}});
  c.context.document={hidden:false,addEventListener(){},removeEventListener(){},createElement:element,createTextNode:text=>({textContent:text})};
  vm.runInContext(src,c.context);
  const Card=c.registered.get('spot-trace-history-card');
  const leaflet=fakeLeaflet();let loads=0;
  Card.loadLeaflet=async()=>{loads++;return leaflet.L};
  const card=new Card();
  const nodes=new Map();
  const node=selector=>{
    if(!nodes.has(selector)) nodes.set(selector,{value:'',textContent:'',clientWidth:0,clientHeight:0,children:[],
      addEventListener(){},replaceChildren(){this.children=[]},append(child){this.children.push(child)}});
    return nodes.get(selector);
  };
  card.attachShadow=()=>{card.shadowRoot={querySelector:node}};
  card.setConfig({type:'custom:spot-trace-history-card',...config});
  card.devices=[{entry_id:'a',device:'car',name:'Car',icon:'mdi:van-utility'},{entry_id:'b',device:'trailer',name:'Trailer'}];
  return {card,node,...leaflet,loads:()=>loads,resize:()=>resize.forEach(fn=>fn())};
}

test('the map loads the bundled Leaflet once, with smooth zoom and the configured tile provider', async () => {
  const {card,made,loads}=leafletCard({tile_url:'https://tiles.example/{z}/{x}/{y}.png',tile_attribution:'Example tiles'});
  await Promise.all([card.ensureMap(),card.ensureMap()]);
  assert.equal(loads(),1);
  assert.equal(made.maps.length,1);
  const options=made.maps[0].options;
  assert.ok(options.zoomSnap<1,'zoom must not be limited to whole levels');
  assert.ok(options.inertiaMaxSpeed<=600,'drag momentum must be capped');
  assert.equal(options.minZoom,1);assert.equal(options.maxZoom,17);
  assert.equal(made.tiles[0].url,'https://tiles.example/{z}/{x}/{y}.png');
  assert.equal(made.tiles[0].options.attribution,'Example tiles');
  assert.equal(made.tiles[0].options.referrerPolicy,'strict-origin-when-cross-origin');
  assert.match(src,/leaflet\.css\?v=\$\{LEAFLET_VERSION\}/);
});

test('a failed Leaflet load is reported and can be retried', async () => {
  const {card,node,L}=leafletCard();
  card.constructor.loadLeaflet=async()=>{throw Error('offline')};
  await card.ensureMap();
  assert.match(node('.note').textContent,/Unable to load the map: offline/);
  card.constructor.loadLeaflet=async()=>L;
  await card.ensureMap();
  assert.ok(card.map);
});

test('tile failures are reported at most every 30 seconds', async () => {
  const {card,node,made}=leafletCard();
  await card.ensureMap();
  made.tiles[0].handlers.tileerror();
  assert.match(node('.note').textContent,/tiles failed to load/);
  node('.note').textContent='';made.tiles[0].handlers.tileerror();
  assert.equal(node('.note').textContent,'');
  assert.equal(card.tileFailures,2);
});

test('fit waits for a sized map and covers every vehicle without spreading arrays', async () => {
  const {card,node,made,resize}=leafletCard();
  await card.ensureMap();
  card.tracks=Array.from({length:4},(_,i)=>({d:card.devices[0],points:Array.from({length:40000},()=>({lat:-37-i,lon:145+i}))}));
  card.fit();
  assert.equal(made.maps[0].fitted.length,0);
  Object.assign(node('.map'),{clientWidth:800,clientHeight:600});
  resize();
  assert.equal(made.maps[0].resized,1);
  sameJSON(made.maps[0].fitted[0][0],[[-40,145],[-37,148]]);
  assert.equal(made.maps[0].fitted[0][1].maxZoom,16);
  resize();
  assert.equal(made.maps[0].fitted.length,1,'a later resize must not undo the user\'s pan or zoom');
  card.tracks=[];card.fit();
  assert.equal(made.maps[0].fitted.length,1);
});

test('tracks drawn before Leaflet loads appear and fit once it is ready', async () => {
  const {card,node,made}=leafletCard();
  Object.assign(node('.map'),{clientWidth:800,clientHeight:600});
  card.tracks=[{d:card.devices[0],points:[{time:1,lat:-37,lon:145},{time:2,lat:-38,lon:146}]}];
  card.draw();card.fit();
  await card.ensureMap();
  assert.equal(made.polylines.length,1);
  sameJSON(made.polylines[0].latlngs,[[-37,145],[-38,146]]);
  assert.equal(made.polylines[0].options.color,'#1976d2');
  assert.equal(made.maps[0].fitted.length,1);
});

test('vehicle markers use each vehicle\'s icon and colour, and a dot when it has none', async () => {
  const {card,made}=leafletCard({devices:{'b:trailer':{icon:'mdi:caravan',color:'#123456'}}});
  card.devices.push({entry_id:'c',device:'bike',name:'Bike'});
  await card.ensureMap();
  card.tracks=card.devices.map(d=>({d,points:[{time:1,lat:-37,lon:145}]}));
  card.draw();
  const icons=made.icons.map(icon=>icon.html.children[0]?.attrs.icon);
  sameJSON(icons,['mdi:van-utility','mdi:caravan',undefined]);
  assert.equal(made.icons[1].html.style.background,'#123456');
  assert.equal(made.icons[1].className,'','Leaflet\'s default white box must not wrap the marker');
  sameJSON(made.icons[0].iconAnchor,[15,15]);
  sameJSON(made.icons[2].iconSize,[16,16]);
  assert.equal(made.markers[0].options.title,'Car');
});

test('playback moves existing markers and shows only vehicles with an earlier fix', async () => {
  const {card,made}=leafletCard();
  await card.ensureMap();
  card.tracks=[{d:card.devices[0],points:[{time:100,lat:-37,lon:145},{time:200,lat:-38,lon:146}]},
               {d:card.devices[1],points:[{time:250,lat:-39,lon:147}]}];
  card.playbackTime=150;card.draw();
  assert.equal(card.markerLayer.layers.size,1);
  sameJSON(made.markers[0].latlng,[-37,145]);
  const lines=made.polylines.length;
  card.playbackTime=300;card.drawMarkers();
  assert.equal(made.polylines.length,lines,'playback must not redraw routes');
  assert.equal(made.markers.length,2,'the car marker is moved, not rebuilt');
  assert.equal(made.markers[0].moves,1);
  sameJSON(made.markers[0].latlng,[-38,146]);
  assert.equal(card.markerLayer.layers.size,2);
  card.playbackTime=150;card.drawMarkers();
  assert.equal(card.markerLayer.layers.size,1);
  card.playbackTime=null;card.drawMarkers();
  sameJSON(made.markers[0].latlng,[-38,146]);
});

test('every view names and colours a vehicle the same way: card setting, then SPOT name, then messenger ID', async () => {
  const {card,node}=leafletCard({devices:{'a:car':{name:'Ute',color:'#123456'}}});
  card.devices=[{entry_id:'a',device:'car',name:'Bluey'},{entry_id:'b',device:'trailer',name:'Camper'},{entry_id:'c',device:'0-123'}];
  card.allDevices=card.devices;
  const names=['Ute','Camper','0-123'],colours=['#123456','#e65100','#388e3c'];
  card.legend();
  const legend=node('.legend').children;
  sameJSON(legend.map(label=>label.children[2].textContent),names);
  sameJSON(legend.map(label=>label.children[1].style.background),colours);
  card.renderTripVehicles(null);
  sameJSON(node('.trip-vehicles').children.map(label=>label.children[1].textContent.split(' (')[0]),names);
  card.trips=[{id:'trip',name:'Camping'}];node('.trip-select').value='trip';
  card.tracks=card.devices.map(d=>({d,points:[{time:100,lat:-37,lon:145}]}));
  card.playbackRange={start:0,end:200};card.playbackTime=150;card.renderPlayback();
  sameJSON(node('.playback-positions').children.map(row=>row.textContent.split(' — ')[0]),names);
  await card.ensureMap();
  sameJSON([...card.markerLayer.layers].map(marker=>marker.options.title),names);
  sameJSON([...card.trackLayer.layers].map(line=>line.options.color),colours);
});

test('the timeline floats over the map: a trip enables it, and close, Escape or leaving the trip hides it', () => {
  const {card,node,focused}=tripCard();
  card.trips=[{id:'trip',name:'Camping'}];card.renderPlayback();
  assert.equal(node('.timeline-toggle').disabled,true,'no trip, no timeline');
  node('.trip-select').value='trip';card.syncTripControls();
  assert.equal(node('.timeline-toggle').disabled,false);
  assert.equal(node('.playback').hidden,true);
  node('.timeline-toggle').onclick();
  assert.equal(node('.playback').hidden,false);
  assert.equal(node('.timeline-toggle').attrs['aria-expanded'],'true');
  assert.equal(focused(),'.playback-enabled');
  node('.playback-close').onclick();
  assert.equal(node('.playback').hidden,true);
  assert.equal(node('.timeline-toggle').attrs['aria-expanded'],'false');
  assert.equal(focused(),'.timeline-toggle');
  node('.timeline-toggle').onclick();
  node('.playback').listeners.keydown({key:'Enter'});
  assert.equal(node('.playback').hidden,false);
  node('.playback').listeners.keydown({key:'Escape'});
  assert.equal(node('.playback').hidden,true);
  node('.timeline-toggle').onclick();
  node('.trip-select').value='';card.syncTripControls();
  assert.equal(node('.playback').hidden,true);
  assert.equal(node('.timeline-toggle').disabled,true);
  node('.trip-select').value='trip';card.syncTripControls();
  assert.equal(node('.playback').hidden,true,'returning to a trip does not reopen it');
});

test('the card has no title of its own and the timeline sits over the map, not above it', () => {
  const header=src.slice(src.indexOf('<div class="wrap">'),src.indexOf('<dialog'));
  assert.doesNotMatch(header,/<h3/);
  assert.doesNotMatch(src,/config\.title/);
  assert.match(src,/<div class="map-area"><div class="map"><\/div><section class="playback"/);
});
