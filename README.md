# A national grid-level dataset of wind and solar capacity deployment pathways in China to 2060

## Overview

This script disaggregates **province-level wind and solar PV installed-capacity targets** (for 2030, 2035, 2040, 2050, and 2060) down to **10 km grid cells**. The allocation follows a **year-by-year incremental, score-based greedy filling** strategy: each year uses the previous year's result as a floor (existing capacity is never removed), and the incremental target for that year is filled into grid cells in descending order of suitability score, until the provincial target is met or cells reach their potential-capacity ceiling (KW2).

Two scenarios are computed in the same run:

| Scenario | Planning-table columns | Output columns |
|---|---|---|
| Province (provincial planning scenario) | `2030_province` … `2060_province` | `prov_2030` … `prov_2060` |
| Low Carbon | `2030_low_carbon` … `2060_low_carbon` | `lc_2030` … `lc_2060` |

For wind, the script automatically separates **onshore** cells (`Shengcode ≠ 100`, scored with `score_wind_onshore`) from **offshore** cells (`Shengcode = 100`, scored with `score_wind_offshore`). Solar PV uses a single score field, `score_pv_onshore`.

## Requirements

- **Python 3.x** (must be run with the Python environment bundled with ArcGIS Pro)
- **arcpy** (required — used to read GDB feature classes / shapefiles and to write results back)
- pandas, numpy
- openpyxl (needed by pandas to read the `.xlsx` planning table)

> Because the script depends on arcpy, it must be run on a Windows machine with ArcGIS Pro installed, using the ArcGIS Pro Python environment (or a cloned environment).

## Input Data

The script locates the project root automatically via `Path(__file__).resolve().parents[3]` (i.e., the script is expected to sit three directory levels below the project root), then reads the following inputs by relative path:

| Dataset | Path | Key fields |
|---|---|---|
| Grid suitability scores | `processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84` | `score_wind_onshore`, `score_wind_offshore`, `score_pv_onshore` |
| Provincial planning table | `processing\tables\Planned installed capacity.xlsx` | Sheets: `Wind`, `Solar`; columns: `Shengcode`, `{year}_province`, `{year}_low_carbon` (unit: **10,000 kW / "wan-kW"**) |
| Wind grid potential | `processing\gisfiles\GridValidArea\grid10km_wind_valid_area_statistic.shp` | `cap_kw_new` → renamed to `KW2` |
| Solar grid potential | `processing\gisfiles\GridValidArea\grid10km_solar_valid_area_statistic.shp` | `cap_kw` → renamed to `KW2` |
| Wind current installation | `processing\arcprojects\MyProject1\installation.gdb\grid_wind_turbine_count` | `kw2025` |
| Solar current installation | `processing\arcprojects\MyProject1\installation.gdb\grid_solar_panel_area` | `kw2025` |

All datasets are joined on `NID10_INT` (the unique long-integer ID of each 10 km grid cell). If a source only contains a text-type `NID10` field, the script converts it automatically. If duplicate `NID10_INT` values are found, potential/current-installation data are aggregated by sum and score data by mean, with a warning printed.

## Allocation Logic

For each province and each scenario, the years are processed in order 2030 → 2035 → 2040 → 2050 → 2060:

1. **Inherit**: each cell's capacity for the current year is initialized from the previous year (the first year starts from the `kw2025` current installation).
2. **Compute the gap**: `remain = provincial target for the year (wan-kW × 10,000, converted to kW) − current provincial total`. If the gap ≤ 0, the year is skipped.
3. **Greedy filling**: cells are sorted in descending order by `kw2025`, `Score`, and `KW2`, and each cell receives `min(remaining gap, KW2 − current value)` in turn, until the gap is filled or all cells hit their potential ceiling.
4. **Logging**: for each year, the script prints the target, the amount actually added, and any unallocated remainder (positive when provincial potential is insufficient).

## Usage

Run the main script directly; it performs the wind allocation, then the solar allocation, and exports the results:

```bash
# Within the ArcGIS Pro Python environment
python plan_install_allocation.py
```

You can also call the allocation for a single energy type from another script:

```python
from plan_install_allocation import run_allocation, write_results_to_shp

wind_df = run_allocation("wind")    # or "solar"
```

## Outputs

| Output | Path | Description |
|---|---|---|
| Provincial summary CSVs | `processing\tables\wind_allocation_summary.csv`<br>`processing\tables\solar_allocation_summary.csv` | Per-province, per-year capacity totals (unit: wan-kW), UTF-8-SIG encoding |
| Wind result shapefile | `processing\gisfiles\GridValidArea\grid10km_wind_planned.shp` | Grid-level allocation results |
| Solar result shapefile | `processing\gisfiles\GridValidArea\grid10km_solar_planned.shp` | Grid-level allocation results |
| Intermediate CSVs | `*_result.csv` next to each result shapefile | Tabular results exported before being joined back to the shapefile |

The result table / shapefile contains the following fields:

```
NID50, NID10_INT, Shengcode, kw2025,
prov_2030, prov_2035, prov_2040, prov_2050, prov_2060,
lc_2030,   lc_2035,   lc_2040,   lc_2050,   lc_2060
```

All values are in **kW**. At the end of the run, the console also prints a per-province summary table and national totals (in wan-kW) for cross-checking against the planning targets.

## Notes

- Targets in the planning table are in **wan-kW (10,000 kW)**; the script multiplies by 10,000 internally to convert to kW.
- `Shengcode = 100` is reserved for the **offshore wind** row. If the Wind sheet has no such row, offshore allocation is skipped with a warning.
- Allocation is **monotonically non-decreasing**: a cell's capacity in a later year is never lower than in an earlier year. If a year's target is below the previous year's result, no adjustment is made for that year.
- If a province's total potential (ΣKW2) is smaller than its target, the surplus cannot be allocated; the log will show an "unallocated" remainder. Check the potential data or adjust the targets in that case.
- Writing results back to shapefiles uses `arcpy.env.overwriteOutput = True`, so existing files with the same names will be overwritten.
- All paths are Windows-style (raw strings with backslashes); adjust the path configuration in Section 1 of the script if running in a different environment.
