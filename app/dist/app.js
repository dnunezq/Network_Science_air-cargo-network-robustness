'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const fmt = new Intl.NumberFormat('es-CO');
  const decimal = (v, digits = 3) => Number.isFinite(Number(v)) && v !== null && v !== '' ? Number(v).toLocaleString('es-CO', {maximumFractionDigits: digits, minimumFractionDigits: digits}) : '—';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pairKey = (a, b) => [String(a), String(b)].sort().join('|');
  const state = {data:null, period:'annual', a:'', b:'', simulate:false, routeMode:'top', map:null, layers:null, airports:new Map(), pairMaps:new Map(), tileFailures:0, geography:null, baseLayer:null,mapOverlay:null,rankMode:'synergy',variant:'base',indexMode:'own',interactive:null,model:null,overlayNetwork:null,overlayOrigin:null,discarded:false,comparisonKey:null,nodeColor:'none',exploration:null,playStep:null,playTimers:[],animateFailure:false,goneLayers:[]};
  // Paleta categórica validada para daltonismo en todos los pares (tres tonos) y un gris neutro para un cuarto grupo.
  const COMMUNITY_PALETTE=['#2a78d6','#eb6834','#1baf7a','#52514e'];
  const reducedMotion=()=>window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const titles = {annual:'Enero — diciembre de 2025',T1:'Enero — marzo de 2025',T2:'Abril — junio de 2025',T3:'Julio — septiembre de 2025',T4:'Octubre — diciembre de 2025'};
  const period = () => state.mapOverlay ? state.overlayNetwork : state.model ? state.model.network(state.period,state.variant,state.indexMode) : state.data?.periods?.[state.period];
  const pairs = () => period()?.pairs || [];
  const selectedPair = () => period()?.pairMap?.get(pairKey(state.a,state.b));
  const city = id => state.airports.get(id)?.city || state.airports.get(id)?.name || id;
  const node = id => period()?.nodes?.find(n => String(n.id) === id);
  const finiteCoords = a => a && a.lat !== null && a.lon !== null && Number.isFinite(Number(a.lat)) && Number.isFinite(Number(a.lon));
  const airportPoint = a => [Number(a.lat), Number(a.lon) > 0 ? Number(a.lon) - 360 : Number(a.lon)];
  const comparablePairs = p => (p?.pairs || []).filter(x => Number.isFinite(x.rank_comparable)).slice().sort((a,b) => a.rank_comparable-b.rank_comparable || (a.a_id ?? 0)-(b.a_id ?? 0) || (a.b_id ?? 0)-(b.b_id ?? 0));

  async function init() {
    bindControls();
    try {
      const embedded=document.getElementById('atlas-world-data');
      if(embedded)state.geography=JSON.parse(embedded.textContent);
      else {const response=await fetch('data/world.geojson');if(response.ok)state.geography=await response.json();}
    } catch (_) { /* La red sigue disponible aunque falte el mapa base local. */ }
    try {
      const embedded=document.getElementById('atlas-network-data');
      let data;
      if(embedded)data=JSON.parse(embedded.textContent);
      else {const response=await fetch('data/network.json',{cache:'no-cache'});if(!response.ok)throw new Error(`No se encontró el archivo de resultados (HTTP ${response.status}).`);data=await response.json();}
      if (!Array.isArray(data.airports) || !data.periods) throw new Error('El archivo de resultados no tiene la estructura esperada.');
      state.data = data;
      try{
        const embeddedInteractive=document.getElementById('atlas-interactive-data');
        if(embeddedInteractive)state.interactive=JSON.parse(embeddedInteractive.textContent);
        else{const response=await fetch('data/interactive.json',{cache:'no-cache'});if(response.ok)state.interactive=await response.json();}
      }catch(_){state.interactive=null;}
      state.model=new window.CargoData.ExplorerData(data,state.interactive);
      state.airports = new Map(data.airports.map(a => [String(a.id),a]));
      for (const [key,p] of Object.entries(data.periods)) state.pairMaps.set(key,new Map((p.pairs || []).map(x => [pairKey(x.a,x.b),x])));
      const options = data.airports.slice().sort((a,b)=>String(a.id).localeCompare(String(b.id))).map(a=>`<option value="${esc(a.id)}">${esc(a.id)} · ${esc(a.city || a.name || '')} · ID ${esc(a.airport_id ?? '')}</option>`).join('');
      $('airport-a').innerHTML = '<option value="">Seleccionar aeropuerto…</option>' + options;
      $('airport-b').innerHTML = '<option value="">Seleccionar aeropuerto…</option>' + options;
      setupMap();
      render();
      const missing = data.airports.filter(a=>!finiteCoords(a)).length;
      if (missing) setStatus(`${missing} aeropuerto(s) sin coordenadas disponibles. Sus resultados se conservan en las tablas.`,true);
      else if (!(data.periods.annual?.pairs?.length)) setStatus('La red está disponible. Los resultados de las simulaciones aparecerán cuando se complete su cálculo.');
      else if (!state.tileFailures) $('status').classList.add('hidden');
    } catch (error) {
      setStatus('Los resultados todavía no están disponibles. Ejecuta el notebook y exporta sus resultados para activar el explorador. ' + error.message,true);
      $('ranking-body').innerHTML = '<tr><td colspan="5" class="empty-cell">No hay resultados cargados. No se muestran datos de ejemplo.</td></tr>';
      setupMap();
      renderComparison();
      $('download').disabled = true;
    }
  }
  function setStatus(message,error=false) { $('status').textContent=message; $('status').className='status'+(error?' error':''); }
