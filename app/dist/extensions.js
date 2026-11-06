'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite=v=>typeof v==='number'&&Number.isFinite(v);
  const num=(v,d=3)=>finite(v)?v.toLocaleString('es-CO',{maximumFractionDigits:d}):'—';
  const pct=(v,d=1)=>finite(v)?num(v*100,d)+' %':'—';
  const million=v=>finite(v)?num(v/1e6,1)+' M lb':'—';
  const empty=message=>'<p class="chart-empty">'+esc(message)+'</p>';
  const labels={annual:'Año completo',T1:'Primer trimestre',T2:'Segundo trimestre',T3:'Tercer trimestre',T4:'Cuarto trimestre'};
  const state={data:null,error:false,chartPeriod:null,stabilityPeriod:null,stabilitySource:null,stabilityRows:[]};
  const view=()=>window.AtlasCargo?.getView()||{period:'annual',a:'',b:'',data:null};
  const structural=()=>state.data?.structural;
  const inference=()=>state.data?.inference||state.data?.regression;
  const key=(a,b)=>[String(a),String(b)].sort().join('|');
  const pairButton=(p,variant='',mode='',period='')=>'<button type="button" class="pair-link" data-extension-a="'+esc(p.a)+'" data-extension-b="'+esc(p.b)+'"'+(variant?' data-extension-variant="'+esc(variant)+'"':'')+(mode?' data-extension-mode="'+esc(mode)+'"':'')+(period?' data-extension-period="'+esc(period)+'"':'')+'>'+esc(p.a)+' ↔ '+esc(p.b)+'</button>';
  const metric=(label,value,detail='')=>`<div class="extension-metric"><span>${esc(label)}</span><strong>${esc(value)}</strong>${detail?'<small>'+esc(detail)+'</small>':''}</div>`;

  async function init(){
    document.addEventListener('atlas:viewchange',render);
    $('sensitivity-scenario').addEventListener('change',e=>window.AtlasCargo?.setScenario(e.target.value,'common'));
    $('stability-min').addEventListener('change',renderStability);
    $('stability-search').addEventListener('input',renderStability);
    $('operator-select').addEventListener('change',renderOperator);
    $('operator-view').addEventListener('change',renderOperator);
    $('operator-map').addEventListener('click',showOperatorMap);
    $('operator-reset').addEventListener('click',()=>window.AtlasCargo?.setMapOverlay(null));
    $('regression-model').addEventListener('change',renderRegression);
    document.addEventListener('click',event=>{
      const el=event.target.closest('[data-extension-a]');
      if(el){
        if(el.dataset.extensionPeriod)window.AtlasCargo?.setPeriod(el.dataset.extensionPeriod);
        if(el.dataset.extensionVariant)window.AtlasCargo?.setScenario(el.dataset.extensionVariant,el.dataset.extensionMode||'common');
        window.AtlasCargo?.selectPair(el.dataset.extensionA,el.dataset.extensionB);
        $('explorador').scrollIntoView({behavior:'smooth',block:'start'});
      }
    });
    try{
      const embedded=$('atlas-extensions-data');
      if(embedded)state.data=JSON.parse(embedded.textContent);
      else{const response=await fetch('data/extensions.json',{cache:'no-cache'});if(!response.ok)throw new Error('No disponible');state.data=await response.json();}
      if(!structural()&&!inference())throw new Error('No contiene resultados complementarios');
      $('extension-status').textContent='Resultados complementarios calculados sobre los datos de 2025.';
      const items=structural()?.operators?.items||[];
      $('operator-select').innerHTML='<option value="">Selecciona un operador…</option>'+items.map(o=>`<option value="${esc(o.id)}">${esc(o.id)} · ${esc(o.name)}</option>`).join('');
      if(items.length)$('operator-select').value=String(items[0].id);
    }catch(_){state.error=true;$('extension-status').textContent='Los análisis complementarios aún no están disponibles en esta copia. El explorador base continúa funcionando.';}
    render();
  }
  function render(){renderScatter();renderCases();renderProfiles();renderSensitivity();renderStability();renderOperator();renderRegression();}

  function renderScatter(){
    const v=view(),pairs=v.network?.pairs||[];
    if(v.mapOverlay){state.chartPeriod=null;$('synergy-damage-chart').innerHTML=empty('La vista por operador describe sus conexiones. Restaura una regla de red para consultar sinergia y daño.');return;}
    if(!pairs.length){$('synergy-damage-chart').innerHTML=empty('Carga la red para comparar sinergia y daño.');return;}
    const chartKey=[v.period,v.variant,v.indexMode,v.a,v.b].join('|');
    if(state.chartPeriod===chartKey)return;
    state.chartPeriod=chartKey;
    const xs=pairs.map(p=>p.impact_global).filter(finite),ys=pairs.map(p=>p.score).filter(finite);
    const xlo=Math.min(0,...xs),xhi=Math.max(...xs),ylo=Math.min(0,...ys),yhi=Math.max(...ys),dx=xhi-xlo||1,dy=yhi-ylo||1;
    const x=value=>62+(value-xlo)/dx*446,y=value=>244-(value-ylo)/dy*215;
    let svg=`<svg viewBox="0 0 560 295" role="img" aria-label="Relación entre impacto global e índice compuesto de todas las parejas: ${esc(labels[v.period])}"><rect x="62" y="29" width="446" height="215" fill="#0d1f32"/>`;
    for(let i=0;i<5;i++){const xv=xlo+dx*i/4,yv=ylo+dy*i/4;svg+=`<path d="M${x(xv)} 29V244 M62 ${y(yv)}H508" stroke="#263b51" stroke-width=".6"/><text x="${x(xv)}" y="260" text-anchor="middle">${num(xv,3)}</text><text x="54" y="${y(yv)+4}" text-anchor="end">${num(yv,2)}</text>`;}
    svg+=`<path d="M${x(0)} 29V244 M62 ${y(0)}H508" stroke="#7e98a8" stroke-dasharray="3 4"/>`;
    const highlights=new Set([key('SDF','SEA'),key('MEM','ORD')]);
    for(const p of pairs){if(!finite(p.score)||!finite(p.impact_global))continue;const highlight=highlights.has(key(p.a,p.b));if(highlight)continue;svg+=`<circle cx="${x(p.impact_global).toFixed(2)}" cy="${y(p.score).toFixed(2)}" r="1.7" fill="${p.direct?'#79a6cf':'#50d6ce'}" opacity=".28"><title>${esc(p.a)}–${esc(p.b)} · sinergia ${num(p.score,4)} · impacto ${num(p.impact_global,5)}</title></circle>`;}
    for(const p of pairs.filter(p=>highlights.has(key(p.a,p.b))))svg+=`<circle cx="${x(p.impact_global)}" cy="${y(p.score)}" r="5" fill="#f4b859" stroke="#112238"/><text x="${x(p.impact_global)-7}" y="${y(p.score)-9}" text-anchor="end" class="highlight-label">${esc(p.a)}–${esc(p.b)}</text>`;
    svg+='<text x="285" y="286" text-anchor="middle">Daño global conjunto →</text><text x="17" y="140" text-anchor="middle" transform="rotate(-90 17 140)">Sinergia compuesta →</text></svg>';
    $('synergy-damage-chart').innerHTML=svg+'<p class="detail-caption">'+esc(labels[v.period])+' · '+num(pairs.length,0)+' parejas. Azul: con conexión; turquesa: sin conexión. '+esc(v.network?.label||'')+' · '+(v.indexMode==='common'?'escala común':'índice propio')+'.</p>';
  }

  function renderCases(){
    const cases=state.data?.interpretation?.cases||[];
    const wanted=[key('SDF','SEA'),key('MEM','ORD')];
    const selected=cases.filter(c=>wanted.includes(key(c.a,c.b)));
    if(!selected.length){$('case-comparison').innerHTML=empty('El análisis de caminos entre supervivientes aparecerá al cargar los resultados complementarios.');return;}
    $('case-comparison').innerHTML='<p class="detail-caption">Casos de referencia de la red base anual, con índice propio. Al pulsar una pareja se abre esa vista. Se comparan exactamente las mismas parejas de supervivientes antes y después del fallo.</p>'+selected.map(c=>{
      const paths=c.paths||{},metrics=c.metrics||[];
      const contributions=metrics.map(m=>`<tr><td>${esc(({global:'Global',global_efficiency:'Global',local:'Local',local_efficiency:'Local',natural:'Natural',natural_connectivity:'Natural'})[m.name]||m.name)}</td><td>${num(m.contribution,4)}</td></tr>`).join('');
      const mechanism=paths.worsened_pairs===0?'Ningún camino mínimo entre los supervivientes se alarga. La variación global refleja el cambio del conjunto promediado al retirar nodos.':finite(paths.worsened_pairs)?num(paths.worsened_pairs,0)+' parejas supervivientes tienen un camino mínimo más largo tras el fallo conjunto.':'';
      return `<div class="case-card"><div class="case-card-heading">${pairButton(c,'base','own','annual')}<span class="tag">Sinergia #${num(c.rank,0)}</span></div><p>${esc(mechanism)}</p><div class="case-metrics">${metric('Índice',num(c.score,3))}${metric('Puesto por daño global',num(c.joint_global_rank,1))}</div><details><summary>Contribución al índice por métrica</summary><table class="compact-table"><thead><tr><th>Componente</th><th>Aporte ponderado</th></tr></thead><tbody>${contributions}</tbody></table><p class="detail-caption">Los tres aportes se suman para obtener el índice. La pérdida de recorridos alternativos puede existir aunque no cambie el camino mínimo.</p></details></div>`;
    }).join('');
  }

  function renderProfiles(){
    const v=view(),ids=[v.a,v.b].filter(Boolean),profiles=structural()?.profiles||[];
    if(!ids.length){$('airport-profile-content').innerHTML=empty('Selecciona uno o dos aeropuertos en el mapa o usa los ejemplos del explorador.');return;}
    if(!profiles.length){$('airport-profile-content').innerHTML=empty('El perfil de operadores todavía no está disponible en esta copia.');return;}
    $('airport-profile-content').innerHTML='<div class="profile-grid">'+ids.map(id=>{
      const p=profiles.find(x=>String(x.id)===id);if(!p)return empty('Sin perfil para '+id);
      const top=p.top_operators||[],dominant=top[0];
      return `<div class="profile-card"><h4>${esc(id)} <span>· Contexto de la red base anual</span></h4><div class="profile-metrics">${metric('Carga incidente',million(p.freight_lb),'Puesto '+num(p.rank_freight,1))}${metric('Conexiones',num(p.degree,0),'Puesto '+num(p.rank_degree,1))}${metric('Intermediación',num(p.betweenness,2),'Puesto '+num(p.rank_betweenness,1))}${metric('Operadores',num(p.operator_count,0))}${metric('Concentración HHI',num(p.operator_hhi,3),'0–1; mayor valor, mayor concentración')}${metric('Cuota del principal',pct(dominant?.share),dominant?dominant.name:'')}</div><details><summary>Principales operadores del aeropuerto</summary><ul class="operator-list">${top.map(o=>`<li><span>${esc(o.name||o.id)}</span><strong>${pct(o.share)}</strong></li>`).join('')}</ul></details></div>`;
    }).join('')+'</div><p class="detail-caption">Este perfil conserva el contexto anual de la red base al cambiar de escenario. Carga: entradas + salidas en el conjunto depurado. Centralidades: subred de 100 aeropuertos; rangos medios en empates. HHI: suma de las cuotas de carga de operadores elevadas al cuadrado. Una alta cuota describe concentración; por sí sola no mide capacidad de sustitución.</p>'+renderMetroContext(ids);
  }

  function renderMetroContext(ids){
    const alternatives=(structural()?.city_market_alternatives||[]).filter(x=>x.same_city_market&&(ids.includes(x.hub)||ids.includes(x.airport)||ids.includes(x.alternative)));
    if(!alternatives.length)return '';
    return '<details><summary>Aeropuertos alternativos del mismo mercado</summary><ul>'+alternatives.map(x=>'<li>'+esc(x.airport)+' y '+esc(x.alternative)+' comparten mercado BTS. Desde '+esc(x.hub)+': '+x.routes.map(r=>esc(r.b)+' ('+million(r.freight_lb)+', '+num(r.months_present,0)+' meses)').join('; ')+'.</li>').join('')+'</ul><p class="detail-caption">Esto contextualiza la ausencia de una conexión exacta; no demuestra capacidad de sustitución ni la causa del índice.</p></details>';
  }

  function renderSensitivity(){
    const v=view(),scenarios=structural()?.sensitivity?.periods?.[v.period];
    if(!scenarios){$('sensitivity-summary').innerHTML=empty('No hay resultados de sensibilidad para este período.');$('sensitivity-ranking').innerHTML='';$('sensitivity-detail').innerHTML='';return;}
    const id=v.variant||'base',selected=scenarios[id],rows=Object.entries(scenarios);
    $('sensitivity-scenario').value=id;
    $('sensitivity-summary').innerHTML='<table><caption>'+esc(labels[v.period])+' · cuatro reglas con calibración común</caption><thead><tr><th>Regla</th><th>Enlaces</th><th>Componentes</th><th>Aislados</th><th>Carga conservada</th><th>Spearman con base</th><th>Top20 común</th></tr></thead><tbody>'+rows.map(([code,r])=>'<tr class="'+(code===id?'selected':'')+'"><td>'+esc(r.label||code)+'</td><td>'+num(r.stats?.n_edges,0)+'</td><td>'+num(r.stats?.components,0)+'</td><td>'+num(r.stats?.isolates,0)+'</td><td>'+pct(r.freight_coverage,3)+'</td><td>'+num(r.comparison?.spearman,3)+'</td><td>'+(finite(r.comparison?.shared_top)?num(r.comparison.shared_top,0)+' / '+num(r.comparison.top_k||20,0):'—')+'</td></tr>').join('')+'</tbody></table>';
    if(!selected){$('sensitivity-ranking').innerHTML=empty('Este escenario todavía no está calculado.');$('sensitivity-detail').innerHTML='';return;}
    $('sensitivity-ranking-title').textContent=selected.label+' · top 20 en escala común';
    $('sensitivity-ranking').innerHTML='<div class="table-wrap compact-scroll"><table class="compact-table"><thead><tr><th>Puesto</th><th>Pareja</th><th>Índice común</th></tr></thead><tbody>'+(selected.top20||[]).map((r,i)=>'<tr><td>'+num(r.rank??i+1,1)+'</td><td>'+pairButton(r,id,'common')+'</td><td>'+num(r.score_comparable,3)+'</td></tr>').join('')+'</tbody></table></div><p class="detail-caption">Selecciona una pareja para abrir su mapa, métricas y ficha en esta misma regla y escala común.</p>';
    $('sensitivity-detail').innerHTML='<p>'+esc(labels[v.period])+'. La regla seleccionada se aplica también al explorador y al mapa.</p><div class="profile-metrics">'+metric('Eficiencia global',num(selected.stats?.global_efficiency,4))+metric('Componente mayor',num(selected.stats?.largest_component,0)+' nodos')+metric('Coincidencia top20',pct(selected.comparison?.overlap))+metric('Jaccard de enlaces',num(selected.comparison?.edge_jaccard,3))+'</div><details><summary>Qué significa comparar con una escala común</summary><p>Esta sección fija pesos y normalización entre las cuatro reglas. La base se recalibra y su ranking puede diferir del índice propio del artículo. El selector superior identifica qué escala usa el explorador.</p><p>Spearman compara todas las parejas; el top20 se concentra en las primeras prioridades. Los umbrales son sensibilidades, no filtros de errores.</p></details>';
  }

  function getStabilityRows(){
    const v=view(),ip=v.interactive;
    if(!ip?.stability?.[v.period])return [];
    if(state.stabilityPeriod===v.period&&state.stabilitySource===ip)return state.stabilityRows;
    state.stabilityRows=ip.stability[v.period].map((r,i)=>{
      const ij=ip.pair_indices[i];
      return {a:ip.codes[ij[0]],b:ip.codes[ij[1]],count:r[0],min:r[1],max:r[2],mean:r[3],ranks:r.slice(4,8)};
    });
    state.stabilityPeriod=v.period;state.stabilitySource=ip;
    return state.stabilityRows;
  }

  function renderStability(){
    const v=view(),rows=getStabilityRows();
    if(!rows.length){$('stability-body').innerHTML='<tr><td colspan="7">La estabilidad aparecerá al cargar los datos de estabilidad.</td></tr>';$('stability-detail').innerHTML=empty('Datos de estabilidad no disponibles.');$('stability-summary').textContent='';return;}
    const minimum=Number($('stability-min').value),search=$('stability-search').value.trim().toLowerCase();
    const filtered=rows.filter(r=>r.count>=minimum&&(!search||[r.a,r.b].some(code=>(code+' '+(v.data?.airports||[]).find(a=>a.id===code)?.city).toLowerCase().includes(search)))).sort((a,b)=>b.count-a.count||a.mean-b.mean||a.a.localeCompare(b.a)||a.b.localeCompare(b.b));
    const allFour=rows.filter(r=>r.count===4).length;
    $('stability-summary').textContent=labels[v.period]+': '+num(allFour,0)+' parejas aparecen en el top20 de las cuatro reglas. Se muestran '+Math.min(50,filtered.length)+' de '+num(filtered.length,0)+' coincidencias del filtro.';
    $('stability-body').innerHTML=filtered.slice(0,50).map(r=>'<tr class="'+(key(r.a,r.b)===key(v.a,v.b)?'selected':'')+'"><td>'+pairButton(r)+'</td><td><span class="stability-badge '+(r.count===4?'strong':'')+'">'+num(r.count,0)+' / 4</span></td><td>'+num(r.min,1)+'–'+num(r.max,1)+'</td>'+r.ranks.map(rank=>'<td>'+num(rank,1)+'</td>').join('')+'</tr>').join('')||'<tr><td colspan="7">No hay parejas con estos filtros. Prueba otra frecuencia o código.</td></tr>';
    const selected=rows.find(r=>key(r.a,r.b)===key(v.a,v.b));
    if(!selected){$('stability-detail').innerHTML=empty('Selecciona una pareja para ver sus cuatro posiciones y su rango de variación.');return;}
    const variantNames=['Base','Mitad de meses','Todos los meses','Volumen mínimo'];
    const max=Math.max(1,...selected.ranks.filter(finite));
    $('stability-detail').innerHTML='<h3>'+esc(selected.a)+' ↔ '+esc(selected.b)+'</h3><div class="case-metrics">'+metric('Presencia en top20',num(selected.count,0)+' / 4 reglas')+metric('Rango de puestos',num(selected.min,1)+'–'+num(selected.max,1))+'</div><div class="rank-comparison" role="img" aria-label="Puestos de la pareja en las cuatro reglas">'+selected.ranks.map((rank,i)=>'<div><span>'+variantNames[i]+'</span><i><b style="width:'+Math.max(2,rank/max*100)+'%;background:'+(v.variant===v.interactive?.variants?.[i]?'var(--amber)':'var(--cyan)')+'"></b></i><strong>'+num(rank,1)+'</strong></div>').join('')+'</div><p class="detail-caption">Un puesto menor indica mayor prioridad de sinergia. Las barras se ajustan al mayor puesto de esta pareja; sus valores se muestran explícitamente. La frecuencia entre reglas no es probabilidad de fallo ni nivel de confianza.</p>';
  }

  function operator(){return (structural()?.operators?.items||[]).find(o=>String(o.id)===$('operator-select').value);}
  function renderOperator(){
    const o=operator(),removal=$('operator-view').value==='removal';
    $('operator-map').disabled=!o;
    if(!o){$('operator-detail').innerHTML=empty('Las capas de operadores aparecerán al cargar los análisis complementarios.');return;}
    const stats=removal?o.removal?.stats:o.layer?.stats;
    $('operator-detail').innerHTML=`<h3>${esc(o.name||o.id)}</h3><p class="muted">${removal?'Escenario: red anual después de retirar al operador.':'Capa anual: conexiones observadas del operador.'}</p><div class="operator-metrics">${metric('Carga atribuida',million(o.freight_lb),'Cuota '+pct(o.share))}${metric('Enlaces en esta vista',num(stats?.n_edges,0))}${metric('Componentes',num(stats?.components,0))}${metric('Eficiencia global',num(stats?.global_efficiency,4))}${removal?metric('Enlaces perdidos',Array.isArray(o.removal?.edges_lost)?num(o.removal.edges_lost.length,0):num(o.removal?.edges_lost,0)):metric('Aeropuertos aislados',num(stats?.isolates,0))}</div><p class="detail-caption">El universo conserva 100 aeropuertos. La ausencia de actividad de este operador puede dejar nodos aislados. Los datos describen operaciones observadas, sin simular reasignación de mercancía.</p>`;
  }
  function showOperatorMap(){
    const o=operator();if(!o)return;
    const removal=$('operator-view').value==='removal';
    let edges=removal?(o.removal?.edges||o.removal?.edges_remaining):o.layer?.edges;
    if(!edges&&removal&&Array.isArray(o.removal?.edges_lost)){
      const lost=new Set(o.removal.edges_lost.map(e=>key(e.source,e.target)));
      edges=(view().data?.periods?.annual?.edges||[]).filter(e=>!lost.has(key(e.source,e.target)));
    }
    if(!Array.isArray(edges)){$('operator-detail').insertAdjacentHTML('beforeend','<p class="extension-status">La tabla del escenario está disponible, pero esta copia no incluye sus conexiones para el mapa.</p>');return;}
    window.AtlasCargo?.setMapOverlay({edges,label:(removal?'Sin ':'Capa: ')+(o.name||o.id)+' · 2025',stats:removal?o.removal?.stats:o.layer?.stats,scope:'annual',kind:'operator',operator:o.name||o.id});
    $('explorador').scrollIntoView({behavior:'smooth'});
  }

  function renderRegression(){
    const data=inference(),models=data?.models||[];
    if(!models.length){$('regression-summary').innerHTML=empty('Los resultados de M5 y M6 todavía no están disponibles.');$('regression-coefficients').innerHTML='';$('regression-method').textContent='';return;}
    $('regression-summary').innerHTML=models.map(m=>`<article class="panel"><h3>${esc(m.model)}${m.model==='M6'?' · sensibilidad del artículo (grado²)':''}</h3><div class="case-metrics">${metric('R²',num(m.r2,4))}${metric('R² ajustado',num(m.adjusted_r2,4))}${metric('RMSE interno',num(m.residual_rmse,4))}${metric('Predictores',num(m.n_predictors,0))}</div></article>`).join('');
    const selected=models.find(m=>m.model===$('regression-model').value)||models[0];
    const terms={intercept:'Intercepto',degree_sum:'Suma de centralidades de grado',degree_diff:'Diferencia de centralidades de grado',betweenness_diff:'Diferencia de intermediación',geo_distance_km:'Distancia geográfica',direct:'Conexión directa',freight_sum:'Suma de carga incidente',degree_sum_squared:'Cuadrado de la suma de grado',degree_sum_sq:'Suma de grado al cuadrado'};
    const termLabel=t=>String(t).endsWith('×direct')?(terms[String(t).slice(0,-7)]||String(t).slice(0,-7))+' × conexión directa':terms[t]||String(t);
    $('regression-coefficients').innerHTML='<table><caption>'+esc(selected.model)+' · coeficientes y sensibilidad de inferencia</caption><thead><tr><th>Variable</th><th>Coeficiente</th><th>p · permutación Y</th><th>p · residuos</th><th>Error Monte Carlo</th></tr></thead><tbody>'+(selected.coefficients||[]).map(c=>`<tr><td>${esc(termLabel(c.term))}</td><td>${num(c.coefficient,5)}</td><td>${num(c.p_baseline_Y,4)}</td><td>${num(c.p_sensitivity,4)}</td><td>${num(c.mc_standard_error,4)}</td></tr>`).join('')+'</tbody></table>';
    $('regression-method').textContent='Sensibilidad exploratoria: '+num(data.permutations,0)+' permutaciones, semilla '+String(data.seed)+'. Los contrastes por residuos evalúan efectos parciales bajo otro esquema de permutación; sus p no son intercambiables con la permutación simple de Y. Las celdas sin contraste disponible muestran —. Los coeficientes continuos usan variables estandarizadas. El mejor ajuste interno no demuestra causalidad ni desempeño predictivo.';
  }
  init();
})();
