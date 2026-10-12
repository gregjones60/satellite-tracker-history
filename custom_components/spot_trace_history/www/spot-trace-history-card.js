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
      :host{display:block} .wrap{padding:16px;color:var(--primary-text-color);background:var(--ha-card-background,var(--card-background-color,#fff));border-radius:var(--ha-card-border-radius,12px)}
      .head{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:center}h3{margin:0 0 12px}
      .controls{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;align-items:center}
      label{display:flex;align-items:center;gap:5px;font-size:13px}input[type=date]{background:transparent;color:inherit;border:1px solid var(--divider-color,#aaa);border-radius:5px;padding:5px}
      .map{height:420px;position:relative;overflow:hidden;background:#dce5e7;border-radius:8px;touch-action:none}
      .tiles{position:absolute;inset:0}.tiles img{position:absolute;width:256px;height:256px;max-width:none;pointer-events:none}
      svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
      .legend{display:flex;gap:14px;flex-wrap:wrap;margin:10px 0}.swatch{display:inline-block;width:11px;height:11px;border-radius:50%}
      button{border:1px solid var(--divider-color,#aaa);border-radius:6px;background:transparent;color:inherit;padding:5px 10px;cursor:pointer}
      .note{font-size:12px;color:var(--secondary-text-color);margin-top:8px}
      </style><div class="wrap"><h3></h3><div class="controls"><label>From <input class="from" type="date"></label><label>To <input class="to" type="date"></label><button class="refresh">Refresh</button><button class="fit">Fit routes</button></div><div class="legend"></div><div class="map"><div class="tiles"></div><svg xmlns="http://www.w3.org/2000/svg"></svg></div><div class="note" role="status"></div></div>`;
    this.shadowRoot.querySelector('h3').textContent=config.title || 'SPOT Trace History';
    const today=new Date(), start=new Date(today.getTime()-this.days*86400000);
    const date=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    this.shadowRoot.querySelector('.from').value=date(start);
    this.shadowRoot.querySelector('.to').value=date(today);
    this.shadowRoot.querySelector('.refresh').onclick=()=>this.loadTracks();
    this.shadowRoot.querySelector('.fit').onclick=()=>{this.fit();this.draw()};
    this.shadowRoot.querySelector('.map').addEventListener('wheel',e=>{e.preventDefault();this.zoom=Math.max(1,Math.min(17,this.zoom+(e.deltaY<0?1:-1)));this.draw()},{passive:false});
    this.shadowRoot.querySelector('.map').addEventListener('pointerdown',e=>{this.drag=[e.clientX,e.clientY];e.currentTarget.setPointerCapture(e.pointerId)});
    this.shadowRoot.querySelector('.map').addEventListener('pointermove',e=>{if(!this.drag)return;const scale=256*Math.pow(2,this.zoom);this.cx-=(e.clientX-this.drag[0])/scale;this.cy-=(e.clientY-this.drag[1])/scale;this.drag=[e.clientX,e.clientY];this.draw()});
    this.shadowRoot.querySelector('.map').addEventListener('pointerup',()=>this.drag=null);
    this.zoom=6;this.cx=.5;this.cy=.5;this.tracks=[];
    this.tileNodes=new Map();this.tileFailures=0;this.lastTileError=0;this.lastViewKey='';
    this.resizeObserver=new ResizeObserver(()=>this.draw());this.resizeObserver.observe(this.shadowRoot.querySelector('.map'));
  }
  disconnectedCallback(){this.resizeObserver?.disconnect();this.tileNodes?.clear()}
  connectedCallback(){if(this.resizeObserver && this.shadowRoot) this.resizeObserver.observe(this.shadowRoot.querySelector('.map'))}
  set hass(hass){this._hass=hass;if(!this.initialized){this.initialized=true;this.loadDevices()}}
  async loadDevices(){
    try {
      this.devices=await this._hass.callWS({type:'spot_trace_history/devices'});
      this.devices=this.devices.filter(d=>!this.cfg.entry_id || d.entry_id===this.cfg.entry_id);
      this.devices=this.devices.filter(d=>this.deviceSettings(d)?.enabled!==false);
      this.devices.forEach(d=>{this.selected[d.entry_id+':'+d.device]=true});
      this.legend();await this.loadTracks();
    } catch(e){this.status('Unable to load devices: '+e.message)}
  }
  legend(){const el=this.shadowRoot.querySelector('.legend');el.replaceChildren();
    this.devices.forEach((d,i)=>{const k=d.entry_id+':'+d.device, opt=this.deviceSettings(d)||{},color=opt.color||this.palette(i);
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
    try {this.tracks=await Promise.all(this.devices.filter(d=>this.selected[d.entry_id+':'+d.device]).map(async d=>({d,points:await this._hass.callWS({type:'spot_trace_history/track',entry_id:d.entry_id,device:d.device,start:Math.floor(start),end:Math.floor(end),limit:50000})})));
      this.fit();this.draw();this.status(this.tracks.reduce((s,t)=>s+t.points.length,0)+' positions displayed. Scroll to zoom, drag to pan. Map ' + this.tileAttribution + '');
    }catch(e){this.status('Track loading failed: '+e.message)}
  }
  merc(lat,lon){const phi=Math.max(-85.0511,Math.min(85.0511,lat))*Math.PI/180;return [(lon+180)/360,(1-Math.log(Math.tan(phi)+1/Math.cos(phi))/Math.PI)/2]}
  fit(){const pts=this.tracks.flatMap(t=>t.points);if(!pts.length)return;
    const xy=pts.map(p=>this.merc(p.lat,p.lon)), xs=xy.map(p=>p[0]),ys=xy.map(p=>p[1]);
    const minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);
    this.cx=(minx+maxx)/2;this.cy=(miny+maxy)/2;
    const el=this.shadowRoot.querySelector('.map'),w=el.clientWidth||600,h=el.clientHeight||420;
    this.zoom=Math.max(1,Math.min(16,Math.floor(Math.log2(Math.min(w/(Math.max(.00001,maxx-minx)*320),h/(Math.max(.00001,maxy-miny)*320))))));
  }
  draw(){if(!this.shadowRoot)return;const map=this.shadowRoot.querySelector('.map'),w=map.clientWidth,h=map.clientHeight;if(!w||!h)return;
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
customElements.define('spot-trace-history-card',SpotTraceHistoryCard);
window.customCards=window.customCards||[];
window.customCards.push({type:'spot-trace-history-card',name:'SPOT Trace History',description:'Historical GPS tracks for independently configurable SPOT devices'});
