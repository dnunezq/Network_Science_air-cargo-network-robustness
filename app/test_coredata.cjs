'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {ExplorerData,pairKey}=require('./dist/coredata.js');
const read=n=>JSON.parse(fs.readFileSync(path.join(__dirname,'dist/data',n),'utf8'));
const base=read('network.json'),ip=read('interactive.json'),ext=read('extensions.json'),exp=read('exploration.json');
const model=new ExplorerData(base,ip);
let networks=0;
for(const period of Object.keys(base.periods))for(const variant of ip.variants)for(const mode of ['own','common']){
  const n=model.network(period,variant,mode);
  assert.equal(n.nodes.length,100);assert.equal(n.pairs.length,4950);
  assert.equal(n.edges.length,n.n_edges);
  const links=new Set(n.edges.map(e=>pairKey(e.source,e.target)));
  const nodes=new Map(n.nodes.map(x=>[x.id,x]));
  assert.equal(n.nodes.reduce((a,x)=>a+x.degree,0),2*n.edges.length);
  for(const p of n.pairs.filter((_,i)=>i%107===0)){
    assert.equal(p.direct,links.has(pairKey(p.a,p.b)));
    let sum=0;
    ['global','local','natural'].forEach((k,j)=>{
      assert.ok(Math.abs(p['single_a_'+k]-nodes.get(p.a)['impact_'+k])<1e-10);
      assert.ok(Math.abs(p['impact_'+k]-p['single_a_'+k]-p['single_b_'+k]-p['synergy_'+k])<2e-11);
      sum+=p['synergy_'+k]/n.composite.scales[j]*n.composite.weights[j];
    });
    assert.ok(Math.abs(sum-p.score)<1e-7,'Components match '+period+'/'+variant+'/'+mode);
  }
  networks++;
}
const baseAnnual=model.network('annual','base','own');
assert.equal(baseAnnual.pairMap.get(pairKey('SDF','SEA')).rank,1);
assert.equal(model.stability('annual','SDF','SEA').count,4);
assert.deepEqual(model.stability('annual','SDF','SEA').ranks,[1,1,3,1]);
assert.deepEqual(model.stability('annual','SDF','SFO').ranks,[2,2,5,2]);
const ups=ext.structural.operators.items.find(x=>x.id==='19917');
const overlay=model.overlay({edges:ups.removal.edges,stats:ups.removal.stats,label:'Sin UPS'});
assert.equal(overlay.analysisAvailable,false);assert.equal(overlay.pairs.length,0);
assert.equal(overlay.n_edges,2180);assert.equal(overlay.metrics.global_efficiency,ups.removal.stats.global_efficiency);
assert.equal(overlay.nodes.reduce((s,n)=>s+n.degree,0),2*overlay.edges.length);
assert.throws(()=>model.network('annual','nonexistent','own'));
// Caracterización estructural: un bloque por período y regla, coherente con la red exportada.
let blocks=0;
for(const period of Object.keys(base.periods))for(const variant of ip.variants){
  const b=exp.networks[period][variant];assert.ok(b,'exploration block '+period+'/'+variant);
  const n=model.network(period,variant,'own');
  assert.equal(b.summary.n_nodes,100);assert.equal(b.summary.n_edges,n.n_edges);
  const degrees=new Map(n.nodes.map(x=>[x.id,x.degree]));
  exp.metadata.codes.forEach((code,i)=>{assert.equal(b.centrality_values.degree[i],degrees.get(code),'degree '+code);});
  for(const name of exp.metadata.centralities){assert.equal(b.centrality_values[name].length,100);assert.equal(b.centrality_ranks[name].length,100);}
  assert.equal(b.communities_weighted,undefined,'sin comunidades ponderadas');
  const c=b.communities;assert.equal(c.membership.length,100);
  assert.equal(c.communities.reduce((s,x)=>s+x.size,0),100);
  assert.equal(new Set(c.membership).size,c.n_communities);
  assert.ok(c.modularity>-1&&c.modularity<=1);
  assert.equal(b.degree_distribution.histogram.reduce((s,r)=>s+r.count,0),100);
  assert.ok(Math.abs(b.summary.density-2*n.n_edges/(100*99))<1e-12);
  assert.equal(b.summary.rich_club,undefined,'sin club de ricos');
  assert.deepEqual(Object.keys(b.models.models),['erdos_renyi','watts_strogatz','barabasi_albert']);
  for(const m of Object.values(b.models.models)){assert.ok(m.metrics.average_clustering.mean>0);assert.ok(Math.abs(m.metrics.n_edges.mean-n.n_edges)/n.n_edges<0.05,'modelos con casi los mismos enlaces');}
  blocks++;
}
assert.equal(blocks,20);
assert.equal(exp.networks.annual.base.summary.max_degree,89);
assert.deepEqual(exp.metadata.centralities,['degree','betweenness','closeness','eigenvector']);
assert.equal(exp.networks.annual.base.models.course_match,'barabasi_albert');
// Laboratorio: mismas definiciones que el notebook (valores de NetworkX para la red de un hub).
const lab=require('./dist/lab.js');
const hub=lab.scenario(lab.NETWORKS.hub,'H','D').rows;
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,a+' ≠ '+b);
close(hub.global.base,2/3);close(hub.local.base,13/36);close(hub.natural.base,0.9711866906539357);
close(hub.global.impactA,0.4666666667);close(hub.local.impactB,-0.1055555556);close(hub.global.synergy,-0.1333333333);
const backup=lab.scenario(lab.NETWORKS.backup,'H1','H2').rows;
for(const k of ['global','local','natural'])assert.ok(backup[k].synergy>0,'hubs que se respaldan: sinergia positiva');
console.log('PASS: '+networks+' period/rule/scale networks; graph/indices/trace, stability, operator overlay and '+blocks+' structure blocks; laboratorio verificado.');
