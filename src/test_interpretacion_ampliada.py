"""Comprueba mecanismos sobre los mismos extremos supervivientes."""
import unittest
import networkx as nx
from ampliaciones_interpretacion import _survivor_paths


class SurvivorPathTests(unittest.TestCase):
    def test_removing_an_articulation_tracks_disconnection(self):
        result = _survivor_paths(nx.path_graph(4),[1])
        self.assertEqual(result['n_surviving_pairs'],3)
        self.assertEqual(result['worsened_pairs'],2)
        self.assertEqual(result['disconnected_pairs'],2)
        self.assertAlmostEqual(result['global_before_survivors'],11/18)
        self.assertAlmostEqual(result['global_after_survivors'],1/3)

    def test_leaf_removal_changes_population_but_not_surviving_paths(self):
        result = _survivor_paths(nx.star_graph(4),[4])
        self.assertEqual(result['n_surviving_pairs'],6)
        self.assertEqual(result['worsened_pairs'],0)
        self.assertEqual(result['disconnected_pairs'],0)
        self.assertEqual(result['global_before_survivors'],result['global_after_survivors'])

if __name__=='__main__':
    unittest.main()
