#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Figure 2 - Provincial installed capacity by terrain type, stacked bars.
Two energies (wind, solar), each a separate figure with two scenarios
(policy, low-carbon) x 4 years (2025, 2030, 2035, 2060) = 8 stacked subplots.
Y axis in GW; provinces ordered by descending total (base year 2025, policy).
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from pathlib import Path
import os
# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
base_folder = Path(__file__).resolve().parents[3]
XLSX = os.path.join(base_folder, r"processing\tables\statistic_by_province_terrain.xlsx")
YEARS = ["2025", "2030", "2035", "2060"]
TERRAINS = ["Plain", "Hills", "Mountainous", "Complex terrain"]
SCENARIOS = [("province", "Policy scenario"),
             ("low_carbon", "Low-carbon scenario")]

# Colours: 4 terrains + offshore
TERRAIN_COLORS = {
    "Plain":           "#2f6db0",   # blue
    "Hills":           "#e07b39",   # orange
    "Mountainous":     "#c0392b",   # red
    "Complex terrain": "#3aa0a0",   # teal
}
OFFSHORE_COLOR = "#9b6fb0"          # purple

# Global font sizes (enlarged for readability per reviewer request)
plt.rcParams.update({
    "font.size": 11,
    "axes.labelsize": 13,
    "xtick.labelsize": 10.5,
    "ytick.labelsize": 11,
    "legend.fontsize": 11,
    "font.family": "DejaVu Sans",
})


def load_energy(sheet):
    df = pd.read_excel(XLSX, sheet_name=sheet)
    # drop fully-empty terrain rows that are NOT offshore
    df = df[~((df["terrain_type"].isna()) & (df["Province"] != "Offshore"))]
    # convert kW -> GW for all year/scenario columns
    for y in YEARS:
        for scen, _ in SCENARIOS:
            col = f"{y}_{scen}(kW)"
            df[col] = df[col] / 1e6
    return df


def build_matrix(df, scen, year, provinces):
    """Return dict terrain-> array over provinces, plus offshore array."""
    col = f"{year}_{scen}(kW)"
    land = df[df["Province"] != "Offshore"]
    mat = {}
    for t in TERRAINS:
        sub = land[land["terrain_type"] == t].set_index("Province")[col]
        mat[t] = np.array([sub.get(p, 0.0) for p in provinces])
    # offshore: single value placed as its own bar
    off_val = df[df["Province"] == "Offshore"][col].sum()
    return mat, off_val


def province_order(df):
    """Order land provinces by descending total capacity in base year 2025 policy."""
    col = "2025_province(kW)"
    land = df[df["Province"] != "Offshore"]
    tot = land.groupby("Province")[col].sum().sort_values(ascending=False)
    return list(tot.index)


def plot_energy(sheet, out_png):
    df = load_energy(sheet)
    provinces = province_order(df)
    # x layout: offshore bar first (like original), then provinces
    labels = ["Offshore"] + provinces
    x = np.arange(len(labels))

    nrow = len(SCENARIOS) * len(YEARS)   # 8 rows
    fig, axes = plt.subplots(nrow, 1, figsize=(13, 16), sharex=True)

    row = 0
    for scen, scen_label in SCENARIOS:
        for year in YEARS:
            ax = axes[row]
            mat, off_val = build_matrix(df, scen, year, provinces)

            # offshore bar (single colour) at x=0
            ax.bar(0, off_val, color=OFFSHORE_COLOR, width=0.8,
                   edgecolor="none")

            # stacked land bars starting at x=1
            xl = x[1:]
            bottom = np.zeros(len(provinces))
            for t in TERRAINS:
                ax.bar(xl, mat[t], bottom=bottom,
                       color=TERRAIN_COLORS[t], width=0.8, edgecolor="none")
                bottom += mat[t]

            # year label on the RIGHT side of each subplot
            ax.text(1.008, 0.5, year, transform=ax.transAxes,
                    rotation=0, ha="left", va="center",
                    fontsize=11, fontweight="bold")
            ax.margins(x=0.005)
            ax.tick_params(axis="y", labelsize=10)
            # keep only a few y ticks, integer-ish
            ymax = bottom.max() if len(bottom) else 0
            ymax = max(ymax, off_val)
            if ymax > 0:
                # 3 ticks: 0, mid, top (rounded)
                import math
                step = ymax / 2
                mag = 10 ** math.floor(math.log10(step)) if step > 0 else 1
                nice = math.ceil(step / mag) * mag
                ticks = [0, nice, 2 * nice]
                ax.set_yticks(ticks)
                ax.set_ylim(0, 2 * nice * 1.02)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            row += 1

    # scenario group labels on the far left of the figure
    fig.text(0.02, 0.72, "Policy scenario (GW)", rotation=90,
             va="center", ha="center", fontsize=14, fontweight="bold")
    fig.text(0.02, 0.30, "Low-carbon scenario (GW)", rotation=90,
             va="center", ha="center", fontsize=14, fontweight="bold")

    # x tick labels (province names) only on bottom axis
    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(labels, rotation=90, fontsize=10)

    # legend
    handles = [Patch(facecolor=TERRAIN_COLORS[t], label=t) for t in TERRAINS]
    handles.append(Patch(facecolor=OFFSHORE_COLOR, label="Offshore"))
    axes[0].legend(handles=handles, title="Terrain classification",
                   ncol=5, loc="lower center", frameon=False,
                   bbox_to_anchor=(0.5, 1.25), fontsize=10.5,
                   title_fontsize=11)

    fig.subplots_adjust(left=0.10, right=0.955, top=0.94, bottom=0.11,
                        hspace=0.28)
    fig.savefig(out_png, dpi=400, bbox_inches="tight")
    print(f"saved {out_png}")
    plt.close(fig)


if __name__ == "__main__":
    plot_energy("wind", os.path.join(base_folder, r"processing\images\figure2_wind.png"))
    plot_energy("solar", os.path.join(base_folder, r"processing\images\figure2_solar.png"))
