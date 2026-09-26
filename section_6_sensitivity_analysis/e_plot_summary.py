"""
Three-metric sensitivity heatmap (Supplementary).
Panels: Spearman rho | Top-k overlap | Jaccard, sharing one colour scale.
Rows = system -> scenario; Columns = year.
Each cell = mean of the metric across the two planning modes (low_carbon, province).
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from pathlib import Path
import os
base_folder = Path(__file__).resolve().parents[3]
rcParams['font.family'] = 'DejaVu Sans'
rcParams['pdf.fonttype'] = 42
rcParams['ps.fonttype'] = 42

df = pd.read_csv(os.path.join(base_folder, 'processing', 'tables', 'sensitivity_summary.csv'))
df.columns = [c.strip() for c in df.columns]

YEARS = [2030, 2035, 2040, 2050, 2060]
SYS_ORDER = ['solar', 'wind_onshore', 'wind_offshore']
SYS_LABEL = {'solar': 'Solar PV', 'wind_onshore': 'Onshore wind',
             'wind_offshore': 'Offshore wind'}
SCEN_ORDER = ['equal', 'infra', 'resource', 'terrain']
SCEN_LABEL = {'equal': 'Equal', 'infra': 'Infra',
              'resource': 'Resource', 'terrain': 'Terrain'}

METRICS = [('rho_mean', 'Spearman \u03c1'),
           ('overlap_mean', 'Top-k overlap'),
           ('jaccard_mean', 'Jaccard')]

# average across the two planning modes
agg = df.groupby(['system', 'scenario', 'year'])[
    ['rho_mean', 'overlap_mean', 'jaccard_mean']].mean().reset_index()

rows = [(s, sc) for s in SYS_ORDER for sc in SCEN_ORDER
        if not agg[(agg.system == s) & (agg.scenario == sc)].empty]

VMIN, VMAX = 0.6, 1.0
cmap = plt.get_cmap("PuBu_r")
norm = Normalize(vmin=VMIN, vmax=VMAX)

fig, axes = plt.subplots(1, 3, figsize=(14, 6.4), sharey=True)

for ax, (col, mlabel) in zip(axes, METRICS):
    M = np.full((len(rows), len(YEARS)), np.nan)
    for i, (s, sc) in enumerate(rows):
        for j, y in enumerate(YEARS):
            cell = agg[(agg.system == s) & (agg.scenario == sc) & (agg.year == y)]
            if not cell.empty:
                M[i, j] = cell[col].values[0]

    ax.imshow(M, cmap=cmap, norm=norm, aspect='auto')
    for i in range(len(rows)):
        for j in range(len(YEARS)):
            v = M[i, j]
            if np.isnan(v):
                continue
            tc = 'white' if v < 0.7 else 'black'
            ax.text(j, i, f'{v:.2f}', ha='center', va='center',
                    fontsize=7, color=tc)

    ax.set_xticks(range(len(YEARS)))
    ax.set_xticklabels(YEARS, fontsize=8, rotation=45, ha='right')
    ax.set_xlabel('Year', fontsize=9)
    ax.set_title(mlabel, fontsize=11, fontweight='bold')
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([SCEN_LABEL[sc] for (_, sc) in rows], fontsize=8)
    ax.set_xticks(np.arange(-.5, len(YEARS), 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(rows), 1), minor=True)
    ax.grid(which='minor', color='white', linewidth=0.5)
    ax.tick_params(which='minor', length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)

# system group labels + separators on the leftmost panel
blocks, start = [], 0
for i in range(1, len(rows) + 1):
    if i == len(rows) or rows[i][0] != rows[start][0]:
        blocks.append((rows[start][0], start, i - 1))
        start = i
for s, a, b in blocks:
    axes[0].text(-1.5, (a + b) / 2, SYS_LABEL[s], fontsize=9, fontweight='bold',
                 rotation=90, ha='center', va='center')
    if b + 1 < len(rows):
        for ax in axes:
            ax.axhline(b + 0.5, color='black', linewidth=1.1)

sm = ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])
cbar = fig.colorbar(sm, ax=axes, fraction=0.02, pad=0.06)
cbar.set_label('Ranking similarity to baseline', fontsize=9)
cbar.ax.tick_params(labelsize=8)

fig.suptitle('Sensitivity of provincial rankings across three consistency metrics',
             fontsize=12.5, fontweight='bold', x=0.44, y=0.98)
fig.text(0.44, 0.02,
         'Each cell = mean across the two planning modes. '
         'The three metrics yield a consistent pattern; Jaccard is the strictest.',
         ha='center', fontsize=8, color='0.35')

fig.subplots_adjust(left=0.11, right=0.88, top=0.9, bottom=0.13, wspace=0.08)
fig.savefig(os.path.join(base_folder,  'processing\images\sensitivity_three_metrics.png'), dpi=300, bbox_inches='tight')
print('saved')