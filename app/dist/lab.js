'use strict';
/* Laboratorio: redes de juguete para ver qué miden las tres medidas al retirar nodos.
   No usa datos reales. Las medidas se calculan en el navegador con las mismas
   definiciones del notebook: los denominadores se reducen al retirar nodos. */
(function(root){
  const NETWORKS={
    hub:{label:'Un hub con alimentadores',
      nodes:{H:[200,140],A:[90,62],B:[310,62],C:[310,222],D:[90,222],E:[30,140]},
      edges:[['H','A'],['H','B'],['H','C'],['H','D'],['A','B'],['D','E']],
      presets:[['H','D'],['H','A'],['A','B']],
      note:'Un hub conecta a casi todos. A y B se conectan entre sí; E solo llega a la red a través de D.'},
    backup:{label:'Dos hubs que se respaldan',
      nodes:{H1:[120,140],H2:[280,140],A:[200,40],B:[200,105],C:[200,175],D:[200,240],E:[40,140]},
      edges:[['H1','A'],['H1','B'],['H1','C'],['H1','D'],['H2','A'],['H2','B'],['H2','C'],['H2','D'],['A','B'],['H1','E']],
      presets:[['H1','H2'],['H1','A'],['A','B']],
      note:'H1 y H2 no tienen enlace directo, pero sirven a los mismos cuatro aeropuertos: cada uno es la alternativa del otro.'},
    linked:{label:'Dos hubs conectados entre sí',
      nodes:{H1:[130,140],H2:[270,140],A:[50,60],B:[50,220],C:[200,40],D:[350,60],E:[350,220],F:[200,240]},
      edges:[['H1','H2'],['H1','A'],['H1','B'],['H1','C'],['H2','D'],['H2','E'],['H2','F'],['A','B'],['D','E'],['C','D']],
      presets:[['H1','H2'],['H1','D'],['A','B']],
      note:'Cada hub tiene su propio grupo de aeropuertos y ambos se conectan directamente.'}
  };
  const MEASURES=[['global','Eficiencia global'],['local','Eficiencia local'],['natural','Conectividad natural']];

  function neighbours(net,removed){
    const keep=Object.keys(net.nodes).filter(n=>!removed.includes(n));
    const adj=new Map(keep.map(n=>[n,new Set()]));
    for(const [u,v] of net.edges)if(adj.has(u)&&adj.has(v)){adj.get(u).add(v);adj.get(v).add(u);}
    return adj;
  }
  function globalEfficiency(adj,subset){
    const nodes=subset||[...adj.keys()],n=nodes.length,inside=new Set(nodes);
    if(n<2)return 0;
    let total=0;
    for(const s of nodes){
      const dist=new Map([[s,0]]),queue=[s];
      while(queue.length){const u=queue.shift();for(const v of adj.get(u))if(inside.has(v)&&!dist.has(v)){dist.set(v,dist.get(u)+1);queue.push(v);}}
      for(const [t,d] of dist)if(t!==s)total+=1/d;
    }
    return total/(n*(n-1));
  }
  function localEfficiency(adj){
    const nodes=[...adj.keys()];if(!nodes.length)return 0;
    let total=0;
    for(const v of nodes){const nb=[...adj.get(v)];total+=nb.length<2?0:globalEfficiency(adj,nb);}
    return total/nodes.length;
  }
  function eigenvalues(matrix){
    // Método de Jacobi para matrices simétricas pequeñas.
    const n=matrix.length,a=matrix.map(r=>r.slice());
    for(let sweep=0;sweep<100;sweep++){
      let off=0;for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)off+=a[i][j]*a[i][j];
      if(off<1e-22)break;
      for(let p=0;p<n;p++)for(let q=p+1;q<n;q++){
        if(Math.abs(a[p][q])<1e-15)continue;
        const theta=(a[q][q]-a[p][p])/(2*a[p][q]);
        const t=Math.sign(theta||1)/(Math.abs(theta)+Math.sqrt(theta*theta+1));
        const c=1/Math.sqrt(t*t+1),s=t*c;
        for(let k=0;k<n;k++){const akp=a[k][p],akq=a[k][q];a[k][p]=c*akp-s*akq;a[k][q]=s*akp+c*akq;}
        for(let k=0;k<n;k++){const apk=a[p][k],aqk=a[q][k];a[p][k]=c*apk-s*aqk;a[q][k]=s*apk+c*aqk;}
      }
    }
    return a.map((r,i)=>r[i]).sort((x,y)=>x-y);
  }
  function naturalConnectivity(adj){
    const nodes=[...adj.keys()],n=nodes.length;if(!n)return 0;
    const index=new Map(nodes.map((v,i)=>[v,i]));
    const m=nodes.map(()=>Array(n).fill(0));
    for(const [u,set] of adj)for(const v of set)m[index.get(u)][index.get(v)]=1;
    const lambda=eigenvalues(m),top=Math.max(...lambda);
    return top+Math.log(lambda.reduce((s,x)=>s+Math.exp(x-top),0)/n);
  }
  function metrics(net,removed=[]){
    const adj=neighbours(net,removed);
    return {global:globalEfficiency(adj),local:localEfficiency(adj),natural:naturalConnectivity(adj)};
  }
  function scenario(net,a,b){
    const base=metrics(net),out={base,rows:{}};
    const without=list=>metrics(net,list);
    const wa=a?without([a]):null,wb=b?without([b]):null,wab=a&&b?without([a,b]):null;
    for(const [k] of MEASURES){
      const row={base:base[k]};
      if(wa){row.withoutA=wa[k];row.impactA=base[k]-wa[k];}
      if(wb){row.withoutB=wb[k];row.impactB=base[k]-wb[k];}
      if(wab){row.withoutAB=wab[k];row.joint=base[k]-wab[k];row.synergy=row.joint-row.impactA-row.impactB;}
      out.rows[k]=row;
    }
    return out;
  }
  const LabMath={NETWORKS,MEASURES,metrics,scenario,eigenvalues};
  if(typeof module!=='undefined'&&module.exports){module.exports=LabMath;return;}
  root.AtlasLab=LabMath;

  // ---------------------------------------------------------------- Interfaz
  const $=id=>document.getElementById(id);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=(v,d=4)=>Number.isFinite(v)?v.toLocaleString('es-CO',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
  const state={net:'hub',selected:[]};
  function net(){return NETWORKS[state.net];}
  function drawGraph(){
    const g=net(),sel=state.selected,degree=neighbours(g,[]);
    let svg='<svg viewBox="0 0 400 280" role="img" aria-label="Red de juguete: haz clic en un nodo para retirarlo">';
    for(const [u,v] of g.edges){const [x1,y1]=g.nodes[u],[x2,y2]=g.nodes[v],gone=sel.includes(u)||sel.includes(v);
      svg+=`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="lab-edge${gone?' gone':''}"/>`;}
    for(const [id,[x,y]] of Object.entries(g.nodes)){const gone=sel.includes(id);
      svg+=`<g class="lab-node${gone?' gone':''}" tabindex="0" role="button" data-lab-node="${esc(id)}" aria-pressed="${gone}" aria-label="${gone?'Restaurar':'Retirar'} ${esc(id)}"><title>${esc(id)} · ${degree.get(id).size} conexiones</title><circle cx="${x}" cy="${y}" r="19"/><text x="${x}" y="${y+4}" text-anchor="middle">${esc(id)}</text></g>`;}
    $('lab-graph').innerHTML=svg+'</svg>';
    $('lab-note').textContent=g.note;
    $('lab-presets').innerHTML='Probar: '+g.presets.map(([a,b])=>`<button type="button" class="quiet-button" data-lab-preset="${esc(a)}|${esc(b)}">${esc(a)} + ${esc(b)}</button>`).join(' ');
    $('lab-selection').textContent=sel.length?'Retirados: '+sel.join(' y '):'Ningún nodo retirado. Haz clic en uno o dos nodos.';
  }
  function drawTable(){
    const [a,b]=state.selected,s=scenario(net(),a,b);
    const cols=[['base','Red completa']];
    if(a)cols.push(['withoutA','Sin '+a]);
    if(b)cols.push(['withoutB','Sin '+b],['withoutAB','Sin '+a+' y '+b]);
    if(a)cols.push(['impactA','Impacto de '+a]);
    if(b)cols.push(['impactB','Impacto de '+b],['joint','Impacto conjunto'],['synergy','Sinergia']);
    let html='<table class="compact-table"><thead><tr><th>Medida</th>'+cols.map(c=>'<th>'+esc(c[1])+'</th>').join('')+'</tr></thead><tbody>';
    for(const [k,label] of MEASURES)html+='<tr><td>'+label+'</td>'+cols.map(([key])=>`<td${key==='synergy'?' class="lab-synergy-cell"':''}>${num(s.rows[k][key])}</td>`).join('')+'</tr>';
    $('lab-table').innerHTML=html+'</tbody></table>';
    if(!(a&&b)){$('lab-reading').innerHTML='<p class="detail-caption">'+(a?'El impacto es el valor de la red completa menos el valor sin '+esc(a)+'. Retira un segundo nodo para calcular la sinergia de la pareja.':'Retira un nodo para ver su impacto; retira dos para ver la sinergia.')+'</p>';return;}
    const lines=MEASURES.map(([k,label])=>{const r=s.rows[k],kind=r.synergy>1e-9?'positiva: juntos dañan más que la suma de sus fallos':r.synergy<-1e-9?'negativa: parte del daño se solapa':'nula: los daños se suman sin interacción';
      const term=v=>v<0?'('+num(v)+')':num(v);
      return `<li><strong>${label}:</strong> ${num(r.joint)} − ${term(r.impactA)} − ${term(r.impactB)} = <strong>${num(r.synergy)}</strong>, ${kind}.</li>`;});
    const direct=net().edges.some(([u,v])=>(u===a&&v===b)||(u===b&&v===a));
    $('lab-reading').innerHTML='<p class="detail-caption">Sinergia = impacto conjunto − impacto de '+esc(a)+' − impacto de '+esc(b)+'.</p><ul class="lab-lines">'+lines.join('')+'</ul><p class="detail-caption">'+(direct?esc(a)+' y '+esc(b)+' tienen enlace directo: ese enlace se pierde al retirar cualquiera de los dos, así que cuenta dos veces en la suma de impactos y la sinergia tiende a bajar.':esc(a)+' y '+esc(b)+' no tienen enlace directo: si cada uno ofrecía alternativas al otro, retirarlos juntos elimina esas alternativas a la vez.')+'</p>';
  }
  function render(){drawGraph();drawTable();}
  function toggle(id){
    const i=state.selected.indexOf(id);
    if(i>=0)state.selected.splice(i,1);else{if(state.selected.length===2)state.selected.shift();state.selected.push(id);}
    render();
  }
  function init(){
    if(!$('lab-graph'))return;
    $('lab-network').innerHTML=Object.entries(NETWORKS).map(([k,v])=>`<option value="${k}">${esc(v.label)}</option>`).join('');
    $('lab-network').addEventListener('change',e=>{state.net=e.target.value;state.selected=[];render();});
    $('lab-reset').addEventListener('click',()=>{state.selected=[];render();});
    $('laboratorio').addEventListener('click',e=>{
      const node=e.target.closest('[data-lab-node]');if(node){toggle(node.dataset.labNode);return;}
      const preset=e.target.closest('[data-lab-preset]');if(preset){state.selected=preset.dataset.labPreset.split('|');render();}
    });
    $('lab-graph').addEventListener('keydown',e=>{const node=e.target.closest('[data-lab-node]');if(node&&(e.key==='Enter'||e.key===' ')){e.preventDefault();toggle(node.dataset.labNode);}});
    render();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})(typeof globalThis!=='undefined'?globalThis:this);
