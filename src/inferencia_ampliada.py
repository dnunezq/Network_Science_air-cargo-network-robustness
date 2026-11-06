"""Sensibilidades exploratorias de M5/M6, separadas de la inferencia base.

La respuesta y varias covariables se derivan del mismo grafo. Estos análisis
describen asociaciones y ajuste interno; no establecen causalidad ni capacidad
predictiva. La permutación residual studentizada es un contraste de sensibilidad
tipo Freedman--Lane, no una garantía general de calibración para cualquier red.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits


CONTINUOUS = (
    "freight_sum", "degree_sum", "degree_diff", "betweenness_diff",
    "geo_distance_km",
)
M5_TERMS = (
    "degree_sum", "degree_diff", "betweenness_diff", "geo_distance_km",
    "direct", "freight_sum×direct", "degree_sum×direct", "degree_diff×direct",
)
METHOD = "Freedman–Lane: permutación conjunta de residuos por nodos; t bilateral"


def _validate_input(predictors, airport_ids, permutations, seed):
    if isinstance(permutations, (bool, np.bool_)) or not isinstance(permutations, (int, np.integer)) or permutations < 1:
        raise ValueError("permutations debe ser un entero positivo.")
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError("seed debe ser un entero no negativo.")
    required = {"a_id", "b_id", "score", "direct", *CONTINUOUS}
    if not required.issubset(predictors.columns):
        raise ValueError(f"Faltan columnas: {sorted(required-set(predictors.columns))}")
    frame = predictors.copy()
    ids = list(airport_ids)
    if len(ids) != len(set(ids)):
        raise ValueError("airport_ids contiene identificadores repetidos.")
    lookup = {value: i for i, value in enumerate(ids)}
    if not (frame.a_id.isin(lookup).all() and frame.b_id.isin(lookup).all()):
        raise ValueError("Hay extremos de parejas fuera de airport_ids.")
    ii = frame.a_id.map(lookup).to_numpy(dtype=int)
    jj = frame.b_id.map(lookup).to_numpy(dtype=int)
    keys = np.sort(np.column_stack([ii, jj]), axis=1)
    if (ii == jj).any() or len(np.unique(keys, axis=0)) != len(frame):
        raise ValueError("Se requieren parejas únicas, no ordenadas y sin autoenlaces.")
    if len(frame) != len(ids)*(len(ids)-1)//2:
        raise ValueError("Se requieren todas las parejas del universo de nodos.")
    try:
        numeric = frame[["score", "direct", *CONTINUOUS]].astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Respuesta, indicadores y predictores deben ser numéricos.") from exc
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("No se admiten valores no finitos en respuesta o predictores.")
    if not numeric.direct.isin([0., 1.]).all():
        raise ValueError("direct debe contener solo 0/1 o False/True.")
    if np.ptp(numeric.score.to_numpy()) == 0:
        raise ValueError("La respuesta debe tener variación.")
    frame[["score", "direct", *CONTINUOUS]] = numeric
    return frame, ii, jj, len(ids)


def _designs(frame):
    raw = frame[list(CONTINUOUS)].astype(float)
    mean, scale = raw.mean(), raw.std(ddof=0)
    if (scale <= 0).any():
        raise ValueError("Todos los predictores continuos deben tener variación.")
    z = (raw-mean)/scale
    z["direct"] = frame.direct.astype(float)
    for name in CONTINUOUS:
        z[name+"×direct"] = z[name]*z.direct
    z["degree_sum_squared"] = z.degree_sum**2
    terms = {"M5": list(M5_TERMS), "M6": [*M5_TERMS, "degree_sum_squared"]}
    designs = {}
    for model, names in terms.items():
        x = np.column_stack([np.ones(len(frame)), z[names].to_numpy()])
        if len(x) <= x.shape[1]:
            raise ValueError(f"{model}: se necesitan más parejas que parámetros.")
        if np.linalg.matrix_rank(x) != x.shape[1]:
            raise ValueError(f"{model}: diseño sin rango completo; revisar variables y conexiones.")
        designs[model] = (x, ["intercept", *names])
    standardization = {
        name: {"mean": float(mean[name]), "std": float(scale[name])}
        for name in CONTINUOUS
    }
    return designs, z, standardization


def _fit(x, y):
    inverse = np.linalg.pinv(x)
    beta = inverse@y
    fitted = x@beta
    residual = y-fitted
    sse = float(residual@residual)
    sst = float((y-y.mean())@(y-y.mean()))
    df = len(y)-x.shape[1]
    variance_factors = np.diag(inverse@inverse.T)
    # Un ajuste exacto tiene t infinito en teoría. Un suelo relativo evita NaN
    # sin inventar p paramétricos; se registra si fue necesario en diagnósticos.
    floor = np.finfo(float).eps*max(sst, np.finfo(float).tiny)
    t_values = beta/np.sqrt(max(sse, floor)/df*variance_factors)
    return {
        "inverse": inverse, "beta": beta, "fitted": fitted, "residual": residual,
        "sse": sse, "sst": sst, "df": df, "variance_factors": variance_factors,
        "t_values": t_values, "floor_used": sse < floor,
        "r2": 1-sse/sst, "rmse": float(np.sqrt(sse/len(y))),
    }


def _partial_residual_test(x, y, fitted, ii, jj, n_nodes, permutations, term_index):
    """Contrasta un término manteniendo el ajuste de los demás bajo la nula.

    Se ajusta Y~X[-k], se forma una matriz simétrica con sus residuos y se
    aplica la misma permutación a ambos ejes. Y* = ajuste_reducido + residuos*.
    Se reajusta el modelo completo y se compara |t_k*| con |t_k|.
    """
    if term_index <= 0 or term_index >= x.shape[1]:
        raise ValueError("El contraste parcial requiere un término distinto de la constante.")
    reduced = np.delete(x, term_index, axis=1)
    reduced_prediction = reduced@np.linalg.lstsq(reduced, y, rcond=None)[0]
    residual = y-reduced_prediction
    matrix = np.zeros((n_nodes, n_nodes))
    matrix[ii, jj] = matrix[jj, ii] = residual
    observed = abs(fitted["t_values"][term_index])
    counts = 0
    for start in range(0, len(permutations), 128):
        perm = permutations[start:start+128]
        y_perm = reduced_prediction[:, None] + matrix[perm[:, ii], perm[:, jj]].T
        beta_perm = fitted["inverse"]@y_perm
        errors = y_perm-x@beta_perm
        sse_perm = (errors*errors).sum(axis=0)
        centered = y_perm-y_perm.mean(axis=0)
        floors = np.finfo(float).eps*np.maximum((centered*centered).sum(axis=0), np.finfo(float).tiny)
        t_perm = beta_perm[term_index]/np.sqrt(
            np.maximum(sse_perm, floors)/fitted["df"]*fitted["variance_factors"][term_index]
        )
        if not np.isfinite(t_perm).all():
            raise ArithmeticError("Estadístico de permutación no finito.")
        counts += int((np.abs(t_perm) >= observed-1e-12).sum())
    p = (counts+1)/(len(permutations)+1)
    # Aproximación Monte Carlo; no es incertidumbre de muestreo ni un IC del beta.
    mcse = float(np.sqrt(p*(1-p)/(len(permutations)+1)))
    return {"p_sensitivity": float(p), "mc_standard_error": mcse,
            "permutation_exceedances": counts}


def run_inference_extensions(predictors, airport_ids, out_dir, permutations=1999, seed=2025):
    """Escribe diagnósticos nuevos y devuelve un resumen JSON serializable.

    predictors: DataFrame anual completo de 4.950 parejas en el proyecto.
    airport_ids: identificadores del universo en un orden fijo y reproducible.
    out_dir: carpeta exclusiva de ampliaciones; nunca sobrescribe p de la base.
    permutations: entero positivo; resolución mínima 1/(permutations+1).
    """
    frame, ii, jj, n_nodes = _validate_input(predictors, airport_ids, permutations, seed)
    designs, standardized, standardization = _designs(frame)
    y = frame.score.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    permutations_array = np.array([rng.permutation(n_nodes) for _ in range(permutations)])
    residuals = frame[[name for name in ("a_id", "b_id", "a", "b", "pair_key") if name in frame]].copy()
    residuals["observed_score"] = y
    for name in CONTINUOUS:
        residuals[name] = frame[name].to_numpy()
        residuals[name+"_z"] = standardized[name].to_numpy()
    residuals["direct"] = frame.direct.to_numpy()
    residuals["degree_sum_squared"] = standardized.degree_sum_squared.to_numpy()
    models, flat_coefficients, vif_rows = [], [], []
    with threadpool_limits(limits=1):
        for name, (x, terms) in designs.items():
            fit = _fit(x, y)
            residuals["fitted_"+name] = fit["fitted"]
            residuals["residual_"+name] = fit["residual"]
            centered_ss = ((x-x.mean(axis=0))**2).sum(axis=0)
            vifs = {term: float(fit["variance_factors"][k]*centered_ss[k])
                    for k, term in enumerate(terms) if k > 0}
            for term, value in vifs.items():
                vif_rows.append({"model": name, "term": term, "vif": value})
            quadratic = standardized.degree_sum_squared.to_numpy()
            curve_r = None if fit["floor_used"] else float(np.corrcoef(fit["residual"], quadratic)[0, 1])
            model = {
                "model": name, "r2": float(fit["r2"]),
                "adjusted_r2": float(1-(1-fit["r2"])*(len(y)-1)/fit["df"]),
                "n_predictors": len(terms)-1, "matrix_rank": int(np.linalg.matrix_rank(x)),
                "condition_number": float(np.linalg.cond(x)),
                "residual_rmse": fit["rmse"], "coefficients": [],
                "diagnostics": {"vif": vifs, "max_vif": max(vifs.values()),
                    "residual_degree_squared_correlation": curve_r,
                    "studentization_numerical_floor_used": bool(fit["floor_used"])},
            }
            for k, term in enumerate(terms):
                row = {"term": term, "coefficient": float(fit["beta"][k]),
                       "t_observed": float(fit["t_values"][k]),
                       "p_sensitivity": None, "mc_standard_error": None,
                       "permutation_exceedances": None}
                if k > 0:
                    row.update(_partial_residual_test(x, y, fit, ii, jj, n_nodes, permutations_array, k))
                model["coefficients"].append(row)
                flat_coefficients.append({"model": name, **row})
            models.append(model)
    by_model = {m["model"]: m for m in models}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifacts = {key: str(out/file) for key, file in {
        "summary_json": "inferencia_ampliada_resumen.json",
        "coefficients_csv": "inferencia_ampliada_coeficientes.csv",
        "models_csv": "inferencia_ampliada_modelos.csv",
        "residuals_csv": "inferencia_ampliada_residuos.csv",
        "vif_csv": "inferencia_ampliada_vif.csv",
    }.items()}
    summary = {
        "schema_version": "1.0", "method": METHOD,
        "inference_scope": "Sensibilidad metodológica exploratoria; ajuste dentro de muestra.",
        "permutations": int(permutations), "seed": int(seed),
        "n_nodes": n_nodes, "n_pairs": len(frame), "response": "score anual del índice compuesto",
        "standardization": standardization, "models": models,
        "comparison": {
            "r2_M5": by_model["M5"]["r2"], "r2_M6": by_model["M6"]["r2"],
            "delta_r2": by_model["M6"]["r2"]-by_model["M5"]["r2"],
            "rmse_M5": by_model["M5"]["residual_rmse"], "rmse_M6": by_model["M6"]["residual_rmse"],
        },
        "notes": [
            "M6 añade el cuadrado de degree_sum estandarizado a la especificación fija M5.",
            "R², R² ajustado y RMSE son descripciones del ajuste interno; no validación predictiva ni evidencia causal.",
            "Los p_sensitivity conservan los otros términos bajo la nula mediante ajuste reducido y permutación de residuos por nodos.",
            "El estadístico t solo studentiza la comparación por permutaciones; no se usan p-valores t paramétricos.",
            "Se usa contraste bilateral y corrección +1. La constante no recibe p de sensibilidad.",
            "Los p de esta sensibilidad no reemplazan los p de permutación de Y de la entrega base.",
            "Sin ajuste por contrastes múltiples. La intercambiabilidad residual requiere juicio metodológico; no se certifica calibración general.",
            "El error Monte Carlo es aproximado y solo describe variación por permutaciones; no es intervalo de confianza del coeficiente.",
            "La matriz de respuesta y varias covariables proceden de la misma topología; un ajuste alto puede reflejar relaciones estructurales matemáticas.",
        ], "artifacts": artifacts,
    }
    # allow_nan=False evita exportaciones JSON que el navegador no pueda leer.
    encoded = json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)
    pd.DataFrame(flat_coefficients).to_csv(artifacts["coefficients_csv"], index=False)
    pd.DataFrame([{k: v for k, v in m.items() if k not in ("coefficients", "diagnostics")} for m in models]).to_csv(artifacts["models_csv"], index=False)
    residuals.to_csv(artifacts["residuals_csv"], index=False)
    pd.DataFrame(vif_rows).to_csv(artifacts["vif_csv"], index=False)
    Path(artifacts["summary_json"]).write_text(encoded, encoding="utf-8")
    return summary