function bindControls() {
    document.querySelectorAll('[data-period]').forEach(button=>button.addEventListener('click',()=>setPeriod(button.dataset.period)));
    $('airport-a').addEventListener('change',e=>selectPair(e.target.value,state.b===e.target.value?'':state.b));
    $('airport-b').addEventListener('change',e=>selectPair(state.a,e.target.value===state.a?'':e.target.value));
    $('clear-selection').addEventListener('click',()=>selectPair('',''));
    $('simulate').addEventListener('change',e=>{stopPlay();state.simulate=e.target.checked;state.animateFailure=state.simulate;render();});
    $('node-color').addEventListener('change',e=>setNodeColor(e.target.value));
    $('selection-detail').addEventListener('click',e=>{if(e.target.closest('#play-failure'))playFailure();if(e.target.closest('#stop-failure'))stopPlay(true);});
    $('route-mode').addEventListener('change',e=>{state.routeMode=e.target.value;renderMap();});
    $('discarded-routes').addEventListener('change',e=>{state.discarded=e.target.checked;renderMap();});
    $('reset-map').addEventListener('click',()=>{if(state.map)fitMap();});
    $('pair-search').addEventListener('input',renderRanking);
    $('rank-limit').addEventListener('change',renderRanking);
    $('rank-mode').addEventListener('change',e=>{state.rankMode=e.target.value;renderRanking();});
    $('network-rule').addEventListener('change',e=>setScenario(e.target.value,'common'));
    $('index-mode').addEventListener('change',e=>setScenario(state.variant,e.target.value));
    $('reset-view').addEventListener('click',resetView);
    $('download').addEventListener('click',downloadRanking);
    $('download-card').addEventListener('click',downloadCard);
    document.querySelectorAll('[data-example-a]').forEach(button=>button.addEventListener('click',()=>{
      clearMapOverlay(false);state.period='annual';state.variant='base';state.indexMode='own';
      state.rankMode=button.dataset.exampleA==='MEM'?'damage':'synergy';$('rank-mode').value=state.rankMode;
      state.a='';state.b='';state.simulate=false;
      selectPair(button.dataset.exampleA,button.dataset.exampleB||'');
    }));
    $('ranking-body').addEventListener('click',e=>{const b=e.target.closest('[data-pair-a]');if(b){selectPair(b.dataset.pairA,b.dataset.pairB);$('explorador').scrollIntoView({behavior:'smooth'});}});
  }
