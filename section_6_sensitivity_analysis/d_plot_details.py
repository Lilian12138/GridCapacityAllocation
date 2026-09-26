"""
Provincial sensitivity heatmap.
Rows = provinces (English names), Columns = year.
Cell value = worst-case (min) Spearman rho across all weight scenarios and both
planning modes, for that province-year. One panel per system.

Onshore wind & Solar PV: 31 provinces.
Offshore wind: single offshore unit (code 100), shown as its own one-row panel.
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

# GB 2260 province code -> English name
NAME = {
    11: 'Beijing', 12: 'Tianjin', 13: 'Hebei', 14: 'Shanxi', 15: 'Inner Mongolia',
    21: 'Liaoning', 22: 'Jilin', 23: 'Heilongjiang',
    31: 'Shanghai', 32: 'Jiangsu', 33: 'Zhejiang', 34: 'Anhui', 35: 'Fujian',
    36: 'Jiangxi', 37: 'Shandong',
    41: 'Henan', 42: 'Hubei', 43: 'Hunan', 44: 'Guangdong', 45: 'Guangxi',
    46: 'Hainan', 50: 'Chongqing', 51: 'Sichuan', 52: 'Guizhou', 53: 'Yunnan',
    54: 'Tibet', 61: 'Shaanxi', 62: 'Gansu', 63: 'Qinghai', 64: 'Ningxia',
    65: 'Xinjiang', 100: 'Offshore',
}
# geographic-ish ordering (N->S, then by region) for readability
ORDER = [15, 11, 12, 13, 14, 21, 22, 23, 37, 41, 61, 62, 63, 64, 65, 54,
         51, 50, 52, 53, 42, 43, 31, 32, 33, 34, 35, 36, 44, 45, 46]
sensitivity_csv = os.path.join(base_folder, r"processing\tables\sensitivity_detail.csv")
df = pd.read_csv(sensitivity_csv)
df.columns = [c.strip() for c in df.columns]
METRIC = 'spearman_rho'
YEARS = [2030, 2035, 2040, 2050, 2060]

SYSTEMS = [('wind_onshore', 'Onshore wind'),
           ('solar', 'Solar PV'),
           ('wind_offshore', 'Offshore wind')]

VMIN, VMAX = 0.4, 1.0
cmap = plt.get_cmap('PuBu_r')
norm = Normalize(vmin=VMIN, vmax=VMAX)

# width ratios: two full-province panels + a slim offshore panel.
# Use a gridspec with as many rows as provinces, so the single-row offshore
# panel occupies only 1/len(ORDER) of the figure height instead of being
# stretched to match the 31-row panels.
n_rows = len(ORDER)
fig = plt.figure(figsize=(13, 9))
gs = fig.add_gridspec(n_rows, 3, width_ratios=[1, 1, 0.5], wspace=0.5)

for k, (sysname, label) in enumerate(SYSTEMS):
    sub = df[df.system == sysname]
    row_order = [100] if sysname == 'wind_offshore' else ORDER
    codes = [c for c in row_order if c in sub.Shengcode.unique()]

    if sysname == 'wind_offshore':
        ax = fig.add_subplot(gs[0:len(codes), k])
    else:
        ax = fig.add_subplot(gs[:, k])

    M = np.full((len(codes), len(YEARS)), np.nan)
    for i, code in enumerate(codes):
        for j, y in enumerate(YEARS):
            cell = sub[(sub.Shengcode == code) & (sub.year == y)]
            if not cell.empty:
                M[i, j] = cell[METRIC].min()   # worst across scenarios & plans

    ax.imshow(M, cmap=cmap, norm=norm, aspect='auto')

    for i in range(len(codes)):
        for j in range(len(YEARS)):
            v = M[i, j]
            if np.isnan(v):
                continue
            tc = 'white' if v < 0.62 else 'black'
            ax.text(j, i, f'{v:.2f}', ha='center', va='center',
                    fontsize=6.5, color=tc)

    ax.set_xticks(range(len(YEARS)))
    ax.set_xticklabels(YEARS, fontsize=7.5, rotation=45, ha='right')
    ax.set_yticks(range(len(codes)))
    ax.set_yticklabels([NAME[c] for c in codes], fontsize=7.5)
    ax.set_title(label, fontsize=11, fontweight='bold')
    ax.set_xlabel('Year', fontsize=8.5)

    ax.set_xticks(np.arange(-.5, len(YEARS), 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(codes), 1), minor=True)
    ax.grid(which='minor', color='white', linewidth=0.5)
    ax.tick_params(which='minor', length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)

sm = ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])
cbar = fig.colorbar(sm, ax=fig.axes, fraction=0.018, pad=0.02)
cbar.set_label('Worst-case rank correlation across scenarios (min Spearman \u03c1)',
               fontsize=9)
cbar.ax.tick_params(labelsize=8)

fig.suptitle('Provincial robustness of resource rankings to indicator-weight scenarios',
             fontsize=12.5, fontweight='bold', x=0.45, y=0.965)
fig.text(0.45, 0.0005,
         'Each cell = minimum Spearman \u03c1 across all weight scenarios and both '
         'planning modes. Lower = more sensitive to weighting.',
         ha='center', fontsize=8, color='0.35')

fig.subplots_adjust(left=0.1, right=0.9, top=0.92, bottom=0.07)
fig.savefig(os.path.join(base_folder, 'processing\\images\\sensitivity_province_heatmap.png'), dpi=300, bbox_inches='tight')
print('saved')