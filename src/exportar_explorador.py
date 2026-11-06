"""Exporta estabilidad y escenarios completos sin cambiar el análisis científico."""
from pathlib import Path
from itertools import combinations
import json
import hashlib
import numpy as np
import pandas as pd
import networkx as nx
from analisis_red import simulate_period, entropy_composite, write_json, SHORT

VARIANT_ORDER = ['base','half_months','all_months','min_monthly_freight']
PAIR_FIELDS = ['score_own','rank_own','score_comparable','rank',
                  'synergy_global','synergy_local','synergy_natural',
                  'impact_global','impact_local','impact_natural']


def stability_table(frames, top_k=20):
    """Cuenta pertenencia exacta al top_k, con desempate por IDs, no rank<=k."""
    if 'base' not in frames or not isinstance(top_k,int) or isinstance(top_k,bool) or top_k<1:
        raise ValueError('Se requiere base y top_k entero positivo.')
    base=frames['base']
    required={'pair_key','a_id','b_id','a','b','score_comparable','rank'}
    for name,frame in frames.items():
        if not required.issubset(frame.columns) or frame.pair_key.isna().any() or frame.pair_key.duplicated().any():
            raise ValueError('Parejas ausentes, duplicadas o columnas incompletas: '+name)
        if set(frame.pair_key)!=set(base.pair_key):
            raise ValueError('Cada regla debe contener exactamente las mismas parejas.')
        if not np.isfinite(frame[['score_comparable','rank']].to_numpy(dtype=float)).all():
            raise ValueError('Índices y rangos deben ser finitos.')
        expected=[f'{min(int(a),int(b))}-{max(int(a),int(b))}' for a,b in zip(frame.a_id,frame.b_id)]
        if expected!=frame.pair_key.tolist() or frame.a_id.eq(frame.b_id).any():
            raise ValueError('Identificadores incoherentes con pair_key.')
        aligned=frame.set_index('pair_key').loc[base.pair_key]
        for column in ['a_id','b_id','a','b']:
            if aligned[column].tolist()!=base[column].tolist():
                raise ValueError('Identificadores o códigos no corresponden a la pareja base.')
    keys = frames['base'].pair_key.tolist()
    result = frames['base'][['pair_key','a_id','b_id','a','b']].copy().set_index('pair_key')
    membership = []
    for variant,frame in frames.items():
        f = frame.set_index('pair_key').reindex(keys)
        if f.score_comparable.isna().any():
            raise ValueError('Faltan parejas en la comparación de estabilidad.')
        ranks = f.score_comparable.rank(ascending=False,method='average')
        np.testing.assert_allclose(ranks,f['rank'],atol=1e-10)
        top = set(f.sort_values(['score_comparable','a_id','b_id'],
                               ascending=[False,True,True]).head(top_k).index)
        result[variant+'_rank'] = ranks
        result[variant+'_top'] = result.index.isin(top)
        membership.append(result[variant+'_top'].to_numpy())
    columns = [v+'_rank' for v in frames]
    result['top_count'] = np.asarray(membership,dtype=int).sum(axis=0)
    result['rank_min'] = result[columns].min(axis=1)
    result['rank_max'] = result[columns].max(axis=1)
    result['rank_mean'] = result[columns].mean(axis=1)
    return result.reset_index()


