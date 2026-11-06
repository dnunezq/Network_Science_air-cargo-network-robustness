"""Verifica pertenencia exacta, alineación y fidelidad del exportador del explorador."""
import json
from pathlib import Path
import unittest
from itertools import combinations
import numpy as np
import pandas as pd
from exportar_explorador import stability_table, VARIANT_ORDER, PAIR_FIELDS


def sample_frame(scores=(2., 1., 1.)):
    frame = pd.DataFrame({
        'pair_key': ['10-20','10-30','20-40'],
        'a_id': [10,10,20], 'b_id': [20,30,40],
        'a': ['A','A','B'], 'b': ['B','C','D'],
        'score_comparable': list(scores),
    })
    frame['rank'] = frame.score_comparable.rank(ascending=False,method='average')
    return frame


class StabilitySemanticsTests(unittest.TestCase):
    def test_tie_at_cutoff_uses_ids_without_expanding_top_k(self):
        base = sample_frame().iloc[::-1].copy()
        variant = sample_frame().iloc[[1,0,2]].copy()
        result = stability_table({'base':base,'variant':variant},top_k=2).set_index('pair_key')
        # A-C y B-D tienen rango medio 2,5; solo A-C entra al top2.
        self.assertEqual(result.loc['10-30','base_rank'],2.5)
        self.assertEqual(result.loc['20-40','base_rank'],2.5)
        self.assertEqual(result.loc['10-30','top_count'],2)
        self.assertEqual(result.loc['20-40','top_count'],0)
        self.assertEqual(int(result.base_top.sum()),2)
        self.assertEqual(int(result.variant_top.sum()),2)

    def test_rows_are_aligned_by_pair_identity(self):
        base = sample_frame((3.,2.,1.))
        variant = sample_frame((3.,0.,4.)).iloc[[2,0,1]].copy()
        result = stability_table({'base':base,'variant':variant},top_k=2).set_index('pair_key')
        self.assertEqual(result.loc['10-20','top_count'],2)
        self.assertEqual(result.loc['10-30','top_count'],1)
        self.assertEqual(result.loc['20-40','top_count'],1)
        self.assertEqual(result.loc['10-20','rank_min'],1)
        self.assertEqual(result.loc['10-20','rank_max'],2)
        self.assertEqual(result.loc['10-30','rank_mean'],2.5)

    def test_missing_pair_is_an_explicit_error(self):
        base = sample_frame()
        with self.assertRaises(ValueError):
            stability_table({'base':base,'variant':base.iloc[:-1]},top_k=2)

    def test_extra_pair_is_not_silently_dropped(self):
        base = sample_frame()
        extra = pd.DataFrame([{'pair_key':'30-40','a_id':30,'b_id':40,
                               'a':'C','b':'D','score_comparable':-1.,'rank':4.}])
        with self.assertRaises(ValueError):
            stability_table({'base':base,'variant':pd.concat([base,extra],ignore_index=True)},top_k=2)

    def test_unknown_endpoint_with_existing_key_is_rejected(self):
        base = sample_frame()
        corrupted = base.copy()
        corrupted.loc[0,'a_id'] = 999
        with self.assertRaises(ValueError):
            stability_table({'base':base,'variant':corrupted},top_k=2)

    def test_duplicate_keys_are_rejected(self):
        base = sample_frame()
        repeated = pd.concat([base,base.iloc[[0]]],ignore_index=True)
        with self.assertRaises(ValueError):
            stability_table({'base':base,'variant':repeated},top_k=2)


class ExportedScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # En el repositorio los módulos están en src/ y los datos un nivel arriba.
        cls.root = (lambda here: here if (here/'app').exists() else here.parent)(Path(__file__).resolve().parent)
        path = cls.root/'app/dist/data/interactive.json'
        if not path.exists():
            raise unittest.SkipTest('Generar exportar_explorador.py primero.')
        cls.data = json.loads(path.read_text())
        cls.extensions = json.loads((cls.root/'resultados/ampliaciones/extensions.json').read_text())
        cls.catalog = pd.read_csv(cls.root/'resultados/catalogo_aeropuertos.csv')

    def test_canonical_mapping_and_common_scores_match_all_saved_scenarios(self):
        data = self.data
        ids = self.catalog.airport_id.astype(int).tolist()
        self.assertEqual(data['airport_ids'],ids)
        self.assertEqual(data['codes'],self.catalog.code.tolist())
        self.assertEqual(data['pair_indices'],[list(p) for p in combinations(range(100),2)])
        keys = [f'{min(ids[i],ids[j])}-{max(ids[i],ids[j])}' for i,j in data['pair_indices']]
        weights = np.array(self.extensions['structural']['sensitivity']['calibration']['weights'])
        scales = np.array(self.extensions['structural']['sensitivity']['calibration']['scales'])
        self.assertEqual(data['pair_fields'],PAIR_FIELDS)
        for period,scenarios in data['periods'].items():
            self.assertEqual(set(scenarios),set(VARIANT_ORDER))
            for variant,scenario in scenarios.items():
                with self.subTest(period=period,variant=variant):
                    frame = pd.read_csv(self.root/f'resultados/ampliaciones/pares_sensibilidad_{period}_{variant}.csv')
                    frame = frame.set_index('pair_key').loc[keys]
                    self.assertEqual(len(frame),4950)
                    self.assertEqual(frame.index.nunique(),4950)
                    # Comprobación independiente de la calibración común.
                    synergy = frame[['synergy_global','synergy_local','synergy_natural']].to_numpy()
                    normalized = np.divide(synergy,scales,out=np.zeros_like(synergy),where=scales>0)
                    expected = normalized@weights
                    np.testing.assert_allclose(expected,frame.score_comparable,atol=1e-12,rtol=1e-10)
                    expected_ranks = pd.Series(expected).rank(ascending=False,method='average')
                    np.testing.assert_allclose(expected_ranks,frame['rank'],atol=1e-10)
                    if variant=='base':
                        np.testing.assert_allclose(scenario['comparison_pairs'],frame[['score_comparable','rank']],atol=1e-12)
                    else:
                        self.assertEqual(scenario['n_nodes'],100)
                        self.assertEqual(len(scenario['nodes']),100)
                        self.assertEqual(len(scenario['edges']),scenario['n_edges'])
                        np.testing.assert_allclose(scenario['pairs'],frame[PAIR_FIELDS],atol=1e-12)

    def test_single_impacts_and_pair_impacts_match_original_simulation_caches(self):
        for period,scenarios in self.data['periods'].items():
            for variant,scenario in scenarios.items():
                if variant=='base':
                    continue
                with self.subTest(period=period,variant=variant):
                    with np.load(self.root/f'cache/ampliaciones/{period}_{variant}.npz') as cache:
                        single = cache['single_impact']
                        joint = cache['joint_impact']
                        baseline = cache['baseline']
                    nodes = scenario['nodes']
                    self.assertEqual([n['airport_id'] for n in nodes],self.data['airport_ids'])
                    np.testing.assert_allclose(
                        [scenario['metrics'][m] for m in
                         ['global_efficiency','local_efficiency','natural_connectivity']],
                        baseline,atol=1e-12)
                    self.assertEqual(sum(n['degree'] for n in nodes),2*len(scenario['edges']))
                    self.assertAlmostEqual(sum(n['freight_lb'] for n in nodes),
                                           2*sum(e['freight_lb'] for e in scenario['edges']),
                                           delta=1e-5)
                    np.testing.assert_allclose([[n['impact_global'],n['impact_local'],n['impact_natural']]
                                               for n in nodes],single,atol=1e-12)
                    packed = np.asarray(scenario['pairs'])
                    fields = self.data['pair_fields']
                    columns = [fields.index('impact_'+s) for s in ['global','local','natural']]
                    np.testing.assert_allclose(packed[:,columns],joint,atol=1e-12)
                    for a,b in self.data['pair_indices'][::503]:
                        node_a = nodes[a]
                        node_b = nodes[b]
                        self.assertNotEqual(node_a['id'],node_b['id'])

    def test_stability_arrays_preserve_frequency_and_annual_robust_pairs(self):
        data = self.data
        for period,rows in data['stability'].items():
            frame = pd.read_csv(self.root/f'resultados/ampliaciones/estabilidad_parejas_{period}.csv')
            expected_columns = ['top_count','rank_min','rank_max','rank_mean']+[v+'_rank' for v in VARIANT_ORDER]
            np.testing.assert_allclose(rows,frame[expected_columns],atol=1e-10)
            counts = frame[[v+'_top' for v in VARIANT_ORDER]].sum(axis=1)
            np.testing.assert_array_equal(counts,frame.top_count)
            self.assertEqual(int(frame.top_count.sum()),4*20)
        summary = next(s for s in data['stability_summary'] if s['period']=='annual')
        self.assertEqual(summary['pairs_top20_all_rules'],2)
        self.assertEqual({frozenset((p['a'],p['b'])) for p in summary['pairs']},
                         {frozenset(('SDF','SEA')),frozenset(('SDF','SFO'))})
        self.assertIn('no probabilidad',data['metadata']['stability_scope'])


if __name__=='__main__':
    unittest.main(verbosity=2)
