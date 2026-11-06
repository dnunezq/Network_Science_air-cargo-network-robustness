"""Sensibilidad y contexto operativo de la red de carga aérea de 2025.

Extiende el análisis base sin modificarlo. Mantiene los mismos 100 nodos;
los umbrales son escenarios predefinidos, no reglas de limpieza de errores.
"""
from pathlib import Path
import json
import hashlib

import networkx as nx
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from analisis_red import (METRICS, SHORT, PERIODS, robustness_metrics,
                         simulate_period, entropy_composite, write_json)

VERSION = 'estructura-2025-v1'
CASES = [('SDF', 'SEA'), ('MEM', 'ORD'), ('ONT', 'STL'), ('CVG', 'IAD')]
VARIANTS = {
    'base': 'Todas las conexiones con mercancía positiva',
    'half_months': 'Presente en al menos la mitad de los meses',
    'all_months': 'Presente en todos los meses',
    'min_monthly_freight': 'Promedio de al menos 1.000 lb por mes calendario',
}


def _json_records(frame):
    """Convierte escalares numpy y ausencias a JSON estándar."""
    return json.loads(frame.to_json(orient='records', force_ascii=False,
                                   double_precision=15))


def _calendar_months(period):
    if period == 'annual':
        return list(range(1, 13))
    quarter = int(period[1:])
    if quarter not in range(1, 5):
        raise ValueError('Período trimestral inválido.')
    return list(range(3 * quarter - 2, 3 * quarter + 1))


def _undirected_edges(routes, airport_ids, months):
    """Agrega ambos sentidos y cuenta meses distintos, sin duplicar persistencia."""
    ids = set(map(int, airport_ids))
    rows = routes.loc[routes.MONTH.isin(months) &
                      routes.ORIGIN_AIRPORT_ID.isin(ids) &
                      routes.DEST_AIRPORT_ID.isin(ids)].copy()
    rows['u'] = np.minimum(rows.ORIGIN_AIRPORT_ID, rows.DEST_AIRPORT_ID)
    rows['v'] = np.maximum(rows.ORIGIN_AIRPORT_ID, rows.DEST_AIRPORT_ID)
    return rows.groupby(['u', 'v'], as_index=False).agg(
        freight_lb=('freight_lb', 'sum'), months_present=('MONTH', 'nunique'),
        departures=('departures', 'sum')).sort_values(['u', 'v']).reset_index(drop=True)


def _variant_edges(edges, variant, calendar_count):
    """La carga media divide por meses calendario, incluidos los meses sin ruta."""
    if variant == 'base':
        keep = np.ones(len(edges), dtype=bool)
    elif variant == 'half_months':
        keep = edges.months_present.ge(int(np.ceil(calendar_count / 2)))
    elif variant == 'all_months':
        keep = edges.months_present.ge(calendar_count)
    elif variant == 'min_monthly_freight':
        keep = edges.freight_lb.ge(1000 * calendar_count)
    else:
        raise ValueError(f'Escenario desconocido: {variant}')
    return edges.loc[keep].copy()


def _graph_from_edges(airport_ids, edges):
    ids = list(map(int, airport_ids))
    graph = nx.Graph()
    graph.add_nodes_from(ids)
    for row in edges.itertuples(index=False):
        if row.u == row.v or row.u not in graph or row.v not in graph:
            raise ValueError('Arista inválida o nodo fuera del universo fijo.')
        if not np.isfinite(row.freight_lb) or row.freight_lb <= 0:
            raise ValueError('Las aristas retenidas deben tener carga positiva.')
        graph.add_edge(int(row.u), int(row.v), freight_lb=float(row.freight_lb))
    adj = nx.to_numpy_array(graph, nodelist=ids, weight=None, dtype=bool)
    return graph, adj


def _graph_stats(graph, adj):
    return {
        'n_nodes': graph.number_of_nodes(), 'n_edges': graph.number_of_edges(),
        'components': nx.number_connected_components(graph),
        'isolates': nx.number_of_isolates(graph),
        'largest_component': max(map(len, nx.connected_components(graph)), default=0),
        'density': nx.density(graph),
        'freight_lb': float(sum(w['freight_lb'] for _, _, w in graph.edges(data=True))),
        **dict(zip(METRICS, robustness_metrics(adj).tolist())),
    }


