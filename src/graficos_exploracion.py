"""Figuras de la caracterización estructural: grado frente a modelos y comunidades."""
from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np

from exploracion_red import MODELS, PROPERTIES, _generate

# Paleta categórica validada (deuteranopia, protanopia y tritanopia) para todos
# los pares: tres tonos distinguibles y un gris neutro para un cuarto grupo, que
# además se identifica por la leyenda.
COMMUNITY_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#52514e']
SERIES_COLORS = {'observed': '#2a78d6', 'erdos_renyi': '#eb6834',
                 'watts_strogatz': '#1baf7a', 'barabasi_albert': '#eda100'}
INK, MUTED, GRID = '#0b0b0b', '#52514e', '#e4e3df'


def _style(ax):
    for side in ['top', 'right']:
        ax.spines[side].set_visible(False)
    for side in ['left', 'bottom']:
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(False)
    ax.grid(axis='y', color=GRID, lw=.6)
    ax.set_axisbelow(True)


def plot_degree_and_models(result, path, replicas=10, seed=2025):
    """Distribución de grado y las tres propiedades del curso frente a los modelos."""
    path = Path(path)
    models = result['models']
    degrees = np.array(result['degree_distribution']['degrees'])
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.4), gridspec_kw={'width_ratios': [1.6, 1, 1, 1]})
    ax = axes[0]
    grid = np.arange(0, degrees.max() + 1)
    ax.plot(grid, [(degrees >= k).mean() for k in grid], color=SERIES_COLORS['observed'], lw=2.2,
            label='Red observada', zorder=3)
    rng = np.random.default_rng(seed)
    for name, model in models['models'].items():
        sample = np.concatenate([[d for _, d in _generate(name, model['parameters'], int(s)).degree()]
                                 for s in rng.integers(0, 2**31 - 1, replicas)])
        mgrid = np.arange(0, max(sample.max(), degrees.max()) + 1)
        ax.plot(mgrid, [(sample >= k).mean() for k in mgrid], color=SERIES_COLORS[name], lw=2, ls='--',
                label=model['label'])
    ax.set(xlabel='Grado k (aeropuertos conectados)', ylabel='Fracción de aeropuertos con grado ≥ k')
    ax.set_title('Distribución de grado', loc='left', fontsize=11, color=INK)
    ax.legend(frameon=False, fontsize=8.5, loc='lower left')
    _style(ax)
    names = ['observed'] + list(models['models'])
    short = {'observed': 'Observada', 'erdos_renyi': 'Aleatoria', 'watts_strogatz': 'Mundo\npequeño',
             'barabasi_albert': 'Preferencial'}
    for ax, metric in zip(axes[1:], PROPERTIES):
        values = [models['observed'][metric]] + [m['metrics'][metric]['mean'] for m in models['models'].values()]
        bars = ax.bar(range(len(names)), [v or 0 for v in values], width=.62,
                      color=[SERIES_COLORS[n] for n in names], edgecolor='white', lw=2)
        for bar, value in zip(bars, values):
            if value is not None:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{value:.2f}' if value < 10 else f'{value:.1f}',
                        ha='center', va='bottom', fontsize=8.5, color=INK)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels([short[n] for n in names], fontsize=8.5)
        ax.set_title(PROPERTIES[metric], loc='left', fontsize=11, color=INK)
        _style(ax)
    fig.text(.01, -.04, f"Modelos con los mismos 100 nodos y casi los mismos enlaces; medias de {models['replicas']} réplicas. "
             'Agrupamiento y distancia se comparan con la red aleatoria; la desviación del grado mide la presencia de hubs.',
             fontsize=8.5, color=MUTED)
    plt.tight_layout()
    fig.savefig(path, bbox_inches='tight', dpi=160)
    fig.savefig(path.with_suffix('.pdf'), bbox_inches='tight')
    plt.show()
    return path


def plot_community_map(result, airports, world_path, path, title=None):
    """Aeropuertos coloreados por comunidad Louvain (red binaria) sobre la cartografía local."""
    path = Path(path)
    block = result['communities']
    membership = {row['airport_id']: row['community'] for row in block['nodes']}
    world = json.loads(Path(world_path).read_text())
    fig = plt.figure(figsize=(13, 7))
    ax = fig.add_axes([.06, .12, .9, .8])
    ax_ak = fig.add_axes([.065, .14, .25, .25])
    ax_hi = fig.add_axes([.325, .14, .18, .19])
    label = title or 'Comunidades Louvain · red binaria anual'
    for axis, bounds, name in [(ax, (-128, -65, 23, 51), label), (ax_ak, (-180, -129, 50, 73), 'Alaska'),
                               (ax_hi, (-161, -154, 18, 23), 'Hawái')]:
        for feature in world['features']:
            geom = feature['geometry']
            polygons = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
            for polygon in polygons:
                xy = np.array(polygon[0])
                axis.fill(xy[:, 0], xy[:, 1], color='#f1f0ec', edgecolor='#c9c7c0', lw=.35, zorder=0)
        for row in airports.itertuples():
            k = membership[int(row.airport_id)]
            axis.scatter(row.lon, row.lat, s=30 + 220 * np.sqrt(row.annual_freight_lb / airports.annual_freight_lb.max()),
                         color=COMMUNITY_COLORS[k % len(COMMUNITY_COLORS)], edgecolor='white', lw=1.2, zorder=2)
        axis.set(xlim=bounds[:2], ylim=bounds[2:])
        axis.set_title(name, loc='left', fontsize=11 if axis is ax else 9, color=INK)
        axis.set_xticks([]); axis.set_yticks([])
        for spine in axis.spines.values():
            spine.set_color('#c9c7c0')
    for row in airports.head(15).itertuples():
        if -128 < row.lon < -65 and 23 < row.lat < 51:
            ax.annotate(row.code, (row.lon, row.lat), xytext=(5, 4), textcoords='offset points', fontsize=8, color=INK)
    handles = [plt.Line2D([], [], marker='o', ls='', markersize=9, markeredgecolor='white',
                          color=COMMUNITY_COLORS[c['id'] % len(COMMUNITY_COLORS)],
                          label=f"Comunidad {c['id'] + 1} · {c['size']} aeropuertos · {', '.join(c['members'][:4])}")
               for c in block['communities']]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.51, .045), ncol=len(handles), fontsize=9, frameon=False)
    fig.text(.06, .015, f"Modularidad {block['modularity']:.3f} y NMI media {block['nmi_mean']:.2f} entre {block['runs']} ejecuciones: "
             'comunidades débiles. Tamaño del punto: carga anual. Los grupos describen estructura; no acuerdos operativos.',
             fontsize=8.5, color=MUTED)
    fig.savefig(path, bbox_inches='tight', dpi=160)
    fig.savefig(path.with_suffix('.pdf'), bbox_inches='tight')
    plt.show()
    return path
