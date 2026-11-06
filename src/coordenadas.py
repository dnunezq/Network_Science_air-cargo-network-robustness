"""Unión de coordenadas oficiales BTS (Master Coordinate) a los aeropuertos seleccionados.

Se separa del descargador para que el análisis parta de los archivos locales
sin depender de las bibliotecas de descarga.
"""
from pathlib import Path

import pandas as pd


def merge_coordinates(airports, clean, coords):
    """Une coordenadas oficiales por la versión observada en T-100 de 2025.

    Devuelve ``(airports_enriquecidos, validacion)``. Conserva los 100 nodos y
    su orden. Cuando hubo varias versiones en el año, toma la observada en el
    último mes; en empate, la de inicio de vigencia más reciente y finalmente
    AIRPORT_SEQ_ID. No usa automáticamente la versión vigente hoy.
    """
    import pandas as pd

    if isinstance(coords, (str, Path)):
        coords = pd.read_csv(coords, low_memory=False)
    coords = coords.copy()
    coords.columns = coords.columns.str.strip().str.upper()
    required = ["AIRPORT_SEQ_ID", "AIRPORT_ID", "LATITUDE", "LONGITUDE",
                "DISPLAY_AIRPORT_NAME", "AIRPORT_START_DATE"]
    missing_cols = sorted(set(required) - set(coords.columns))
    if missing_cols:
        raise ValueError(f"Faltan columnas de Master Coordinate: {missing_cols}")
    if coords.AIRPORT_SEQ_ID.duplicated().any():
        raise ValueError("Master Coordinate contiene AIRPORT_SEQ_ID duplicados.")
    selected = set(airports.airport_id.astype(int))
    pieces = []
    for endpoint in ("ORIGIN", "DEST"):
        part = clean.loc[clean[f"{endpoint}_AIRPORT_ID"].isin(selected),
                         [f"{endpoint}_AIRPORT_ID", f"{endpoint}_AIRPORT_SEQ_ID", "MONTH"]].copy()
        part.columns = ["airport_id", "coords_seq", "last_observed_month"]
        pieces.append(part)
    observed = pd.concat(pieces, ignore_index=True).groupby(
        ["airport_id", "coords_seq"], as_index=False).last_observed_month.max()
    joined = observed.merge(coords, left_on="coords_seq", right_on="AIRPORT_SEQ_ID",
                            how="left", validate="many_to_one", indicator=True)
    unmatched = joined.loc[joined._merge.ne("both"), "coords_seq"].astype(int).tolist()
    if unmatched:
        raise ValueError(f"Versiones de 2025 sin coordenadas BTS: {unmatched}")
    if not joined.airport_id.eq(joined.AIRPORT_ID).all():
        raise ValueError("AirportSeqID se unió a un AirportID diferente.")
    joined["_start"] = pd.to_datetime(joined.AIRPORT_START_DATE, errors="raise", format="mixed")
    chosen = joined.sort_values(["airport_id", "last_observed_month", "_start", "coords_seq"]).drop_duplicates("airport_id", keep="last")
    chosen = chosen.rename(columns={"DISPLAY_AIRPORT_NAME": "name", "LATITUDE": "lat", "LONGITUDE": "lon"})
    out = airports.merge(chosen[["airport_id", "name", "lat", "lon", "coords_seq", "last_observed_month", "AIRPORT_START_DATE"]],
                         on="airport_id", how="left", validate="one_to_one", sort=False)
    if len(out) != len(airports) or out[["lat", "lon", "name", "coords_seq"]].isna().any().any():
        raise ValueError("No fue posible ubicar todos los aeropuertos seleccionados.")
    if not (out.lat.between(-90, 90).all() and out.lon.between(-180, 180).all()):
        raise ValueError("Coordenadas fuera de rango geográfico.")
    counts = observed.groupby("airport_id").size()
    changes = joined.groupby("airport_id")[["LATITUDE", "LONGITUDE"]].nunique().max(axis=1)
    validation = {
        "selected_airports": len(airports),
        "matched_airports": len(out),
        "observed_airport_seq_ids": len(observed),
        "matched_airport_seq_ids": int(joined._merge.eq("both").sum()),
        "airports_with_multiple_versions": int(counts.gt(1).sum()),
        "airports_with_coordinate_changes": int(changes.gt(1).sum()),
        "unmatched_sequences": unmatched,
        "selection_rule": "AirportSeqID observado en el último mes de T-100 2025; empates por AirportStartDate y AirportSeqID crecientes.",
        "temporal_scope": "Catálogo histórico BTS descargado actualmente; coordenadas enlazadas a versiones usadas en los registros de 2025, no a la versión vigente actual.",
        "dictionary_url": "https://transtats.bts.gov/Fields.asp?gnoyr_VQ=FLL",
    }
    return out, validation