function selectPair(a,b) {
    if(!state.data)return;
    a=String(a||'');b=String(b||'');
    state.a=state.airports.has(a)?a:'';
    state.b=state.airports.has(b)&&b!==state.a?b:'';
    $('airport-a').value=state.a;$('airport-b').value=state.b;
    for(const option of $('airport-b').options)option.disabled=Boolean(state.a&&option.value===state.a);
    stopPlay();
    if(!state.a&&!state.b)state.simulate=false;
    render();
  }
  /* Nodos retirados en la vista: durante la reproducción paso a paso se retira primero A y después B. */
  function removedNodes(){
    const selection=[state.a,state.b].filter(Boolean);
    if(state.playStep!==null)return selection.slice(0,state.playStep===1?1:state.playStep>=2?2:0);
    return state.simulate?selection:[];
  }
  function stopPlay(rerender=false){
    for(const t of state.playTimers)clearTimeout(t);
    state.playTimers=[];
    if(state.playStep!==null){state.playStep=null;if(rerender)render();}
  }
  /* Simulación guiada con valores precalculados: red intacta → sin A → sin A y B → comparación con la suma. */
  function playFailure(){
    if(!state.a||!state.b||period()?.analysisAvailable===false)return;
    stopPlay();
    state.simulate=true;$('simulate').checked=true;
    const delay=reducedMotion()?0:1400;
    const steps=[0,1,2,3];
    steps.forEach((step,i)=>state.playTimers.push(setTimeout(()=>{state.playStep=step;state.animateFailure=step>0;render();},i*delay)));
  }
  function nodeColorFor(id){
    const mode=state.nodeColor;
    if(mode==='none'||!state.exploration||state.mapOverlay)return null;
    const b=state.exploration.networks?.[state.period]?.[state.variant];if(!b)return null;
    const index=state.exploration.metadata.codes.indexOf(id);if(index<0)return null;
    if(mode.startsWith('centrality:')){
      const name=mode.slice(11),ranks=b.centrality_ranks?.[name];if(!ranks)return null;
      const t=1-(ranks[index]-1)/Math.max(1,ranks.length-1);
      const mix=(a,c)=>Math.round(a+(c-a)*t);
      return {fill:`rgb(${mix(214,6)},${mix(232,79)},${mix(236,87)})`,stroke:t>.6?'#eff9f8':'#6d8690',title:(state.exploration.metadata.centrality_labels[name]||name)+' · puesto '+ranks[index]};
    }
    const block=b[mode];if(!block)return null;
    const k=block.membership?.[index];if(k==null)return null;
    const stability=block.stability?.[index];
    return {fill:COMMUNITY_PALETTE[k%COMMUNITY_PALETTE.length],stroke:'#eff9f8',title:'Comunidad '+(k+1)+(stability!=null?' · estabilidad '+Math.round(stability*100)+' %':'')};
  }
  function renderLegend(){
    const legend=$('map-legend');if(!legend)return;
    const mode=state.nodeColor,b=state.exploration?.networks?.[state.period]?.[state.variant];
    if(mode==='none'||!b||state.mapOverlay){legend.innerHTML='<span><i class="dot cyan"></i>Aeropuerto</span><span><i class="dot amber"></i>Seleccionado</span><span><i class="line"></i>Conexión de carga</span>';return;}
    if(mode.startsWith('centrality:')){const name=mode.slice(11);legend.innerHTML='<span><i class="dot" style="background:#064f57"></i>Mayor '+esc((state.exploration.metadata.centrality_labels[name]||name).toLowerCase())+'</span><span><i class="dot" style="background:#d6e8ec;border:1px solid #9bb"></i>Menor</span><span><i class="dot amber"></i>Seleccionado</span>';return;}
    const block=b[mode];legend.innerHTML=(block?.communities||[]).map(c=>'<span><i class="dot" style="background:'+COMMUNITY_PALETTE[c.id%COMMUNITY_PALETTE.length]+'"></i>Com. '+(c.id+1)+' · '+c.size+'</span>').join('')+'<span><i class="dot amber"></i>Seleccionado</span>';
  }
  function setNodeColor(mode){
    const valid=mode==='none'||mode==='communities'||/^centrality:(degree|betweenness|closeness|eigenvector)$/.test(mode);
    state.nodeColor=valid&&state.exploration?mode:'none';
    if($('node-color'))$('node-color').value=state.nodeColor;
    renderMap();notifyView();
  }
  function setExploration(data){state.exploration=data||null;if($('node-color'))$('node-color').disabled=!state.exploration;renderMap();}
  function animateGone(){
    state.animateFailure=false;
    const layers=state.goneLayers;if(!layers.length||reducedMotion()||!state.map)return;
    const start=performance.now(),duration=650;
    const frame=now=>{
      const t=Math.min(1,(now-start)/duration),ease=1-Math.pow(1-t,3);
      for(const item of layers){
        if(item.kind==='node')item.layer.setStyle({radius:item.radius*(1-ease)+2.2*ease,fillOpacity:.9-.45*ease,opacity:1-.3*ease});
        else item.layer.setStyle({opacity:item.opacity*(1-ease)+.18*ease});
      }
      if(t<1)requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }
  function selectFromMap(id) { if(!state.a || (state.a && state.b)) selectPair(id,'');else if(state.a===id)selectPair('','');else selectPair(state.a,id); }
function render() {
    const p=period();if(!p)return;
    const analysis=p.analysisAvailable!==false,selected=[state.a,state.b].filter(Boolean);
    document.querySelectorAll('[data-period]').forEach(b=>b.classList.toggle('active',b.dataset.period===state.period));
    $('period-label').textContent=titles[state.period]||state.period;
    $('network-rule').value=state.variant;$('index-mode').value=state.indexMode;
    if($('node-color')){$('node-color').disabled=Boolean(state.mapOverlay)||!state.exploration;$('node-color').value=state.nodeColor;}
    $('network-rule').disabled=Boolean(state.mapOverlay)||!state.interactive;
    $('index-mode').disabled=Boolean(state.mapOverlay)||!state.interactive?.sensitivity_calibration;
    $('simulate').disabled=!analysis||!selected.length;
    if(!analysis)state.simulate=false;
    $('simulate').checked=state.simulate;
    const canCompare=state.variant!=='base'&&!state.mapOverlay;
    $('discarded-routes').disabled=!canCompare;
    if(!canCompare)state.discarded=false;
    $('discarded-routes').checked=state.discarded;
    $('stat-pairs').textContent=analysis?fmt.format(p.pairs?.length||0):'—';
    $('stat-pairs').parentElement.querySelector('small').textContent=analysis?'Fallos simultáneos calculados':'Sin índice de fallo de aeropuertos';
    $('download').disabled=!pairs().length;
    $('download-card').disabled=!selected.length;
    $('view-context').textContent=(titles[state.period]||state.period)+' · '+p.label+' · '+p.calibration_label+(state.simulate?' · Fallo de '+selected.join(' + '):'');
    renderScenarioStats();renderMap();renderDetail();renderRanking();renderComparison();renderTrend();notifyView();
  }
  function setupMap() {
    if(!window.L) { $('map').style.display='none';$('fallback-map').style.display='block';$('map-note').textContent=state.geography?'Mapa local · Natural Earth (dominio público)':'Vista por coordenadas · mapa base no disponible';return; }
    state.map=L.map('map',{zoomControl:false,preferCanvas:true,minZoom:2,maxZoom:12,zoomSnap:.25,zoomDelta:.5}).setView([38,-101],4);
    L.control.zoom({position:'topright'}).addTo(state.map);
    if(state.geography){
      state.map.createPane('offlineBase');state.map.getPane('offlineBase').style.zIndex=150;
      state.baseLayer=L.geoJSON(state.geography,{pane:'offlineBase',style:{color:'#aabcc2',weight:.8,fillColor:'#f4f5ef',fillOpacity:1},interactive:false,attribution:'<a href="https://www.naturalearthdata.com/">Natural Earth</a> · dominio público'}).addTo(state.map);
    }
    $('map').style.background='#dceaf0';
    $('map-note').textContent='Mapa local · selecciona un aeropuerto';
    state.layers=L.layerGroup().addTo(state.map);
    fitMap();
  }
  function fitMap() {
    const locations=[...state.airports.values()].filter(finiteCoords).map(airportPoint);
    if(locations.length && state.map) state.map.fitBounds(locations,{padding:[30,35],maxZoom:4});
  }
function filterEdges(edges) {
    if(state.routeMode==='none')return [];
    let result=edges.slice();
    if(state.routeMode==='selected')return state.a||state.b?result.filter(e=>[state.a,state.b].includes(String(e.source))||[state.a,state.b].includes(String(e.target))):[];
    result.sort((a,b)=>Number(b.freight_lb)-Number(a.freight_lb));
    return state.routeMode==='top'?result.slice(0,200):result;
  }
  function visibleEdges(){return filterEdges(period()?.edges||[]);}
  function discardedEdges(){
    if(!state.discarded||state.variant==='base'||state.mapOverlay)return [];
    const keep=new Set((period()?.edges||[]).map(e=>pairKey(e.source,e.target)));
    return filterEdges((state.data?.periods?.[state.period]?.edges||[]).filter(e=>!keep.has(pairKey(e.source,e.target))));
  }
  function renderMap() {
    const selection=[state.a,state.b].filter(Boolean);
    $('map-title').textContent=state.simulate&&selection.length?'Fallo de '+selection.join(' + '):period()?.label||'Conexiones de carga';
    $('map-note').textContent=fmt.format(visibleEdges().length)+' de '+fmt.format(period()?.n_edges||0)+' conexiones visibles'+(state.discarded?' · '+fmt.format(discardedEdges().length)+' descartadas, en rojo discontinuo':'');
    if(!state.map) { renderFallback();return; }
    state.layers.clearLayers();state.goneLayers=[];renderLegend();
    const removed=removedNodes(),animate=state.animateFailure;
    const maxFreight=Math.max(1,...(period()?.nodes || []).map(n=>Number(n.freight_lb)||0));
    const edgeList=visibleEdges();const maxEdge=Math.max(1,...edgeList.map(e=>Number(e.freight_lb)||0));
    for(const e of discardedEdges()){
      const a=state.airports.get(String(e.source)),b=state.airports.get(String(e.target));if(!finiteCoords(a)||!finiteCoords(b))continue;
      const start=airportPoint(a),end=airportPoint(b);if(end[1]-start[1]>180)end[1]-=360;if(start[1]-end[1]>180)end[1]+=360;
      L.polyline([start,end],{color:'#c6675c',opacity:.5,weight:1,dashArray:'2 6',interactive:false}).addTo(state.layers);
    }
    for(const e of edgeList){
      const a=state.airports.get(String(e.source)),b=state.airports.get(String(e.target));if(!finiteCoords(a)||!finiteCoords(b))continue;
      const hit=selection.includes(String(e.source)) || selection.includes(String(e.target));
      const gone=removed.includes(String(e.source))||removed.includes(String(e.target));
      const start=airportPoint(a),end=airportPoint(b);if(end[1]-start[1]>180)end[1]-=360;if(start[1]-end[1]>180)end[1]+=360;
      const opacity=hit?.75:selection.length?.13:.29;
      const line=L.polyline([start,end],{color:gone?'#d6786c':hit?'#dc9a32':'#1594a0',opacity:gone&&!animate?.22:opacity,weight:hit?1.8:.6+1.6*Math.sqrt((Number(e.freight_lb)||0)/maxEdge),dashArray:gone?'4 5':undefined,interactive:false}).addTo(state.layers);
      if(gone)state.goneLayers.push({kind:'edge',layer:line,opacity});
    }
    for(const a of state.airports.values()){
      if(!finiteCoords(a))continue;const n=node(String(a.id)),selected=selection.includes(String(a.id)),gone=removed.includes(String(a.id));
      const radius=selected?7:3+5*Math.sqrt((Number(n?.freight_lb)||0)/maxFreight);
      const color=selected?null:nodeColorFor(String(a.id));
      const marker=L.circleMarker(airportPoint(a),{radius:gone&&!animate?2.2:radius,color:gone?'#963f37':selected?'#9b6524':color?color.stroke:'#eff9f8',weight:selected?2:1,fillColor:gone?'#cf776c':selected?'#f4b859':color?color.fill:'#108f98',fillOpacity:gone&&!animate?.45:.88}).bindTooltip(`<b>${esc(a.id)}</b> · ${esc(a.city || a.name)}<br>AirportID BTS ${esc(a.airport_id ?? '—')}<br>${fmt.format(n?.degree ?? 0)} conexiones${color?'<br>'+esc(color.title):''}${gone?' · Retirado en este escenario':''}`).on('click',()=>selectFromMap(String(a.id))).addTo(state.layers);
      if(gone)state.goneLayers.push({kind:'node',layer:marker,radius});
      if(selected)L.marker(airportPoint(a),{icon:L.divIcon({className:'',html:`<span style="display:block;margin:8px 0 0 9px;font-weight:700;color:#624117;font-size:11px;white-space:nowrap">${esc(a.id)}</span>`}),interactive:false}).addTo(state.layers);
    }
    if(animate)animateGone();
  }
  function renderFallback() {
    const svg=$('fallback-map');if(!svg || state.map)return;
    const list=[...state.airports.values()].filter(finiteCoords),coords=list.map(airportPoint);
    const minLon=Math.min(-130,...coords.map(p=>p[1]))-4,maxLon=Math.max(-65,...coords.map(p=>p[1]))+4,minLat=Math.min(22,...coords.map(p=>p[0]))-3,maxLat=Math.max(50,...coords.map(p=>p[0]))+3;
    const project=a=>{const [lat,lon]=airportPoint(a);return [35+(lon-minLon)/(maxLon-minLon)*930,525-(lat-minLat)/(maxLat-minLat)*490];};
    const selected=[state.a,state.b].filter(Boolean);
    let markup='<rect width="1000" height="560" fill="#e5ecee"/>';
    for(let lon=Math.ceil(minLon/20)*20;lon<maxLon;lon+=20){const x=35+(lon-minLon)/(maxLon-minLon)*930;markup+=`<path d="M${x} 25V525" stroke="#d0dde2"/><text x="${x+5}" y="45" fill="#8a9fa9" font-size="11">${lon}°</text>`;}
    for(let lat=Math.ceil(minLat/10)*10;lat<maxLat;lat+=10){const y=525-(lat-minLat)/(maxLat-minLat)*490;markup+=`<path d="M35 ${y}H965" stroke="#d0dde2"/><text x="38" y="${y-5}" fill="#8a9fa9" font-size="11">${lat}°</text>`;}
    markup+=geographyPaths(minLon,maxLon,minLat,maxLat);
    markup+='<text x="500" y="300" text-anchor="middle" font-size="17" letter-spacing="6" fill="#a2b6bd">AMÉRICA DEL NORTE</text>';
    for(const e of discardedEdges()){
      const a=state.airports.get(String(e.source)),b=state.airports.get(String(e.target));if(!finiteCoords(a)||!finiteCoords(b))continue;
      const [x1,y1]=project(a),[x2,y2]=project(b);
      markup+='<line x1="'+x1+'" y1="'+y1+'" x2="'+x2+'" y2="'+y2+'" stroke="#c6675c" opacity=".5" stroke-width="1" stroke-dasharray="2 6"/>';
    }
    for(const e of visibleEdges()){const a=state.airports.get(String(e.source)),b=state.airports.get(String(e.target));if(!finiteCoords(a)||!finiteCoords(b))continue;const [x1,y1]=project(a),[x2,y2]=project(b);const hit=selected.includes(String(e.source))||selected.includes(String(e.target));markup+=`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${hit?'#d99936':'#2897a2'}" opacity="${hit?.75:.27}" stroke-width="${hit?1.7:1}" ${state.simulate&&hit?'stroke-dasharray="4 5"':''}/>`;}
    const removed=removedNodes();
    for(const a of list){const [x,y]=project(a),chosen=selected.includes(String(a.id)),gone=removed.includes(String(a.id)),color=chosen?null:nodeColorFor(String(a.id));markup+=`<g class="svg-node" tabindex="0" role="button" data-airport="${esc(a.id)}" aria-label="Seleccionar ${esc(a.id)}"><title>${esc(a.id)} · ${esc(a.city || a.name)}</title><circle cx="${x}" cy="${y}" r="${chosen?7:4}" fill="${gone?'#cf776c':chosen?'#e6ac4e':color?color.fill:'#188e98'}" stroke="white"/>${chosen?`<text x="${x+10}" y="${y-8}" font-size="13" fill="#785019">${esc(a.id)}</text>`:''}</g>`;}
    svg.innerHTML=markup;
    svg.querySelectorAll('[data-airport]').forEach(el=>{el.addEventListener('click',()=>selectFromMap(el.dataset.airport));el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectFromMap(el.dataset.airport);}});});
  }
  function geographyPaths(minLon,maxLon,minLat,maxLat) {
    if(!state.geography)return '';
    let html='<defs><clipPath id="geo-clip"><rect x="35" y="25" width="930" height="500"/></clipPath></defs><g clip-path="url(#geo-clip)">';
    for(const f of state.geography.features || []){
      if(!['North America','South America'].includes(f.properties?.CONTINENT))continue;
      const polygons=f.geometry?.type==='MultiPolygon'?f.geometry.coordinates:f.geometry?.type==='Polygon'?[f.geometry.coordinates]:[];
      for(const polygon of polygons){
        const points=polygon[0].map(([lon,lat])=>{if(lon>0)lon-=360;return [35+(lon-minLon)/(maxLon-minLon)*930,525-(lat-minLat)/(maxLat-minLat)*490];});
        const d=points.map((p,i)=>(i?'L':'M')+p.join(',')).join('')+'Z';
        html+=`<path d="${d}" fill="#f3f5f3" stroke="#b4c7ce" stroke-width=".8"/>`;
      }
    }
    return html+'</g>';
  }
  function renderScenarioStats() {
    const p=period();if(!p)return;
    const selected=removedNodes(),active=p.analysisAvailable!==false&&state.simulate&&selected.length;
    const impact=selected.length===2?selectedPair():selected.length===1?node(selected[0]):null;
    const remaining=(p.edges || []).filter(e=>!selected.includes(String(e.source))&&!selected.includes(String(e.target))).length;
    for(const [id,label] of [['stat-nodes','AEROPUERTOS'],['stat-edges','CONEXIONES'],['stat-efficiency','EFICIENCIA GLOBAL']]) $(id).parentElement.querySelector('span').textContent=label+(active?' · TRAS EL FALLO':' · RED MOSTRADA');
    $('stat-nodes').textContent=fmt.format((p.n_nodes ?? 100)-(active?selected.length:0));
    $('stat-edges').textContent=fmt.format(active?remaining:p.n_edges);
    $('stat-efficiency').textContent=decimal(p.metrics?.global_efficiency-(active&&Number.isFinite(impact?.impact_global)?impact.impact_global:0),4);
    $('stat-nodes').parentElement.querySelector('small').textContent=active?'Nodos que permanecen en el escenario':state.mapOverlay?'Universo fijo de la capa':'Mismo universo de análisis';
    $('stat-edges').parentElement.querySelector('small').textContent=active?'Conexiones restantes tras el fallo':'Conexiones de la regla o capa actual';
    $('stat-efficiency').parentElement.querySelector('small').textContent=active?'Valor tras retirar los nodos':'Valor antes de fallos de aeropuertos';
  }
  function impactTable(impact,title) {
    if(!impact)return '';
    let html=`<h4 class="impact-header">${esc(title)}</h4><div class="impact-table"><table><thead><tr><th>Métrica</th><th>Antes</th><th>Después</th><th>Impacto</th></tr></thead><tbody>`;
    for(const [short,metric,label] of [['global','global_efficiency','Global'],['local','local_efficiency','Local'],['natural','natural_connectivity','Natural']]){
      const before=period()?.metrics?.[metric],loss=impact['impact_'+short];
      const after=Number.isFinite(before)&&Number.isFinite(loss)?before-loss:null;
      html+=`<tr><td>${label}</td><td>${decimal(before,4)}</td><td>${decimal(after,4)}</td><td>${decimal(loss,4)}</td></tr>`;
    }
    return html+'</tbody></table></div>';
  }
  function metricRow(label,value) {return `<div class="metric-row"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;}
  /* Simulación guiada: barras con los valores precalculados de la red intacta, sin A, sin A y B,
     y la expectativa aditiva (sin A − sin B). La diferencia con el valor conjunto es la sinergia. */
  function playPanel(p){
    if(period()?.analysisAvailable===false)return '';
    const step=state.playStep,playing=step!==null;
    const captions=['Red intacta: valores antes de cualquier fallo.','Paso 1 · se retira '+state.a+': cada métrica cae su impacto individual.','Paso 2 · se retira también '+state.b+': valor conjunto frente a la suma de los dos fallos.','Comparación: la marca ◇ es lo que se esperaría sumando los dos fallos; la diferencia con la barra es la sinergia.'];
    let html='<div class="failure-play"><div class="failure-play-head"><h4 class="impact-header">Simulación paso a paso</h4>'+(playing?'<button type="button" id="stop-failure" class="quiet-button">■ Detener</button>':'<button type="button" id="play-failure" class="quiet-button">▶ Reproducir el fallo</button>')+'</div>';
    html+='<p class="detail-caption">'+esc(playing?captions[step]:'Retira primero '+state.a+' y después '+state.b+' sobre el mapa y las métricas, con los valores calculados en el notebook.')+'</p>';
    const width=180,x0=92;
    let svg='<svg viewBox="0 0 340 118" class="failure-chart" role="img" aria-label="Métricas antes y después del fallo">';
    [['global','global_efficiency','Ef. global'],['local','local_efficiency','Ef. local'],['natural','natural_connectivity','Con. natural']].forEach(([short,metric,label],i)=>{
      const before=Number(period()?.metrics?.[metric]),afterA=before-Number(p['single_a_'+short]),afterB=before-Number(p['single_b_'+short]),joint=before-Number(p['impact_'+short]),additive=before-Number(p['single_a_'+short])-Number(p['single_b_'+short]);
      // Escala ampliada alrededor de los valores: los impactos son pequeños frente al nivel de la métrica.
      const values=[before,afterA,afterB,joint,additive].filter(Number.isFinite),vmin=Math.min(...values),vmax=Math.max(...values),span=(vmax-vmin)||Math.abs(vmax)||1,lo=vmin-span*.6,hi=vmax+span*.1,scale=v=>x0+(v-lo)/(hi-lo)*width;
      const current=!playing||step===0?before:step===1?afterA:joint;
      const y=14+i*34;
      svg+=`<text x="${x0-6}" y="${y+13}" text-anchor="end" class="failure-label">${label}</text>`;
      svg+=`<rect x="${x0}" y="${y}" width="${Math.max(0,scale(before)-x0).toFixed(1)}" height="18" fill="#1d3449"/>`;
      svg+=`<rect x="${x0}" y="${y}" width="${Math.max(0,scale(current)-x0).toFixed(1)}" height="18" fill="${!playing||step===0?'#50d6ce':step===1?'#f4b859':'#e07a6c'}" class="failure-bar"/>`;
      if(playing&&step>=3)svg+=`<path d="M${scale(additive).toFixed(1)} ${y-3}l4 6l-4 6l-4-6z" fill="#eef4f7" stroke="#0c1a2b" stroke-width=".8"><title>Esperado si los impactos se sumaran: ${decimal(additive,4)}</title></path>`;
      svg+=`<text x="${x0+width+6}" y="${y+13}" class="failure-value">${decimal(current,3)}</text>`;
    });
    svg+='</svg>';
    if(playing&&step>=3)html+=svg+'<p class="detail-caption">Sinergia por métrica: global '+decimal(p.synergy_global,5)+' · local '+decimal(p.synergy_local,5)+' · natural '+decimal(p.synergy_natural,4)+'. Positiva significa que el fallo conjunto daña más que la suma de los fallos separados.</p>';
    else html+=svg;
    return html+'<p class="detail-caption">Escala ampliada: cada barra empieza cerca del valor mínimo para que se vean las diferencias; las cifras indican el valor real.</p></div>';
  }

  function traceTable(p) {
    const calibration=period()?.composite;
    if(!p||!calibration)return '';
    let html='<details class="pair-trace"><summary>Ver cálculo paso a paso</summary><p class="detail-caption">A = '+esc(p.a)+'; B = '+esc(p.b)+'. Sinergia = impacto conjunto − impacto de A − impacto de B.</p>';
    let total=0;
    for(const [j,short,label] of [[0,'global','Eficiencia global'],[1,'local','Eficiencia local'],[2,'natural','Conectividad natural']]){
      const scale=calibration.scales?.[j],weight=calibration.weights?.[j],synergy=p['synergy_'+short];
      const contribution=Number.isFinite(scale)&&scale>0&&Number.isFinite(weight)?synergy/scale*weight:0;
      total+=contribution;
      html+='<div class="trace-block"><h5>'+label+'</h5><p>'+decimal(p['impact_'+short],6)+' − '+decimal(p['single_a_'+short],6)+' − '+decimal(p['single_b_'+short],6)+' = <strong>'+decimal(synergy,6)+'</strong></p><p class="detail-caption">Sinergia / '+decimal(scale,6)+' × peso '+decimal(weight,4)+' = aporte <strong>'+decimal(contribution,6)+'</strong></p></div>';
    }
    return html+'<p class="trace-total">Suma de aportes: <strong>'+decimal(total,6)+'</strong></p><p class="detail-caption">'+esc(period().calibration_label)+'. El índice no es un porcentaje de carga perdida.</p></details>';
  }
  function renderDetail() {
    if(!state.a && !state.b){$('selection-detail').innerHTML='<div class="empty-selection">◎<h3>Empieza por un aeropuerto</h3><p>También puedes seleccionar una pareja desde el ranking inferior.</p></div>';return;}
    if(state.a && state.b){const p=selectedPair();let html=`<h3 class="selection-title">${esc(state.a)} <span style="color:#7f93a7;font-weight:300">+</span> ${esc(state.b)}</h3><p class="selection-city">${esc(city(state.a))} · ${esc(city(state.b))}<br>AirportID BTS ${esc(state.airports.get(state.a)?.airport_id ?? '—')} · ${esc(state.airports.get(state.b)?.airport_id ?? '—')}</p>`;
      if(!p){$('selection-detail').innerHTML=html+'<p class="detail-caption">'+(state.mapOverlay?'Esta capa muestra conexiones del operador. No se han calculado índices de fallo de parejas para la capa.':'No hay resultados para esta pareja en el escenario seleccionado.')+'</p>';return;}
      html+=`<div class="score-hero"><strong>${decimal(p.score)}</strong><small>${esc(period().calibration_label)}</small></div>`;
      html+=metricRow('Puesto en el período',p.rank?`${fmt.format(p.rank)} de ${fmt.format(pairs().length)}`:'—')+metricRow('Conexión directa',p.direct?'Sí':'No');
      html+=impactTable(p,'Impacto de retirar ambos aeropuertos')+playPanel(p)+traceTable(p);
      html+='<p class="detail-caption">Impacto = valor de la red original − valor tras retirar ambos aeropuertos. Cada métrica conserva su propia escala.</p>';
      $('selection-detail').innerHTML=html;
    }else{const id=state.a || state.b,a=state.airports.get(id),n=node(id);let html=`<h3 class="selection-title">${esc(id)}</h3><p class="selection-city">${esc(a?.name || city(id))}</p>`;
      html+=metricRow('AirportID BTS',esc(a?.airport_id ?? '—'))+metricRow('Conexiones (grado)',fmt.format(n?.degree ?? 0))+metricRow('Centralidad de grado',decimal(n?.degree_centrality))+metricRow('Intermediación',decimal(n?.betweenness,4))+metricRow('Carga de entrada + salida',n?.freight_lb!=null?`${decimal(n.freight_lb/1e6,1)} M lb`:'—');
      html+='<p class="detail-caption">La carga sirve para describir el aeropuerto. Las métricas de robustez se calculan sobre conexiones binarias.</p>';
      if(period()?.analysisAvailable!==false)html+=impactTable(n,'Impacto de retirar este aeropuerto');
      html+='<p class="detail-caption">'+esc(period()?.freight_scope||'')+'</p>';
      $('selection-detail').innerHTML=html;
    }
  }
  function renderRanking() {
    const search=$('pair-search').value.trim().toLowerCase(),limit=Number($('rank-limit').value),damage=state.rankMode==='damage';
    let rows=pairs().slice().sort((a,b)=>damage?Number(b.impact_global)-Number(a.impact_global)||a.a_id-b.a_id||a.b_id-b.b_id:(a.rank ?? Infinity)-(b.rank ?? Infinity)||a.a_id-b.a_id||a.b_id-b.b_id);
    rows=rows.map((p,i)=>({...p,displayRank:damage?i+1:p.rank,displayValue:damage?p.impact_global:p.score}));
    $('ranking-title').textContent=damage?'Parejas con mayor daño global conjunto':'Parejas con mayor sinergia';
    $('ranking-value-heading').textContent=damage?'Impacto en eficiencia global':'Sinergia compuesta';
    if(search)rows=rows.filter(p=>[p.a,p.b,city(p.a),city(p.b)].some(x=>String(x).toLowerCase().includes(search)));
    rows=rows.slice(0,limit);
    if(!rows.length){$('ranking-body').innerHTML='<tr><td colspan="5" class="empty-cell">'+(search?'No se encontraron parejas para esta búsqueda.':state.mapOverlay?'No hay índices de fallo de aeropuertos calculados para esta capa.':'No hay resultados de simulación para este período.')+'</td></tr>';return;}
    const max=Math.max(1e-12,...rows.map(p=>Math.abs(p.displayValue)||0));
    $('ranking-body').innerHTML=rows.map(p=>`<tr class="${pairKey(p.a,p.b)===pairKey(state.a,state.b)?'selected':''}"><td>${fmt.format(p.displayRank || 0)}</td><td><span class="pair-code">${esc(p.a)} <span style="color:#637d93">↔</span> ${esc(p.b)}</span><span class="pair-cities">${esc(city(p.a))} · ${esc(city(p.b))} · ID ${esc(p.a_id ?? '')}–${esc(p.b_id ?? '')}</span></td><td><div class="score-cell"><span>${decimal(p.displayValue,damage?5:3)}</span><i class="score-track"><i style="width:${Math.min(100,Math.abs(p.displayValue)/max*100)}%"></i></i></div></td><td><span class="tag ${p.direct?'':'negative'}">${p.direct?'Con conexión':'Sin conexión'}</span></td><td><button class="explore-button" data-pair-a="${esc(p.a)}" data-pair-b="${esc(p.b)}" aria-label="Explorar pareja ${esc(p.a)} y ${esc(p.b)}">Explorar ↗</button></td></tr>`).join('');
  }
function quarterNetworks(){
    if(!state.model)return [];
    return ['T1','T2','T3','T4'].map(q=>state.model.network(q,state.variant,'common'));
  }
  function renderComparison(){
    if(state.mapOverlay){state.comparisonKey=null;$('overlap-chart').innerHTML='<p class="chart-empty">Restaura una red agregada para comparar sus trimestres.</p>';$('spearman-summary').innerHTML='';return;}
    if(!state.model){$('overlap-chart').innerHTML='';$('spearman-summary').innerHTML='';return;}
    const cacheKey=state.variant+'|'+Boolean(state.interactive?.sensitivity_calibration);
    if(state.comparisonKey===cacheKey)return;state.comparisonKey=cacheKey;
    const quarters=['T1','T2','T3','T4'],nets=quarterNetworks();
    const top=nets.map(n=>n.pairs.slice().sort((a,b)=>a.rank-b.rank||a.a_id-b.a_id||a.b_id-b.b_id).slice(0,20));
    let html='<div class="heatmap"><div></div>'+quarters.map(q=>'<div class="heat-label">'+q+'</div>').join('');
    for(let i=0;i<4;i++){
      html+='<div class="heat-label">'+quarters[i]+'</div>';
      for(let j=0;j<4;j++){
        const bs=new Set(top[j].map(p=>pairKey(p.a,p.b))),shared=top[i].filter(p=>bs.has(pairKey(p.a,p.b))).length,overlap=shared/20;
        html+='<div class="heat-cell" style="background:rgba(80,214,206,'+(.08+overlap*.82)+');color:'+(overlap>.55?'#092d37':'#bdeae6')+'" title="'+quarters[i]+' y '+quarters[j]+': '+shared+' de 20 parejas">'+Math.round(overlap*100)+'%</div>';
      }
    }
    $('overlap-chart').innerHTML=html+'</div><p class="detail-caption">'+esc(nets[0].label)+' · escala común entre reglas y períodos.</p>';
    let summary='';
    for(let i=0;i<3;i++){const rho=spearman(nets[i].pairs,nets[i+1].pairs);if(rho!==null)summary+='<span>Spearman '+quarters[i]+'–'+quarters[i+1]+': <strong>'+decimal(rho)+'</strong></span>';}
    $('spearman-summary').innerHTML=summary;
  }
  function averageRanks(values){const sorted=values.map((v,i)=>({v,i})).sort((a,b)=>a.v-b.v),ranks=[];for(let i=0;i<sorted.length;){let j=i+1;while(j<sorted.length&&sorted[j].v===sorted[i].v)j++;const rank=(i+1+j)/2;for(let k=i;k<j;k++)ranks[sorted[k].i]=rank;i=j;}return ranks;}
function spearman(a,b){
    const bm=new Map(b.map(p=>[pairKey(p.a,p.b),p.rank])),matches=a.filter(p=>bm.has(pairKey(p.a,p.b)));
    if(matches.length<3)return null;
    const x=matches.map(p=>p.rank),y=matches.map(p=>bm.get(pairKey(p.a,p.b))),mx=x.reduce((s,v)=>s+v,0)/x.length,my=y.reduce((s,v)=>s+v,0)/y.length;
    let cov=0,vx=0,vy=0;for(let i=0;i<x.length;i++){cov+=(x[i]-mx)*(y[i]-my);vx+=(x[i]-mx)**2;vy+=(y[i]-my)**2;}
    return vx&&vy?cov/Math.sqrt(vx*vy):null;
  }
  function renderTrend() {
    if(state.mapOverlay){$('trend-title').textContent='Trayectoria trimestral';$('trend-subtitle').textContent='Las capas por operador se analizaron solo para el año completo.';$('trend-chart').innerHTML='<p class="chart-empty">Selecciona una regla de red agregada.</p>';$('trend-values').innerHTML='';return;}
    if(!state.a||!state.b){$('trend-title').textContent='Trayectoria de una pareja';$('trend-subtitle').textContent='Selecciona una pareja en el mapa o en el ranking.';$('trend-chart').innerHTML='<p class="chart-empty">Los cuatro trimestres, en una misma escala.</p>';$('trend-values').innerHTML='';return;}
    $('trend-title').textContent=`${state.a} + ${state.b} · evolución trimestral`;$('trend-subtitle').textContent=(state.model?.network('annual',state.variant,'common').label||'')+' · pesos y normalización comunes entre reglas y períodos.';
    const quarters=['T1','T2','T3','T4'],ps=quarterNetworks().map(n=>n.pairMap.get(pairKey(state.a,state.b))),vals=ps.map(p=>Number.isFinite(p?.score)?p.score:null),valid=vals.filter(v=>v!==null);
    if(!valid.length){$('trend-chart').innerHTML='<p class="chart-empty">Aún no hay resultados comparables para esta pareja.</p>';$('trend-values').innerHTML='';return;}
    const low=Math.min(0,...valid),high=Math.max(.01,...valid),pad=(high-low)*.15,min=low-pad,max=high+pad,x=i=>65+i*125,y=v=>178-(v-min)/(max-min)*145;
    let svg='<svg viewBox="0 0 500 220" role="img" aria-label="Evolución del índice compuesto de sinergia de la pareja seleccionada">';
    for(let i=0;i<4;i++){const v=min+(max-min)*i/3,py=y(v);svg+=`<path d="M55 ${py}H455" stroke="#2b4058" stroke-dasharray="3 4"/><text x="45" y="${py+4}" text-anchor="end" fill="#8da3b7" font-size="10">${decimal(v,2)}</text>`;}
    for(let i=0;i<3;i++)if(vals[i]!==null&&vals[i+1]!==null)svg+=`<path d="M${x(i)} ${y(vals[i])}L${x(i+1)} ${y(vals[i+1])}" stroke="#50d6ce" stroke-width="2.5" fill="none"/>`;
    vals.forEach((v,i)=>{svg+=`<text x="${x(i)}" y="205" text-anchor="middle" fill="#93a6ba" font-size="12">${quarters[i]}</text>`;if(v!==null)svg+=`<circle cx="${x(i)}" cy="${y(v)}" r="5" fill="#50d6ce" stroke="#112238" stroke-width="2"><title>${quarters[i]}: ${decimal(v,4)}</title></circle>`;});
    $('trend-chart').innerHTML=svg+'</svg>';
    $('trend-values').innerHTML=ps.map((p,i)=>`<div>${quarters[i]}<strong>${decimal(p?.score)}</strong><small>${p?.rank?'Puesto '+fmt.format(p.rank):'Sin resultado'}</small></div>`).join('');
  }

  function downloadText(text,filename,type){
    const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');
    a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function downloadRanking(){
    if(!pairs().length)return;
    const damage=state.rankMode==='damage';
    const ordered=pairs().slice().sort((a,b)=>damage?b.impact_global-a.impact_global||a.a_id-b.a_id||a.b_id-b.b_id:a.rank-b.rank||a.a_id-b.a_id||a.b_id-b.b_id);
    const columns=['period','variant','index_mode','ranking_order','position','rank_synergy','a','b','score','direct','impact_global','impact_local','impact_natural','synergy_global','synergy_local','synergy_natural'];
    const lines=[columns.join(',')];
    ordered.forEach((p,index)=>{
      const row={...p,period:state.period,variant:state.variant,index_mode:state.indexMode,ranking_order:state.rankMode,position:index+1,rank_synergy:p.rank};
      lines.push(columns.map(k=>JSON.stringify(row[k]??'')).join(','));
    });
    downloadText(String.fromCharCode(65279)+lines.join(String.fromCharCode(10)),'ranking_2025_'+state.period+'_'+state.variant+'_'+state.indexMode+'_'+state.rankMode+'.csv','text/csv;charset=utf-8');
  }
  function downloadCard(){
    const selected=[state.a,state.b].filter(Boolean);if(!selected.length)return;
    const n=period(),title=selected.join(' + ')+' · '+(titles[state.period]||state.period);
    const params={year:2025,period:state.period,rule:state.mapOverlay?'operator':state.variant,index_mode:state.mapOverlay?'not_available':state.indexMode,
      network:n.label,calibration:n.calibration_label,selected_airports:selected,
      failure_shown:state.simulate,source_sha256:state.interactive?.metadata?.source_sha256||'No disponible en esta copia',
      scope:'Vulnerabilidad estructural; no estima pérdidas operativas, probabilidades ni capacidad de desvío.'};
    const body=$('selection-detail').innerHTML.replace(/<details([^>]*)>/g,'<details$1 open>');
    const config=Object.entries(params).map(([k,v])=>'<tr><th>'+esc(k)+'</th><td>'+esc(Array.isArray(v)?v.join(', '):v)+'</td></tr>').join('');
    const html='<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>body{font:15px/1.6 system-ui,sans-serif;color:#163341;max-width:940px;margin:35px auto;padding:0 22px}h1,h2,h3,h4,h5{line-height:1.25}table{border-collapse:collapse;width:100%;font-size:13px}td,th{text-align:left;padding:9px;border:1px solid #c6d5db;overflow-wrap:anywhere}th{background:#edf4f5}.metric-row{display:flex;justify-content:space-between;gap:25px;border-bottom:1px solid #dce5e9;padding:6px 0}.score-hero strong{font-size:34px;display:block;color:#087f8c}.score-hero small{display:block}.detail-caption,small{color:#526b77;font-size:13px}.trace-block{border-top:1px solid #c6d5db;padding:8px 0}.trace-total{background:#e3f2ef;padding:12px}details{margin:18px 0}summary{font-weight:600}a{color:#087f8c}.source{margin-top:35px;border-top:1px solid #c6d5db;padding-top:18px}th{width:27%}@media print{body{margin:0;max-width:none}details{break-inside:avoid}}</style></head><body><h1>Atlas Cargo · ficha de análisis</h1><p>'+esc(title)+'</p><p><strong>'+esc(n.label)+' · '+esc(n.calibration_label)+'</strong></p>'+body+'<h2>Parámetros de la vista</h2><table>'+config+'</table><p class="source">Datos: <a href="https://transtats.bts.gov/Fields.asp?gnoyr_VQ=GEE">BTS T-100 Domestic Segment, 2025</a>. Metodología adaptada de <a href="https://doi.org/10.1038/s41598-026-38153-y">Zhou y Razavi (2026)</a>. ******** · ********.</p></body></html>';
    downloadText(html,'ficha_'+selected.join('_')+'_2025_'+state.period+'_'+(state.mapOverlay?'operator':state.variant)+'_'+state.indexMode+'.html','text/html;charset=utf-8');
  }
  function notifyView(){document.dispatchEvent(new CustomEvent('atlas:viewchange',{detail:{period:state.period,variant:state.variant,indexMode:state.indexMode,a:state.a,b:state.b}}));}
  function clearMapOverlay(restore=false){
    const origin=state.overlayOrigin;
    state.mapOverlay=null;state.overlayNetwork=null;state.overlayOrigin=null;
    if(restore&&origin){state.period=origin.period;state.variant=origin.variant;state.indexMode=origin.indexMode;}
  }
  function setPeriod(value){
    if(!state.data?.periods?.[value])return;
    const origin=state.overlayOrigin;
    clearMapOverlay(false);stopPlay();
    if(origin){state.variant=origin.variant;state.indexMode=origin.indexMode;}
    state.period=value;render();
  }
  function setScenario(variant,mode='common'){
    if(!['base','half_months','all_months','min_monthly_freight'].includes(variant)||!['own','common'].includes(mode))return;
    if(variant!=='base'&&!state.interactive?.periods?.[state.period]?.[variant]){
      setStatus('No se incluyen los datos completos de esa regla en esta copia.',true);return;
    }
    clearMapOverlay(false);stopPlay();state.variant=variant;
    state.indexMode=mode==='common'&&state.interactive?.sensitivity_calibration?'common':'own';
    render();
  }
  function setMapOverlay(overlay){
    if(!state.model)return;
    if(!overlay){clearMapOverlay(true);render();return;}
    if(!state.overlayOrigin)state.overlayOrigin={period:state.period,variant:state.variant,indexMode:state.indexMode};
    state.period='annual';state.variant='base';state.indexMode='own';state.simulate=false;state.discarded=false;stopPlay();
    state.mapOverlay=overlay;state.overlayNetwork=state.model.overlay(overlay);
    render();
  }
  function resetView(){
    clearMapOverlay(false);state.period='annual';state.variant='base';state.indexMode='own';state.simulate=false;state.discarded=false;
    state.routeMode='top';state.rankMode='synergy';state.a='';state.b='';state.nodeColor='none';stopPlay();
    $('airport-a').value='';$('airport-b').value='';if($('node-color'))$('node-color').value='none';
    for(const option of $('airport-b').options)option.disabled=false;
    $('route-mode').value='top';$('rank-mode').value='synergy';$('rank-limit').value='20';$('pair-search').value='';
    if($('stability-min'))$('stability-min').value='4';
    if($('stability-search'))$('stability-search').value='';
    render();fitMap();
  }
  window.AtlasCargo=Object.freeze({
    getView:()=>({period:state.period,variant:state.variant,indexMode:state.indexMode,a:state.a,b:state.b,
      data:state.data,network:period(),interactive:state.interactive,mapOverlay:state.mapOverlay,nodeColor:state.nodeColor,playStep:state.playStep}),
    selectPair,setPeriod,setScenario,setMapOverlay,resetView,setNodeColor,setExploration,playFailure,
    communityPalette:COMMUNITY_PALETTE.slice()
  });
  init();
})();
