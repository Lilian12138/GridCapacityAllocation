# Wind & Solar Development Potential Assessment — Code Framework

## Overview

This codebase uses a national **10km × 10km grid** (feature class `CL_WGS84`, key field `NID10`) as the basic analysis unit to sequentially complete the following sections:

1. Developable area calculation and installed capacity potential estimation
2. Multi-dimensional index system construction and scoring
3. Current installation statistics and provincial allocation
4. Multi-year planned installation allocation by province
5. Provincial / terrain statistics on planned allocation
6. Sensitivity analysis of provincial rankings to index-weight choices

---

## Directory Structure

```
code/
├── section_1_1_wind_valid_area/        # Wind power developable area
├── section_1_2_solar_valid_area/       # Solar PV developable area
├── section_1_3_installation/           # Installed capacity potential
├── section_2_1_index/                  # Onshore wind indices
├── section_2_2_offshore_index/         # Offshore wind indices
├── section_2_3_onshore_pv_index/       # Onshore PV indices
├── section_2_4_weight_cal/             # Composite score weight calculation
├── section_3_current_installation/     # Current installation statistics & allocation
├── section_4_planning/                 # Planned installation allocation
├── section_5_statistic/                # Provincial / terrain statistics on planned allocation
└── section_6_sensitivity_analysis/     # Weight-scenario sensitivity analysis
```

---

## Section 1: Developable Area and Installation Potential

### 1.1 Wind Power Developable Area (`section_1_1_wind_valid_area/`)

Uses an **exclusion method**: all restrictive factors are overlaid, and the combined restricted area is subtracted from the total grid area to derive the wind-developable area (km²) per grid cell.

**Restrictive Factors and Processing Scripts**

| Restrictive Factor | Script | Description |
|---|---|---|
| Existing wind turbine buffer | `a_windturbines_buffer.py` | 500 m geodesic buffer around turbine points, dissolved into a single polygon |
| Road & railway buffer | `b_road_railway_buffer500m.py` | Roads and railways merged, then buffered 1000 m geodesically and dissolved |
| High-elevation area | `c_dem_above_4000m.py` | DEM ≥ 4000 m pixels extracted and vectorized |
| Low wind-speed area | `d_windspeed_below_4p5.py` | Annual mean wind speed at 100 m < 4.5 m/s pixels extracted and vectorized |
| Steep-slope area | `e_slope_above_30.py` | Slope ≥ 30° pixels extracted and vectorized |
| Combined restriction dissolve | `f_limited_area_dissolve.py` | All factors (plus water bodies, nature reserves, solar panels, buildup) merged and dissolved into a single MultiPolygon |
| Area statistics | `g_wind_valid_stastic_areakm2.py` | Intersection of restricted areas with grid, geodesic area calculated and aggregated by NID10, written back to grid layer |

**Raster Processing (GDAL)**: Rasters are processed in 512-row blocks to avoid loading the full national 250 m dataset (~700 million pixels) into memory at once.

**Vector Tools**: ArcPy (`PairwiseBuffer`, `Merge`, `Dissolve`, `Intersect`, `CalculateGeometryAttributes`).

---

### 1.2 Solar PV Developable Area (`section_1_2_solar_valid_area/`)

Reuses slope, turbine buffer, and road/railway buffer outputs from 1.1, then adds PV-specific restrictive factors to derive the solar-developable area per grid cell.

**PV-Specific Restrictive Factors**

| Restrictive Factor | Script | Description |
|---|---|---|
| High-elevation area | `a_dem_above_4500m.py` | DEM ≥ 4500 m (500 m higher threshold than wind) |
| Low irradiation area | `b_ghi_1000kwh_m2.py` | Annual GHI ≤ 1000 kWh/m² pixels extracted and vectorized |
| Combined restriction dissolve | `c_limited_area_dissolve.py` | All factors merged via ArcPy Merge + Dissolve → `solar_limited_areas_dissolved.shp` |
| Area statistics | `d_calculate_areakm2.py` | Restricted areas and residential areas intersected with grid separately; valid area computed per formula |

**Solar Developable Area Formula**

```math
\text{valid\_km2} = \text{grid\_km2} - \text{limited\_km2} - \text{resident\_km2} \times 75\%
```

> Residential areas are not fully excluded — only 75% of their area is deducted (25% utilization rate retained).

---

