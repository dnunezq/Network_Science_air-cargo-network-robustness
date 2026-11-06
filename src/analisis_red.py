"""Funciones reproducibles del proyecto de carga aérea 2025.

El notebook incorpora este código completo; este módulo permite ejecutar el
mismo análisis por terminal. Las métricas se calculan sobre grafos binarios.
"""
# %% IMPORTS
from pathlib import Path
from itertools import combinations
from datetime import datetime, timezone
import hashlib
import json
import math
import time
import zipfile
import shutil
import platform
import importlib.metadata

import numpy as np
import pandas as pd
import networkx as nx
from numba import njit
from scipy.linalg import eigvalsh
from scipy.special import logsumexp
from scipy.stats import spearmanr
from threadpoolctl import threadpool_limits

METRICS = ['global_efficiency', 'local_efficiency', 'natural_connectivity']
SHORT = ['global', 'local', 'natural']
PERIODS = {'annual': 'Año 2025', 'T1': 'Enero–marzo', 'T2': 'Abril–junio',
           'T3': 'Julio–septiembre', 'T4': 'Octubre–diciembre'}
ALGORITHM_VERSION = '2025-v1.0-exact-binary'

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False), encoding='utf-8')

# %% DATA
def read_t100(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None, 'El ZIP no supera la comprobación CRC.'
        names = [x for x in z.namelist() if x.lower().endswith('.csv')]
        assert len(names) == 1, 'Se requiere un único CSV de T-100.'
        with z.open(names[0]) as f:
            return pd.read_csv(f, low_memory=False)

def clean_t100(raw, year=2025):
    """Audita todos los registros; elimina duplicados exactos y filas no válidas.

    Filas distintas del mismo par no son duplicados: pueden representar
    meses, transportistas, equipos o clases de servicio diferentes.
    """
    required = ['YEAR', 'MONTH', 'QUARTER', 'ORIGIN_AIRPORT_ID',
                'DEST_AIRPORT_ID', 'ORIGIN', 'DEST', 'FREIGHT', 'MAIL',
                'DISTANCE', 'DEPARTURES_PERFORMED']
    assert set(required).issubset(raw.columns)
    assert set(raw.YEAR.dropna().unique()) == {year}, 'El archivo no es exclusivamente de 2025.'
    assert set(raw.MONTH.dropna().unique()) == set(range(1, 13)), 'Faltan meses.'
    audit = {'raw_rows': len(raw), 'columns': len(raw.columns),
             'source_years': sorted(int(x) for x in raw.YEAR.dropna().unique()),
             'rows_by_month': {str(int(k)): int(v) for k,v in raw.groupby('MONTH').size().items()},
             'missing_required': {c: int(raw[c].isna().sum()) for c in required},
             'exact_duplicates': int(raw.duplicated().sum())}
    df = raw.drop_duplicates().copy()
    counts = [{'stage': 'Registros originales', 'remaining': len(raw), 'removed': 0},
              {'stage': 'Eliminar duplicados exactos', 'remaining': len(df),
               'removed': len(raw)-len(df)}]
    checks = [
        ('Identificadores, códigos y calendario válidos',
         df.ORIGIN_AIRPORT_ID.notna() & df.DEST_AIRPORT_ID.notna() &
         df.ORIGIN.notna() & df.DEST.notna() & df.YEAR.eq(year) & df.MONTH.isin(range(1,13))),
        ('Carga finita y estrictamente positiva', np.isfinite(df.FREIGHT) & df.FREIGHT.gt(0)),
        ('Origen diferente del destino', df.ORIGIN_AIRPORT_ID.ne(df.DEST_AIRPORT_ID))]
    for name, mask in checks:
        n = len(df)
        df = df.loc[mask.reindex(df.index)].copy()
        counts.append({'stage': name, 'remaining': len(df), 'removed': n-len(df)})
    assert (df.QUARTER == ((df.MONTH-1)//3+1)).all(), 'QUARTER no corresponde a MONTH.'
    for c in ['YEAR','MONTH','QUARTER','ORIGIN_AIRPORT_ID','DEST_AIRPORT_ID']:
        assert (df[c] == df[c].astype(int)).all()
        df[c] = df[c].astype(int)
    audit.update(clean_rows=len(df), cleaning_steps=counts,
                 invalid_distance_rows=int((df.DISTANCE.isna() | df.DISTANCE.le(0)).sum()),
                 clean_segment_freight_lb=float(df.FREIGHT.sum()),
                 nonnegative_mail=bool(df.MAIL.fillna(0).ge(0).all()))
    return df, audit

def airport_catalog(clean, top_n=100):
    origin = clean[['ORIGIN_AIRPORT_ID','ORIGIN','ORIGIN_CITY_NAME','ORIGIN_STATE_ABR','FREIGHT']].copy()
    dest = clean[['DEST_AIRPORT_ID','DEST','DEST_CITY_NAME','DEST_STATE_ABR','FREIGHT']].copy()
    cols = ['airport_id','code','city','state','freight_lb']
    origin.columns = dest.columns = cols
    endpoints = pd.concat([origin,dest], ignore_index=True)
    assert endpoints.groupby('airport_id').code.nunique().max() == 1, 'Revisar cambios de códigos dentro de 2025.'
    totals = endpoints.groupby('airport_id', as_index=False).agg(
        annual_freight_lb=('freight_lb','sum'), code=('code','first'),
        city=('city','first'), state=('state','first'))
    totals = totals.sort_values(['annual_freight_lb','airport_id'], ascending=[False,True])
    selected = totals.head(top_n).copy().reset_index(drop=True)
    assert len(selected) == top_n and selected.code.is_unique
    selected['annual_rank'] = np.arange(1, top_n+1)
    return selected, totals

def aggregate_routes(clean):
    return clean.groupby(['YEAR','QUARTER','MONTH','ORIGIN_AIRPORT_ID','DEST_AIRPORT_ID'],
                         as_index=False).agg(freight_lb=('FREIGHT','sum'),
                         mail_lb=('MAIL','sum'), departures=('DEPARTURES_PERFORMED','sum'),
                         distance_miles=('DISTANCE','median'), source_rows=('FREIGHT','size'))

def build_networks(routes, airports):
    ids = airports.airport_id.astype(int).tolist()
    index = {a:i for i,a in enumerate(ids)}
    result = {}
    for key,label in PERIODS.items():
        r = routes if key == 'annual' else routes[routes.QUARTER.eq(int(key[1]))]
        inside = r[r.ORIGIN_AIRPORT_ID.isin(ids) & r.DEST_AIRPORT_ID.isin(ids)].copy()
        inside['u'] = np.minimum(inside.ORIGIN_AIRPORT_ID, inside.DEST_AIRPORT_ID)
        inside['v'] = np.maximum(inside.ORIGIN_AIRPORT_ID, inside.DEST_AIRPORT_ID)
        edges = inside.groupby(['u','v'],as_index=False).agg(freight_lb=('freight_lb','sum'))
        adj = np.zeros((len(ids),len(ids)), dtype=np.bool_)
        g = nx.Graph()
        g.add_nodes_from(ids)
        for row in edges.itertuples():
            adj[index[row.u],index[row.v]] = adj[index[row.v],index[row.u]] = True
            g.add_edge(int(row.u),int(row.v),freight_lb=float(row.freight_lb))
        assert np.array_equal(adj,adj.T) and not np.diag(adj).any()
        incident = pd.concat([
            r.groupby('ORIGIN_AIRPORT_ID').freight_lb.sum(),
            r.groupby('DEST_AIRPORT_ID').freight_lb.sum()], axis=1).fillna(0).sum(axis=1)
        centrality = nx.betweenness_centrality(g, normalized=False, weight=None)
        nodes = pd.DataFrame({'airport_id':ids,
            'freight_lb':[float(incident.get(a,0)) for a in ids],
            'degree':[g.degree(a) for a in ids],
            'degree_centrality':[g.degree(a)/(len(ids)-1) for a in ids],
            'betweenness':[centrality[a] for a in ids]})
        stats = {'n_nodes':len(ids),'n_edges':len(edges), 'density':nx.density(g),
            'components':nx.number_connected_components(g),
            'largest_component':len(max(nx.connected_components(g),key=len)),
            'isolates':len(list(nx.isolates(g))),
            'freight_lb':float(inside.freight_lb.sum()),
            'all_network_freight_lb':float(r.freight_lb.sum()),
            'inside_freight_share':float(inside.freight_lb.sum()/r.freight_lb.sum())}
        result[key] = {'label':label,'adj':adj,'graph':g,'edges':edges,'nodes':nodes,'stats':stats}
    return result

# %% METRICS
@njit
def _contains(lo, hi, k):
    if k < 64:
        return (lo & (np.uint64(1) << np.uint64(k))) != 0
    return (hi & (np.uint64(1) << np.uint64(k-64))) != 0

@njit
def _efficiency_bits(rows0, rows1, allow0, allow1):
    """Eficiencia exacta: distancias 1/2 con conjuntos; BFS para las restantes."""
    n = len(rows0)
    active = np.empty(n, dtype=np.int64)
    size = 0
    for k in range(n):
        if _contains(allow0,allow1,k):
            active[size] = k
            size += 1
    if size < 2:
        return 0.0
    total = 0.0
    for ii in range(size):
        i = active[ii]
        distances = np.full(n,-1,dtype=np.int64)
        searched = False
        for jj in range(ii+1,size):
            j = active[jj]
            if _contains(rows0[i],rows1[i],j):
                total += 1.0
            elif ((rows0[i] & rows0[j] & allow0) != 0 or
                  (rows1[i] & rows1[j] & allow1) != 0):
                total += 0.5
            else:
                if not searched:
                    queue = np.empty(n,dtype=np.int64)
                    queue[0], distances[i] = i, 0
                    head, tail = 0, 1
                    while head < tail:
                        v = queue[head]
                        head += 1
                        for kk in range(size):
                            w = active[kk]
                            if distances[w] < 0 and _contains(rows0[v],rows1[v],w):
                                distances[w] = distances[v]+1
                                queue[tail] = w
                                tail += 1
                    searched = True
                if distances[j] > 0:
                    total += 1.0/distances[j]
    return 2.0*total/(size*(size-1))

@njit
def _efficiencies(adj):
    n = len(adj)
    if n == 0:
        return 0.0, 0.0
    r0 = np.zeros(n, dtype=np.uint64)
    r1 = np.zeros(n, dtype=np.uint64)
    a0, a1 = np.uint64(0), np.uint64(0)
    for j in range(n):
        if j < 64:
            a0 |= np.uint64(1) << np.uint64(j)
        else:
            a1 |= np.uint64(1) << np.uint64(j-64)
        for i in range(n):
            if adj[i,j]:
                if j < 64:
                    r0[i] |= np.uint64(1) << np.uint64(j)
                else:
                    r1[i] |= np.uint64(1) << np.uint64(j-64)
    global_eff = _efficiency_bits(r0,r1,a0,a1)
    local_eff = 0.0
    for i in range(n):
        local_eff += _efficiency_bits(r0,r1,r0[i],r1[i])
    return global_eff, local_eff/n

def robustness_metrics(adj):
    """Ecuaciones 1–4; denominadores corresponden al grafo restante.

    A es binaria, simétrica, sin diagonal. Los pares desconectados aportan
    cero a eficiencia. Para 0 nodos definimos las tres métricas como cero.
    El cálculo por conjuntos soporta hasta 128 nodos (proyecto:100).
    """
    a = np.asarray(adj,dtype=np.bool_)
    assert a.ndim == 2 and a.shape[0] == a.shape[1] and len(a) <= 128
    assert np.array_equal(a,a.T) and not np.diag(a).any()
    if not len(a):
        return np.zeros(3)
    g,l = _efficiencies(a)
    values = eigvalsh(a.astype(float), check_finite=False)
    natural = float(logsumexp(values)-np.log(len(a)))
    return np.array([g,l,natural])

def verify_metrics():
    """Contraste contra NetworkX y casos con solución conocida, sin aproximar."""
    cases = [('vacío',nx.empty_graph(5)),('completo',nx.complete_graph(7)),
             ('camino',nx.path_graph(9)),('ciclo',nx.cycle_graph(8)),
             ('estrella',nx.star_graph(8)),('dos componentes',nx.disjoint_union(nx.path_graph(4),nx.path_graph(5))),
             ('cruce de 64 bits',nx.path_graph(70))]
    for n in [6,12,65,100]:
        for p in [.04,.25,.75]:
            cases.append((f'aleatorio n={n},p={p}',nx.gnp_random_graph(n,p,seed=2025)))
    for name,g in cases:
        a = nx.to_numpy_array(g,dtype=bool)
        got = robustness_metrics(a)
        expected = [nx.global_efficiency(g),nx.local_efficiency(g),
                    float(np.log(np.exp(np.linalg.eigvalsh(a.astype(float))).mean()))]
        np.testing.assert_allclose(got,expected,atol=1e-12,rtol=1e-12,err_msg=name)
    full = robustness_metrics(nx.to_numpy_array(nx.complete_graph(7),dtype=bool))
    np.testing.assert_allclose(full[:2],[1.,1.])
    # Diamante: A y B no son adyacentes, pero retirar ambos aísla los extremos.
    g = nx.cycle_graph(4)
    a = nx.to_numpy_array(g,dtype=bool)
    base = robustness_metrics(a)
    one = base-robustness_metrics(np.delete(np.delete(a,1,0),1,1))
    two = base-robustness_metrics(np.delete(np.delete(a,3,0),3,1))
    keep = [0,2]
    joint = base-robustness_metrics(a[np.ix_(keep,keep)])
    assert (joint-one-two)[0] > 0
    return {'graphs_checked':len(cases),'networkx_agreement':True,
            'diamond_global_synergy':float((joint-one-two)[0])}

# %% SIMULATION
def simulate_period(adj, cache_path, use_cache=True, verbose=True):
    """Todas las eliminaciones individuales y todos los pares, con caché validada."""
    fingerprint = hashlib.sha256(ALGORITHM_VERSION.encode()+np.ascontiguousarray(adj).tobytes()).hexdigest()
    cache_path = Path(cache_path)
    if use_cache and cache_path.exists():
        with np.load(cache_path,allow_pickle=False) as z:
            if str(z['fingerprint']) == fingerprint:
                if verbose: print(f'{cache_path.stem}: caché verificada',flush=True)
                return {k:z[k].copy() for k in ['baseline','single_impact','pair_indices','joint_impact','synergy']}
    t0 = time.perf_counter()
    n = len(adj)
    baseline = robustness_metrics(adj)
    single = np.zeros((n,3))
    with threadpool_limits(limits=1):
        for i in range(n):
            keep = np.arange(n) != i
            single[i] = baseline-robustness_metrics(adj[np.ix_(keep,keep)])
        pairs = np.array(list(combinations(range(n),2)),dtype=int)
        joint = np.zeros((len(pairs),3))
        for k,(i,j) in enumerate(pairs):
            keep = (np.arange(n)!=i)&(np.arange(n)!=j)
            joint[k] = baseline-robustness_metrics(adj[np.ix_(keep,keep)])
            if verbose and (k+1)%1000 == 0:
                print(f'{cache_path.stem}: {k+1}/{len(pairs)} pares ({time.perf_counter()-t0:.1f} s)',flush=True)
    synergy = joint-single[pairs[:,0]]-single[pairs[:,1]]
    result = dict(baseline=baseline,single_impact=single,pair_indices=pairs,
                  joint_impact=joint,synergy=synergy)
    assert all(np.isfinite(v).all() for v in result.values())
    cache_path.parent.mkdir(parents=True,exist_ok=True)
    temp = cache_path.with_suffix('.tmp')
    with open(temp,'wb') as f:
        np.savez_compressed(f,fingerprint=fingerprint,**result)
    temp.replace(cache_path)
    if verbose: print(f'{cache_path.stem}: terminado en {time.perf_counter()-t0:.1f} s',flush=True)
    return result

def entropy_composite(synergies, scales=None, weights=None):
    """Ecs.7–12: escala máximo absoluto; probabilidades con magnitudes.

    Conserva signo en el índice final. Columnas nulas o constantes en
    magnitud tienen peso informativo cero; si todas son degeneradas, pesos0.
    """
    s = np.asarray(synergies,dtype=float)
    scales = np.max(np.abs(s),axis=0) if scales is None else np.asarray(scales)
    z = np.divide(s,scales,out=np.zeros_like(s),where=scales>1e-14)
    masses = np.abs(z).sum(axis=0)
    p = np.divide(np.abs(z),masses,out=np.zeros_like(z),where=masses>0)
    logs = np.zeros_like(p)
    np.log(p,out=logs,where=p>0)
    entropy = -(p*logs).sum(axis=0)/np.log(len(s))
    info = np.where(masses>1e-14,np.maximum(0,1-entropy),0)
    info[info < 1e-12] = 0
    if weights is None:
        weights = info/info.sum() if info.sum()>0 else np.zeros(s.shape[1])
    return {'score':z@weights,'normalized':z,'scales':scales,
            'weights':np.asarray(weights),'entropy':entropy}

def attach_results(networks, simulations, airports):
    annual_weights = entropy_composite(simulations['annual']['synergy'])['weights']
    common_scales = np.max(np.abs(np.vstack([simulations[q]['synergy'] for q in ['T1','T2','T3','T4']])),axis=0)
    ids = airports.airport_id.to_numpy()
    codes = airports.code.to_numpy()
    for period,sim in simulations.items():
        indices = sim['pair_indices']
        original = entropy_composite(sim['synergy'])
        common = entropy_composite(sim['synergy'],scales=common_scales,weights=annual_weights)
        rows = pd.DataFrame({'a_id':ids[indices[:,0]],'b_id':ids[indices[:,1]],
                             'a':codes[indices[:,0]],'b':codes[indices[:,1]],
                             'direct':networks[period]['adj'][indices[:,0],indices[:,1]],
                             'score':original['score'],'score_comparable':common['score']})
        rows['pair_key'] = [f'{min(int(a),int(b))}-{max(int(a),int(b))}' for a,b in zip(rows.a_id,rows.b_id)]
        for j,name in enumerate(SHORT):
            rows[f'synergy_{name}'] = sim['synergy'][:,j]
            rows[f'impact_{name}'] = sim['joint_impact'][:,j]
            rows[f'single_a_{name}'] = sim['single_impact'][indices[:,0],j]
            rows[f'single_b_{name}'] = sim['single_impact'][indices[:,1],j]
        # Rango medio respeta empates para Spearman; selección top20 estable por ID.
        rows['rank'] = rows.score.rank(ascending=False,method='average')
        rows['rank_comparable'] = rows.score_comparable.rank(ascending=False,method='average')
        networks[period]['pairs'] = rows
        networks[period]['composite'] = {k:v.tolist() for k,v in original.items() if k in ['weights','scales','entropy']}
        networks[period]['stats'].update(dict(zip(METRICS,sim['baseline'].tolist())))
        for j,name in enumerate(SHORT):
            networks[period]['nodes'][f'impact_{name}'] = sim['single_impact'][:,j]
    return {'weights_from_annual':annual_weights.tolist(),'scales_from_quarters':common_scales.tolist(),
            'method':'Pesos de entropía anuales; máximo absoluto común de los cuatro trimestres.'}

def compare_quarters(networks, top_k=20):
    quarters = ['T1','T2','T3','T4']
    records = []
    for p,q in combinations(quarters,2):
        a = networks[p]['pairs'].set_index('pair_key').sort_index()
        b = networks[q]['pairs'].set_index('pair_key').reindex(a.index)
        ta = set(a.sort_values(['score_comparable','a_id','b_id'],ascending=[False,True,True]).head(top_k).index)
        tb = set(b.sort_values(['score_comparable','a_id','b_id'],ascending=[False,True,True]).head(top_k).index)
        ga,gb = networks[p]['adj'],networks[q]['adj']
        union = int(np.logical_or(ga,gb).sum()/2)
        common = int(np.logical_and(ga,gb).sum()/2)
        records.append({'period_a':p,'period_b':q,
            'spearman':float(spearmanr(a.score_comparable,b.score_comparable).statistic),
            'spearman_period_specific':float(spearmanr(a.score,b.score).statistic),
            'top_k':top_k,'shared_top':len(ta&tb),'overlap':len(ta&tb)/top_k,
            'top_jaccard':len(ta&tb)/len(ta|tb),'edge_jaccard':common/union,
            'edges_common':common,'edges_lost':int(np.logical_and(ga,~gb).sum()/2),
            'edges_added':int(np.logical_and(~ga,gb).sum()/2)})
    trajectories = networks['T1']['pairs'][['pair_key','a','b']].copy().set_index('pair_key')
    for q in quarters:
        t = networks[q]['pairs'].set_index('pair_key')
        trajectories[f'{q}_rank'] = t.rank_comparable
        trajectories[f'{q}_score'] = t.score_comparable
    trajectories['top20_quarters'] = sum(trajectories[f'{q}_rank'].le(top_k).astype(int) for q in quarters)
    trajectories['rank_range'] = trajectories[[f'{q}_rank' for q in quarters]].max(axis=1)-trajectories[[f'{q}_rank' for q in quarters]].min(axis=1)
    return pd.DataFrame(records), trajectories.reset_index()

# %% EXPLANATORY
def haversine_km(lat1,lon1,lat2,lon2):
    p1,p2 = np.radians(lat1),np.radians(lat2)
    dp,dl = p2-p1,np.radians(lon2)-np.radians(lon1)
    a = np.sin(dp/2)**2+np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
    return 6371.0088*2*np.arcsin(np.sqrt(np.clip(a,0,1)))

def pair_predictors(network, airports):
    p = network['pairs'].copy()
    nodes = network['nodes'].set_index('airport_id')
    geo = airports.set_index('airport_id')
    for prefix,source,operation in [
        ('freight_sum','freight_lb','sum'),('degree_sum','degree_centrality','sum'),
        ('degree_diff','degree_centrality','diff'),('betweenness_diff','betweenness','diff')]:
        x,y = p.a_id.map(nodes[source]),p.b_id.map(nodes[source])
        p[prefix] = x+y if operation=='sum' else abs(x-y)
    p['geo_distance_km'] = haversine_km(p.a_id.map(geo.lat),p.a_id.map(geo.lon),p.b_id.map(geo.lat),p.b_id.map(geo.lon))
    return p

def mrqap_models(predictors, airport_ids, permutations=9999, seed=2025):
    """MRQAP con permutación simultánea de filas/columnas de Y.

    Especificaciones predefinidas inspiradas en modelos1–5; no seleccionamos
    variables por sus p de2025. Continuas estandarizadas antes de interactuar.
    Contraste bilateral de coeficientes; inferencia exploratoria sin ajuste
    múltiple. No equivale a MRQAP-DSP ni demuestra causalidad.
    """
    continuous = ['freight_sum','degree_sum','degree_diff','betweenness_diff','geo_distance_km']
    z = predictors[continuous].astype(float)
    means, scales = z.mean(),z.std(ddof=0)
    assert scales.gt(0).all()
    z = (z-means)/scales
    z['direct'] = predictors.direct.astype(float)
    for col in continuous:
        z[col+'×direct'] = z[col]*z.direct
    specs = {'M1':continuous, 'M2':['direct'], 'M3':continuous+['direct'],
             'M4':continuous+['direct']+[c+'×direct' for c in continuous],
             'M5':['degree_sum','degree_diff','betweenness_diff','geo_distance_km',
                   'direct','freight_sum×direct','degree_sum×direct','degree_diff×direct']}
    y = predictors.score.to_numpy()
    lookup = {int(a):i for i,a in enumerate(airport_ids)}
    ii = np.array([lookup[int(a)] for a in predictors.a_id])
    jj = np.array([lookup[int(b)] for b in predictors.b_id])
    Y = np.zeros((len(airport_ids),len(airport_ids)))
    Y[ii,jj] = Y[jj,ii] = y
    fitted, coef_tables, summaries = {},[],[]
    for name,cols in specs.items():
        X = np.column_stack([np.ones(len(y)),z[cols]])
        inverse = np.linalg.pinv(X)
        beta = inverse@y
        prediction = X@beta
        r2 = 1-np.sum((y-prediction)**2)/np.sum((y-y.mean())**2)
        fitted[name] = {'X':X,'inverse':inverse,'beta':beta,'counts':np.zeros(len(beta),dtype=int),
                        'r2_count':0,'r2':r2,'cols':['intercept']+cols}
        summaries.append({'model':name,'r2':float(r2),'predictors':len(cols),
            'condition_number':float(np.linalg.cond(X)),'matrix_rank':int(np.linalg.matrix_rank(X)),
            'permutations':permutations,'seed':seed})
    rng = np.random.default_rng(seed)
    with threadpool_limits(limits=1):
        for b in range(permutations):
            perm = rng.permutation(len(airport_ids))
            yp = Y[perm[ii],perm[jj]]
            for model in fitted.values():
                bp = model['inverse']@yp
                model['counts'] += np.abs(bp) >= np.abs(model['beta'])-1e-14
                residual = yp-model['X']@bp
                rp = 1-np.sum(residual**2)/np.sum((yp-yp.mean())**2)
                model['r2_count'] += rp >= model['r2']-1e-14
    for summary in summaries:
        name = summary['model']
        model = fitted[name]
        summary['p_r2'] = (1+model['r2_count'])/(permutations+1)
        ps = (1+model['counts'])/(permutations+1)
        for col,beta,p in zip(model['cols'],model['beta'],ps):
            coef_tables.append({'model':name,'variable':col,'coefficient':float(beta),
                                'p_permutation':float(p),'mc_standard_error':float(np.sqrt(p*(1-p)/(permutations+1)))})
    standardization = {c:{'mean':float(means[c]),'std':float(scales[c])} for c in continuous}
    return pd.DataFrame(summaries),pd.DataFrame(coef_tables),standardization

# %% EXPORT
def export_app(networks, airports, comparison, calibration, audit, out_path):
    codes = airports.set_index('airport_id').code.to_dict()
    out = {'metadata':{'year':2025,'n_airports':len(airports),
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'source':'BTS T-100 Domestic Segment (All Carriers)',
        'source_url':'https://transtats.bts.gov/Fields.asp?gnoyr_VQ=GEE',
        'paper_url':'https://doi.org/10.1038/s41598-026-38153-y',
        'freight_unit':'lb','graph':'binaria, no dirigida; FREIGHT > 0',
        'raw_rows':audit['raw_rows'],'clean_rows':audit['clean_rows'],
        'calibration':calibration,'scope':'Vulnerabilidad estructural; no estima pérdidas operativas de carga.'},
        'airports':[], 'periods':{}, 'comparison':{'pairs':comparison.to_dict(orient='records')}}
    for row in airports.to_dict(orient='records'):
        out['airports'].append({'id':row['code'],'airport_id':int(row['airport_id']),
            'name':row['name'],'city':row['city'],'state':row['state'],
            'lat':float(row['lat']),'lon':float(row['lon']),
            'annual_freight_lb':float(row['annual_freight_lb'])})
    for period,net in networks.items():
        nodes=[]
        for row in net['nodes'].to_dict(orient='records'):
            row['id']=codes[row['airport_id']]
            nodes.append(row)
        edges=[{'source':codes[int(r.u)],'target':codes[int(r.v)],'freight_lb':float(r.freight_lb)} for r in net['edges'].itertuples()]
        rows=net['pairs'].sort_values(['score','a_id','b_id'],ascending=[False,True,True]).copy()
        floatcols=rows.select_dtypes(include='float').columns
        rows[floatcols]=rows[floatcols].round(12)
        out['periods'][period]={**net['stats'],'label':net['label'],
            'metrics':{k:net['stats'][k] for k in METRICS},
            'composite':net['composite'],'nodes':nodes,'edges':edges,'pairs':rows.to_dict(orient='records')}
    Path(out_path).parent.mkdir(parents=True,exist_ok=True)
    Path(out_path).write_text(json.dumps(out,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    return out
