"""Comprobaciones focalizadas; no certifican calibración estadística general."""
import json
import tempfile
import unittest
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd
from inferencia_ampliada import (
    CONTINUOUS, _fit, _partial_residual_test, run_inference_extensions,
)


def sample_predictors(n=12, seed=47):
    rng = np.random.default_rng(seed)
    pairs = np.array(list(combinations(range(n), 2)))
    data = pd.DataFrame(rng.normal(size=(len(pairs), 5)), columns=CONTINUOUS)
    data["a_id"], data["b_id"] = pairs[:, 0], pairs[:, 1]
    data["direct"] = rng.integers(0, 2, len(pairs))
    degree_z = (data.degree_sum-data.degree_sum.mean())/data.degree_sum.std(ddof=0)
    data["score"] = 1.3+0.8*degree_z+2.4*degree_z**2-0.6*data.direct
    return data, list(range(n))


class InferenceExtensionTests(unittest.TestCase):
    def test_m6_recovers_known_quadratic_coefficients(self):
        frame, ids = sample_predictors()
        with tempfile.TemporaryDirectory() as directory:
            result = run_inference_extensions(frame, ids, directory, permutations=39, seed=8)
            model = next(m for m in result["models"] if m["model"] == "M6")
            co = {row["term"]: row for row in model["coefficients"]}
            self.assertAlmostEqual(model["r2"], 1., places=12)
            for term, value in [("intercept", 1.3), ("degree_sum", 0.8),
                                ("degree_sum_squared", 2.4), ("direct", -0.6)]:
                self.assertAlmostEqual(co[term]["coefficient"], value, places=10)
            self.assertIsNone(co["intercept"]["p_sensitivity"])
            for row in model["coefficients"][1:]:
                self.assertTrue(np.isfinite(row["t_observed"]))
                self.assertGreaterEqual(row["p_sensitivity"], 1/40)
                self.assertLessEqual(row["p_sensitivity"], 1)
            self.assertTrue(model["diagnostics"]["studentization_numerical_floor_used"])
            self.assertGreater(result["comparison"]["delta_r2"], 0.1)
            for path in result["artifacts"].values():
                self.assertTrue(Path(path).is_file())
            json.dumps(result, allow_nan=False)
            rerun = run_inference_extensions(frame, ids, directory, permutations=39, seed=8)
            self.assertEqual(result["models"], rerun["models"])

    def test_partial_null_and_nuisance_invariance(self):
        # El efecto de X1 es exactamente nulo pese a estar correlacionado con
        # una covariable Z de efecto fuerte. El residuo se hace ortogonal al
        # diseño para comprobar esta hipótesis parcial conocida algebraicamente.
        rng = np.random.default_rng(2025)
        n = 12
        pairs = np.array(list(combinations(range(n), 2)))
        z = rng.normal(size=len(pairs))
        x1 = 0.9*z+0.3*rng.normal(size=len(pairs))
        design = np.column_stack([np.ones(len(pairs)), x1, z])
        noise = rng.normal(size=len(pairs))
        residual = noise-design@np.linalg.lstsq(design, noise, rcond=None)[0]
        null_y = 20*z+residual
        perms = np.array([rng.permutation(n) for _ in range(199)])
        fit = _fit(design, null_y)
        test = _partial_residual_test(design, null_y, fit, pairs[:, 0], pairs[:, 1], n, perms, 1)
        self.assertAlmostEqual(fit["beta"][1], 0, places=10)
        self.assertEqual(test["p_sensitivity"], 1)
        # Añadir efecto de una covariable controlada no cambia el contraste X1.
        y = null_y+0.7*x1
        original = _partial_residual_test(design, y, _fit(design, y), pairs[:, 0], pairs[:, 1], n, perms, 1)
        shifted = y+7*z
        changed = _partial_residual_test(design, shifted, _fit(design, shifted), pairs[:, 0], pairs[:, 1], n, perms, 1)
        self.assertEqual(original, changed)

    def test_identity_permutations_preserve_test_statistic(self):
        rng = np.random.default_rng(13)
        n = 8
        pairs = np.array(list(combinations(range(n), 2)))
        design = np.column_stack([np.ones(len(pairs)), rng.normal(size=(len(pairs), 2))])
        y = design@np.array([1., 0.4, 2.])+rng.normal(size=len(pairs))
        perms = np.tile(np.arange(n), (11, 1))
        test = _partial_residual_test(design, y, _fit(design, y), pairs[:, 0], pairs[:, 1], n, perms, 1)
        self.assertEqual(test["permutation_exceedances"], 11)
        self.assertEqual(test["p_sensitivity"], 1.)

    def test_invalid_inputs_fail_explicitly(self):
        data, ids = sample_predictors()
        with tempfile.TemporaryDirectory() as directory:
            cases = [
                (data, ids, 0, 1), (data, ids, True, 1),
                (data, ids, 2, -1), (data, ids, 2, True),
                (data.iloc[:-1], ids, 2, 1),
                (pd.concat([data.iloc[:-1], data.iloc[[0]]]), ids, 2, 1),
                (data.assign(score=np.nan), ids, 2, 1),
                (data.assign(score=1.), ids, 2, 1),
                (data.assign(direct=2), ids, 2, 1),
                (data.assign(freight_sum=1.), ids, 2, 1),
                (data.assign(direct=0), ids, 2, 1),
                (data, ids+[ids[0]], 2, 1),
            ]
            for frame, universe, permutations, seed in cases:
                with self.subTest(permutations=permutations, seed=seed, rows=len(frame)):
                    with self.assertRaises(ValueError):
                        run_inference_extensions(frame, universe, directory, permutations, seed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
