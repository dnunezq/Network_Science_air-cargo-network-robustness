"""Caracterización estructural de las redes de carga aérea de 2025.

Aporte propio del equipo: el artículo de referencia no describe la topología
de su red. Se calculan medidas globales y locales, centralidades,
asortatividad, núcleo k-core, comunidades y una comparación con los tres
modelos de red del curso (aleatoria, mundo pequeño y preferencial) por sus
tres propiedades distintivas: agrupamiento, longitud de caminos y hubs.

Todo es descriptivo y retrospectivo. Las comunidades y los modelos sirven para
leer la estructura; no demuestran mecanismos operativos.
"""
from itertools import combinations
from pathlib import Path
import json

import networkx as nx
import numpy as np
import pandas as pd
from networkx.algorithms import community as nx_community

VERSION = 'exploracion-2025-v2'
CENTRALITIES = ['degree', 'betweenness', 'closeness', 'eigenvector']
CENTRALITY_LABELS = {
    'degree': 'Grado', 'betweenness': 'Intermediación', 'closeness': 'Cercanía',
    'eigenvector': 'Autovector'}
MODELS = {
    'erdos_renyi': 'Aleatoria (Erdős–Rényi)',
    'watts_strogatz': 'Mundo pequeño (Watts–Strogatz)',
    'barabasi_albert': 'Preferencial (Barabási–Albert)'}
# Perfil de cada modelo según el material del curso (Network Models, unidad 3).
COURSE_PROFILES = {
    'erdos_renyi': {'clustering': 'bajo', 'paths': 'cortos', 'hubs': 'no'},
    'watts_strogatz': {'clustering': 'alto', 'paths': 'cortos', 'hubs': 'no'},
    'barabasi_albert': {'clustering': 'alto', 'paths': 'cortos', 'hubs': 'sí'}}
PROPERTIES = {
    'average_clustering': 'Agrupamiento medio',
    'average_path_length': 'Distancia media (escalas)',
    'degree_std': 'Desviación típica del grado'}
MODEL_METRICS = list(PROPERTIES) + ['max_degree', 'n_edges']
# Umbrales de las etiquetas cualitativas, siempre relativos a la red aleatoria
# con los mismos nodos y enlaces.
THRESHOLDS = {'clustering_high': 1.2, 'paths_long': 1.2, 'hubs': 2.0}
WS_REWIRING = 0.1


def graph_from_edges(airport_ids, edges):
    """Grafo no dirigido con los 100 nodos fijos y carga bilateral como atributo."""
    ids = [int(x) for x in airport_ids]
    graph = nx.Graph()
    graph.add_nodes_from(ids)
    for row in edges[['u', 'v', 'freight_lb']].itertuples(index=False):
        u, v = int(row.u), int(row.v)
        if u == v or u not in graph or v not in graph:
            raise ValueError('Arista inválida o nodo fuera del universo fijo.')
        if not np.isfinite(row.freight_lb) or row.freight_lb <= 0:
            raise ValueError('Las aristas deben tener carga positiva.')
        graph.add_edge(u, v, weight=float(row.freight_lb))
    return graph


def _finite(value):
    if value is None:
        return None
    value = float(value)
    return value if np.isfinite(value) else None


def structural_summary(graph):
    """Describe tamaño, distancias, agrupamiento, mezcla por grado y núcleo."""
    n, m = graph.number_of_nodes(), graph.number_of_edges()
    degrees = np.array([d for _, d in graph.degree()], dtype=float)
    connected = n > 1 and nx.is_connected(graph)
    core = nx.core_number(graph) if m else {v: 0 for v in graph}
    max_core = max(core.values()) if core else 0
    return {
        'n_nodes': n, 'n_edges': m, 'density': nx.density(graph) if n > 1 else 0.0,
        'mean_degree': float(degrees.mean()) if n else 0.0,
        'degree_std': float(degrees.std()) if n else 0.0,
        'degree_cv': float(degrees.std() / degrees.mean()) if n and degrees.mean() > 0 else None,
        'min_degree': int(degrees.min()) if n else 0,
        'max_degree': int(degrees.max()) if n else 0,
        'components': nx.number_connected_components(graph) if n else 0,
        'isolates': nx.number_of_isolates(graph),
        'largest_component': max(map(len, nx.connected_components(graph)), default=0),
        'diameter': int(nx.diameter(graph)) if connected else None,
        'average_path_length': float(nx.average_shortest_path_length(graph)) if connected else None,
        'average_clustering': float(nx.average_clustering(graph)) if n else 0.0,
        'transitivity': float(nx.transitivity(graph)) if m else 0.0,
        'degree_assortativity': _assortativity(graph),
        'max_core': int(max_core),
        'max_core_size': int(sum(1 for v in core.values() if v == max_core)) if m else 0,
    }


