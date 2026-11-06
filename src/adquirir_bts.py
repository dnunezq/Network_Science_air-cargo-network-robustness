"""Descarga reproducible desde los formularios públicos de BTS TranStats.

Obtiene los tokens ASP.NET de una sesión nueva; no fija VIEWSTATE ni enlaces
temporales. Requiere requests. No sustituye datos guardados sin solicitud.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import io
import json
import zipfile
from urllib.parse import urljoin

import requests

URL_COORDENADAS = "https://transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FLL&QO_fu146_anzr=Nv42146"
URL_T100 = "https://transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=GEE&QO_fu146_anzr=Nv4+Pn44vr45"


class _Formulario(HTMLParser):
    """Lee exclusivamente el formulario de descarga y sus controles."""
    def __init__(self):
        super().__init__()
        self.active = False
        self.form_depth = 0
        self.action = ""
        self.fields = {}
        self.select = None
        self.options = {}
        self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "form":
            if self.active:
                # TranStats contiene un formulario de búsqueda anidado.
                self.form_depth += 1
            elif a.get("id") == "form1":
                self.active = True
                self.form_depth = 1
                self.action = a.get("action", "")
        if not self.active:
            return
        if tag == "input" and a.get("name"):
            name, kind = a["name"], a.get("type", "text")
            if kind == "hidden":
                self.fields[name] = a.get("value", "")
            elif kind == "checkbox" and name.isupper():
                # Las variables de las tablas usan nombres SQL en mayúsculas.
                self.fields[name] = a.get("value", "on")
            elif kind == "submit" and name == "btnDownload":
                self.fields[name] = a.get("value", "Download")
        elif tag == "select":
            self.select = a.get("name")
            self.options[self.select] = []
        elif tag == "option" and self.select:
            value = a.get("value", "")
            self.options[self.select].append(value)
            if "selected" in a or self.select not in self.fields:
                self.fields[self.select] = value

    def handle_endtag(self, tag):
        if tag == "form" and self.active:
            self.form_depth -= 1
            self.active = self.form_depth > 0
        elif tag == "select":
            self.select = None


def descargar_tabla(url, destino, year=None, timeout=240):
    """Descarga ZIP oficial con todas las variables y todos los meses.

    ``year=2025`` filtra T-100; para Master Coordinate se deja ``None`` porque
    su catálogo contiene versiones históricas por AIRPORT_SEQ_ID. Valida ZIP
    antes de escribir y devuelve procedencia/hash. Falla explícitamente si
    cambia el formulario, el año no está disponible o BTS devuelve un error.
    """
    destino = Path(destino)
    with requests.Session() as session:
        session.headers["User-Agent"] = "Mozilla/5.0 (academic reproducibility; BTS public data)"
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        form = _Formulario()
        form.feed(response.text)
        if not form.fields.get("__VIEWSTATE") or "btnDownload" not in form.fields:
            raise RuntimeError("No se encontró el formulario ASP.NET esperado de BTS.")
        payload = dict(form.fields)
        for name in ("cboGeography", "cboPeriod"):
            if "All" in form.options.get(name, []):
                payload[name] = "All"
        if year is not None:
            if str(year) not in form.options.get("cboYear", []):
                raise ValueError(f"El año {year} no está disponible en el formulario BTS.")
            payload["cboYear"] = str(year)
        payload["chkAllVars"] = "on"
        target = urljoin(response.url, form.action)
        downloaded = session.post(target, data=payload, timeout=timeout)
        downloaded.raise_for_status()
        content = downloaded.content
        if not zipfile.is_zipfile(io.BytesIO(content)):
            links = _Formulario()
            links.feed(downloaded.text)
            candidates = [urljoin(downloaded.url, x) for x in links.links if ".zip" in x.lower()]
            if len(candidates) == 1:
                downloaded = session.get(candidates[0], timeout=timeout)
                downloaded.raise_for_status()
                content = downloaded.content
        if not zipfile.is_zipfile(io.BytesIO(content)):
            raise RuntimeError("BTS no devolvió un ZIP válido; puede requerir descarga manual desde el formulario oficial.")
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            bad = z.testzip()
            if bad:
                raise RuntimeError(f"ZIP BTS dañado: {bad}")
            members = z.namelist()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(content)
        return {
            "source_url": url,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
            "year_filter": year,
            "period_filter": payload.get("cboPeriod"),
            "sha256": sha256(content).hexdigest(),
            "bytes": len(content),
            "members": members,
        }


def extraer_csv(zip_path, csv_path):
    """Extrae el único CSV del ZIP, sin confiar en rutas internas del archivo."""
    csv_path = Path(csv_path)
    with zipfile.ZipFile(zip_path) as z:
        members = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"Se esperaba un CSV; se encontraron {members}")
        data = z.read(members[0])
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_bytes(data)
    return {"sha256": sha256(data).hexdigest(), "bytes": len(data)}


from coordenadas import merge_coordinates  # noqa: E402,F401  (se conserva el nombre público)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", choices=("coordenadas", "t100"), default="coordenadas")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "data" / "raw")
    args = parser.parse_args()
    stem = "coordenadas_bts" if args.table == "coordenadas" else f"t100_bts_{args.year}"
    url = URL_COORDENADAS if args.table == "coordenadas" else URL_T100
    meta = descargar_tabla(url, args.output_dir / f"{stem}.zip", None if args.table == "coordenadas" else args.year)
    meta["csv"] = extraer_csv(args.output_dir / f"{stem}.zip", args.output_dir / f"{stem}.csv")
    name = "metadata_coordenadas.json" if args.table == "coordenadas" else f"metadata_t100_{args.year}.json"
    (args.output_dir / name).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(meta, indent=2, ensure_ascii=False))