### 1.3 Installed Capacity Potential (`section_1_3_installation/`)

Based on the developable areas from 1.1 and 1.2, terrain parameters are used to estimate the theoretical installed capacity (kW) for each grid cell.

#### Wind Capacity Estimation (`wind_installation.py`)

ArcPy Spatial Analyst (`ZonalStatisticsAsTable`) computes the mean slope per grid cell. A capacity density (MW/km²) is looked up from a slope-interval table, then multiplied by the developable area.

**Capacity Density by Slope Interval**

| Slope Range (°) | Capacity Density (MW/km²) |
|---|---|
| 0 – 1.7 | 6.27 |
| 1.7 – 3.4 | 5.68 |
| 3.4 – 16.7 | 5.05 |
| 16.7 – 30 | 4.28 |
| ≥ 30 | 0 (not developable) |

```math
\text{cap\_kw} = \text{valid\_area\_km2} \times \text{density}\;(\mathrm{MW/km^2}) \times 1000\;\mathrm{kW/MW}
```

> Offshore grid cells (`Shengcode = 100`) apply an additional area factor of 8.

#### Solar PV Capacity Estimation (`solar_installation.py`)

Each grid cell is first classified into a terrain type (I / II / III), then the capacity density (kW/km²) is interpolated by the grid centroid **latitude** using `numpy.interp`.

**Terrain Classification**

| Type | Slope | Relief (Elevation Range) |
|---|---|---|
| Type I (plain) | ≤ 3° | — |
| Type II (gentle hill) | 3° – 20° | < 200 m |
| Type III (hilly/mountain) | 20° – 30° | ≥ 200 m |
| Not developable | ≥ 30° | — |

Capacity density values are loaded from an external Excel file (`wind_solar_capacity_density.xlsx`), grouped by terrain type, and interpolated linearly against latitude.

---

## Section 2: Grid Index System

Three evaluation scenarios are defined — onshore wind, offshore wind, and onshore PV — each with its own set of indices (range: 0–1) written back to the `CL_WGS84` feature class.

### 2.1 Onshore Wind Indices (`section_2_1_index/`)

Grid filter: `Shengcode <> 100 AND Shengcode > 0`

| Index Field | Script | Calculation |
|---|---|---|
| `idx_terrain` | `a_terrain_topography_index.py` | Majority land-use class (k3classes) + mean elevation: no restriction = 1, light = 0.8, moderate = 0.6, ocean / high elevation = 0 |
| `wind_idx_install` | `b_wind_power_installation_index.py` | Wind capacity potential (`cap_kw_new`) min-max normalized to 0–1 |
| `idx_wind` | `c_average_wind_speed_index.py` | Zonal mean of 100 m annual wind speed, classified into five categories (≤4, 4–5, 5–6, 6–7, >7 m/s) scored as 0.2, 0.4, 0.6, 0.8, 1.0 |
| `idx_road` | `d_distance_to_road_index.py` | Geodesic distance from grid centroid to nearest road: ≤30 km = 1, 30–40 km = 0.8, 40–50 km = 0.6, 50–100 km = 0.4, >100 km = 0.2 |

**Common Technical Pattern**: `ZonalStatisticsAsTable` → centroid point extraction as fallback (`ExtractMultiValuesToPoints`) → write results back to the original feature class.

### 2.2 Offshore Wind Indices (`section_2_2_offshore_index/`)

Grid filter: `Shengcode = 100`

| Index Field | Script | Calculation |
|---|---|---|
| `off_idx_shore` | `a_distance_to_shore.py` | Geodesic distance from centroid to coastline: 10–20 km = 1, 20–30 km = 0.8, >30 km = 0.6, <10 km = 0 (too close) |
| `off_idx_wind` | `b_offhore_wind_speed_index.py` | Cells with wind speed ≥ 6 m/s: min-max normalized to 0.2–1; cells below threshold assigned 0 |
| `off_idx_install` | `c_wind_installation_index.py` | Offshore capacity potential (`cap_kw`) min-max normalized to 0–1 |

### 2.3 Onshore PV Indices (`section_2_3_onshore_pv_index/`)

Grid filter: `Shengcode <> 100 AND Shengcode > 0`

| Index Field | Script | Calculation |
|---|---|---|
| `pv_idx_install` | `a_installation_index.py` | Solar capacity potential (`cap_kw`) min-max normalized to 0–1 |
| `idx_ghi` | `b_ghi_index.py` | Zonal mean of annual GHI, min-max normalized to 0–1 |