def _assortativity(graph, weight=None):
    degrees = [d for _, d in graph.degree(weight=weight)]
    if graph.number_of_edges() == 0 or len(set(degrees)) < 2:
        return None
    with np.errstate(invalid='ignore', divide='ignore'):
        return _finite(nx.degree_assortativity_coefficient(graph, weight=weight))


def degree_distribution(graph):
    """Histograma y función de supervivencia P(K >= k) sobre los grados observados."""
    degrees = np.array(sorted((d for _, d in graph.degree()), reverse=True))
    values, counts = np.unique(degrees, return_counts=True)
    n = len(degrees)
    survival = [{'degree': int(k), 'count': int(c),
                 'survival': float((degrees >= k).sum() / n)} for k, c in zip(values, counts)]
    return {'degrees': degrees.astype(int).tolist(), 'histogram': survival,
            'percentiles': {str(p): float(np.percentile(degrees, p)) for p in [10, 25, 50, 75, 90]}}


def centrality_table(graph, codes):
    """Cuatro centralidades sobre la red binaria; intermediación sin normalizar.

    La intermediación sin normalizar y el grado centralidad /(n-1) coinciden con
    las definiciones usadas en el análisis base y en el artículo.
    """
    n = graph.number_of_nodes()
    betweenness = nx.betweenness_centrality(graph, normalized=False, weight=None)
    closeness = nx.closeness_centrality(graph)
    try:
        eigenvector = nx.eigenvector_centrality_numpy(graph, weight=None)
    except (nx.NetworkXException, ValueError):
        eigenvector = {v: None for v in graph}
    table = pd.DataFrame({
        'airport_id': list(graph.nodes), 'id': [codes[int(v)] for v in graph.nodes],
        'degree': [graph.degree(v) for v in graph.nodes],
        'degree_centrality': [graph.degree(v) / (n - 1) for v in graph.nodes],
        'betweenness': [betweenness[v] for v in graph.nodes],
        'closeness': [closeness[v] for v in graph.nodes],
        'eigenvector': [eigenvector[v] for v in graph.nodes],
    })
    for name in CENTRALITIES:
        table[f'rank_{name}'] = table[name].rank(ascending=False, method='average')
    correlation = table[CENTRALITIES].corr(method='spearman')
    return table, correlation


def top_by_centrality(table, top_k=10, digits=None):
    """Tabla de los top_k aeropuertos de cada centralidad: «código (valor)» por columna.

    Desempata por código para que el orden sea determinista.
    """
    digits = digits or {'degree': 0, 'betweenness': 1, 'closeness': 3, 'eigenvector': 3}
    columns = {}
    for name in CENTRALITIES:
        ordered = table.sort_values([name, 'id'], ascending=[False, True]).head(top_k)
        columns[CENTRALITY_LABELS[name]] = [
            f"{row.id} ({getattr(row, name):,.{digits[name]}f})" for row in ordered.itertuples()]
    frame = pd.DataFrame(columns, index=pd.RangeIndex(1, top_k + 1, name='puesto'))
    return frame


