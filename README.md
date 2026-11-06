# Robustez de la red de carga aérea de Estados Unidos ante fallos simultáneos de aeropuertos · 2025

Proyecto del curso **Network Science for Data Analytics** (Universidad Nacional de Colombia).
Adapta a los datos de 2025 el método de Zhou y Razavi (2026) para medir la **sinergia** de cada pareja de aeropuertos. La sinergia es el daño adicional que sufre la estructura de la red cuando dos aeropuertos fallan a la vez, por encima de la suma de sus fallos por separado. El proyecto añade un análisis de la firmeza de esa priorización.

**Equipo:** \*\*\*\*\*\*\*\* · \*\*\*\*\*\*\*\*.

## Por dónde empezar

| Archivo | Qué es |
|---|---|
| [`PIF-NS4DA-4.ipynb`](PIF-NS4DA-4.ipynb) | **Informe final** (resumen según la plantilla del curso): problema, datos, métodos, resultados y conclusiones |
| [`NS4DA_Desarrollo_carga_aerea_2025.ipynb`](NS4DA_Desarrollo_carga_aerea_2025.ipynb) | **Notebook completo**, ejecutado y reproducible ([lectura en nbviewer](https://nbviewer.org/github/dnunezq/Network_Science_air-cargo-network-robustness/blob/main/NS4DA_Desarrollo_carga_aerea_2025.ipynb)) |
| [`Atlas_Carga_Aerea_2025.html`](Atlas_Carga_Aerea_2025.html) | **App Atlas Cargo** en un solo archivo: descargar y abrir con doble clic, sin servidor ni internet |
| [`app/`](app/) | Código de la app (HTML, CSS, JavaScript y Leaflet) |

El video explicativo está pendiente; se enlazará aquí y en el informe cuando esté disponible.

## Resultados principales

- La red anual tiene 100 aeropuertos y 2.441 enlaces. Es densa (densidad 0,49), de caminos cortos (diámetro 3) y *hub-and-spoke*. Por agrupamiento, longitud de caminos y hubs, se parece al modelo preferencial de Barabási–Albert. Sus comunidades son débiles.
- La pareja con mayor sinergia es **SDF–SEA** (Louisville–Seattle), sin enlace directo. Nueve de las diez primeras parejas tampoco lo tienen, igual que en el artículo para 2022. Sinergia no es daño total: MEM–ORD es la pareja que más daño causa, pero es la tercera en sinergia.
- La conexión directa y la suma de grados explican casi toda la sinergia: el modelo M5 alcanza R² 0,87. Los pesos de las tres medidas de robustez son casi idénticos a los del artículo.
- El ranking completo cambia mucho con el trimestre y con la definición de enlace. Aun así, SDF–SEA y SDF–SFO encabezan bajo todas las variantes.

## Estructura del repositorio

```
PIF-NS4DA-4.ipynb                          informe final (resumen, plantilla del curso)
NS4DA_Desarrollo_carga_aerea_2025.ipynb    notebook completo
Atlas_Carga_Aerea_2025.html                app autónoma
app/                                       código de la app; app/dist/data/ = JSON exportados por el notebook
src/                                       módulos del análisis y pruebas
data/raw/                                  datos de entrada (BTS T-100 2025, coordenadas BTS, Natural Earth)
data/LEEME_datos_BTS_T100_2025.txt         descarga y diccionario de las 45 columnas
cache/                                     cachés de la simulación de fallos (verificadas por huella)
resultados/                                tablas exportadas: rutas, enlaces, pares, centralidades, sensibilidades
figuras/                                   figuras exportadas
requirements.txt
```

## Datos

- **Tráfico.** Bureau of Transportation Statistics, *T-100 Domestic Segment (All Carriers)*, 2025, doce meses. El archivo tiene 458.793 filas y 45 columnas; se descargó el 4 de octubre de 2026 desde [TranStats](https://transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=GEE&QO_fu146_anzr=Nv4+Pn44vr45).
- **Coordenadas.** Catálogo *Master Coordinate* de BTS.
- **Cartografía.** Natural Earth, dominio público.

Los archivos están en `data/raw/`, y el notebook comprueba su SHA-256 antes de usarlos. `src/adquirir_bts.py` documenta cómo descargar una edición nueva.

## Reproducir

Se probó con Python 3.14. Desde la raíz del repositorio:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/ejecutar_notebook.py NS4DA_Desarrollo_carga_aerea_2025.ipynb
python -m unittest discover -s src -p "test*.py"
```

Con las cachés incluidas, la ejecución completa tarda alrededor de un minuto. El notebook también puede abrirse con Jupyter y ejecutarse celda por celda.

Para la app:

```bash
python -m http.server 8765 --directory app/dist
python src/empaquetar_app.py
node app/test_coredata.cjs
```

- El primer comando sirve la versión de desarrollo; se abre en `http://localhost:8765`.
- El segundo reconstruye `Atlas_Carga_Aerea_2025.html` con los JSON exportados.
- El tercero prueba el contrato de datos y requiere Node.js.

## Referencia

Zhou, H., & Razavi, S. (2026). An explanatory composite metric for air cargo network robustness: incorporating pairwise synergistic effects. *Scientific Reports, 16*, 7071. https://doi.org/10.1038/s41598-026-38153-y

La caracterización estructural de la red, el análisis de firmeza y la app son aportes propios del equipo; el modelo M6 proviene del artículo como análisis de sensibilidad. Los resultados son descriptivos y exploratorios: describen vulnerabilidad estructural, no pérdidas de carga ni relaciones causales.
