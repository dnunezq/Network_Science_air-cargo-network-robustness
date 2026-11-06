"""Pruebas de la caracterización estructural con grafos de solución conocida."""
import json
import tempfile
import unittest
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

import exploracion_red as ex


def _edges(graph):
    return pd.DataFrame([{'u': u, 'v': v, 'freight_lb': 1000.0} for u, v in graph.edges])


def _codes(n):
    return {i: f'A{i:02d}' for i in range(n)}


class GraphConstruction(unittest.TestCase):
    def test_rejects_self_loops_and_outside_nodes(self):
        edges = pd.DataFrame({'u': [0, 1], 'v': [0, 7], 'freight_lb': [10.0, 10.0]})
        with self.assertRaises(ValueError):
            ex.graph_from_edges(range(5), edges.iloc[[0]])
        with self.assertRaises(ValueError):
            ex.graph_from_edges(range(5), edges.iloc[[1]])
        with self.assertRaises(ValueError):
            ex.graph_from_edges(range(5), pd.DataFrame({'u': [0], 'v': [1], 'freight_lb': [0.0]}))

    def test_keeps_isolated_nodes(self):
        graph = ex.graph_from_edges(range(6), pd.DataFrame({'u': [0], 'v': [1], 'freight_lb': [5.0]}))
        self.assertEqual(graph.number_of_nodes(), 6)
        self.assertEqual(graph.number_of_edges(), 1)
        self.assertEqual(graph[0][1]['weight'], 5.0)


class StructuralSummary(unittest.TestCase):
    def test_complete_graph(self):
        summary = ex.structural_summary(nx.complete_graph(8))
        self.assertEqual(summary['density'], 1.0)
        self.assertEqual(summary['average_clustering'], 1.0)
        self.assertEqual(summary['diameter'], 1)
        self.assertEqual(summary['max_core'], 7)
        self.assertIsNone(summary['degree_assortativity'])

    def test_star_is_disassortative_without_triangles(self):
        summary = ex.structural_summary(nx.star_graph(9))
        self.assertEqual(summary['average_clustering'], 0.0)
        self.assertEqual(summary['transitivity'], 0.0)
        self.assertEqual(summary['diameter'], 2)
        self.assertLess(summary['degree_assortativity'], -0.99)
        self.assertEqual(summary['max_degree'], 9)
        self.assertNotIn('rich_club', summary)

    def test_disconnected_graph_has_no_global_distances(self):
        summary = ex.structural_summary(nx.disjoint_union(nx.path_graph(3), nx.path_graph(4)))
        self.assertEqual(summary['components'], 2)
        self.assertIsNone(summary['diameter'])
        self.assertIsNone(summary['average_path_length'])

    def test_k_core_of_clique_with_pendants(self):
        graph = nx.complete_graph(10)
        graph.add_edges_from((i, 10 + i) for i in range(10))
        summary = ex.structural_summary(graph)
        self.assertEqual(summary['max_core'], 9)
        self.assertEqual(summary['max_core_size'], 10)


class DegreeDistribution(unittest.TestCase):
    def test_survival_is_monotone_and_starts_at_one(self):
        result = ex.degree_distribution(nx.barabasi_albert_graph(60, 3, seed=1))
        survival = [row['survival'] for row in result['histogram']]
        self.assertEqual(survival[0], 1.0)
        self.assertTrue(all(a >= b for a, b in zip(survival, survival[1:])))
        self.assertEqual(sum(row['count'] for row in result['histogram']), 60)


class Centralities(unittest.TestCase):
    def test_matches_networkx_and_ranks(self):
        graph = nx.gnp_random_graph(30, .3, seed=4)
        table, correlation = ex.centrality_table(graph, _codes(30))
        expected = nx.betweenness_centrality(graph, normalized=False)
        for row in table.itertuples():
            self.assertAlmostEqual(row.betweenness, expected[row.airport_id], places=12)
            self.assertAlmostEqual(row.degree_centrality, graph.degree(row.airport_id) / 29, places=12)
        # Rango medio en empates: la suma de puestos es fija, 1+2+...+n.
        self.assertAlmostEqual(table.rank_degree.sum(), 30 * 31 / 2)
        self.assertEqual(table.loc[table.degree.idxmax(), 'rank_degree'], table.rank_degree.min())
        self.assertEqual(correlation.shape, (4, 4))
        self.assertNotIn('pagerank', table.columns)
        self.assertTrue(np.allclose(np.diag(correlation), 1))

    def test_top_by_centrality(self):
        graph = nx.star_graph(6)
        table, _ = ex.centrality_table(graph, _codes(7))
        top = ex.top_by_centrality(table, top_k=3)
        self.assertEqual(list(top.columns), ['Grado', 'Intermediación', 'Cercanía', 'Autovector'])
        self.assertEqual(len(top), 3)
        self.assertTrue(top.iloc[0]['Grado'].startswith('A00'))


