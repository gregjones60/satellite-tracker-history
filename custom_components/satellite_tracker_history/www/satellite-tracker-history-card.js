(() => {
// Leaflet is bundled with the integration and served next to this card.
const LEAFLET_VERSION='1.9.4',LEAFLET_URL='/satellite_tracker_history/leaflet/';
// The card was "spot-trace-history-card" before the integration was renamed; dashboards using it keep working.
const CARD_TYPES=['custom:satellite-tracker-history-card','custom:spot-trace-history-card'];
class SatelliteTrackerHistoryCard extends HTMLElement {
  static loadLeaflet(){return import(`${LEAFLET_URL}leaflet-src.esm.js?v=${LEAFLET_VERSION}`)}
  setConfig(config) {
    if (!config || !CARD_TYPES.includes(config.type)) throw Error('Invalid card type');
    this.pausePlayback(false);
    this.cfg=config;
    this.tileUrl=config.tile_url || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
    if (!/^https:\/\//.test(this.tileUrl) && !this.tileUrl.startsWith("/")) throw Error("tile_url must be HTTPS or a local path");
    this.tileAttribution=config.tile_attribution || "© OpenStreetMap contributors";
    this.settings=config.devices || {};
    this.days=Number(config.days || 30);
    this.selected={};
    this.attachShadow({mode:'open'});
    this.shadowRoot.innerHTML=`<link rel="stylesheet" href="${LEAFLET_URL}leaflet.css?v=${LEAFLET_VERSION}"><style>
      :host{display:block;width:100%;height:100%;min-height:0;box-sizing:border-box} .wrap{display:flex;flex-direction:column;width:100%;height:100%;min-height:0;box-sizing:border-box;padding:8px;color:var(--primary-text-color);background:var(--ha-card-background,var(--card-background-color,#fff));border-radius:var(--ha-card-border-radius,12px)}
      .filters,.controls{display:flex;gap:6px 10px;flex-wrap:wrap;align-items:center}.filters{margin-bottom:8px}
      label{display:flex;align-items:center;gap:5px;font-size:13px}input,select{background:var(--ha-card-background,var(--card-background-color,#fff));color:inherit;border:1px solid var(--divider-color,#aaa);border-radius:5px;padding:5px;max-width:100%;box-sizing:border-box}
      .map-area{flex:1 1 420px;min-height:200px;position:relative}
      .map{position:absolute;inset:0;overflow:hidden;background:#dce5e7;border-radius:8px;touch-action:none}
      .filters,.note{flex-shrink:0}
      .playback{position:absolute;top:8px;right:8px;z-index:1000;display:flex;flex-direction:column;gap:8px;box-sizing:border-box;width:min(360px,calc(100% - 64px));max-height:calc(100% - 16px);overflow:auto;padding:10px;border-radius:8px;background:var(--ha-card-background,var(--card-background-color,#fff));box-shadow:0 2px 8px #0005}
      .playback[hidden]{display:none}.playback-head{display:flex;justify-content:space-between;align-items:center;gap:8px}.playback-close{padding:0 8px;font-size:18px;line-height:28px}
      .playback input[type=range]{flex:1;min-width:100px}.playback-time,.playback-positions{display:block;font-size:12px}.playback-positions{max-height:100px;overflow:auto}
      .timeline-toggle[aria-expanded=true]{background:var(--primary-color,#03a9f4);border-color:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}
      .vehicle-marker{display:flex;align-items:center;justify-content:center;box-sizing:border-box;width:100%;height:100%;border:2px solid #fff;border-radius:50%;color:#fff;box-shadow:0 1px 4px #0006;--mdc-icon-size:18px}
      .legend{display:flex;gap:10px;flex-wrap:wrap}.swatch{display:inline-block;width:11px;height:11px;border-radius:50%}
      button{border:1px solid var(--divider-color,#aaa);border-radius:6px;background:transparent;color:inherit;padding:5px 10px;cursor:pointer}
      .trip-dialog{width:min(420px,calc(100vw - 48px));border:1px solid var(--divider-color,#aaa);border-radius:12px;padding:20px;color:inherit;background:var(--ha-card-background,var(--card-background-color,#fff))}.trip-dialog::backdrop{background:#0008}.trip-form{display:flex;flex-direction:column;gap:14px}.trip-form h3{margin:0}.trip-form label{display:flex;flex-direction:column;align-items:stretch}.trip-form .trip-vehicle{flex-direction:row;align-items:center;margin:8px 0}.trip-vehicles{max-height:200px;overflow:auto}.trip-error{margin:0;color:var(--error-color,#db4437)}
      .note{font-size:12px;color:var(--secondary-text-color);margin-top:4px}
      </style><div class="wrap"><div class="filters"><label>Year <select class="year-select" aria-label="Filter by year"><option value="">Custom dates</option></select></label><label>From <input class="from" type="date"></label><label>To <input class="to" type="date"></label><label>Trip <select class="trip-select" aria-label="Saved trip"><option value="">Custom dates</option></select></label><button class="new-trip" type="button">New trip</button><button class="edit-trip" type="button" disabled>Edit trip</button><button class="delete-trip" type="button" disabled>Delete trip</button><button class="timeline-toggle" type="button" aria-expanded="false" aria-controls="timeline" disabled title="Select a trip to explore its timeline">Timeline</button><button class="refresh">Refresh</button><button class="fit">Fit routes</button><div class="legend"></div></div><dialog class="trip-dialog" aria-labelledby="trip-dialog-title"><form class="trip-form"><h3 id="trip-dialog-title" class="trip-dialog-title">New trip</h3><label>Name <input class="trip-name" type="text" required maxlength="100" autofocus></label><label>From <input class="trip-from" type="date" required></label><label>To <input class="trip-to" type="date" required></label><fieldset><legend>Vehicles involved</legend><label class="trip-vehicle"><input class="trip-all-devices" type="checkbox">All vehicles (including future trackers)</label><div class="trip-vehicles"></div></fieldset><p class="trip-error" role="alert"></p><div class="controls"><button class="cancel-trip-edit" type="button">Cancel</button><button class="save-trip" type="submit">Create trip</button></div></form></dialog><div class="map-area"><div class="map"></div><section class="playback" id="timeline" hidden aria-label="Trip timeline"><div class="playback-head"><label><input class="playback-enabled" type="checkbox">Explore trip timeline</label><button class="playback-close" type="button" aria-label="Close timeline" title="Close timeline">×</button></div><div class="controls"><button class="playback-play" type="button" disabled>Play</button><label>Speed <select class="playback-speed" aria-label="Playback speed"><option value="60">1 minute / second</option><option value="600">10 minutes / second</option><option value="3600" selected>1 hour / second</option><option value="21600">6 hours / second</option><option value="86400">1 day / second</option></select></label></div><label>Time <input class="playback-slider" type="range" step="1" aria-label="Trip playback time" disabled></label><output class="playback-time"></output><div class="playback-positions"></div></section></div><div class="note" role="status"></div></div>`;
    const today=new Date(), start=new Date(today.getTime()-this.days*86400000);
    const date=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    this.shadowRoot.querySelector('.from').value=date(start);
    this.shadowRoot.querySelector('.to').value=date(today);
    this.shadowRoot.querySelector('.year-select').onchange=()=>this.selectYear();
    this.shadowRoot.querySelector('.refresh').onclick=async()=>{await this.loadTrips(this.shadowRoot.querySelector('.trip-select').value);await this.loadTracks()};
    this.trips=[];
    this.playbackTime=null;this.playbackRange=null;this.trackRequest=0;this.playbackRate=3600;
    this.shadowRoot.querySelector('.playback-play').onclick=()=>this.playbackPlaying?this.pausePlayback():this.startPlayback();
    this.shadowRoot.querySelector('.playback-speed').onchange=()=>{const rate=Number(this.shadowRoot.querySelector('.playback-speed').value);if([60,600,3600,21600,86400].includes(rate))this.playbackRate=rate};
    this.visibilityHandler=()=>{if(document.hidden)this.pausePlayback()};
    document.addEventListener?.('visibilitychange',this.visibilityHandler);
    this.shadowRoot.querySelector('.playback-enabled').onchange=()=>this.togglePlayback();
    // The timeline floats over the map, so opening it never shrinks the map.
    this.timelineOpen=false;
    this.shadowRoot.querySelector('.timeline-toggle').onclick=()=>this.showTimeline(!this.timelineOpen);
    this.shadowRoot.querySelector('.playback-close').onclick=()=>this.showTimeline(false);
    this.shadowRoot.querySelector('.playback').addEventListener('keydown',e=>{if(e.key==='Escape')this.showTimeline(false)});
    this.shadowRoot.querySelector('.playback-slider').oninput=()=>this.scrubPlayback(Number(this.shadowRoot.querySelector('.playback-slider').value));
    this.editingTrip=null;
    this.shadowRoot.querySelector('.trip-select').onchange=()=>this.selectTrip();
    this.shadowRoot.querySelector('.new-trip').onclick=()=>this.openTripDialog();
    this.shadowRoot.querySelector('.trip-form').addEventListener('submit',e=>{e.preventDefault();this.saveTrip()});
    this.shadowRoot.querySelector('.trip-dialog').addEventListener('cancel',e=>{if(this.savingTrip)e.preventDefault()});
    this.shadowRoot.querySelector('.trip-dialog').addEventListener('close',()=>{this.editingTrip=null;this.syncTripControls()});
    this.shadowRoot.querySelector('.edit-trip').onclick=()=>this.editTrip();
    this.shadowRoot.querySelector('.delete-trip').onclick=()=>this.deleteTrip();
    this.shadowRoot.querySelector('.cancel-trip-edit').onclick=()=>this.cancelTripEdit();
    for(const selector of ['.from','.to']) this.shadowRoot.querySelector(selector).onchange=()=>{this.shadowRoot.querySelector('.trip-select').value='';this.syncTripControls();this.syncYear();this.legend()};
    this.shadowRoot.querySelector('.fit').onclick=()=>this.fit();
    this.tracks=[];this.markers=new Map();this.pendingFit=false;
    this.tileFailures=0;this.lastTileError=0;
    this.resizeObserver=new ResizeObserver(()=>this.resized());this.resizeObserver.observe(this.shadowRoot.querySelector('.map'));
  }
  disconnectedCallback(){this.pausePlayback(false);document.removeEventListener?.('visibilitychange',this.visibilityHandler);this.resizeObserver?.disconnect()}
  ensureMap(){
    this.mapReady??=SatelliteTrackerHistoryCard.loadLeaflet().then(L=>{
      this.L=L;
      // Fractional zoom steps let wheel and pinch gestures zoom smoothly instead of jumping a whole level,
      // and capping drag momentum keeps a quick flick to a few hundred pixels instead of across the world.
      this.map=L.map(this.shadowRoot.querySelector('.map'),{preferCanvas:true,zoomSnap:.25,zoomDelta:.5,wheelPxPerZoomLevel:120,
        inertiaMaxSpeed:600,minZoom:1,maxZoom:17,worldCopyJump:true}).setView([0,0],2);
      L.tileLayer(this.tileUrl,{maxZoom:17,attribution:this.tileAttribution,referrerPolicy:'strict-origin-when-cross-origin'})
        .on('tileerror',()=>{
          this.tileFailures++;
          if(Date.now()-this.lastTileError>30000){
            this.lastTileError=Date.now();
            this.status('Some map tiles failed to load. Check the tile provider, browser Referer and caching policy (HTTP 403 is possible).');
          }
        }).addTo(this.map);
      this.trackLayer=L.layerGroup().addTo(this.map);this.markerLayer=L.layerGroup().addTo(this.map);
      this.draw();if(this.pendingFit)this.fit();
    }).catch(e=>{this.mapReady=null;this.status('Unable to load the map: '+e.message)});
    return this.mapReady;
  }
  resized(){if(!this.map)return;this.map.invalidateSize();if(this.pendingFit)this.fit()}
  connectedCallback(){if(this.resizeObserver && this.shadowRoot) this.resizeObserver.observe(this.shadowRoot.querySelector('.map'));if(this.visibilityHandler)document.addEventListener?.('visibilitychange',this.visibilityHandler);if(this.shadowRoot&&this.trips)this.renderPlayback()}
  renderYears(){
    const current=new Date().getFullYear(),years=new Set([current]);
    for(const device of this.devices||[]){
      const first=new Date(device.first*1000).getFullYear(),last=new Date(device.last*1000).getFullYear();
      if(Number.isInteger(first)&&Number.isInteger(last)&&first>=1&&last<=9999&&last>=first){
        for(let year=first;year<=last;year++)years.add(year);
      }
    }
    this.availableYears=[...years].sort((a,b)=>b-a);
    const select=this.shadowRoot.querySelector('.year-select');select.replaceChildren();
    const custom=document.createElement('option');custom.value='';custom.textContent='Custom dates';select.append(custom);
    for(const year of this.availableYears){const option=document.createElement('option');option.value=String(year);option.textContent=String(year);select.append(option)}
    this.syncYear();
  }
  syncYear(){
    const from=this.shadowRoot.querySelector('.from').value,to=this.shadowRoot.querySelector('.to').value;
    const year=from.slice(0,4);
    this.shadowRoot.querySelector('.year-select').value=(from===`${year}-01-01`&&to===`${year}-12-31`&&(this.availableYears||[]).includes(Number(year)))?year:'';
  }
  async selectYear(){
    const year=Number(this.shadowRoot.querySelector('.year-select').value);
    if(!(this.availableYears||[]).includes(year))return;
    this.shadowRoot.querySelector('.from').value=`${year}-01-01`;
    this.shadowRoot.querySelector('.to').value=`${year}-12-31`;
    this.shadowRoot.querySelector('.trip-select').value='';
    this.syncTripControls();this.legend();await this.loadTracks();
  }
  set hass(hass){this._hass=hass;if(!this.initialized){this.initialized=true;this.ensureMap();this.loadDevices()}}
  async loadDevices(){
    try {
      this.allDevices=await this._hass.callWS({type:'satellite_tracker_history/devices'});
      this.devices=this.allDevices;
      this.devices=this.devices.filter(d=>!this.cfg.entry_id || d.entry_id===this.cfg.entry_id);
      this.devices=this.devices.filter(d=>this.deviceSettings(d)?.enabled!==false);
      this.devices.forEach(d=>{this.selected[d.entry_id+':'+d.device]=true});
      this.renderYears();this.legend();await this.loadTracks();await this.loadTrips();
    } catch(e){this.status('Unable to load devices: '+e.message)}
  }
  async loadTrips(selected=''){
    try {
      this.trips=await this._hass.callWS({type:'satellite_tracker_history/trips'});
      this.renderTrips(selected);
    }catch(e){this.status('Unable to load trips: '+e.message)}
  }
  renderTrips(selected=''){
    const select=this.shadowRoot.querySelector('.trip-select');
    select.replaceChildren();
    const custom=document.createElement('option');custom.value='';custom.textContent='Custom dates';select.append(custom);
    for(const trip of this.trips){const opt=document.createElement('option');opt.value=trip.id;opt.textContent=`${trip.name} (${trip.start_date} – ${trip.end_date})`;select.append(opt)}
    select.value=this.trips.some(trip=>trip.id===selected)?selected:'';
    this.syncTripControls();
    if(this.devices)this.legend();
  }
  syncTripControls(){
    const selected=this.trips.some(t=>t.id===this.shadowRoot.querySelector('.trip-select').value);
    this.shadowRoot.querySelector('.edit-trip').disabled=!selected||Boolean(this.editingTrip);
    this.shadowRoot.querySelector('.delete-trip').disabled=!selected||Boolean(this.editingTrip);
    this.shadowRoot.querySelector('.save-trip').textContent=this.editingTrip?'Save changes':'Create trip';
    const previous=this.playbackTime;this.renderPlayback();if(previous!==this.playbackTime)this.draw();
  }
  async selectTrip(){
    this.syncTripControls();
    const trip=this.trips.find(t=>t.id===this.shadowRoot.querySelector('.trip-select').value);
    this.legend();
    if(!trip){await this.loadTracks();return}
    this.shadowRoot.querySelector('.from').value=trip.start_date;
    this.shadowRoot.querySelector('.to').value=trip.end_date;
    this.syncYear();await this.loadTracks();
  }
  openTripDialog(trip=null){
    this.editingTrip=trip?.id||null;
    this.shadowRoot.querySelector('.trip-dialog-title').textContent=trip?'Edit trip':'New trip';
    this.shadowRoot.querySelector('.trip-name').value=trip?.name||'';
    this.shadowRoot.querySelector('.trip-from').value=trip?.start_date||this.shadowRoot.querySelector('.from').value;
    this.shadowRoot.querySelector('.trip-to').value=trip?.end_date||this.shadowRoot.querySelector('.to').value;
    this.shadowRoot.querySelector('.trip-error').textContent='';
    this.renderTripVehicles(trip);
    this.syncTripControls();
    this.shadowRoot.querySelector('.trip-dialog').showModal();
  }
  tripDevices(){
    const trip=this.trips?.find(t=>t.id===this.shadowRoot.querySelector('.trip-select').value);
    if(!trip?.devices)return this.devices||[];
    return (this.devices||[]).filter(d=>trip.devices.some(p=>p.feed_id===d.feed_id&&p.device===d.device));
  }
  renderTripVehicles(trip){
    const container=this.shadowRoot.querySelector('.trip-vehicles');container.replaceChildren();
    const all=this.shadowRoot.querySelector('.trip-all-devices');all.checked=Boolean(trip)&&trip.devices==null;
    const available=[...(this.allDevices||this.devices||[])];
    for(const participant of trip?.devices||[]) {
      if(!available.some(d=>d.feed_id===participant.feed_id&&d.device===participant.device))available.push({...participant,name:participant.device,unavailable:true});
    }
    this.tripVehicleChecks=available.map(d=>{
      const reference={feed_id:d.feed_id,device:d.device};
      const label=document.createElement('label');label.className='trip-vehicle';
      const checkbox=document.createElement('input');checkbox.type='checkbox';
      checkbox.checked=trip?(trip.devices==null||trip.devices.some(p=>p.feed_id===d.feed_id&&p.device===d.device)):this.selected[d.entry_id+':'+d.device]!==false;
      label.append(checkbox,document.createTextNode(`${this.deviceName(d)} (${d.device}, feed ${d.feed_id})${d.unavailable?' — unavailable':''}`));container.append(label);
      return {reference,checkbox};
    });
    const toggle=()=>{for(const item of this.tripVehicleChecks)item.checkbox.disabled=all.checked};
    all.onchange=toggle;toggle();
  }
  editTrip(){
    const trip=this.trips.find(t=>t.id===this.shadowRoot.querySelector('.trip-select').value);
    if(trip)this.openTripDialog(trip);
  }
  cancelTripEdit(){
    if(this.savingTrip)return;
    this.editingTrip=null;
    this.shadowRoot.querySelector('.trip-dialog').close();
    this.syncTripControls();
  }
  async deleteTrip(){
    const trip=this.trips.find(t=>t.id===this.shadowRoot.querySelector('.trip-select').value);
    if(!trip||!window.confirm(`Delete trip "${trip.name}"? GPS records will be kept.`))return;
    const button=this.shadowRoot.querySelector('.delete-trip');button.disabled=true;
    try {
      await this._hass.callWS({type:'satellite_tracker_history/delete_trip',trip_id:trip.id});
      this.trips=this.trips.filter(t=>t.id!==trip.id);this.renderTrips();
      this.status('Trip deleted. GPS records are preserved; the displayed dates remain as custom dates.');
    }catch(e){this.status('Unable to delete trip: '+e.message)}
    finally{this.syncTripControls()}
  }
  async saveTrip(){
    const name=this.shadowRoot.querySelector('.trip-name').value.trim();
    const start_date=this.shadowRoot.querySelector('.trip-from').value,end_date=this.shadowRoot.querySelector('.trip-to').value;
    if(this.savingTrip)return;
    const error=this.shadowRoot.querySelector('.trip-error');
    if(!name){error.textContent='Enter a trip name';return}
    if(!start_date||!end_date||end_date<start_date){error.textContent='Choose valid start and end dates';return}
    error.textContent='';
    this.savingTrip=true;
    const button=this.shadowRoot.querySelector('.save-trip');button.disabled=true;
    this.shadowRoot.querySelector('.cancel-trip-edit').disabled=true;
    try {
      const devices=this.shadowRoot.querySelector('.trip-all-devices').checked?null:this.tripVehicleChecks.filter(item=>item.checkbox.checked).map(item=>item.reference);
      if(devices&& !devices.length){error.textContent='Select at least one vehicle or choose all vehicles';return}
      const payload={type:this.editingTrip?'satellite_tracker_history/update_trip':'satellite_tracker_history/create_trip',name,start_date,end_date,devices};
      if(this.editingTrip)payload.trip_id=this.editingTrip;
      const trip=await this._hass.callWS(payload);
      this.editingTrip=null;
      this.trips=[trip,...this.trips.filter(t=>t.id!==trip.id)];this.renderTrips(trip.id);
      this.shadowRoot.querySelector('.from').value=trip.start_date;
      this.shadowRoot.querySelector('.to').value=trip.end_date;
      this.shadowRoot.querySelector('.trip-name').value='';
      this.shadowRoot.querySelector('.trip-dialog').close();
      this.syncYear();this.legend();await this.loadTracks();
    }catch(e){error.textContent='Unable to save trip: '+e.message}
    finally{this.savingTrip=false;button.disabled=false;this.shadowRoot.querySelector('.cancel-trip-edit').disabled=false}
  }
  legend(){const el=this.shadowRoot.querySelector('.legend');el.replaceChildren();
    this.tripDevices().forEach(d=>{const k=d.entry_id+':'+d.device;
      const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=this.selected[k];check.onchange=()=>{this.selected[k]=check.checked;this.loadTracks()};
      const dot=document.createElement('span');dot.className='swatch';dot.style.background=this.trackColor(d);
      label.append(check,dot,document.createTextNode(this.deviceName(d)));el.append(label)})
  }
  deviceSettings(d){return this.settings[d.entry_id+':'+d.device] || this.settings[d.device] || this.settings[d.name] || {}}
  deviceName(d){return this.deviceSettings(d).name||d.name||d.device}
  trackColor(d){return this.deviceSettings(d).color||this.palette(this.devices.indexOf(d))}
  palette(i){return ['#1976d2','#e65100','#388e3c','#8e24aa','#c2185b','#00838f'][i%6]}
  status(s){this.shadowRoot.querySelector('.note').textContent=s}
  playbackPoint(points){
    if(this.playbackTime==null)return points[points.length-1]||null;
    let low=0,high=points.length;
    while(low<high){const mid=Math.floor((low+high)/2);if(points[mid].time<=this.playbackTime)low=mid+1;else high=mid}
    return low?points[low-1]:null;
  }
  startPlayback(){
    if(this.playbackPlaying||document.hidden||!this.playbackRange||!this.tracks?.some(t=>t.points.length)||!this.trips?.some(t=>t.id===this.shadowRoot.querySelector('.trip-select').value))return;
    if(this.playbackTime===null||this.playbackTime>=this.playbackRange.end)this.playbackTime=this.playbackRange.start;
    this.playbackPlaying=true;this.playbackLastTick=null;this.playbackLastDraw=null;
    this.renderPlayback();this.drawMarkers();
    this.playbackFrame=requestAnimationFrame(time=>this.playbackTick(time));
  }
  pausePlayback(render=true){
    this.playbackPlaying=false;
    if(this.playbackFrame!=null)cancelAnimationFrame(this.playbackFrame);
    this.playbackFrame=null;this.playbackLastTick=null;
    if(render&&this.shadowRoot){this.renderPlayback();this.drawMarkers();}
  }
  playbackTick(time){
    this.playbackFrame=null;
    if(!this.playbackPlaying)return;
    if(document.hidden){this.pausePlayback();return;}
    if(this.playbackLastTick===null){this.playbackLastTick=time;this.playbackLastDraw=time;}
    const elapsed=Math.max(0,Math.min(250,time-this.playbackLastTick))/1000;
    this.playbackLastTick=time;
    this.playbackTime=Math.min(this.playbackRange.end,this.playbackTime+elapsed*this.playbackRate);
    if(this.playbackTime>=this.playbackRange.end){
      this.pausePlayback(false);this.renderPlayback();this.drawMarkers();return;
    }
    if(time-this.playbackLastDraw>=100){this.playbackLastDraw=time;this.renderPlayback();this.drawMarkers();}
    if(this.playbackPlaying)this.playbackFrame=requestAnimationFrame(next=>this.playbackTick(next));
  }
  togglePlayback(){
    this.pausePlayback(false);
    const checked=this.shadowRoot.querySelector('.playback-enabled').checked;
    this.playbackTime=checked&&this.playbackRange?this.playbackRange.start:null;
    this.renderPlayback();this.drawMarkers();
  }
  scrubPlayback(time){
    this.pausePlayback(false);
    if(this.playbackTime===null||!this.playbackRange||!Number.isFinite(time))return;
    this.playbackTime=Math.max(this.playbackRange.start,Math.min(this.playbackRange.end,time));
    this.renderPlayback();this.drawMarkers();
  }
  showTimeline(open){
    this.timelineOpen=open;this.renderPlayback();
    this.shadowRoot.querySelector(this.timelineOpen?'.playback-enabled':'.timeline-toggle').focus?.();
  }
  renderPlayback(){
    const trip=this.trips?.find(t=>t.id===this.shadowRoot.querySelector('.trip-select').value);
    if(!trip)this.timelineOpen=false;
    const toggle=this.shadowRoot.querySelector('.timeline-toggle');toggle.disabled=!trip;toggle.setAttribute?.('aria-expanded',String(this.timelineOpen));
    this.shadowRoot.querySelector('.playback').hidden=!this.timelineOpen;
    const available=Boolean(trip&&this.playbackRange&&this.tracks?.some(t=>t.points.length));
    if(!available){this.pausePlayback(false);this.playbackTime=null;}
    const enabled=this.shadowRoot.querySelector('.playback-enabled');enabled.disabled=!available;enabled.checked=this.playbackTime!==null;
    const play=this.shadowRoot.querySelector('.playback-play');play.disabled=!available;play.textContent=this.playbackPlaying?'Pause':this.playbackTime!==null&&this.playbackTime>=this.playbackRange?.end?'Replay':'Play';play.setAttribute?.('aria-pressed',String(Boolean(this.playbackPlaying)));
    this.shadowRoot.querySelector('.playback-speed').disabled=!available;
    const slider=this.shadowRoot.querySelector('.playback-slider');slider.disabled=!available||this.playbackTime===null;
    slider.min=String(this.playbackRange?.start||0);slider.max=String(this.playbackRange?.end||0);
    slider.value=String(this.playbackTime??this.playbackRange?.start??0);
    const format=time=>new Date(time*1000).toLocaleString(undefined,{timeZoneName:'short'});
    this.shadowRoot.querySelector('.playback-time').textContent=!available?'No loaded positions for this trip.':this.playbackTime===null?'Enable the timeline to explore recorded positions.':`Timeline: ${format(this.playbackTime)}`;
    const positions=this.shadowRoot.querySelector('.playback-positions');positions.replaceChildren();
    if(this.playbackTime!==null)for(const track of this.tracks){
      const point=this.playbackPoint(track.points),row=document.createElement('div');
      const name=this.deviceName(track.d);
      row.textContent=point?`${name} — last recorded fix: ${format(point.time)}`:`${name} — no recorded fix yet`;
      positions.append(row);
    }
  }
  async loadTracks(){if(!this.devices)return;
    this.pausePlayback(false);
    const request=++this.trackRequest;
    const a=this.shadowRoot.querySelector('.from').value,b=this.shadowRoot.querySelector('.to').value;
    const start=Date.parse(a+'T00:00:00')/1000,end=Date.parse(b+'T23:59:59')/1000;
    if(!Number.isFinite(start)||!Number.isFinite(end)||end<start){this.status('Invalid date range');return}
    if(end-start>366*86400){this.status('Select a date range of up to 366 days');return}
    this.playbackTime=null;this.playbackRange=null;this.renderPlayback();
    this.status('Loading tracks…');
    try {const tracks=await Promise.all(this.tripDevices().filter(d=>this.selected[d.entry_id+':'+d.device]).map(async d=>({d,points:await this._hass.callWS({type:'satellite_tracker_history/track',entry_id:d.entry_id,device:d.device,start:Math.floor(start),end:Math.floor(end),limit:50000})})));
      if(request!==this.trackRequest)return;
      this.tracks=tracks;this.playbackRange={start:Math.floor(start),end:Math.floor(end)};this.renderPlayback();
      this.draw();this.fit();this.status(this.tracks.reduce((s,t)=>s+t.points.length,0)+' positions displayed. Scroll or pinch to zoom, drag to pan' + (this.tracks.some(t=>t.points.length>=50000)?'. A vehicle reached the 50,000-position limit; its timeline may be incomplete.':'.'));
    }catch(e){if(request===this.trackRequest)this.status('Track loading failed: '+e.message)}
  }
  trackBounds(){
    let south=Infinity,west=Infinity,north=-Infinity,east=-Infinity;
    for(const track of this.tracks)for(const p of track.points){south=Math.min(south,p.lat);north=Math.max(north,p.lat);west=Math.min(west,p.lon);east=Math.max(east,p.lon)}
    return Number.isFinite(south)?[[south,west],[north,east]]:null;
  }
  fit(){
    const bounds=this.trackBounds(),map=this.shadowRoot.querySelector('.map');
    // Leaflet cannot fit a hidden map, so wait until it has a size.
    this.pendingFit=Boolean(bounds)&&!(this.map&&map.clientWidth&&map.clientHeight);
    if(bounds&&!this.pendingFit)this.map.fitBounds(bounds,{padding:[24,24],maxZoom:16});
  }
  draw(){
    if(!this.map){this.ensureMap();return}
    this.trackLayer.clearLayers();this.markerLayer.clearLayers();this.markers.clear();
    for(const t of this.tracks){
      if(t.points.length)this.L.polyline(t.points.map(p=>[p.lat,p.lon]),{color:this.trackColor(t.d),weight:3,lineJoin:'round',lineCap:'round'}).addTo(this.trackLayer);
    }
    this.drawMarkers();
  }
  vehicleIcon(d){
    const icon=this.deviceSettings(d).icon||d.icon,size=icon?30:16;
    const el=document.createElement('div');el.className='vehicle-marker';el.style.background=this.trackColor(d);
    if(icon){const haIcon=document.createElement('ha-icon');haIcon.setAttribute('icon',icon);el.append(haIcon)}
    return this.L.divIcon({html:el,className:'',iconSize:[size,size],iconAnchor:[size/2,size/2]});
  }
  drawMarkers(){
    if(!this.markerLayer)return;
    // Markers are moved rather than rebuilt, so playback does not reload their icons on every frame.
    for(const track of this.tracks){
      const key=track.d.entry_id+':'+track.d.device,point=this.playbackPoint(track.points);
      let marker=this.markers.get(key);
      if(!point){if(marker){this.markerLayer.removeLayer(marker);this.markers.delete(key)}continue}
      if(marker){marker.setLatLng([point.lat,point.lon]);continue}
      const name=this.deviceName(track.d);
      marker=this.L.marker([point.lat,point.lon],{icon:this.vehicleIcon(track.d),title:name,alt:name,keyboard:false}).addTo(this.markerLayer);
      this.markers.set(key,marker);
    }
  }
  getCardSize(){return 6}
}
if (!customElements.get('satellite-tracker-history-card')) {
  customElements.define('satellite-tracker-history-card',SatelliteTrackerHistoryCard);
}
// A second name needs its own class. Skipped if the old integration's card is still loaded.
if (!customElements.get('spot-trace-history-card')) {
  customElements.define('spot-trace-history-card',class extends SatelliteTrackerHistoryCard {});
}
window.customCards=window.customCards||[];
if (!window.customCards.some(card=>card.type==='satellite-tracker-history-card')) {
  window.customCards.push({type:'satellite-tracker-history-card',name:'Satellite Tracker History',description:'Historical GPS tracks of SPOT and Garmin inReach vehicles'});
}
})();
