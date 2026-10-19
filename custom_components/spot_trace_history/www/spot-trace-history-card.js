(() => {
class SpotTraceHistoryCard extends HTMLElement {
  setConfig(config) {
    if (!config || config.type !== 'custom:spot-trace-history-card') throw Error('Invalid card type');
    this.cfg=config;
    this.tileUrl=config.tile_url || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
    if (!/^https:\/\//.test(this.tileUrl) && !this.tileUrl.startsWith("/")) throw Error("tile_url must be HTTPS or a local path");
    this.tileAttribution=config.tile_attribution || "© OpenStreetMap contributors";
    this.settings=config.devices || {};
    this.days=Number(config.days || 30);
    this.selected={};
    this.attachShadow({mode:'open'});
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;width:100%;height:100%;min-height:0;box-sizing:border-box} .wrap{display:flex;flex-direction:column;width:100%;height:100%;min-height:0;box-sizing:border-box;padding:16px;color:var(--primary-text-color);background:var(--ha-card-background,var(--card-background-color,#fff));border-radius:var(--ha-card-border-radius,12px)}
      .head{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:center}h3{margin:0 0 12px}
      .controls{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
      label{display:flex;align-items:center;gap:5px;font-size:13px}input,select{background:var(--ha-card-background,var(--card-background-color,#fff));color:inherit;border:1px solid var(--divider-color,#aaa);border-radius:5px;padding:5px;max-width:100%;box-sizing:border-box}
      .map{flex:1 1 420px;min-height:200px;width:100%;position:relative;overflow:hidden;background:#dce5e7;border-radius:8px;touch-action:none}
      .controls,.legend,h3,.note{flex-shrink:0}
      .zoom-controls{position:absolute;top:10px;right:10px;z-index:1;display:flex;flex-direction:column;gap:4px}
      .zoom-controls button{width:40px;height:40px;padding:0;font-size:24px;background:var(--ha-card-background,var(--card-background-color,#fff));box-shadow:0 1px 4px #0004}
      .zoom-controls button:disabled{opacity:.45;cursor:default}
      .tiles{position:absolute;inset:0}.tiles img{position:absolute;width:256px;height:256px;max-width:none;pointer-events:none}
      svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
      .legend{display:flex;gap:14px;flex-wrap:wrap;margin:10px 0}.swatch{display:inline-block;width:11px;height:11px;border-radius:50%}
      button{border:1px solid var(--divider-color,#aaa);border-radius:6px;background:transparent;color:inherit;padding:5px 10px;cursor:pointer}
      .trip-dialog{width:min(420px,calc(100vw - 48px));border:1px solid var(--divider-color,#aaa);border-radius:12px;padding:20px;color:inherit;background:var(--ha-card-background,var(--card-background-color,#fff))}.trip-dialog::backdrop{background:#0008}.trip-form{display:flex;flex-direction:column;gap:14px}.trip-form label{display:flex;flex-direction:column;align-items:stretch}.trip-form .trip-vehicle{flex-direction:row;align-items:center;margin:8px 0}.trip-vehicles{max-height:200px;overflow:auto}.trip-error{margin:0;color:var(--error-color,#db4437)}
      .note{font-size:12px;color:var(--secondary-text-color);margin-top:8px}
      </style><div class="wrap"><h3></h3><div class="controls"><label>Year <select class="year-select" aria-label="Filter by year"><option value="">Custom dates</option></select></label><label>From <input class="from" type="date"></label><label>To <input class="to" type="date"></label><button class="refresh">Refresh</button><button class="fit">Fit routes</button></div><div class="controls trip-controls"><label>Trip <select class="trip-select" aria-label="Saved trip"><option value="">Custom dates</option></select></label><button class="new-trip" type="button">New trip</button><button class="edit-trip" type="button" disabled>Edit trip</button><button class="delete-trip" type="button" disabled>Delete trip</button></div><dialog class="trip-dialog" aria-labelledby="trip-dialog-title"><form class="trip-form"><h3 id="trip-dialog-title" class="trip-dialog-title">New trip</h3><label>Name <input class="trip-name" type="text" required maxlength="100" autofocus></label><label>From <input class="trip-from" type="date" required></label><label>To <input class="trip-to" type="date" required></label><fieldset><legend>Vehicles involved</legend><label class="trip-vehicle"><input class="trip-all-devices" type="checkbox">All vehicles (including future trackers)</label><div class="trip-vehicles"></div></fieldset><p class="trip-error" role="alert"></p><div class="controls"><button class="cancel-trip-edit" type="button">Cancel</button><button class="save-trip" type="submit">Create trip</button></div></form></dialog><div class="legend"></div><div class="map"><div class="tiles"></div><svg xmlns="http://www.w3.org/2000/svg"></svg><div class="zoom-controls" role="group" aria-label="Map zoom"><button type="button" class="zoom-in" aria-label="Zoom in" title="Zoom in">+</button><button type="button" class="zoom-out" aria-label="Zoom out" title="Zoom out">−</button></div></div><div class="note" role="status"></div></div>`;
    this.shadowRoot.querySelector('h3').textContent=config.title || 'SPOT Trace History';
    const today=new Date(), start=new Date(today.getTime()-this.days*86400000);
    const date=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    this.shadowRoot.querySelector('.from').value=date(start);
    this.shadowRoot.querySelector('.to').value=date(today);
    this.shadowRoot.querySelector('.year-select').onchange=()=>this.selectYear();
    this.shadowRoot.querySelector('.refresh').onclick=async()=>{await this.loadTrips(this.shadowRoot.querySelector('.trip-select').value);await this.loadTracks()};
    this.trips=[];
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
    this.shadowRoot.querySelector('.fit').onclick=()=>{this.fit();this.draw()};
    this.shadowRoot.querySelector('.zoom-in').onclick=()=>this.changeZoom(1);
    this.shadowRoot.querySelector('.zoom-out').onclick=()=>this.changeZoom(-1);
    this.shadowRoot.querySelector('.zoom-controls').addEventListener('pointerdown',e=>e.stopPropagation());
    this.shadowRoot.querySelector('.map').addEventListener('wheel',e=>this.wheelZoom(e),{passive:false});
    this.shadowRoot.querySelector('.map').addEventListener('pointerdown',e=>{this.drag=[e.clientX,e.clientY];e.currentTarget.setPointerCapture(e.pointerId)});
    this.shadowRoot.querySelector('.map').addEventListener('pointermove',e=>{if(!this.drag)return;const scale=256*Math.pow(2,this.zoom);this.cx-=(e.clientX-this.drag[0])/scale;this.cy-=(e.clientY-this.drag[1])/scale;this.drag=[e.clientX,e.clientY];this.draw()});
    this.shadowRoot.querySelector('.map').addEventListener('pointerup',()=>this.drag=null);
    this.zoom=6;this.cx=.5;this.cy=.5;this.tracks=[];
    this.wheelDelta=0;this.wheelLastEvent=null;this.wheelLastZoom=-Infinity;
    this.tileNodes=new Map();this.tileFailures=0;this.lastTileError=0;this.lastViewKey='';
    this.resizeObserver=new ResizeObserver(()=>this.draw());this.resizeObserver.observe(this.shadowRoot.querySelector('.map'));
  }
  disconnectedCallback(){this.resizeObserver?.disconnect();this.tileNodes?.clear()}
  changeZoom(delta,anchor=null){
    const next=Math.max(1,Math.min(17,this.zoom+delta));
    if(anchor&&next!==this.zoom){
      const map=this.shadowRoot.querySelector('.map'),rect=map.getBoundingClientRect();
      const x=anchor.x-rect.left-rect.width/2,y=anchor.y-rect.top-rect.height/2;
      const oldScale=256*2**this.zoom,newScale=256*2**next;
      this.cx+=x/oldScale-x/newScale;this.cy+=y/oldScale-y/newScale;
    }
    this.zoom=next;this.draw();
  }
  wheelZoom(event){
    event.preventDefault();
    if(!Number.isFinite(event.deltaY)||event.deltaY===0)return;
    const map=this.shadowRoot.querySelector('.map');
    const unit=event.deltaMode===1?100/3:event.deltaMode===2?(map.clientHeight||800):1;
    const movement=Math.max(-100,Math.min(100,event.deltaY*unit));
    const now=Number.isFinite(event.timeStamp)?event.timeStamp:Date.now();
    if(this.wheelLastEvent===null||now-this.wheelLastEvent>250||Math.sign(movement)!==Math.sign(this.wheelDelta)){
      this.wheelDelta=0;
    }
    this.wheelLastEvent=now;
    this.wheelDelta=Math.max(-100,Math.min(100,this.wheelDelta+movement));
    if(Math.abs(this.wheelDelta)<100||now-this.wheelLastZoom<120)return;
    const direction=this.wheelDelta<0?1:-1;
    this.wheelDelta=0;this.wheelLastZoom=now;
    const anchor=Number.isFinite(event.clientX)&&Number.isFinite(event.clientY)?{x:event.clientX,y:event.clientY}:null;
    this.changeZoom(direction,anchor);
  }
  connectedCallback(){if(this.resizeObserver && this.shadowRoot) this.resizeObserver.observe(this.shadowRoot.querySelector('.map'))}
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
  set hass(hass){this._hass=hass;if(!this.initialized){this.initialized=true;this.loadDevices()}}
  async loadDevices(){
    try {
      this.allDevices=await this._hass.callWS({type:'spot_trace_history/devices'});
      this.devices=this.allDevices;
      this.devices=this.devices.filter(d=>!this.cfg.entry_id || d.entry_id===this.cfg.entry_id);
      this.devices=this.devices.filter(d=>this.deviceSettings(d)?.enabled!==false);
      this.devices.forEach(d=>{this.selected[d.entry_id+':'+d.device]=true});
      this.renderYears();this.legend();await this.loadTracks();await this.loadTrips();
    } catch(e){this.status('Unable to load devices: '+e.message)}
  }
  async loadTrips(selected=''){
    try {
      this.trips=await this._hass.callWS({type:'spot_trace_history/trips'});
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
      const name=this.deviceSettings(d).name||d.name||d.device;
      label.append(checkbox,document.createTextNode(`${name} (${d.device}, feed ${d.feed_id})${d.unavailable?' — unavailable':''}`));container.append(label);
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
      await this._hass.callWS({type:'spot_trace_history/delete_trip',trip_id:trip.id});
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
      const payload={type:this.editingTrip?'spot_trace_history/update_trip':'spot_trace_history/create_trip',name,start_date,end_date,devices};
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
    this.tripDevices().forEach(d=>{const k=d.entry_id+':'+d.device, opt=this.deviceSettings(d)||{},color=opt.color||this.palette(this.devices.indexOf(d));
      const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=this.selected[k];check.onchange=()=>{this.selected[k]=check.checked;this.loadTracks()};
      const dot=document.createElement('span');dot.className='swatch';dot.style.background=color;
      label.append(check,dot,document.createTextNode(opt.name||d.name||d.device));el.append(label)})
  }
  deviceSettings(d){return this.settings[d.entry_id+':'+d.device] || this.settings[d.device] || this.settings[d.name] || {}}
  palette(i){return ['#1976d2','#e65100','#388e3c','#8e24aa','#c2185b','#00838f'][i%6]}
  status(s){this.shadowRoot.querySelector('.note').textContent=s}
  async loadTracks(){if(!this.devices)return;
    const a=this.shadowRoot.querySelector('.from').value,b=this.shadowRoot.querySelector('.to').value;
    const start=Date.parse(a+'T00:00:00')/1000,end=Date.parse(b+'T23:59:59')/1000;
    if(!Number.isFinite(start)||!Number.isFinite(end)||end<start){this.status('Invalid date range');return}
    if(end-start>366*86400){this.status('Select a date range of up to 366 days');return}
    this.status('Loading tracks…');
    try {this.tracks=await Promise.all(this.tripDevices().filter(d=>this.selected[d.entry_id+':'+d.device]).map(async d=>({d,points:await this._hass.callWS({type:'spot_trace_history/track',entry_id:d.entry_id,device:d.device,start:Math.floor(start),end:Math.floor(end),limit:50000})})));
      this.fit();this.draw();this.status(this.tracks.reduce((s,t)=>s+t.points.length,0)+' positions displayed. Scroll to zoom, drag to pan. Map ' + this.tileAttribution + '');
    }catch(e){this.status('Track loading failed: '+e.message)}
  }
  merc(lat,lon){const phi=Math.max(-85.0511,Math.min(85.0511,lat))*Math.PI/180;return [(lon+180)/360,(1-Math.log(Math.tan(phi)+1/Math.cos(phi))/Math.PI)/2]}
  fit(){const pts=this.tracks.flatMap(t=>t.points);if(!pts.length)return;
    let minx=Infinity,maxx=-Infinity,miny=Infinity,maxy=-Infinity;
    for(const p of pts){const [x,y]=this.merc(p.lat,p.lon);minx=Math.min(minx,x);maxx=Math.max(maxx,x);miny=Math.min(miny,y);maxy=Math.max(maxy,y)}
    this.cx=(minx+maxx)/2;this.cy=(miny+maxy)/2;
    const el=this.shadowRoot.querySelector('.map'),w=el.clientWidth||600,h=el.clientHeight||420;
    this.zoom=Math.max(1,Math.min(16,Math.floor(Math.log2(Math.min(w/(Math.max(.00001,maxx-minx)*320),h/(Math.max(.00001,maxy-miny)*320))))));
  }
  draw(){if(!this.shadowRoot)return;
    this.shadowRoot.querySelector('.zoom-in').disabled=this.zoom>=17;
    this.shadowRoot.querySelector('.zoom-out').disabled=this.zoom<=1;
    const map=this.shadowRoot.querySelector('.map'),w=map.clientWidth,h=map.clientHeight;if(!w||!h)return;
    const z=this.zoom,scale=256*2**z, tiles=this.shadowRoot.querySelector('.tiles');
    const left=this.cx*scale-w/2,top=this.cy*scale-h/2;
    // Reuse existing image elements when only the position changes.
    // Keep a one-tile buffer to avoid needless downloads on small pans.
    const needed=new Set(), max=2**z;
    const x0=Math.floor(left/256)-1,x1=Math.floor((left+w)/256)+1;
    const y0=Math.max(0,Math.floor(top/256)-1),y1=Math.min(max-1,Math.floor((top+h)/256)+1);
    for(let x=x0;x<=x1;x++)for(let y=y0;y<=y1;y++){
      const wrappedX=((x%max)+max)%max, key=`${z}/${wrappedX}/${y}`;
      needed.add(key);
      let img=this.tileNodes.get(key);
      if(!img){
        img=document.createElement('img');img.loading='lazy';img.alt='';img.decoding='async';
        img.referrerPolicy='strict-origin-when-cross-origin';
        img.dataset.key=key;
        img.onerror=()=>{
          if(!this.tileNodes.has(key))return;
          this.tileFailures++;
          if(Date.now()-this.lastTileError>30000){
            this.lastTileError=Date.now();
            this.status('Some map tiles failed to load. Check the tile provider, browser Referer and caching policy (HTTP 403 is possible).');
          }
        };
        img.src=this.tileUrl.replaceAll("{z}",String(z)).replaceAll("{x}",String(wrappedX)).replaceAll("{y}",String(y));
        this.tileNodes.set(key,img);tiles.append(img);
      }
      img.style.left=(x*256-left)+'px';
      img.style.top=(y*256-top)+'px';
    }
    // Only remove tiles that are no longer near the visible viewport.
    for(const [key,img] of this.tileNodes){
      if(!needed.has(key)){img.remove();this.tileNodes.delete(key)}
    }
    const svg=this.shadowRoot.querySelector('svg');svg.replaceChildren();svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
    this.tracks.forEach((t,i)=>{if(!t.points.length)return;const color=(this.deviceSettings(t.d)||{}).color||this.palette(this.devices.indexOf(t.d));
      const path=document.createElementNS('http://www.w3.org/2000/svg','polyline');path.setAttribute('fill','none');path.setAttribute('stroke',color);path.setAttribute('stroke-width','3');path.setAttribute('stroke-linejoin','round');path.setAttribute('stroke-linecap','round');
      path.setAttribute('points',t.points.map(p=>{const xy=this.merc(p.lat,p.lon);return `${(xy[0]*scale-left).toFixed(1)},${(xy[1]*scale-top).toFixed(1)}`}).join(' '));svg.append(path);
      const last=t.points[t.points.length-1],xy=this.merc(last.lat,last.lon),marker=document.createElementNS('http://www.w3.org/2000/svg','circle');marker.setAttribute('cx',xy[0]*scale-left);marker.setAttribute('cy',xy[1]*scale-top);marker.setAttribute('r','5');marker.setAttribute('fill',color);marker.setAttribute('stroke','#fff');marker.setAttribute('stroke-width','2');svg.append(marker)
    })
  }
  getCardSize(){return 6}
}
if (!customElements.get('spot-trace-history-card')) {
  customElements.define('spot-trace-history-card',SpotTraceHistoryCard);
}
window.customCards=window.customCards||[];
if (!window.customCards.some(card=>card.type==='spot-trace-history-card')) {
  window.customCards.push({type:'spot-trace-history-card',name:'SPOT Trace History',description:'Historical GPS tracks for independently configurable SPOT devices'});
}
})();