class Communities(unittest.TestCase):
    def test_nmi_identical_and_independent(self):
        self.assertAlmostEqual(ex.normalized_mutual_information([0, 0, 1, 1], [1, 1, 0, 0]), 1.0)
        self.assertAlmostEqual(ex.normalized_mutual_information([0, 0, 1, 1], [0, 1, 0, 1]), 0.0)
        self.assertEqual(ex.normalized_mutual_information([0, 0, 0], [0, 0, 0]), 1.0)
        with self.assertRaises(ValueError):
            ex.normalized_mutual_information([0, 1], [0])

    def test_two_cliques_are_recovered_and_stable(self):
        graph = nx.disjoint_union(nx.complete_graph(10), nx.complete_graph(10))
        graph.add_edge(0, 10)
        result = ex.community_analysis(graph, _codes(20), runs=6, seed=3)
        self.assertEqual(result['n_communities'], 2)
        self.assertEqual(result['nmi_mean'], 1.0)
        self.assertGreater(result['modularity'], 0.4)
        self.assertEqual(result['greedy']['nmi_with_louvain'], 1.0)
        self.assertEqual(sum(c['size'] for c in result['communities']), 20)
        self.assertTrue(all(row['stability'] == 1.0 for row in result['nodes']))

    def test_empty_graph_and_bad_runs(self):
        result = ex.community_analysis(nx.empty_graph(4), _codes(4), runs=3)
        self.assertEqual(result['n_communities'], 4)
        with self.assertRaises(ValueError):
            ex.community_analysis(nx.complete_graph(4), _codes(4), runs=0)


class Models(unittest.TestCase):
    def test_parameters_match_edges(self):
        params = ex.model_parameters(100, 2441)
        self.assertEqual(params['barabasi_albert']['m'], 42)
        self.assertLess(abs(42 * 58 - 2441), 10)
        self.assertEqual(params['watts_strogatz']['k'] % 2, 0)
        self.assertEqual(params['erdos_renyi']['m'], 2441)

    def test_course_profiles_are_recovered(self):
        ba = ex.model_comparison(nx.barabasi_albert_graph(100, 20, seed=3), replicas=4, seed=1)
        ws = ex.model_comparison(nx.connected_watts_strogatz_graph(100, 20, .05, seed=3), replicas=4, seed=1)
        self.assertEqual(ba['observed_labels']['hubs'], 'sí')
        self.assertEqual(ws['observed_labels'], {'clustering': 'alto', 'paths': 'cortos', 'hubs': 'no'})
        self.assertEqual(ws['course_match'], 'watts_strogatz')
        self.assertEqual(ws['models']['erdos_renyi']['labels'], ex.COURSE_PROFILES['erdos_renyi'])
        for model in ba['models'].values():
            self.assertLess(abs(model['metrics']['n_edges']['mean'] - 1600) / 1600, .05)

    def test_reproducible_and_validated(self):
        graph = nx.connected_watts_strogatz_graph(60, 8, .05, seed=7)
        first = ex.model_comparison(graph, replicas=3, seed=11)
        second = ex.model_comparison(graph, replicas=3, seed=11)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertIn(first['closest_model'], ex.MODELS)
        with self.assertRaises(ValueError):
            ex.model_comparison(graph, replicas=1)
        empty = ex.model_comparison(nx.empty_graph(5), replicas=2)
        self.assertIsNone(empty['closest_model'])


class EndToEnd(unittest.TestCase):
    def test_explore_and_export(self):
        graph = nx.gnp_random_graph(12, .5, seed=2)
        airports = pd.DataFrame({'airport_id': range(12), 'code': [f'A{i:02d}' for i in range(12)]})
        with tempfile.TemporaryDirectory() as directory:
            networks = {'annual': {'edges': _edges(graph),
                                   'adj': nx.to_numpy_array(graph, nodelist=range(12), dtype=bool)}}
            results = ex.explore_base_networks(networks, airports, directory, runs=3, replicas=3, seed=1)
            self.assertIn(('annual', 'base'), results)
            self.assertTrue((Path(directory) / 'resumen_estructura_base.csv').exists())
            payload = ex.export_exploration(results, airports, Path(directory) / 'exploracion.json')
            block = payload['networks']['annual']['base']
            self.assertEqual(len(block['communities']['membership']), 12)
            self.assertEqual(len(block['centrality_values']['degree']), 12)
            self.assertEqual(block['summary']['n_edges'], graph.number_of_edges())
            text = (Path(directory) / 'exploracion.json').read_text()
            self.assertNotIn('NaN', text)
            self.assertNotIn('communities_weighted', block)
            self.assertIn('models', block)
            lines = ex.describe_network_type(results[('annual', 'base')])
            self.assertTrue(any('Densidad' in line for line in lines))
            table = ex.model_table(results[('annual', 'base')])
            self.assertEqual(len(table), 4)

    def test_adjacency_mismatch_is_detected(self):
        graph = nx.path_graph(5)
        airports = pd.DataFrame({'airport_id': range(5), 'code': list('ABCDE')})
        with tempfile.TemporaryDirectory() as directory:
            networks = {'annual': {'edges': _edges(graph), 'adj': np.zeros((5, 5), dtype=bool)}}
            with self.assertRaises(AssertionError):
                ex.explore_base_networks(networks, airports, directory, runs=2, replicas=2)


if __name__ == '__main__':
    unittest.main()