def export_explorer(root):
    root = Path(root)
    out = root/'resultados/ampliaciones'
    extensions = json.loads((out/'extensions.json').read_text())
    catalog = pd.read_csv(root/'resultados/catalogo_aeropuertos.csv')
    ids = catalog.airport_id.astype(int).tolist()
    codes = catalog.code.tolist()
    code_by_id = dict(zip(ids,codes))
    ij = np.array(list(combinations(range(len(ids)),2)),dtype=int)
    keys = [f'{min(ids[i],ids[j])}-{max(ids[i],ids[j])}' for i,j in ij]
    structure = extensions['structural']
    periods, stable, summaries = {},{},[]
    for period, scenario_info in structure['sensitivity']['periods'].items():
        periods[period] = {}
        frames = {}
        for variant,info in scenario_info.items():
            frame = pd.read_csv(out/f'pares_sensibilidad_{period}_{variant}.csv')
            if frame.pair_key.duplicated().any() or set(frame.pair_key)!=set(keys):
                raise ValueError('El CSV debe contener exactamente las parejas esperadas, sin extras ni duplicados.')
            frame = frame.set_index('pair_key').loc[keys].reset_index()
            for col,expected in [('a_id',[ids[i] for i,j in ij]),('b_id',[ids[j] for i,j in ij]),
                                 ('a',[codes[i] for i,j in ij]),('b',[codes[j] for i,j in ij])]:
                if frame[col].tolist()!=expected:
                    raise ValueError('Extremos del CSV incompatibles con el catálogo: '+col)
            frames[variant] = frame
            edges = pd.read_csv(out/f'enlaces_sensibilidad_{period}_{variant}.csv')
            graph = nx.Graph()
            graph.add_nodes_from(ids)
            graph.add_weighted_edges_from([(int(e.u),int(e.v),float(e.freight_lb)) for e in edges.itertuples()],weight='freight_lb')
            adj = nx.to_numpy_array(graph,nodelist=ids,weight=None,dtype=bool)
            cache = root/'cache'/f'{period}.npz' if variant=='base' else root/'cache/ampliaciones'/f'{period}_{variant}.npz'
            simulation = simulate_period(adj,cache,use_cache=True,verbose=False)
            np.testing.assert_array_equal(simulation['pair_indices'],ij)
            np.testing.assert_allclose(frame[[f'synergy_{s}' for s in SHORT]],simulation['synergy'],atol=1e-12,rtol=1e-10)
            np.testing.assert_allclose(frame[[f'impact_{s}' for s in SHORT]],simulation['joint_impact'],atol=1e-12,rtol=1e-10)
            own=entropy_composite(simulation['synergy'])
            np.testing.assert_allclose(own['score'],frame.score_own,atol=1e-12)
            common=structure['sensitivity']['calibration']
            comparable=entropy_composite(simulation['synergy'],scales=common['scales'],weights=common['weights'])
            np.testing.assert_allclose(comparable['score'],frame.score_comparable,atol=1e-12)
            np.testing.assert_allclose(own['weights'],info['own_calibration']['weights'],atol=1e-12)
            if variant=='base':
                # La red base ya se distribuye en network.json; solo se agrega su escala de sensibilidad.
                periods[period][variant] = {'comparison_pairs':frame[['score_comparable','rank']].to_numpy().tolist()}
                continue
            between = nx.betweenness_centrality(graph,normalized=False,weight=None)
            node_rows=[]
            for index,id in enumerate(ids):
                incident=sum(graph[id][neighbor]['freight_lb'] for neighbor in graph[id])
                node_rows.append({'id':code_by_id[id],'airport_id':id,'degree':graph.degree(id),
                    'degree_centrality':graph.degree(id)/(len(ids)-1),'betweenness':between[id],
                    'freight_lb':float(incident),**{f'impact_{s}':float(simulation['single_impact'][index,j]) for j,s in enumerate(SHORT)}})
            periods[period][variant] = {
                'label':info['label'],'n_nodes':100,'n_edges':len(edges),'nodes':node_rows,
                'edges':[{'source':code_by_id[int(e.u)],'target':code_by_id[int(e.v)],
                          'freight_lb':float(e.freight_lb),'months_present':int(e.months_present)}
                         for e in edges.itertuples()],
                'metrics':{name:info['stats'][name] for name in ['global_efficiency','local_efficiency','natural_connectivity']},
                'composite':info['own_calibration'],
                'pairs':frame[PAIR_FIELDS].to_numpy().tolist(),
                'freight_scope':'Carga incidente de enlaces internos retenidos por la regla.',
            }
        stability = stability_table(frames)
        stability.to_csv(out/f'estabilidad_parejas_{period}.csv',index=False)
        stable[period] = stability[['top_count','rank_min','rank_max','rank_mean']+
                                   [v+'_rank' for v in VARIANT_ORDER]].to_numpy().tolist()
        robust = stability[stability.top_count.eq(4)].sort_values(['rank_mean','a_id','b_id'])
        summaries.append({'period':period,'pairs_top20_all_rules':len(robust),
                          'pairs':[{'a':r.a,'b':r.b,'rank_min':r.rank_min,'rank_max':r.rank_max} for r in robust.itertuples()]})
    result = {
        'metadata':{'version':3,'year':2025,'n_nodes':100,'n_pairs':4950,
            'source_sha256':extensions['metadata']['raw_zip_sha256'],
            'stability_scope':'Frecuencia entre cuatro reglas de construcción, no probabilidad ni intervalo de confianza.',
            'rank_ties':'Rango medio; top20 exacto con desempate por a_id,b_id.',
            'freight_scope':'Base: todos los segmentos depurados incidentes. Variantes: enlaces internos retenidos.',
            'notes':['Los índices propios y comunes son modos distintos y siempre se identifican.',
                     'La pérdida de un operador no incluye fallos de nodos adicionales precomputados.',
                     'La estabilidad se compara dentro del mismo período con calibración común.']},
        'codes':codes,'airport_ids':ids,'pair_indices':ij.tolist(),'pair_fields':PAIR_FIELDS,
        'variants':VARIANT_ORDER,'sensitivity_calibration':structure['sensitivity']['calibration'],'periods':periods,'stability':stable,'stability_summary':summaries,
    }
    write_json(out/'explorador.json',result)
    # Compacto para reducir carga y memoria de la app; conserva exactamente los valores.
    (root/'app/dist/data/interactive.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    write_json(out/'estabilidad_resumen.json',summaries)
    return result


if __name__=='__main__':
    result=export_explorer((lambda here: here if (here/'app').exists() else here.parent)(Path(__file__).resolve().parent))
    print('Exportación completa. Parejas estables:',result['stability_summary'][0])