> `idx_terrain` and `idx_road` are shared with the onshore wind scenario (already written to the grid layer in section_2_1).

### 2.4 Composite Scoring (`section_2_4_weight_cal/`)

`a_weight_calcaulation.py` computes a weighted composite score (0–100) for each scenario:

$$\text{Score} = \sum_i \text{index}_i \times \text{weight}_i$$

| Scenario | Output Field | Indices | Weights |
|---|---|---|---|
| Onshore Wind | `score_wind_onshore` | `idx_terrain`, `wind_idx_install`, `idx_wind`, `idx_road` | 40, 10, 10, 40 |
| Offshore Wind | `score_wind_offshore` | `off_idx_shore`, `off_idx_install`, `off_idx_wind` | 40, 30, 30 |
| Onshore PV | `score_pv_onshore` | `idx_terrain`, `pv_idx_install`, `idx_ghi`, `idx_road` | 30, 20, 20, 30 |

> Grid cells where any index value is NULL will receive a NULL composite score.

---

## Section 3: Current Installation Statistics and Allocation

### 3a — Grid Statistics (`a_statistic_by_grid10km.py`)

- Uses ArcPy `SpatialJoin` (CONTAINS) to count **wind turbines** per grid cell → output field `Wind_Turbine_Count`.
- Computes geodesic area (m²) for each solar panel polygon, then spatially joins and sums `Area_m2` per grid cell → output field `Solar_Area_m2`.

### 3b — Provincial Allocation (`b_allocation.py`)

Reads the 2025 provincial installed capacity and full-load hours from an external Excel file (`wind and solar development - EN.xlsx`), then distributes the provincial totals to individual grid cells using the following rules:

- **Onshore wind**: Each grid cell's share = its turbine count ÷ provincial total turbine count. Output: `kw2025` (kW), `kwh2025` (kWh = capacity × full-load hours).
- **Offshore wind**: Each grid cell's share = its turbine count ÷ national offshore total. Uses the national offshore capacity total.
- **Onshore PV**: Each grid cell's share = its solar panel area ÷ provincial total solar panel area.

---

## Section 4: Planned Installation Allocation (`section_4_planning/`)

`plan_install_allocation.py` distributes provincial planning targets to individual grid cells using a **greedy incremental fill** ordered by composite score.

### Core Algorithm

1. **Data assembly**: Join capacity potential (`KW2` = maximum capacity), current installation (`kw2025`), and composite score (`Score`) onto a single grid DataFrame.
2. **Intra-province sorting**: Grid cells sorted descending by `kw2025` (current), `Score` (rating), `KW2` (potential) — highest-scoring cells filled first.
3. **Multi-year incremental fill**: Years processed in sequence 2030 → 2035 → 2040 → 2050 → 2060. Each year uses the previous year's result as a floor; only the incremental gap is filled, capped at `KW2`.
4. **Dual scenarios**: Each province is processed under two target sets — "Province Plan" and "Low Carbon" — producing parallel output columns with prefixes `prov_*` and `lc_*`.
5. **Output**: Per-province summary exported to CSV (`*_allocation_summary.csv`); grid-level results optionally written back to shapefile via `write_results_to_shp`.

### Output Fields

| Field | Description |
|---|---|
| `kw2025` | Current installed capacity as of 2025 (kW) |
| `prov_2030` – `prov_2060` | Province-plan scenario installed capacity by year (kW) |
| `lc_2030` – `lc_2060` | Low-carbon scenario installed capacity by year (kW) |

---

## Section 5: Provincial / Terrain Statistics (`section_5_statistic/`)

Breaks down the Section 4 planned-allocation results (`prov_*`, `lc_*`, `kw2025`) by **province × terrain type**, for wind and solar separately. This is a reporting/aggregation step — it does not compute anything new, only groups and sums the Section 4 output.

### 5a — Statistics by Province and Terrain (`a_statistic_by_terrain.py`)

