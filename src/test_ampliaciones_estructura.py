"""Pruebas de semántica de escenarios y conservación de flujos."""
import unittest
import numpy as np
import pandas as pd
from ampliaciones_estructura import (_undirected_edges, _variant_edges,
                                    _graph_from_edges, _remove_operator, _comparison)


class StructuralExtensionTests(unittest.TestCase):
    def test_persistence_counts_unique_calendar_months_across_directions(self):
        routes = pd.DataFrame({'MONTH': [1, 1, 2, 3],
                               'ORIGIN_AIRPORT_ID': [10, 20, 10, 20],
                               'DEST_AIRPORT_ID': [20, 10, 20, 30],
                               'freight_lb': [100., 200., 300., 400.],
                               'departures': [1, 2, 3, 4]})
        edges = _undirected_edges(routes, [10, 20, 30, 40], [1, 2, 3])
        first = edges[edges.u.eq(10)].iloc[0]
        self.assertEqual(first.months_present, 2)
        self.assertEqual(first.freight_lb, 600)
        filtered = _variant_edges(edges, 'half_months', 3)
        self.assertEqual(len(filtered), 1)
        graph, adj = _graph_from_edges([10, 20, 30, 40], filtered)
        self.assertEqual(len(graph), 4)
        self.assertEqual(list(graph.degree([30, 40])), [(30, 0), (40, 0)])
        self.assertEqual(adj.sum(), 2)

    def test_volume_threshold_uses_calendar_months_not_active_months(self):
        edges = pd.DataFrame({'u': [1, 1, 2], 'v': [2, 3, 3],
                              'freight_lb': [2999., 3000., 4000.],
                              'months_present': [1, 1, 3], 'departures': [1, 1, 3]})
        got = _variant_edges(edges, 'min_monthly_freight', 3)
        self.assertEqual(got.freight_lb.tolist(), [3000., 4000.])
        self.assertEqual(len(_variant_edges(edges, 'min_monthly_freight', 12)), 0)
        self.assertEqual(len(_variant_edges(edges, 'all_months', 3)), 1)

    def test_operator_removal_preserves_shared_edges_and_volume_identity(self):
        base = pd.DataFrame({'u': [1, 1, 2], 'v': [2, 3, 3],
                             'freight_lb': [100., 60., 40.]})
        operator = pd.DataFrame({'u': [1, 1], 'v': [2, 3],
                                 'freight_lb': [30., 60.]})
        remaining = _remove_operator(base, operator)
        self.assertEqual(set(zip(remaining.u, remaining.v)), {(1, 2), (2, 3)})
        self.assertEqual(float(remaining.freight_lb.sum()), 110)
        self.assertEqual(float(remaining.freight_lb.sum() + operator.freight_lb.sum()), 200)

    def test_comparison_aligns_pairs_and_ignores_own_scales(self):
        base = pd.DataFrame({'pair_key': ['1-2', '1-3', '2-3'],
                             'a_id': [1, 1, 2], 'b_id': [2, 3, 3],
                             'score_comparable': [.2, .5, .5], 'score_own': [1, 2, 3]})
        variant = base.iloc[::-1].copy()
        variant['score_own'] = [100, 0, -100]
        adj = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], dtype=bool)
        result = _comparison(base, variant, adj, adj, top_k=2)
        self.assertAlmostEqual(result['spearman'], 1)
        self.assertEqual(result['shared_top'], 2)
        self.assertEqual(result['edge_jaccard'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