def normalized_mutual_information(labels_a, labels_b):
    """NMI con normalización aritmética; 1 significa particiones idénticas."""
    a = np.asarray(labels_a)
    b = np.asarray(labels_b)
    if len(a) != len(b) or not len(a):
        raise ValueError('Las particiones deben etiquetar los mismos nodos.')
    n = len(a)
    _, ia = np.unique(a, return_inverse=True)
    _, ib = np.unique(b, return_inverse=True)
    table = np.zeros((ia.max() + 1, ib.max() + 1))
    np.add.at(table, (ia, ib), 1)
    pa, pb = table.sum(axis=1) / n, table.sum(axis=0) / n
    joint = table / n
    with np.errstate(divide='ignore', invalid='ignore'):
        terms = joint * np.log(joint / np.outer(pa, pb))
    mutual = float(np.nansum(terms))
    ha = -float(np.sum(pa[pa > 0] * np.log(pa[pa > 0])))
    hb = -float(np.sum(pb[pb > 0] * np.log(pb[pb > 0])))
    if ha + hb == 0:
        return 1.0
    return max(0.0, min(1.0, 2 * mutual / (ha + hb)))


def community_analysis(graph, codes, runs=20, seed=2025, weight=None):
    """Louvain repetido con semillas derivadas; contrasta con el método voraz.

    Se conserva la partición de mayor modularidad como representativa y se
    informa la estabilidad entre ejecuciones (NMI media). Una modularidad baja
    o una NMI baja indican grupos débiles que no deben sobreinterpretarse.
    """
    if not isinstance(runs, (int, np.integer)) or isinstance(runs, bool) or runs < 1:
        raise ValueError('runs debe ser un entero positivo.')
    nodes = list(graph.nodes)
    position = {v: i for i, v in enumerate(nodes)}
    if graph.number_of_edges() == 0:
        labels = list(range(len(nodes)))
        return _community_payload(graph, codes, nodes, labels, 0.0, [], None, None, weight)
    rng = np.random.default_rng(seed)
    seeds = [int(s) for s in rng.integers(0, 2**31 - 1, size=runs)]
    partitions, modularities = [], []
    for s in seeds:
        parts = nx_community.louvain_communities(graph, weight=weight, seed=s)
        labels = np.zeros(len(nodes), dtype=int)
        for k, part in enumerate(sorted(parts, key=lambda p: (-len(p), min(p)))):
            for v in part:
                labels[position[v]] = k
        partitions.append(labels)
        modularities.append(float(nx_community.modularity(graph, parts, weight=weight)))
    best = int(np.argmax(modularities))
    representative = partitions[best]
    nmi = [normalized_mutual_information(p, q) for p, q in combinations(partitions, 2)] if runs > 1 else [1.0]
    greedy_parts = list(nx_community.greedy_modularity_communities(graph, weight=weight))
    greedy = {'n_communities': len(greedy_parts),
              'modularity': float(nx_community.modularity(graph, greedy_parts, weight=weight)),
              'nmi_with_louvain': normalized_mutual_information(
                  representative, _labels_from_parts(greedy_parts, nodes))}
    co_membership = np.zeros((len(nodes), len(nodes)))
    for labels in partitions:
        co_membership += labels[:, None] == labels[None, :]
    co_membership /= runs
    by_run = sorted({int(len(set(p.tolist()))) for p in partitions})
    return _community_payload(graph, codes, nodes, representative.tolist(), modularities[best],
                              modularities, nmi, greedy, weight, co_membership, by_run)


def _labels_from_parts(parts, nodes):
    position = {v: i for i, v in enumerate(nodes)}
    labels = np.zeros(len(nodes), dtype=int)
    for k, part in enumerate(parts):
        for v in part:
            labels[position[v]] = k
    return labels