def _pair_frame(sim, adj, airports):
    ids, codes = airports.airport_id.to_numpy(), airports.code.to_numpy()
    ij = sim['pair_indices']
    own = entropy_composite(sim['synergy'])
    frame = pd.DataFrame({
        'a_id': ids[ij[:, 0]], 'b_id': ids[ij[:, 1]],
        'a': codes[ij[:, 0]], 'b': codes[ij[:, 1]],
        'direct': adj[ij[:, 0], ij[:, 1]], 'score_own': own['score'],
    })
    frame['pair_key'] = [f'{min(a,b)}-{max(a,b)}' for a,b in zip(frame.a_id,frame.b_id)]
    for j, name in enumerate(SHORT):
        frame[f'synergy_{name}'] = sim['synergy'][:, j]
        frame[f'impact_{name}'] = sim['joint_impact'][:, j]
    frame['rank_own'] = frame.score_own.rank(ascending=False, method='average')
    return frame, {k: own[k].tolist() for k in ['weights', 'scales', 'entropy']}


def _comparison(base, variant, base_adj, variant_adj, top_k=20):
    """Solo compara score_comparable; rango medio para empates, corte por IDs."""
    a = base.set_index('pair_key').sort_index()
    b = variant.set_index('pair_key').reindex(a.index)
    if b.score_comparable.isna().any():
        raise ValueError('La comparación exige el mismo universo de parejas.')
    rank_columns = ['score_comparable', 'a_id', 'b_id']
    order = [False, True, True]
    k = min(top_k, len(a))
    aa = set(a.sort_values(rank_columns, ascending=order).head(k).index)
    bb = set(b.sort_values(rank_columns, ascending=order).head(k).index)
    rho = None
    if a.score_comparable.nunique() > 1 and b.score_comparable.nunique() > 1:
        rho = float(spearmanr(a.score_comparable, b.score_comparable).statistic)
    common = int(np.logical_and(base_adj, variant_adj).sum() // 2)
    union = int(np.logical_or(base_adj, variant_adj).sum() // 2)
    return {'spearman': rho, 'top_k': k, 'shared_top': len(aa & bb),
            'overlap': len(aa & bb) / k if k else None,
            'edge_jaccard': common / union if union else 1.0,
            'edges_common': common,
            'edges_lost': int(np.logical_and(base_adj, ~variant_adj).sum() // 2)}


def _compact_pairs(frame, top_k=20):
    ordered = frame.sort_values(['score_comparable', 'a_id', 'b_id'],
                                ascending=[False, True, True])
    cols = ['a', 'b', 'score_comparable', 'rank', 'direct', 'impact_global']
    top = _json_records(ordered.head(top_k)[cols])
    cases = []
    for a, b in CASES:
        row = frame.loc[(frame.a.eq(a) & frame.b.eq(b)) |
                        (frame.a.eq(b) & frame.b.eq(a)), cols]
        if len(row):
            cases.append({'case': f'{a}–{b}', **_json_records(row)[0]})
    return top, cases


def _operator_totals(clean, airports):
    """Carga incidente en todos los segmentos depurados, no solo enlaces internos."""
    ids = set(airports.airport_id.astype(int))
    pieces = []
    for endpoint in ['ORIGIN', 'DEST']:
        part = clean.loc[clean[f'{endpoint}_AIRPORT_ID'].isin(ids),
                         [f'{endpoint}_AIRPORT_ID', 'AIRLINE_ID', 'UNIQUE_CARRIER_NAME', 'FREIGHT']].copy()
        part.columns = ['airport_id', 'operator_id', 'operator_name', 'freight_lb']
        pieces.append(part)
    combined = pd.concat(pieces, ignore_index=True)
    return combined.groupby(['airport_id', 'operator_id'], as_index=False).agg(
        name=('operator_name', 'first'), freight_lb=('freight_lb', 'sum'))


def _airport_profiles(clean, airports, annual_nodes):
    frame = airports[['airport_id', 'code']].merge(annual_nodes, on='airport_id',
                                                validate='one_to_one')
    for source, dest in [('freight_lb', 'rank_freight'), ('degree', 'rank_degree'),
                         ('betweenness', 'rank_betweenness'), ('impact_global', 'rank_impact_global')]:
        frame[dest] = frame[source].rank(ascending=False, method='average')
    operator_totals = _operator_totals(clean, airports)
    profiles = []
    for row in _json_records(frame):
        selected = operator_totals.loc[operator_totals.airport_id.eq(row['airport_id'])].copy()
        total = selected.freight_lb.sum()
        selected['share'] = selected.freight_lb / total if total else 0.0
        selected = selected.sort_values(['freight_lb', 'operator_id'], ascending=[False, True])
        operators = [{'id': str(int(x.operator_id)), 'name': x.name,
                      'freight_lb': float(x.freight_lb), 'share': float(x.share)}
                     for x in selected.head(3).itertuples(index=False)]
        profiles.append({**row, 'id': row['code'], 'operator_count': len(selected),
                         'operator_hhi': float(np.square(selected.share).sum()),
                         'top_operators': operators})
    return profiles, operator_totals


def _operator_edges(clean, airport_ids):
    ids = set(map(int, airport_ids))
    inside = clean.loc[clean.ORIGIN_AIRPORT_ID.isin(ids) & clean.DEST_AIRPORT_ID.isin(ids)].copy()
    inside['u'] = np.minimum(inside.ORIGIN_AIRPORT_ID, inside.DEST_AIRPORT_ID)
    inside['v'] = np.maximum(inside.ORIGIN_AIRPORT_ID, inside.DEST_AIRPORT_ID)
    return inside.groupby(['AIRLINE_ID', 'u', 'v'], as_index=False).agg(
        freight_lb=('FREIGHT', 'sum'), name=('UNIQUE_CARRIER_NAME', 'first'))


def _remove_operator(base_edges, operator_edges):
    """Resta volumen atribuido; conserva la arista si otro operador transportó carga."""
    merged = base_edges[['u', 'v', 'freight_lb']].merge(
        operator_edges[['u', 'v', 'freight_lb']], on=['u', 'v'], how='left',
        suffixes=('_all', '_operator'), validate='one_to_one')
    merged['freight_lb_operator'] = merged.freight_lb_operator.fillna(0)
    merged['freight_lb'] = merged.freight_lb_all - merged.freight_lb_operator
    if merged.freight_lb.lt(-1e-6).any():
        raise ValueError('El volumen de operador supera el volumen total del enlace.')
    return merged.loc[merged.freight_lb.gt(1e-6), ['u', 'v', 'freight_lb']].copy()


def _operators(clean, airports, annual_edges, annual_stats, output_dir):
    ids = airports.airport_id.astype(int).tolist()
    code = dict(zip(ids, airports.code))
    by_operator = _operator_edges(clean, ids)
    totals = by_operator.groupby('AIRLINE_ID', as_index=False).agg(
        freight_lb=('freight_lb', 'sum'), name=('name', 'first'))
    totals = totals.sort_values(['freight_lb', 'AIRLINE_ID'], ascending=[False, True]).head(8)
    items, summary_rows = [], []
    for operator in totals.itertuples(index=False):
        op_id = int(operator.AIRLINE_ID)
        layer_edges = by_operator.loc[by_operator.AIRLINE_ID.eq(op_id)].copy()
        graph, adj = _graph_from_edges(ids, layer_edges)
        layer_stats = _graph_stats(graph, adj)
        remaining = _remove_operator(annual_edges, layer_edges)
        residual_graph, residual_adj = _graph_from_edges(ids, remaining)
        residual_stats = _graph_stats(residual_graph, residual_adj)
        impacts = {m: annual_stats[m] - residual_stats[m] for m in METRICS}
        edges = [{'source': code[int(e.u)], 'target': code[int(e.v)],
                  'freight_lb': float(e.freight_lb)} for e in layer_edges.itertuples(index=False)]
        item = {'id': str(op_id), 'name': operator.name,
                'freight_lb': float(operator.freight_lb),
                'share': float(operator.freight_lb / annual_stats['freight_lb']),
                'layer': {'stats': layer_stats, 'edges': edges},
                'removal': {'stats': residual_stats, 'metrics_impact': impacts,
                            'edges_lost': annual_stats['n_edges'] - residual_stats['n_edges'],
                            'edges': [{'source': code[int(e.u)], 'target': code[int(e.v)],
                                       'freight_lb': float(e.freight_lb)}
                                      for e in remaining.itertuples(index=False)],
                            'freight_attributed_lb': float(operator.freight_lb),
                            'freight_remaining_lb': residual_stats['freight_lb']}}
        items.append(item)
        summary_rows.append({'operator_id': op_id, 'name': operator.name,
                             'freight_share': item['share'], 'edges_in_layer': len(layer_edges),
                             'edges_lost': item['removal']['edges_lost'],
                             **{f'impact_{k}': v for k, v in impacts.items()},
                             **{f'remaining_{k}': v for k, v in residual_stats.items()}})
    by_operator.to_csv(output_dir / 'enlaces_por_operador.csv', index=False)
    pd.DataFrame(summary_rows).to_csv(output_dir / 'escenarios_operadores.csv', index=False)
    return {'scope': 'annual', 'items': items,
            'volume_scope': 'Segmentos internos entre los 100 aeropuertos; cada segmento se cuenta una vez.',
            'removal_rule': 'Retirar la carga atribuida al operador; mantener conexiones con carga de otros operadores y los 100 nodos.',
            'note': 'Es un contrafactual estructural. El volumen atribuido no estima pérdida operativa ni redistribución; no se suponen transferencias entre operadores.'}


def _city_market_alternatives(raw, clean):
    result = []
    for hub, main, alternative in [('SDF', 'SEA', 'BFI'), ('SDF', 'SFO', 'OAK'), ('SDF', 'SMF', 'MHR')]:
        market_ids = {}
        route_records = []
        for code in [main, alternative]:
            values = set(raw.loc[raw.ORIGIN.eq(code), 'ORIGIN_CITY_MARKET_ID'].dropna().astype(int))
            values |= set(raw.loc[raw.DEST.eq(code), 'DEST_CITY_MARKET_ID'].dropna().astype(int))
            market_ids[code] = sorted(values)
            route = clean.loc[(clean.ORIGIN.eq(hub) & clean.DEST.eq(code)) |
                              (clean.ORIGIN.eq(code) & clean.DEST.eq(hub))]
            by_operator = route.groupby(['AIRLINE_ID', 'UNIQUE_CARRIER_NAME'], as_index=False).FREIGHT.sum()
            by_operator = by_operator.sort_values(['FREIGHT', 'AIRLINE_ID'], ascending=[False, True])
            route_records.append({'a': hub, 'b': code, 'freight_lb': float(route.FREIGHT.sum()),
                                  'months_present': int(route.MONTH.nunique()),
                                  'departures': float(route.DEPARTURES_PERFORMED.sum()),
                                  'top_operators': [{'id': str(int(r.AIRLINE_ID)), 'name': r.UNIQUE_CARRIER_NAME,
                                                     'freight_lb': float(r.FREIGHT)}
                                                    for r in by_operator.head(3).itertuples(index=False)]})
        result.append({'hub': hub, 'airport': main, 'alternative': alternative,
                       'city_market_ids': market_ids,
                       'same_city_market': len(market_ids[main]) == 1 and market_ids[main] == market_ids[alternative],
                       'routes': route_records})
    return result


def run_structural_extensions(raw, clean, routes, airports, networks, root, use_cache=True):
    """Genera extensión serializable {'structural': ...}; no modifica inputs.

    Requiere networks base con resultados adjuntos mediante attach_results.
    La escala de sensibilidad usa base y tres variantes en los cinco períodos;
    los pesos se fijan con la red anual base. No reutiliza la calibración
    trimestral original ni presenta como comparables los índices propios.
    """
    root = Path(root)
    output = root / 'resultados' / 'ampliaciones'
    cache = root / 'cache' / 'ampliaciones'
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    if len(airports) != 100 or airports.airport_id.nunique() != 100:
        raise ValueError('Estas ampliaciones requieren los mismos 100 aeropuertos base.')
    ids = airports.airport_id.astype(int).tolist()
    scenarios = {}
    for period in PERIODS:
        months = _calendar_months(period)
        full_edges = _undirected_edges(routes, ids, months)
        for variant in VARIANTS:
            print(f'Ampliación estructural: {period} / {variant}', flush=True)
            edges = _variant_edges(full_edges, variant, len(months))
            graph, adj = _graph_from_edges(ids, edges)
            if variant == 'base':
                np.testing.assert_array_equal(adj, networks[period]['adj'])
            cache_path = (root / 'cache' / f'{period}.npz' if variant == 'base'
                          else cache / f'{period}_{variant}.npz')
            sim = simulate_period(adj, cache_path, use_cache=use_cache, verbose=False)
            frame, calibration = _pair_frame(sim, adj, airports)
            scenarios[(period, variant)] = {'sim': sim, 'frame': frame,
                                            'calibration': calibration, 'adj': adj,
                                            'stats': _graph_stats(graph, adj), 'edges': edges}
    scales = np.max(np.abs(np.vstack([s['sim']['synergy'] for s in scenarios.values()])), axis=0)
    weights = entropy_composite(scenarios[('annual', 'base')]['sim']['synergy'])['weights']
    for scenario in scenarios.values():
        score = entropy_composite(scenario['sim']['synergy'], scales=scales, weights=weights)['score']
        scenario['frame']['score_comparable'] = score
        scenario['frame']['rank'] = scenario['frame'].score_comparable.rank(ascending=False, method='average')
    periods, flat_summary, case_rows = {}, [], []
    for period in PERIODS:
        periods[period] = {}
        base = scenarios[(period, 'base')]
        months = _calendar_months(period)
        for variant in VARIANTS:
            s = scenarios[(period, variant)]
            comp = _comparison(base['frame'], s['frame'], base['adj'], s['adj'])
            top, cases = _compact_pairs(s['frame'])
            coverage = s['stats']['freight_lb'] / base['stats']['freight_lb']
            periods[period][variant] = {
                'label': VARIANTS[variant], 'stats': s['stats'],
                'own_calibration': s['calibration'], 'comparison': comp,
                'top20': top, 'cases': cases, 'freight_coverage': coverage,
                'thresholds': {'calendar_months': len(months),
                               'min_months': int(np.ceil(len(months) / 2)) if variant == 'half_months'
                               else len(months) if variant == 'all_months' else None,
                               'min_freight_lb': 1000 * len(months) if variant == 'min_monthly_freight' else None}}
            s['frame'].to_csv(output / f'pares_sensibilidad_{period}_{variant}.csv', index=False)
            s['edges'].to_csv(output / f'enlaces_sensibilidad_{period}_{variant}.csv', index=False)
            flat_summary.append({'period': period, 'variant': variant, **s['stats'],
                                 'freight_coverage': coverage, **comp})
            case_rows.extend({'period': period, 'variant': variant, **row} for row in cases)
    pd.DataFrame(flat_summary).to_csv(output / 'resumen_sensibilidad.csv', index=False)
    pd.DataFrame(case_rows).to_csv(output / 'casos_sensibilidad.csv', index=False)
    profiles, operator_totals = _airport_profiles(clean, airports, networks['annual']['nodes'])
    pd.DataFrame([{k: v for k, v in p.items() if k != 'top_operators'} for p in profiles]).to_csv(output / 'perfiles_aeropuertos.csv', index=False)
    operator_totals.to_csv(output / 'carga_incidente_por_operador.csv', index=False)
    operators = _operators(clean, airports, scenarios[('annual', 'base')]['edges'],
                           scenarios[('annual', 'base')]['stats'], output)
    calibration = {'weights': weights.tolist(), 'scales': scales.tolist(),
                   'scope': 'Máximo absoluto por métrica entre todas las parejas de base+3 variantes en anual+T1–T4; pesos de entropía de la red anual base.',
                   'separate_from_original_quarter_calibration': True,
                   'ties': 'Spearman y rank usan rango medio; top20 desempata por a_id,b_id.'}
    result = {'structural': {
        'metadata': {'version': VERSION, 'year': 2025, 'n_nodes': 100,
                     'n_periods': 5, 'n_variants_excluding_base': 3,
                     'fixed_airport_ids': ids,
                     'base_adjacency_sha256': hashlib.sha256(np.ascontiguousarray(networks['annual']['adj']).tobytes()).hexdigest()},
        'sensitivity': {'calibration': calibration, 'periods': periods},
        'profiles': profiles, 'operators': operators,
        'city_market_alternatives': _city_market_alternatives(raw, clean),
        'notes': [
            'Umbrales predefinidos para sensibilidad: no se eliminan registros del análisis base ni se etiquetan como errores.',
            'Todos los escenarios conservan 100 nodos, incluidos los aislados.',
            'Los índices propios se guardan en CSV; comparaciones, top20 y casos JSON usan exclusivamente la calibración común de sensibilidad.',
            'Los rangos de perfiles se calculan entre los 100 nodos. La carga incidente incluye todos los segmentos depurados, incluso hacia fuera del top100; las centralidades usan la subred.',
            'MAIL y salidas asociados a registros con FREIGHT>0 no equivalen al correo ni al tráfico aéreo total.',
            'Las capas identifican operadores reportantes; no permiten inferir clientes comerciales ni acuerdos de transferencia.',
            'La ausencia de enlace exacto entre aeropuertos no implica ausencia de servicio hacia su mercado urbano.',
        ]}}
    write_json(output / 'estructura.json', result)
    return result
