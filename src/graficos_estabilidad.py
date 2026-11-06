"""Figuras de estabilidad entre reglas de enlace; frecuencia no probabilística."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

STABILITY_VARIANTS = ['base','half_months','all_months','min_monthly_freight']
STABILITY_LABELS = ['Base','Mitad de meses','Todos los meses','Volumen mínimo']


def plot_stability_ranges(stability, output_path, top_n=10):
    """Presenta rangos y frecuencia top20 con el mismo período/calibración."""
    required = {'a','b','a_id','b_id','top_count','rank_mean','rank_min','rank_max',
                *[v+'_rank' for v in STABILITY_VARIANTS]}
    if not required.issubset(stability.columns):
        raise ValueError('La tabla no contiene las columnas de estabilidad esperadas.')
    if len(stability)==0 or top_n<1:
        raise ValueError('Se necesitan parejas y un top_n positivo.')
    if not stability.top_count.between(0,len(STABILITY_VARIANTS)).all():
        raise ValueError('Frecuencia fuera del número de reglas.')
    selected = stability.sort_values(
        ['top_count','rank_mean','a_id','b_id'],
        ascending=[False,True,True,True]).head(top_n).reset_index(drop=True)
    rank_values = selected[[v+'_rank' for v in STABILITY_VARIANTS]].to_numpy()
    if not np.isfinite(rank_values).all() or (rank_values<1).any():
        raise ValueError('Los puestos deben ser finitos y positivos.')
    fig,(ax,counts_ax)=plt.subplots(
        1,2,figsize=(13,5.6),gridspec_kw={'width_ratios':[2.25,1]})
    y = np.arange(len(selected))
    ax.hlines(y,selected.rank_min,selected.rank_max,color='#b7c9ce',lw=3,zorder=1)
    colors=['#087f8c','#c38d31','#4a658b','#a75865']
    markers=['o','s','^','D']
    for variant,label,color,marker in zip(STABILITY_VARIANTS,STABILITY_LABELS,colors,markers):
        ax.scatter(selected[variant+'_rank'],y,s=48,color=color,marker=marker,
                   label=label,zorder=3,edgecolor='white',linewidth=.45)
    ax.set_yticks(y,[f"{r.a}–{r.b} · {int(r.top_count)}/4" for r in selected.itertuples()])
    ax.invert_yaxis()
    ax.set_xscale('log')
    ax.set_xlabel('Puesto en el ranking comparable · escala logarítmica')
    ax.set_title('Parejas con mayor presencia en el top 20')
    ax.grid(axis='x',alpha=.22)
    ax.grid(axis='y',visible=False)
    ax.legend(fontsize=9,loc='lower right')
    counts=stability.top_count.astype(int).value_counts().reindex(range(5),fill_value=0)
    bars=counts_ax.barh(range(5),counts.values,color=['#b5c5cd','#8aaeb9','#4f94a4','#087f8c','#c38d31'])
    counts_ax.set_yticks(range(5),[f'{k}/4 reglas' for k in range(5)])
    counts_ax.set_xlabel('Número de parejas')
    counts_ax.set_title('Distribución de la frecuencia')
    counts_ax.grid(axis='y',visible=False)
    counts_ax.grid(axis='x',alpha=.2)
    for bar,count in zip(bars,counts.values):
        counts_ax.text(count+max(counts.max()*.02,1),bar.get_y()+bar.get_height()/2,
                       str(int(count)),va='center',fontsize=9)
    counts_ax.set_xlim(0,max(1,counts.max())*1.18)
    fig.text(.02,.025,
        'Frecuencia entre cuatro definiciones de enlace del mismo período. No es probabilidad de fallo ni intervalo de confianza.\n'
        'El top 20 usa desempate por IDs; los puestos conservan rango medio en empates. Los índices usan calibración común de sensibilidad.',
        fontsize=8,color='#526c78')
    fig.tight_layout(rect=(0,.10,1,1))
    target=Path(output_path)
    target.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(target,dpi=160,bbox_inches='tight')
    if target.suffix.lower()=='.png':
        fig.savefig(target.with_suffix('.pdf'),bbox_inches='tight')
    plt.show()
    return selected
