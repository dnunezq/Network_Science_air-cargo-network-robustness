'use strict';
/* Pestaña Estructura: caracterización descriptiva de la red del escenario activo.
   Lee exploration.json (exportado por el notebook); no calcula métricas de red. */
(() => {
  const $=id=>document.getElementById(id);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite=v=>Number.isFinite(Number(v))&&v!==null&&v!=='';
  const num=(v,d=3)=>finite(v)?Number(v).toLocaleString('es-CO',{maximumFractionDigits:d,minimumFractionDigits:d}):'—';
  const int=v=>finite(v)?Number(v).toLocaleString('es-CO',{maximumFractionDigits:0}):'—';
  const state={data:null,key:null,centrality:'degree',search:''};
  const labels={annual:'Año 2025',T1:'Enero–marzo',T2:'Abril–junio',T3:'Julio–septiembre',T4:'Octubre–diciembre'};
  const modelName=k=>state.data?.metadata?.models?.[k]||k;
  const view=()=>window.AtlasCargo?.getView()||{period:'annual',variant:'base'};
  const block=()=>{const v=view();return v.mapOverlay?null:state.data?.networks?.[v.period]?.[v.variant]||null;};
  const codes=()=>state.data?.metadata?.codes||[];
  const airport=id=>view().data?.airports?.find(x=>String(x.id)===id);
  const city=id=>{const a=airport(id);return a?.city||a?.name||'';};

  async function init(){
    try{
      const embedded=$('atlas-exploration-data');
      if(embedded)state.data=JSON.parse(embedded.textContent);
      else{const r=await fetch('data/exploration.json',{cache:'no-cache'});if(!r.ok)throw new Error('No disponible');state.data=await r.json();}
      if(!state.data?.networks)throw new Error('Sin bloques');
      window.AtlasCargo?.setExploration?.(state.data);
      $('structure-status').textContent='Caracterización calculada en el notebook sobre las redes binarias de 2025. Aporte propio del equipo: el artículo de referencia no describe la topología.';
    }catch(_){$('structure-status').textContent='La caracterización estructural no está disponible en esta copia. El resto del explorador sigue funcionando.';}
    document.addEventListener('atlas:viewchange',render);
    $('centrality-select').addEventListener('change',e=>{state.centrality=e.target.value;renderCentralities();});
    $('centrality-search').addEventListener('input',e=>{state.search=e.target.value.trim().toLowerCase();renderCentralities();});
    $('structure-color').addEventListener('click',()=>{window.AtlasCargo?.setNodeColor('communities');$('explorador').scrollIntoView({behavior:'smooth',block:'start'});});
    $('centrality-color').addEventListener('click',()=>{window.AtlasCargo?.setNodeColor('centrality:'+state.centrality);$('explorador').scrollIntoView({behavior:'smooth',block:'start'});});
    document.addEventListener('click',e=>{const el=e.target.closest('[data-structure-airport]');if(el){window.AtlasCargo?.selectPair(el.dataset.structureAirport,'');$('explorador').scrollIntoView({behavior:'smooth',block:'start'});}});
    render();
  }

  function render(){
    const b=block(),v=view();
    const key=[v.period,v.variant,Boolean(b)].join('|');
    $('structure-context').textContent=v.mapOverlay?'Capa por operador: la caracterización corresponde a las reglas de red, no a capas.':(labels[v.period]||v.period)+' · '+(b?.label||v.variant);
    if(!b){for(const id of ['structure-cards','null-models','degree-chart','centrality-body','community-list'])if($(id))$(id).innerHTML='<p class="chart-empty">Selecciona una regla de red para ver su estructura.</p>';$('structure-reading').innerHTML='';return;}
    if(state.key!==key){state.key=key;renderCards(b);renderModels(b);renderDegree(b);renderReading(b);}
    renderCentralities();renderCommunities();
  }

  function card(label,value,detail){return `<div class="structure-card"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(detail||'')}</small></div>`;}
  function renderCards(b){
    const s=b.summary,m=b.models,er=m.models?.erdos_renyi?.metrics,c=b.communities,lab=m.observed_labels||{};
    const r=s.degree_assortativity;
    $('structure-cards').innerHTML=[
      card('Conexiones · densidad',int(s.n_edges)+' · '+num(s.density,3),'Fracción de las 4.950 parejas conectadas'),
      card('Grado medio · máximo',num(s.mean_degree,1)+' · '+int(s.max_degree),'Aeropuertos conectados directamente'),
      card('Distancia media · diámetro',(s.average_path_length!=null?num(s.average_path_length,2):'—')+' · '+(s.diameter??'—'),s.components>1?s.components+' componentes':'Escalas mínimas entre aeropuertos'),
      card('Agrupamiento · transitividad',num(s.average_clustering,3)+' · '+num(s.transitivity,3),er?'Red aleatoria: '+num(er.average_clustering.mean,3):''),
      card('Asortatividad de grado',r!=null?num(r,3):'—',r==null?'':r<-0.05?'Negativa: hub-and-spoke':r>0.05?'Positiva: grandes con grandes':'Mezcla casi neutra'),
      card('Núcleo k-core',int(s.max_core_size)+' aeropuertos · k = '+int(s.max_core),'Todos con ≥ k conexiones dentro del núcleo'),
      card('Comunidades Louvain',int(c.n_communities)+' · Q '+num(c.modularity,3),'NMI '+num(c.nmi_mean,2)+(c.modularity<0.3?' · comunidades débiles':'')),
      card('Tipo de red (curso)',m.course_match?modelName(m.course_match).split(' (')[0]:'Sin coincidencia','Agrupamiento '+(lab.clustering||'—')+' · caminos '+(lab.paths||'—')+' · hubs '+(lab.hubs||'—')),
    ].join('');
  }
  function renderReading(b){
    const s=b.summary,m=b.models,lab=m.observed_labels||{},c=b.communities;
    const lines=[];
    lines.push(`<li><strong>Medidas globales.</strong> Densidad ${num(s.density,3)} y distancia media ${s.average_path_length!=null?num(s.average_path_length,2):'—'}: casi todo está a una o dos escalas. ${s.degree_assortativity<-0.05?'La asortatividad negativa indica un patrón hub-and-spoke: los grandes se conectan con muchos pequeños.':'La mezcla por grado es casi neutra.'}</li>`);
    if(m.observed_labels)lines.push(`<li><strong>Tipo de red.</strong> Agrupamiento ${esc(lab.clustering)}, caminos ${esc(lab.paths)} y hubs: ${esc(lab.hubs)}. ${m.course_match?'Coincide con el perfil '+esc(modelName(m.course_match))+'.':'No coincide exactamente con ningún perfil del curso.'} ${m.closest_model?'El modelo simulado más cercano en las tres propiedades es '+esc(modelName(m.closest_model))+'.':''}</li>`);
    lines.push(`<li><strong>Sin ley de potencia.</strong> El grado va de ${int(s.min_degree)} a ${int(s.max_degree)} y no puede superar ${int(s.n_nodes-1)}: un solo orden de magnitud no permite ajustar una ley de potencia de forma fiable. La red tiene hubs, pero no se describe como libre de escala.</li>`);
    lines.push(`<li><strong>Comunidades.</strong> ${c.modularity<0.3?'Modularidad baja ('+num(c.modularity,3)+'): los grupos son débiles y cambian con la semilla (NMI '+num(c.nmi_mean,2)+').':'Modularidad '+num(c.modularity,3)+'.'} Describen estructura; no demuestran acuerdos entre operadores ni regiones operativas.</li>`);
    $('structure-reading').innerHTML='<ul>'+lines.join('')+'</ul>';
  }
  function renderModels(b){
    const m=b.models;
    if(!m?.models||!Object.keys(m.models).length){$('null-models').innerHTML='<p class="chart-empty">Sin comparación con modelos para esta red.</p>';return;}
    const rows=[['Red observada',m.observed,m.observed_labels||{},true]].concat(Object.entries(m.models).map(([k,x])=>[modelName(k),Object.fromEntries(Object.entries(x.metrics).map(([q,v])=>[q,v.mean])),x.labels||{},false]));
    let html='<table class="compact-table"><thead><tr><th>Red</th><th>Agrupamiento</th><th>Distancia media</th><th>Desv. del grado</th><th>Grado máx.</th><th>Perfil</th></tr></thead><tbody>';
    for(const [name,v,lab,obs] of rows)html+=`<tr${obs?' class="selected"':''}><td>${esc(name)}</td><td>${num(v.average_clustering,3)}</td><td>${num(v.average_path_length,2)}</td><td>${num(v.degree_std,1)}</td><td>${num(v.max_degree,0)}</td><td>${esc(lab.clustering||'—')} · ${esc(lab.paths||'—')} · hubs ${esc(lab.hubs||'—')}</td></tr>`;
    html+='</tbody></table>';
    const t=m.thresholds||{};
    $('null-models').innerHTML=html+`<p class="detail-caption">Medias de ${m.replicas} réplicas por modelo con semilla fija. Perfil = agrupamiento · caminos · hubs, relativo a la red aleatoria: agrupamiento alto si es al menos ${num(t.clustering_high,1)} veces el aleatorio; caminos largos si la distancia media supera en más de ${int(100*((t.paths_long||1.2)-1))} % la aleatoria; hubs si la desviación del grado es al menos ${num(t.hubs,0)} veces la aleatoria. Según el curso: aleatoria = bajo · cortos · sin hubs; mundo pequeño = alto · cortos · sin hubs; preferencial = alto · cortos · con hubs.</p>`;
  }
  function renderDegree(b){
    const rows=b.degree_distribution.histogram;if(!rows?.length){$('degree-chart').innerHTML='';return;}
    const maxK=Math.max(...rows.map(r=>r.degree),1);
    const x=k=>52+k/maxK*470,y=p=>22+(1-p)*200;
    let svg=`<svg viewBox="0 0 560 262" role="img" aria-label="Fracción de aeropuertos con grado al menos k"><rect x="52" y="22" width="470" height="200" fill="#0d1f32"/>`;
    for(let i=0;i<=4;i++){const p=i/4,k=Math.round(maxK*i/4);svg+=`<path d="M52 ${y(p)}H522" stroke="#263b51" stroke-width=".6"/><text x="46" y="${y(p)+4}" text-anchor="end">${num(p,2)}</text><text x="${x(k)}" y="238" text-anchor="middle">${k}</text>`;}
    // Escalera: cada escalón mantiene la supervivencia hasta el siguiente grado observado.
    let path='';rows.forEach((r,i)=>{const px=x(r.degree).toFixed(1),py=y(r.survival).toFixed(1);path+=i?`H${px}V${py}`:`M${px} ${py}`;});
    path+=`H${x(maxK).toFixed(1)}`;
    svg+=`<path d="${path}" fill="none" stroke="#50d6ce" stroke-width="2"/>`;
    const mean=b.summary.mean_degree;svg+=`<path d="M${x(mean)} 22V222" stroke="#f4b859" stroke-dasharray="3 4"/><text x="${x(mean)+4}" y="34" class="highlight-label">media ${num(mean,1)}</text>`;
    for(const r of rows)svg+=`<circle cx="${x(r.degree).toFixed(1)}" cy="${y(r.survival).toFixed(1)}" r="2.2" fill="#50d6ce"><title>grado ${r.degree}: ${r.count} aeropuerto(s) · ${num(r.survival*100,0)} % con grado ≥ ${r.degree}</title></circle>`;
    svg+='<text x="287" y="256" text-anchor="middle">Grado k (aeropuertos conectados) →</text><text x="14" y="122" text-anchor="middle" transform="rotate(-90 14 122)">Fracción con grado ≥ k</text></svg>';
    const p=b.degree_distribution.percentiles;
    $('degree-chart').innerHTML=svg+`<p class="detail-caption">Percentiles del grado: 10 % → ${num(p['10'],0)} · mediana ${num(p['50'],0)} · 90 % → ${num(p['90'],0)}. La curva cae de forma gradual entre 20 y 90 conexiones: hay hubs, pero no una cola larga de ley de potencia.</p>`;
  }
  function renderCentralities(){
    const b=block();if(!b)return;
    const name=state.centrality,values=b.centrality_values[name]||[],ranks=b.centrality_ranks[name]||[],list=codes();
    let rows=list.map((id,i)=>({id,value:values[i],rank:ranks[i],degree:b.centrality_values.degree[i]}));
    if(state.search)rows=rows.filter(r=>r.id.toLowerCase().includes(state.search)||city(r.id).toLowerCase().includes(state.search)||String(airport(r.id)?.airport_id??'').includes(state.search));
    rows.sort((a,b2)=>(a.rank??1e9)-(b2.rank??1e9)||a.id.localeCompare(b2.id));
    const shown=rows.slice(0,state.search?rows.length:15),max=Math.max(1e-12,...values.filter(finite).map(Number));
    const digits=name==='degree'?0:name==='betweenness'?1:4;
    $('centrality-body').innerHTML=shown.length?shown.map(r=>`<tr><td>${num(r.rank,Number.isInteger(r.rank)?0:1)}</td><td><button type="button" class="pair-link" data-structure-airport="${esc(r.id)}">${esc(r.id)}</button><span class="pair-cities">${esc(city(r.id))} · ID ${esc(airport(r.id)?.airport_id??'')}</span></td><td><div class="score-cell"><span>${num(r.value,digits)}</span><i class="score-track"><i style="width:${Math.min(100,Number(r.value)/max*100)}%"></i></i></div></td><td>${int(r.degree)}</td></tr>`).join(''):'<tr><td colspan="4" class="empty-cell">Sin coincidencias.</td></tr>';
    const sp=b.centrality_spearman?.[name]||{};
    $('centrality-note').textContent='Spearman con las demás centralidades: '+Object.entries(sp).filter(([k])=>k!==name).map(([k,v])=>(state.data.metadata.centrality_labels[k]||k)+' '+num(v,2)).join(' · ')+'. Un puesto con decimal indica empate. En esta red la cercanía ordena igual que el grado porque casi todo está a una o dos escalas.';
  }
  function renderCommunities(){
    const b=block();if(!b)return;
    const c=b.communities;if(!c){$('community-list').innerHTML='';return;}
    const palette=window.AtlasCargo?.communityPalette||[];
    $('community-summary').textContent=`${c.n_communities} comunidades · modularidad ${num(c.modularity,3)} · NMI media entre ${c.runs} ejecuciones ${num(c.nmi_mean,2)} · comunidades por ejecución: ${(c.n_communities_by_run||[]).join(', ')}`;
    $('community-list').innerHTML=c.communities.map(k=>`<article class="community-card"><div class="community-head"><i class="dot" style="background:${palette[k.id%palette.length]||'#888'}"></i><strong>Comunidad ${k.id+1}</strong><span>${k.size} aeropuertos · ${int(k.internal_edges)} enlaces internos · ${k.internal_share!=null?num(k.internal_share*100,0)+' % del grado dentro del grupo':''}</span></div><p>${k.members.map(m=>`<button type="button" class="pair-link" data-structure-airport="${esc(m)}">${esc(m)}</button>`).join(' · ')}</p></article>`).join('');
  }
  init();
})();
