"""Descompone sinergia, daño y efectos de composición sin alterar la base."""
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx
from scipy.stats import spearmanr
from analisis_red import robustness_metrics, entropy_composite, METRICS, SHORT, write_json


def _survivor_paths(graph, removed):
    """Compara los mismos extremos antes y después de retirar aeropuertos."""
    remaining = [n for n in graph if n not in set(removed)]
    after = graph.subgraph(remaining).copy()
    original_distances = dict(nx.all_pairs_shortest_path_length(graph))
    final_distances = dict(nx.all_pairs_shortest_path_length(after))
    before_sum = after_sum = 0.0
    worsened = disconnected = 0
    for a, b in combinations(remaining, 2):
        d0 = original_distances.get(a, {}).get(b, np.inf)
        d1 = final_distances.get(a, {}).get(b, np.inf)
        before_sum += 0 if not np.isfinite(d0) else 1 / d0
        after_sum += 0 if not np.isfinite(d1) else 1 / d1
        worsened += int(d1 > d0)
        disconnected += int(np.isfinite(d0) and not np.isfinite(d1))
    count = len(remaining) * (len(remaining)-1) // 2
    return {
        'n_surviving_pairs': count,
        'worsened_pairs': worsened,
        'disconnected_pairs': disconnected,
        'global_before_survivors': before_sum/count if count else 0.0,
        'global_after_survivors': after_sum/count if count else 0.0,
    }


def run_interpretation_extensions(networks, simulations, airports, out_dir):
    """Genera evidencia de casos y una sensibilidad de universo fijo."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    net, sim = networks['annual'], simulations['annual']
    pairs = net['pairs'].copy()
    code_to_id = airports.set_index('code').airport_id.astype(int).to_dict()
    base_weights = np.asarray(net['composite']['weights'])
    base_scales = np.asarray(net['composite']['scales'])
    cases = []
    case_codes = [('SDF', 'SEA'), ('MEM', 'ORD'), ('ONT', 'STL'), ('CVG', 'IAD')]
    for a, b in case_codes:
        match = pairs[((pairs.a == a) & (pairs.b == b)) |
                      ((pairs.a == b) & (pairs.b == a))]
        if match.empty:
            continue
        row = match.iloc[0]
        a, b = row.a, row.b
        paths = _survivor_paths(net['graph'], [code_to_id[a], code_to_id[b]])
        paths['composition_component'] = float(sim['baseline'][0]-paths['global_before_survivors'])
        paths['path_component'] = float(paths['global_before_survivors']-paths['global_after_survivors'])
        np.testing.assert_allclose(paths['composition_component']+paths['path_component'], row.impact_global, atol=1e-12)
        components = []
        for j, (name, short) in enumerate(zip(METRICS, SHORT)):
            normalized = float(row['synergy_'+short]/base_scales[j]) if base_scales[j] else 0.0
            components.append({
                'name': name,
                'baseline': float(sim['baseline'][j]),
                'single_a_impact': float(row['single_a_'+short]),
                'single_b_impact': float(row['single_b_'+short]),
                'joint_impact': float(row['impact_'+short]),
                'synergy': float(row['synergy_'+short]),
                'normalized_synergy': normalized,
                'weight': float(base_weights[j]),
                'contribution': normalized*float(base_weights[j]),
            })
        np.testing.assert_allclose(sum(c['contribution'] for c in components), row.score, atol=1e-12)
        cases.append({'a': a, 'b': b, 'score': float(row.score), 'rank': float(row['rank']),
                      'direct': bool(row.direct), 'metrics': components, 'paths': paths,
                      'joint_global_rank': float(pairs.impact_global.rank(ascending=False, method='average').loc[row.name]),
                      'shared_neighbors': len(set(net['graph'][code_to_id[a]]) & set(net['graph'][code_to_id[b]]))})

    n = len(airports)
    def fixed_values(impact, removed):
        remaining = n-removed
        surviving = sim['baseline']-impact
        fixed = surviving.copy()
        fixed[..., 0] *= remaining*(remaining-1)/(n*(n-1))
        fixed[..., 1] *= remaining/n
        # Los nodos aislados añadidos aportan autovalores cero, exp(0)=1.
        fixed[..., 2] = np.logaddexp(np.log(remaining)+surviving[..., 2], np.log(removed))-np.log(n)
        return fixed

    single_fixed_impact = sim['baseline']-fixed_values(sim['single_impact'], 1)
    joint_fixed_impact = sim['baseline']-fixed_values(sim['joint_impact'], 2)
    ij = sim['pair_indices']
    synergy_fixed = joint_fixed_impact-single_fixed_impact[ij[:, 0]]-single_fixed_impact[ij[:, 1]]
    fixed = entropy_composite(synergy_fixed)
    alternative = pairs[['a_id', 'b_id', 'a', 'b', 'pair_key', 'score', 'rank']].copy()
    alternative['score_fixed_universe'] = fixed['score']
    alternative['rank_fixed_universe'] = alternative.score_fixed_universe.rank(ascending=False, method='average')
    for j, short in enumerate(SHORT):
        alternative['synergy_fixed_'+short] = synergy_fixed[:, j]
        alternative['impact_fixed_'+short] = joint_fixed_impact[:, j]
    sort_keys = ['a_id', 'b_id']
    base_top = set(alternative.sort_values(['score']+sort_keys, ascending=[False, True, True]).head(20).pair_key)
    alt_top = alternative.sort_values(['score_fixed_universe']+sort_keys, ascending=[False, True, True]).head(20)
    alternative.to_csv(out_dir/'sensibilidad_universo_fijo.csv', index=False)
    graph = net['graph']
    result = {
        'cases': cases,
        'fixed_universe': {
            'method': 'Se conservan 100 nodos y se aíslan los fallidos; se recalculan las tres métricas, sinergias, normalización y pesos.',
            'spearman': float(spearmanr(alternative.score, alternative.score_fixed_universe).statistic),
            'shared_top': len(base_top & set(alt_top.pair_key)),
            'overlap': len(base_top & set(alt_top.pair_key))/20,
            'weights_base': base_weights.tolist(), 'weights_fixed': fixed['weights'].tolist(),
            'negative_global_impacts_base': int((pairs.impact_global < -1e-12).sum()),
            'negative_global_impacts_fixed': int((joint_fixed_impact[:, 0] < -1e-12).sum()),
            'top20': alt_top[['a', 'b', 'score_fixed_universe', 'rank_fixed_universe']].to_dict(orient='records'),
        },
        'graph_properties': {
            'n_nodes': graph.number_of_nodes(), 'n_edges': graph.number_of_edges(),
            'diameter': nx.diameter(graph) if nx.is_connected(graph) else None,
            'vertex_connectivity': nx.node_connectivity(graph),
        },
        'score_damage_spearman': float(spearmanr(pairs.score, pairs.impact_global).statistic),
        'notes': [
            'Sinergia es exceso de impacto frente a fallos individuales; no equivale al daño total.',
            'Las eficiencias base promedian los nodos supervivientes; retirar nodos cambia el conjunto promediado.',
            'La descomposición global compara los mismos extremos antes y después y separa composición de aumento de distancias.',
            'La conectividad natural describe estructura espectral; no son toneladas perdidas ni capacidad de desvío.',
            'Conectividad de vértices en la red binaria no garantiza continuidad operativa ni transferencia entre operadores.',
        ],
    }
    write_json(out_dir/'interpretacion_ampliada.json', result)
    return result