def _community_payload(graph, codes, nodes, labels, modularity, modularities, nmi,
                       greedy, weight, co_membership=None, by_run=None):
    labels = np.asarray(labels)
    communities = []
    for k in sorted(set(labels.tolist())):
        members = [nodes[i] for i in np.flatnonzero(labels == k)]
        by_degree = sorted(members, key=lambda v: (-graph.degree(v), v))
        inside = graph.subgraph(members).number_of_edges()
        total = sum(graph.degree(v) for v in members)
        communities.append({
            'id': int(k), 'size': len(members),
            'members': [codes[int(v)] for v in by_degree],
            'internal_edges': int(inside),
            'internal_share': float(2 * inside / total) if total else None})
    node_rows = []
    for i, v in enumerate(nodes):
        stability = None
        if co_membership is not None:
            mates = np.flatnonzero((labels == labels[i]) & (np.arange(len(nodes)) != i))
            stability = float(co_membership[i, mates].mean()) if len(mates) else 1.0
        node_rows.append({'airport_id': int(v), 'id': codes[int(v)],
                          'community': int(labels[i]), 'stability': stability})
    return {
        'method': 'Louvain (NetworkX), semillas derivadas de 2025; partición de mayor modularidad',
        'weight': weight or 'binaria', 'runs': len(modularities) if modularities else 0,
        'n_communities': len(communities), 'modularity': float(modularity),
        'modularity_range': [float(min(modularities)), float(max(modularities))] if modularities else None,
        'n_communities_by_run': by_run,
        'nmi_mean': float(np.mean(nmi)) if nmi else None,
        'nmi_min': float(np.min(nmi)) if nmi else None,
        'greedy': greedy, 'communities': communities, 'nodes': node_rows,
    }


def model_parameters(n, m):
    """Parámetros de los tres modelos con el mismo número de nodos y casi los mismos enlaces.

    Barabási–Albert con parámetro b genera b·(n−b) enlaces; se toma el b que
    resuelve b·(n−b) = m. Watts–Strogatz usa el grado medio par más cercano y
    una probabilidad de recableado de 0,1.
    """
    mean_degree = 2 * m / n if n else 0.0
    k = int(2 * round(mean_degree / 2))
    k_max = n - 2 if (n - 2) % 2 == 0 else n - 3
    k = max(2, min(k, max(2, k_max)))
    b = int(round((n - np.sqrt(max(n * n - 4 * m, 0))) / 2))
    b = max(1, min(b, n - 1))
    return {'erdos_renyi': {'n': n, 'm': m},
            'watts_strogatz': {'n': n, 'k': k, 'p': WS_REWIRING},
            'barabasi_albert': {'n': n, 'm': b}}


def _generate(name, params, seed):
    if name == 'erdos_renyi':
        return nx.gnm_random_graph(params['n'], params['m'], seed=seed)
    if name == 'watts_strogatz':
        try:
            return nx.connected_watts_strogatz_graph(params['n'], params['k'], params['p'], tries=200, seed=seed)
        except nx.NetworkXError:
            return nx.watts_strogatz_graph(params['n'], params['k'], params['p'], seed=seed)
    return nx.barabasi_albert_graph(params['n'], params['m'], seed=seed)


def _model_metrics(graph):
    n = graph.number_of_nodes()
    degrees = np.array([d for _, d in graph.degree()], dtype=float)
    connected = n > 1 and nx.is_connected(graph)
    return {
        'n_edges': graph.number_of_edges(),
        'average_clustering': float(nx.average_clustering(graph)) if n else None,
        'average_path_length': float(nx.average_shortest_path_length(graph)) if connected else None,
        'degree_std': float(degrees.std()) if n else None,
        'max_degree': int(degrees.max()) if n else 0,
    }


def _ratio(value, reference):
    if value is None or reference is None:
        return None
    if abs(reference) < 1e-12:
        return None if abs(value) < 1e-12 else float('inf')
    return float(value / reference)


def _labels(values, reference):
    """Etiquetas del curso (agrupamiento, caminos, hubs) relativas a la red aleatoria."""
    ratios = {'clustering': _ratio(values['average_clustering'], reference['average_clustering']),
              'paths': _ratio(values['average_path_length'], reference['average_path_length']),
              'hubs': _ratio(values['degree_std'], reference['degree_std'])}
    labels = {
        'clustering': None if ratios['clustering'] is None else (
            'alto' if ratios['clustering'] >= THRESHOLDS['clustering_high'] else 'bajo'),
        'paths': None if ratios['paths'] is None else (
            'largos' if ratios['paths'] > THRESHOLDS['paths_long'] else 'cortos'),
        'hubs': None if ratios['hubs'] is None else (
            'sí' if ratios['hubs'] >= THRESHOLDS['hubs'] else 'no')}
    return labels, {k: _finite(v) for k, v in ratios.items()}


