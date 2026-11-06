"""Pruebas científicas y de integridad, ejecutables con unittest."""
import unittest
from analisis_red import *

class ScientificTests(unittest.TestCase):
    def test_metrics_against_reference(self):
        self.assertTrue(verify_metrics()['networkx_agreement'])

    def test_empty_singleton_and_128_node_boundary(self):
        for n in [0,1,128]:
            np.testing.assert_allclose(robustness_metrics(np.zeros((n,n),dtype=bool)),0,atol=1e-12)
        g=nx.path_graph(128)
        np.testing.assert_allclose(robustness_metrics(nx.to_numpy_array(g,dtype=bool))[:2],
            [nx.global_efficiency(g),nx.local_efficiency(g)],atol=1e-12)

    def test_entropy_invariance_and_degenerate_columns(self):
        s=np.array([[1.,0.,2.],[-2.,0.,2.],[3.,0.,2.],[4.,0.,2.]])
        r=entropy_composite(s)
        self.assertAlmostEqual(r['weights'][0],1)
        np.testing.assert_allclose(r['weights'][1:],0)
        np.testing.assert_allclose(r['score'],s[:,0]/4)
        other=entropy_composite(s*np.array([9,4,17]))
        np.testing.assert_allclose(r['score'],other['score'])
        np.testing.assert_allclose(entropy_composite(np.zeros((5,3)))['score'],0)

    def test_mrqap_known_linear_response(self):
        rng=np.random.default_rng(42)
        n=14; ij=np.array(list(combinations(range(n),2)))
        x=rng.uniform(size=(len(ij),5))
        d=rng.integers(0,2,len(ij))
        names=['freight_sum','degree_sum','degree_diff','betweenness_diff','geo_distance_km']
        p=pd.DataFrame(x,columns=names)
        p['direct']=d;p['a_id']=ij[:,0];p['b_id']=ij[:,1]
        p['score']=3*x[:,1]-2*d
        m,c,_=mrqap_models(p,list(range(n)),permutations=99,seed=2025)
        self.assertAlmostEqual(m.set_index('model').loc['M3','r2'],1)
        co=c[c.model.eq('M3')].set_index('variable')
        self.assertAlmostEqual(co.loc['degree_sum','coefficient'],3*x[:,1].std())
        self.assertAlmostEqual(co.loc['direct','coefficient'],-2)
        self.assertTrue(c.p_permutation.between(.01,1).all())

    def test_exported_integrity(self):
        # En el repositorio los módulos están en src/ y los datos un nivel arriba.
        root=(lambda here: here if (here/'app').exists() else here.parent)(Path(__file__).resolve().parent)
        path=root/'app/dist/data/network.json'
        if not path.exists():self.skipTest('Ejecutar el análisis antes de comprobar la exportación.')
        data=json.loads(path.read_text())
        codes={a['id'] for a in data['airports']}
        self.assertEqual(len(codes),100)
        for period in data['periods'].values():
            self.assertEqual(len(period['pairs']),4950)
            self.assertEqual({n['id'] for n in period['nodes']},codes)
            self.assertEqual(len(period['edges']),period['n_edges'])
            for p in period['pairs'][::101]:
                self.assertIn(p['a'],codes);self.assertIn(p['b'],codes)
                for k in SHORT:
                    self.assertAlmostEqual(p['synergy_'+k],p['impact_'+k]-p['single_a_'+k]-p['single_b_'+k],places=10)

if __name__=='__main__':unittest.main(verbosity=2)
