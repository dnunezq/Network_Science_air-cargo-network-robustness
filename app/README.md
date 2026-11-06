# Atlas Cargo · Explorador 2025

Aplicación estática en español. No requiere un servicio de datos: lee los resultados reales del notebook desde los JSON locales de `dist/data/`.

## Uso local

La alternativa más sencilla es abrir `../Atlas_Carga_Aerea_2025.html`, que incorpora datos, librerías y estilos en un único archivo. Se regenera desde la raíz del repositorio con `python src/empaquetar_app.py`.

Desde esta carpeta:

```sh
python3 -m http.server 8765 --directory dist
```

Abrir `http://localhost:8765`. Es necesario usar un servidor HTTP para que el navegador pueda leer JSON; abrir `index.html` mediante `file://` no es suficiente.

## Funciones

- Mapa de aeropuertos y conexiones con base Natural Earth local y atribución.
- Red anual y cuatro trimestres, manteniendo el universo de aeropuertos.
- Selección de un aeropuerto o de una pareja desde mapa, listas o ranking.
- Visualización de retirada de nodos y conexiones, acompañada de impactos precomputados.
- Ranking y exportación CSV; búsqueda por código y ciudad.
- Coincidencia de top 20, correlación Spearman con rangos promedio en empates, evolución trimestral de una pareja.
- Pestaña Estructura: medidas globales y locales, cuatro centralidades, comunidades binarias y comparación con los tres modelos del curso.
- Pestaña Laboratorio (`lab.js`): redes de juguete en las que se retiran uno o dos nodos para ver las tres medidas, los impactos y la sinergia; calcula en el navegador con las definiciones del notebook.
- AirportID de BTS junto al código IATA en selector, mapa, ficha y ranking.
- Diseño adaptable a móviles, controles accesibles y respaldo SVG de coordenadas si no carga Leaflet.

Leaflet y la cartografía Natural Earth están incluidos localmente; no requieren internet. Si Leaflet no está disponible, el explorador usa una vista SVG local con la geografía incluida. Los datos del análisis se conservan en el archivo local.

## Contrato de datos

```json
{
  "metadata": {"year": 2025},
  "airports": [{"id": "SDF", "name": "...", "city": "...", "lat": 38.0, "lon": -85.0, "annual_freight_lb": 0}],
  "periods": {
    "annual": {
      "label": "Año 2025", "n_nodes": 100, "n_edges": 0,
      "metrics": {"global_efficiency": 0, "local_efficiency": 0, "natural_connectivity": 0},
      "nodes": [{"id": "SDF", "degree": 0, "degree_centrality": 0, "betweenness": 0, "freight_lb": 0}],
      "edges": [{"source": "SDF", "target": "SEA", "freight_lb": 0}],
      "pairs": [{"a": "SDF", "b": "SEA", "score": 0, "rank": 1, "direct": false, "score_comparable": 0, "rank_comparable": 1, "synergy_global": 0, "synergy_local": 0, "synergy_natural": 0, "impact_global": 0, "impact_local": 0, "impact_natural": 0}]
    }
  }
}
```

El bloque anterior describe campos, no datos para análisis. `T1`, `T2`, `T3`, `T4` usan la misma estructura que `annual`. La app no incluye datos de muestra. Las comparaciones requieren `score_comparable` y `rank_comparable`, obtenidos con una escala y pesos comunes. Si faltan, muestra ausencia de resultados en lugar de sustituirlos por índices con escalas diferentes.

`freight_lb` por nodo es entrada + salida. No sumar todos los nodos para reportar carga total sin corregir el doble conteo. Las métricas e impactos se calculan en el notebook; la app solo visualiza resultados.

## Archivos de datos

Todos los JSON de `dist/data/` los exporta el notebook completo; la app no calcula métricas de red.

| Archivo | Contenido | Pestañas |
|---|---|---|
| `network.json` | Aeropuertos, enlaces y las 4.950 parejas de cada período con impactos y sinergias | Explorador, ranking, ficha, trimestres |
| `interactive.json` | Las cuatro reglas de enlace, calibraciones comunes y estabilidad entre reglas | Selectores de regla y escala, Estabilidad |
| `extensions.json` | Sensibilidad de enlaces, perfiles, capas por operador, caminos entre supervivientes y modelos M5/M6 | Sensibilidad, Operadores, Modelos |
| `exploration.json` | Caracterización estructural de las 20 redes (5 períodos × 4 reglas) | Estructura y coloreado del mapa |
| `world.geojson` | Cartografía Natural Earth | Mapa |

Las tres calibraciones del índice (propia de cada red, común entre trimestres y común de sensibilidad) están identificadas en la interfaz y no deben mezclarse. Las capas por operador muestran sus propias conexiones; no ofrecen índices de fallos calculados en otras redes. La ficha de una pareja incluye la simulación paso a paso: retira A, luego B, y compara con la suma de los fallos individuales usando valores precalculados.

## Pruebas

`node test_coredata.cjs` comprueba el contrato de datos de las 40 combinaciones de período, regla y escala, los 20 bloques de estructura y los cálculos del Laboratorio frente a valores de NetworkX.
