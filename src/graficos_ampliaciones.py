"""Figuras científicas de la versión ampliada, con datos exportados reales."""
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_extensions(extensions, base_pairs, out_dir, residuals_path):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    structural = extensions['structural']
    figures = {}
    def save(name):
        plt.tight_layout()
        plt.savefig(out/name,dpi=160,bbox_inches='tight')
        figures[name] = str(out/name)
        plt.show()

    period_names = ['annual','T1','T2','T3','T4']
    variant_names = ['half_months','all_months','min_monthly_freight']
    labels = ['Mitad de meses','Todos los meses','≥ 1.000 lb / mes']
    periods = structural['sensitivity']['periods']
    overlap = np.array([[periods[p][v]['comparison']['overlap'] for p in period_names] for v in variant_names])
    rho = np.array([[periods[p][v]['comparison']['spearman'] for p in period_names] for v in variant_names],dtype=float)
    fig, axes = plt.subplots(1,2,figsize=(12,4))
    for ax, values, title, percent in [(axes[0],overlap,'Coincidencia del top 20 con la base',True),
                                      (axes[1],rho,'Spearman con la base',False)]:
        im = ax.imshow(values,vmin=0,vmax=1,cmap='YlGnBu',aspect='auto')
        ax.set_xticks(range(5),['Año','T1','T2','T3','T4'])
        ax.set_yticks(range(3),labels)
        ax.set_title(title)
        for i in range(3):
            for j in range(5):
                text = f'{values[i,j]:.0%}' if percent else f'{values[i,j]:.3f}'
                ax.text(j,i,text,ha='center',va='center',color='white' if values[i,j]>.65 else '#162b38')
        fig.colorbar(im,ax=ax,shrink=.8)
    save('08_sensibilidad_rankings.png')

    annual = periods['annual']
    variants = list(annual)
    fig, axes = plt.subplots(1,2,figsize=(12,4))
    short = ['Base','Mitad meses','Todos meses','Volumen mínimo']
    axes[0].bar(short,[annual[v]['stats']['n_edges'] for v in variants],color='#087f8c')
    axes[0].set(title='Enlaces retenidos · red anual',ylabel='Conexiones binarias')
    axes[1].bar(short,[100*annual[v]['freight_coverage'] for v in variants],color='#c18b32')
    axes[1].set(title='Cobertura de carga respecto a la base',ylabel='Porcentaje de la carga interna',ylim=(0,105))
    for ax in axes: ax.tick_params(axis='x',labelrotation=15)
    save('09_sensibilidad_cobertura.png')

    profiles = pd.DataFrame(structural['profiles']).set_index('id')
    fig, ax = plt.subplots(figsize=(8,5))
    ax.scatter(profiles.freight_lb/1e9,profiles.betweenness,s=30,alpha=.55,color='#6e9aa7')
    for code,offset in {'ANC':(5,5),'SDF':(-30,-17),'MEM':(-27,10),'ORD':(5,5),'SEA':(5,5),'RFD':(5,5)}.items():
        row = profiles.loc[code]
        ax.annotate(code,(row.freight_lb/1e9,row.betweenness),xytext=offset,textcoords='offset points',fontweight='bold')
    ax.set(title='Volumen e intermediación: papeles distintos',xlabel='Carga incidente (miles de millones de lb)',ylabel='Intermediación no normalizada')
    save('10_perfiles_importancia.png')

    cases = extensions['interpretation']['cases'][:2]
    fig, axes = plt.subplots(1,2,figsize=(12,4.7))
    axes[0].scatter(base_pairs.impact_global,base_pairs.score,s=7,alpha=.25,color='#769fa9')
    for c in cases:
        axes[0].scatter(c['metrics'][0]['joint_impact'],c['score'],s=65)
        axes[0].annotate(c['a']+'–'+c['b'],(c['metrics'][0]['joint_impact'],c['score']),xytext=(-75,10),textcoords='offset points')
    axes[0].axvline(0,color='#647d89',lw=.7)
    axes[0].set(title='Sinergia e impacto total no son equivalentes',xlabel='Impacto global conjunto',ylabel='Índice compuesto')
    for k,c in enumerate(cases):
        axes[1].bar(np.arange(3)+k*.35,[m['contribution'] for m in c['metrics']],width=.35,label=c['a']+'–'+c['b'])
    axes[1].set_xticks(np.arange(3)+.175,['Global','Local','Natural'])
    axes[1].set(title='Aportes al índice anual',ylabel='Contribución normalizada y ponderada')
    axes[1].legend()
    save('11_sinergia_dano_componentes.png')

    operators = structural['operators']['items']
    fig, axes = plt.subplots(1,2,figsize=(12,5))
    names = [o['name'][:25] for o in operators]
    axes[0].barh(names,[100*o['share'] for o in operators],color='#087f8c')
    axes[0].invert_yaxis()
    axes[0].set(title='Carga atribuida por operador',xlabel='% de carga interna anual')
    axes[1].barh(names,[o['removal']['edges_lost'] for o in operators],color='#c18b32')
    axes[1].invert_yaxis()
    axes[1].set(title='Enlaces que desaparecen sin ese operador',xlabel='Aristas sin otro operador con carga')
    save('12_capas_operadores.png')

    residuals = pd.read_csv(residuals_path)
    fig, axes = plt.subplots(1,2,figsize=(12,4))
    for ax, model in zip(axes,['M5','M6']):
        ax.scatter(residuals.degree_sum_z,residuals['residual_'+model],s=5,alpha=.2,color='#087f8c')
        ax.axhline(0,color='#c18b32')
        ax.set(title=model+' · residuos y suma de grado',xlabel='Suma de grado estandarizada',ylabel='Residuo del índice')
    save('13_regresion_residuos.png')
    return figures