1. **Terrain classification at grid centroids**: each grid's centroid is extracted and overlaid on a terrain raster (`Reclass_geom1.tif`) with codes 1–4 → `Plain`, `Hills`, `Mountainous`, `Complex terrain`. Where a centroid falls on NoData, `EucAllocation` fills it with the nearest valid terrain value — except for offshore cells (`Shengcode = 100`), which are left unfilled and reported as `Unknown` terrain.
2. **Grouping**: grid rows are joined to their terrain type, then grouped by `(Shengcode, Province, terrain_type)` and summed across `kw2025` and both planning modes (`prov_*`, `lc_*`) for every year in `[2025, 2030, 2035, 2040, 2050, 2060]`.
3. **Output**: `processing/tables/statistic_by_province_terrain.xlsx`, with one sheet each for `wind` and `solar`. Columns: `Shengcode`, `Province`, `terrain_type`, `2025_province` … `2060_province`, `2025_low_carbon` … `2060_low_carbon`.

> Input shapefiles (`grid10km_wind_planned.shp`, `grid10km_solar_planned.shp`) must already carry the Section 4 allocation columns (`kw2025`, `prov_2030..prov_2060`, `lc_2030..lc_2060`).

---

## Section 6: Sensitivity Analysis (`section_6_sensitivity_analysis/`)

Tests how robust the provincial capacity **rankings** produced by Section 4 are to the choice of index weights. For each of the three systems (onshore wind, offshore wind, solar PV), several alternative weighting schemes are scored, the Section-4 greedy allocation is re-run under each scheme, and the resulting grid-level allocations are compared back to the `baseline` weights (the weights used in Section 2.4) via rank-correlation metrics. All outputs are written to an independent copy of the grid, `sensitivity.gdb`, so Section 4's original results are never touched.

### Weight Scenarios

Each scenario reuses the same index fields as Section 2.4 but redistributes the weight among them (values sum to 100).

| System | Index Fields | `baseline` | `resource` | `infra` | `terrain` | `equal` |
|---|---|---|---|---|---|---|
| Onshore wind | `idx_terrain`, `wind_idx_install`, `idx_wind`, `idx_road` | 40, 10, 10, 40 | 20, 10, 50, 20 | 20, 30, 10, 40 | 55, 10, 10, 25 | 25, 25, 25, 25 |
| Offshore wind | `off_idx_shore`, `off_idx_install`, `off_idx_wind` | 40, 30, 30 | 25, 25, 50 | 45, 40, 15 | — (no terrain index) | 33.3, 33.3, 33.3 |
| Solar PV | `idx_terrain`, `pv_idx_install`, `idx_ghi`, `idx_road` | 30, 20, 20, 30 | 15, 20, 50, 15 | 20, 30, 10, 40 | 50, 15, 15, 20 | 25, 25, 25, 25 |

### 6a — Scenario Scoring (`a_weight_scence.py`)

- Copies the master grid (`CL_WGS84`) into a dedicated `sensitivity.gdb` so all scenario fields are isolated from the production grid.
- For every scenario in the table above, computes a weighted composite score and writes it to a new field `score_{system}_{scenario}` (e.g. `score_wind_onshore_resource`), using the same weighted-sum formula as Section 2.4. Cells with any NULL index are left NULL.

### 6b — Multi-Year Allocation per Scenario (`b_planning_2030_2060.py`)

Re-runs the Section 4 greedy incremental-fill algorithm (sort by `kw2025` → `Score` → `KW2`, fill 2030 → 2035 → 2040 → 2050 → 2060, both `Province Plan` and `Low Carbon` targets) once per scenario, using each scenario's score field in place of the baseline `Score`.

- Output: one feature class per `{energy_type}_{scenario}` (e.g. `wind_onshore_resource`) inside `sensitivity.gdb`, containing `prov_2030..prov_2060` and `lc_2030..lc_2060`.
- A per-province summary CSV is also exported: `processing/tables/{energy_type}_{scenario}_allocation_summary.csv`.

### 6c — Ranking Robustness Metrics (`c_sensitivity_analysis.py`)

For every system, scenario (excluding `baseline` itself), planning mode (`province` / `low_carbon`), and year, compares each grid cell's allocated capacity under the scenario against the `baseline` allocation, grouped by province:

| Metric | Definition |
|---|---|
| `spearman_rho` | Spearman rank correlation between baseline and scenario grid-cell capacities within the province |
| `topN_overlap` | Fraction of baseline's developed cells (`capacity > 0`) that are also developed under the scenario |
| `jaccard` | Jaccard similarity of the two "developed cell" sets |