def _distance(model_means, observed):
    """Distancia relativa en las tres propiedades: suma de |ln(modelo/observado)|."""
    total = 0.0
    used = 0
    for metric in PROPERTIES:
        a, b = model_means.get(metric), observed.get(metric)
        if a is None or b is None:
            continue
        total += abs(np.log((a + 1e-9) / (b + 1e-9)))
        used += 1
    return float(total) if used else None


def model_comparison(graph, replicas=30, seed=2025):
    """Compara la red con los tres modelos del curso por sus tres propiedades.

    Para cada modelo se generan `replicas` redes con los mismos nodos y casi los
    mismos enlaces y se promedian agrupamiento, distancia media y desviación del
    grado (hubs). Las etiquetas alto/bajo, cortos/largos y sí/no se fijan respecto
    a la red aleatoria. El modelo más cercano es el de menor distancia relativa en
    las tres propiedades. Es una comparación descriptiva, no una prueba.
    """
    if not isinstance(replicas, (int, np.integer)) or isinstance(replicas, bool) or replicas < 2:
        raise ValueError('replicas debe ser un entero mayor que uno.')
    n, m = graph.number_of_nodes(), graph.number_of_edges()
    observed = _model_metrics(graph)
    result = {'observed': observed, 'replicas': replicas, 'models': {},
              'course_profiles': COURSE_PROFILES, 'thresholds': THRESHOLDS}
    if n < 4 or m == 0:
        result.update(observed_labels=None, observed_ratios=None, closest_model=None, course_match=None)
        return result
    params = model_parameters(n, m)
    rng = np.random.default_rng(seed)
    for name in MODELS:
        rows = [_model_metrics(_generate(name, params[name], int(s)))
                for s in rng.integers(0, 2**31 - 1, size=replicas)]
        frame = pd.DataFrame(rows)
        means = {}
        metrics = {}
        for metric in MODEL_METRICS:
            values = pd.to_numeric(frame[metric], errors='coerce')
            mean = _finite(values.mean()) if values.notna().any() else None
            std = _finite(values.std(ddof=1)) if values.notna().sum() > 1 else None
            metrics[metric] = {'mean': mean, 'std': std}
            means[metric] = mean
        result['models'][name] = {'label': MODELS[name], 'parameters': params[name],
                                  'metrics': metrics, 'distance': _distance(means, observed)}
    reference = {k: v['mean'] for k, v in result['models']['erdos_renyi']['metrics'].items()}
    for name, model in result['models'].items():
        model['labels'], model['ratios'] = _labels({k: v['mean'] for k, v in model['metrics'].items()}, reference)
    observed_labels, observed_ratios = _labels(observed, reference)
    distances = {k: v['distance'] for k, v in result['models'].items() if v['distance'] is not None}
    matches = [k for k, profile in COURSE_PROFILES.items() if profile == observed_labels]
    result.update(observed_labels=observed_labels, observed_ratios=observed_ratios,
                  closest_model=min(distances, key=distances.get) if distances else None,
                  course_match=matches[0] if matches else None)
    return result


def explore_network(graph, codes, runs=20, replicas=30, seed=2025):
    """Ejecuta la caracterización completa de una red."""
    summary = structural_summary(graph)
    table, correlation = centrality_table(graph, codes)
    return {
        'summary': summary,
        'degree_distribution': degree_distribution(graph),
        'centralities': table,
        'centrality_spearman': correlation,
        'communities': community_analysis(graph, codes, runs=runs, seed=seed),
        'models': model_comparison(graph, replicas=replicas, seed=seed),
    }


