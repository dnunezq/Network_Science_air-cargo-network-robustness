"""Ejecuta las ampliaciones y exporta exactamente los datos de la app."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from analisis_red import (
    read_t100, clean_t100, airport_catalog, aggregate_routes, build_networks,
    simulate_period, attach_results, pair_predictors, write_json, sha256_file,
)
from coordenadas import merge_coordinates
from ampliaciones_estructura import run_structural_extensions
from ampliaciones_interpretacion import run_interpretation_extensions
from inferencia_ampliada import run_inference_extensions


def run_project_extensions(raw, clean, routes, airports, networks, simulations,
                           root, permutations=1999, seed=2025, use_cache=True):
    root = Path(root)
    out = root/'resultados'/'ampliaciones'
    out.mkdir(parents=True, exist_ok=True)
    structural = run_structural_extensions(raw, clean, routes, airports, networks, root, use_cache)
    interpretation = run_interpretation_extensions(networks, simulations, airports, out)
    predictors = pair_predictors(networks['annual'], airports)
    values = predictors[['a_id','b_id','score','freight_sum','degree_sum','degree_diff',
                         'betweenness_diff','geo_distance_km','direct']].to_numpy(dtype=float)
    # La huella usa el código del método, que vive junto a este módulo.
    method_path = Path(__file__).resolve().parent/'inferencia_ampliada.py'
    method = method_path.read_bytes() if method_path.exists() else b'inferencia-ampliada-v1'
    fingerprint = hashlib.sha256(values.tobytes()+method+str((permutations,seed)).encode()).hexdigest()
    receipt = out/'cache_inferencia.json'
    summary = out/'inferencia_ampliada_resumen.json'
    expected = [summary, out/'inferencia_ampliada_residuos.csv',
                out/'inferencia_ampliada_coeficientes.csv', out/'inferencia_ampliada_vif.csv']
    valid_cache = use_cache and receipt.exists() and all(p.exists() for p in expected)
    if valid_cache:
        record = json.loads(receipt.read_text())
        valid_cache = record.get('fingerprint')==fingerprint and all(
            record.get('files',{}).get(p.name)==sha256_file(p) for p in expected)
    if valid_cache:
        print('Inferencia ampliada: caché de insumos, método y archivos verificada.', flush=True)
        inference = json.loads(summary.read_text())
    else:
        print(f'Inferencia ampliada: {permutations:,} permutaciones por término y modelo.', flush=True)
        inference = run_inference_extensions(predictors, airports.airport_id.tolist(), out, permutations, seed)
        write_json(receipt, {'fingerprint': fingerprint,
                            'files': {p.name: sha256_file(p) for p in expected}})
    baseline_file = root/'resultados'/'mrqap_coeficientes.csv'
    baseline = pd.read_csv(baseline_file) if baseline_file.exists() else pd.DataFrame()
    for model in inference['models']:
        reference = baseline[baseline.model.eq(model['model'])] if len(baseline) else pd.DataFrame()
        lookup = reference.set_index('variable').p_permutation.to_dict() if len(reference) else {}
        for row in model['coefficients']:
            row['p_baseline_Y'] = None if row['term']=='intercept' else lookup.get(row['term'])
    # Las rutas de artefactos son relativas para que el paquete sea transportable.
    inference['artifacts'] = {k: 'resultados/ampliaciones/'+Path(v).name
                              for k,v in inference.get('artifacts',{}).items()}
    result = {
        'metadata': {'version': 2, 'year': 2025, 'seed': seed,
                     'raw_zip_sha256': sha256_file(root/'data/raw/BTS_T100_Domestic_Segment_All_Carriers_2025.zip'),
                     'scope': 'Sensibilidad e interpretación retrospectiva; no predicción de pérdidas operativas.'},
        **structural, 'interpretation': interpretation, 'inference': inference,
    }
    write_json(out/'extensions.json', result)
    write_json(root/'app/dist/data/extensions.json', result)
    return result


def load_base(root, use_cache=True):
    """Reconstruye la base con la instantánea conservada, sin usar CSV derivados."""
    root = Path(root)
    raw = read_t100(root/'data/raw/BTS_T100_Domestic_Segment_All_Carriers_2025.zip')
    clean, audit = clean_t100(raw)
    airports, _ = airport_catalog(clean)
    routes = aggregate_routes(clean)
    networks = build_networks(routes, airports)
    simulations = {p: simulate_period(n['adj'],root/'cache'/f'{p}.npz',use_cache)
                   for p,n in networks.items()}
    attach_results(networks, simulations, airports)
    coords = pd.read_csv(root/'data/raw/coordenadas_bts.csv',low_memory=False)
    airports, _ = merge_coordinates(airports, clean, coords)
    return raw, clean, routes, airports, networks, simulations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--permutations',type=int,default=1999)
    parser.add_argument('--recompute',action='store_true')
    args = parser.parse_args()
    root = (lambda here: here if (here/'app').exists() else here.parent)(Path(__file__).resolve().parent)
    base = load_base(root, not args.recompute)
    result = run_project_extensions(*base, root, args.permutations, 2025, not args.recompute)
    print('Ampliaciones completas:',root/'resultados/ampliaciones')
    print('M5/M6:',result['inference']['comparison'])


if __name__=='__main__':
    main()