**Outputs** (`processing/tables/`):
- `sensitivity_detail.csv` — one row per system / plan / scenario / year / province.
- `sensitivity_summary.csv` — aggregated by system / plan / scenario / year: `rho_mean`, `rho_min`, `overlap_mean`, `overlap_min`, `jaccard_mean`, `n_provinces`, and `frac_robust` (share of provinces with ρ > 0.9).

### 6d — Provincial Heatmap (`d_plot_details.py`)

Plots, per system, a province (rows) × year (columns) heatmap where each cell is the **worst-case** (minimum) `spearman_rho` across all weight scenarios and both planning modes — i.e. how sensitive that province's ranking is to weighting choices in the worst case.

- Onshore wind & Solar PV panels: 31 provinces (`ORDER`, N→S geographic ordering).
- Offshore wind panel: single row (province code `100`), sized to occupy 1/31 of the panel height of the other two systems so it isn't stretched to match a 31-row panel.
- Output: `processing/images/sensitivity_province_heatmap.png`.

### 6e — Three-Metric Summary Heatmap (`e_plot_summary.py`)

Supplementary figure with three side-by-side panels (Spearman ρ, Top-k overlap, Jaccard), rows grouped by system → scenario (`equal`, `infra`, `resource`, `terrain`), columns = year. Each cell is the mean of the metric across the two planning modes, read from `sensitivity_summary.csv`.

- Output: `processing/images/sensitivity_three_metrics.png`.

---

## Technical Dependencies

| Library | Purpose |
|---|---|
| `arcpy` | Vector feature processing, spatial analysis, GDB/Shapefile I/O |
| `gdal` / `ogr` / `osr` | Large-scale raster thresholding, vectorization, CRS management |
| `numpy` | Block-wise raster computation, linear interpolation |
| `pandas` | Provincial data table loading, merging, and allocation result aggregation |
| `scipy` | Spearman rank correlation (`scipy.stats.spearmanr`) for sensitivity analysis |
| `matplotlib` | Heatmap figures for sensitivity analysis results |
| `openpyxl` | Excel (`.xlsx`) read/write for planning targets and statistics output |

**Runtime environment**: ArcGIS Pro with the Spatial Analyst extension activated. Python environment is ArcGIS Pro's bundled conda environment (Python 3.x).

---

## Data Path Convention

All scripts resolve the project root directory (`base_folder`) via `Path(__file__).resolve().parents[3]`. All data paths are expressed relative to this root — no hardcoded absolute paths need to be changed when the project is relocated.

**Key Input Datasets**

| Dataset | Relative Path |
|---|---|
| National 10km grid | `processing/arcprojects/MyProject1/MyProject1.gdb/CL_WGS84` |
| DEM 250 m | `processing/gisfiles/DEM/chinadem250.tif` |
| Slope 250 m | `processing/gisfiles/slope/chinaslope250.tif` |
| 100 m annual mean wind speed | `processing/gisfiles/windspeed100m/merged.tif` |
| Annual GHI | `processing/gisfiles/GHI/GHI_yr_365p25.tif` |
| Wind turbine locations | `processing/gisfiles/wind_solar_distribution_202605/windturbines.shp` |
| Solar panel polygons | `processing/gisfiles/wind_solar_distribution_202605/solar_panel.shp` |
| Provincial installation statistics | `processing/tables/wind and solar development - EN.xlsx` |
| Provincial planning targets | `processing/tables/Planned installed capacity.xlsx` |
| Capacity density table | `processing/tables/wind_solar_capacity_density.xlsx` |

---

## Execution Order

```
section_1_1  →  section_1_2  →  section_1_3
      ↓               ↓
section_2_1      section_2_3
      ↓               ↓
section_2_2       section_2_4  (composite scoring)
                       ↓
               section_3  (current allocation)
                       ↓
               section_4  (planned allocation)
                       ↓
               section_5  (province / terrain statistics)

               section_6  (sensitivity analysis, a → e)
```

Within each section, scripts are executed in alphabetical order (a → g). Each script depends on outputs produced by the preceding scripts in the same or earlier sections. `section_5_statistic` depends on the `prov_*`/`lc_*` allocation columns written by Section 4. `section_6_sensitivity_analysis` depends on the index/score fields from Section 2 and the potential/current-installation data from Sections 1.3 and 3, but writes into its own `sensitivity.gdb` and can be run independently of Section 4/5.