def explore_base_networks(networks, airports, out_dir, runs=20, replicas=30, seed=2025):
    """Caracteriza las redes base (anual y trimestres) y guarda tablas CSV."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    codes = dict(zip(airports.airport_id.astype(int), airports.code))
    ids = airports.airport_id.astype(int).tolist()
    results, summary_rows = {}, []
    for period, net in networks.items():
        graph = graph_from_edges(ids, net['edges'])
        np.testing.assert_array_equal(nx.to_numpy_array(graph, nodelist=ids, weight=None, dtype=bool), net['adj'])
        result = explore_network(graph, codes, runs=runs, replicas=replicas, seed=seed)
        results[(period, 'base')] = result
        result['centralities'].to_csv(out_dir / f'centralidades_{period}_base.csv', index=False)
        summary_rows.append({'period': period, 'variant': 'base', **_flatten_summary(result)})
    pd.DataFrame(summary_rows).to_csv(out_dir / 'resumen_estructura_base.csv', index=False)
    return results


def explore_variant_networks(airports, ampliaciones_dir, out_dir, variants, periods,
                             runs=20, replicas=30, seed=2025):
    """Caracteriza las variantes exportadas por la sensibilidad (enlaces CSV)."""
    out_dir = Path(out_dir)
    ampliaciones_dir = Path(ampliaciones_dir)
    codes = dict(zip(airports.airport_id.astype(int), airports.code))
    ids = airports.airport_id.astype(int).tolist()
    results = {}
    for period in periods:
        for variant in variants:
            if variant == 'base':
                continue
            edges = pd.read_csv(ampliaciones_dir / f'enlaces_sensibilidad_{period}_{variant}.csv')
            graph = graph_from_edges(ids, edges)
            result = explore_network(graph, codes, runs=runs, replicas=replicas, seed=seed)
            results[(period, variant)] = result
            result['centralities'].to_csv(out_dir / f'centralidades_{period}_{variant}.csv', index=False)
    return results


def _flatten_summary(result):
    s = result['summary']
    com = result['communities']
    models = result['models']
    row = dict(s)
    row.update(louvain_communities=com['n_communities'], louvain_modularity=com['modularity'],
               louvain_nmi_mean=com['nmi_mean'], closest_model=models['closest_model'],
               course_match=models['course_match'])
    for name, model in models['models'].items():
        for metric in PROPERTIES:
            row[f'{name}_{metric}'] = model['metrics'][metric]['mean']
    return row


def export_exploration(results, airports, out_path, labels=None):
    """JSON compacto para el explorador: un bloque por período y regla."""
    codes = airports.code.tolist()
    index = {int(a): i for i, a in enumerate(airports.airport_id.astype(int))}
    payload = {'metadata': {'version': VERSION, 'year': 2025, 'codes': codes,
                            'centralities': CENTRALITIES, 'centrality_labels': CENTRALITY_LABELS,
                            'models': MODELS, 'course_profiles': COURSE_PROFILES,
                            'properties': PROPERTIES, 'thresholds': THRESHOLDS,
                            'scope': 'Caracterización descriptiva de redes binarias; aporte propio, no procede del artículo.'},
               'networks': {}}
    for (period, variant), result in results.items():
        table = result['centralities'].set_index('airport_id')
        ordered = table.loc[[a for a in airports.airport_id.astype(int)]]
        node_values = {name: [_finite(x) for x in ordered[name]] for name in CENTRALITIES}
        node_ranks = {name: [float(x) for x in ordered[f'rank_{name}']] for name in CENTRALITIES}
        block = result['communities']
        membership = [None] * len(codes)
        stability = [None] * len(codes)
        for row in block['nodes']:
            membership[index[row['airport_id']]] = row['community']
            stability[index[row['airport_id']]] = row['stability']
        payload['networks'].setdefault(period, {})[variant] = {
            'label': (labels or {}).get(variant, variant),
            'summary': result['summary'],
            'degree_distribution': result['degree_distribution'],
            'centrality_values': node_values, 'centrality_ranks': node_ranks,
            'centrality_spearman': {k: {j: _finite(v) for j, v in row.items()}
                                    for k, row in result['centrality_spearman'].to_dict().items()},
            'communities': {k: v for k, v in block.items() if k != 'nodes'} | {
                'membership': membership, 'stability': stability},
            'models': result['models'],
        }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False),
                        encoding='utf-8')
    return payload


def model_table(result):
    """Tabla de las tres propiedades: red observada frente a la media de cada modelo."""
    models = result['models']
    rows = {'Red observada': {**{PROPERTIES[k]: models['observed'][k] for k in PROPERTIES},
                              'Grado máximo': models['observed']['max_degree'],
                              'Agrupamiento': (models['observed_labels'] or {}).get('clustering'),
                              'Caminos': (models['observed_labels'] or {}).get('paths'),
                              'Hubs': (models['observed_labels'] or {}).get('hubs')}}
    for name, model in models['models'].items():
        rows[f"{model['label']}"] = {
            **{PROPERTIES[k]: model['metrics'][k]['mean'] for k in PROPERTIES},
            'Grado máximo': model['metrics']['max_degree']['mean'],
            'Agrupamiento': model['labels']['clustering'], 'Caminos': model['labels']['paths'],
            'Hubs': model['labels']['hubs']}
    return pd.DataFrame(rows).T


def describe_network_type(result):
    """Frases de lectura, derivadas de los números; no sustituyen la discusión."""
    s, models, com = result['summary'], result['models'], result['communities']
    lines = []
    if s['diameter'] is None:
        lines.append(f"Densidad {s['density']:.3f} y grado medio {s['mean_degree']:.1f}; la red tiene "
                     f"{s['components']} componentes, así que no hay distancia media ni diámetro globales.")
    else:
        lines.append(f"Densidad {s['density']:.3f} y grado medio {s['mean_degree']:.1f}: red densa, "
                     f"distancia media {s['average_path_length']:.2f} escalas y diámetro {s['diameter']}.")
    er = models['models'].get('erdos_renyi') if models['models'] else None
    if er:
        c_er = er['metrics']['average_clustering']['mean']
        lines.append(f"Agrupamiento medio {s['average_clustering']:.3f} frente a {c_er:.3f} en una red aleatoria "
                     f"con los mismos enlaces ({s['average_clustering'] / c_er:.2f} veces).")
        k_er = er['metrics']['degree_std']['mean']
        lines.append(f"Desviación típica del grado {s['degree_std']:.1f} frente a {k_er:.1f} en la red aleatoria: "
                     + ('el grado es heterogéneo y hay hubs.' if models['observed_labels']['hubs'] == 'sí'
                        else 'el grado es homogéneo, sin hubs marcados.'))
    r = s['degree_assortativity']
    if r is not None:
        kind = ('disasortativa: los aeropuertos muy conectados se enlazan con poco conectados (patrón hub-and-spoke)'
                if r < -0.05 else ('asortativa: los nodos tienden a conectarse con otros de grado similar'
                                   if r > 0.05 else 'mezcla casi neutra por grado'))
        lines.append(f"Asortatividad de grado {r:.3f}: {kind}.")
    lines.append(f"Núcleo k-core: {s['max_core_size']} aeropuertos tienen al menos {s['max_core']} "
                 'conexiones con otros miembros del núcleo.')
    labels = models.get('observed_labels')
    if labels:
        match = models.get('course_match')
        closest = models.get('closest_model')
        lines.append(f"Propiedades del curso: agrupamiento {labels['clustering']}, caminos {labels['paths']}, "
                     f"hubs {labels['hubs']}. "
                     + (f"Coincide con el perfil {MODELS[match]}. " if match else 'No coincide exactamente con ningún perfil. ')
                     + (f"El modelo simulado más cercano en las tres propiedades es {MODELS[closest]}." if closest else ''))
    lines.append(f"El grado va de {s['min_degree']} a {s['max_degree']} y no puede superar {s['n_nodes'] - 1}: "
                 'un solo orden de magnitud no permite ajustar una ley de potencia de forma fiable, '
                 'así que la red no se describe como libre de escala.')
    if com['nmi_mean'] is not None:
        strength = 'débiles' if com['modularity'] < 0.3 else 'marcadas'
        lines.append(f"Comunidades Louvain: {com['n_communities']} grupos, modularidad {com['modularity']:.3f} "
                     f"y NMI media {com['nmi_mean']:.2f} entre ejecuciones: comunidades {strength}.")
    return lines
