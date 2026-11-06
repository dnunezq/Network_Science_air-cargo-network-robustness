/* Mapping of exported scientific results. No network metrics are inferred here. */
(function(root){
  'use strict';
  const key=(a,b)=>[String(a),String(b)].sort().join('|');
  const short=['global','local','natural'];
  class ExplorerData {
    constructor(base,interactive){
      this.base=base;this.ip=interactive;this.cache=new Map();
      this.codes=interactive?.codes||base.airports.map(x=>String(x.id));
      this.pairIndex=new Map((interactive?.pair_indices||[]).map((ij,k)=>[key(this.codes[ij[0]],this.codes[ij[1]]),k]));
    }
    network(period='annual',variant='base',mode='own'){
      const id=period+'|'+variant+'|'+mode;
      if(this.cache.has(id))return this.cache.get(id);
      const original=this.base.periods[period],src=this.ip?.periods?.[period]?.[variant];
      if(!original||(!src&&variant!=='base'))throw new Error('Este escenario no está disponible.');
      const common=this.ip?.sensitivity_calibration;
      const calibration=mode==='common'&&common?{weights:common.weights,scales:common.scales}:(variant==='base'?original.composite:src.composite);
      let nodes,edges,pairs;
      if(variant==='base'){
        nodes=original.nodes;edges=original.edges;
        pairs=original.pairs.map(p=>{
          const index=this.pairIndex.get(key(p.a,p.b)),value=src?.comparison_pairs?.[index];
          return {...p,score_own:p.score,rank_own:p.rank,
            score_sensitivity:value?.[0]??null,rank_sensitivity:value?.[1]??null,
            score:mode==='common'&&value?value[0]:p.score,
            rank:mode==='common'&&value?value[1]:p.rank,
            score_comparable:value?.[0]??p.score_comparable,
            rank_comparable:value?.[1]??p.rank_comparable};
        });
      }else{
        nodes=src.nodes;edges=src.edges;
        const nodeMap=new Map(nodes.map(n=>[String(n.id),n]));
        const linked=new Set(edges.map(e=>key(e.source,e.target)));
        pairs=src.pairs.map((values,k)=>{
          const ij=this.ip.pair_indices[k],a=this.codes[ij[0]],b=this.codes[ij[1]];
          const r={};this.ip.pair_fields.forEach((name,j)=>r[name]=values[j]);
          const p={a,b,a_id:this.ip.airport_ids[ij[0]],b_id:this.ip.airport_ids[ij[1]],
            ...r,score_sensitivity:r.score_comparable,rank_sensitivity:r.rank,
            score:mode==='common'?r.score_comparable:r.score_own,
            rank:mode==='common'?r.rank:r.rank_own,direct:linked.has(key(a,b))};
          for(const s of short){p['single_a_'+s]=nodeMap.get(a)['impact_'+s];p['single_b_'+s]=nodeMap.get(b)['impact_'+s];}
          return p;
        });
      }
      const network={...(variant==='base'?original:src),nodes,edges,pairs,
        n_nodes:nodes.length,n_edges:edges.length,composite:calibration,
        label:variant==='base'?'Red base':src.label,analysisAvailable:true,
        calibration_label:mode==='common'?'Índice común entre escenarios':'Índice propio de esta red',
        freight_scope:variant==='base'?'Todos los segmentos depurados incidentes.':'Enlaces internos retenidos por esta regla.',
        pairMap:new Map(pairs.map(p=>[key(p.a,p.b),p]))};
      this.cache.set(id,network);return network;
    }
    overlay(overlay){
      const counts=new Map(this.codes.map(c=>[c,{id:c,degree:0,freight_lb:0,betweenness:null}]));
      for(const e of overlay.edges)for(const c of [e.source,e.target]){
        const n=counts.get(String(c));if(n){n.degree++;n.freight_lb+=Number(e.freight_lb)||0;}
      }
      const nodes=[...counts.values()].map(n=>({...n,degree_centrality:n.degree/(this.codes.length-1)}));
      return {label:overlay.label,n_nodes:nodes.length,n_edges:overlay.edges.length,
        nodes,edges:overlay.edges,pairs:[],pairMap:new Map(),analysisAvailable:false,
        metrics:overlay.stats||{},composite:null,freight_scope:'Carga atribuida a enlaces internos de esta vista.',
        calibration_label:'Capa por operador · sin índice de fallos de aeropuertos'};
    }
    stability(period,a,b){
      const index=this.pairIndex.get(key(a,b)),r=this.ip?.stability?.[period]?.[index];
      return r?{count:r[0],min:r[1],max:r[2],mean:r[3],ranks:r.slice(4)}:null;
    }
  }
  const api={ExplorerData,pairKey:key};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.CargoData=api;
})(typeof window!=='undefined'?window:globalThis);
