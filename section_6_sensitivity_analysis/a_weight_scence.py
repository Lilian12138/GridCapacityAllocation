from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]

import arcpy
import os

# input
src_grid = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")

# Target: a standalone database for sensitivity analysis
sens_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\sensitivity.gdb")
grid_10km = os.path.join(sens_gdb, "CL_WGS84")   # Copy where all scenario fields are written

arcpy.env.overwriteOutput = True

# Create sensitivity.gdb if it does not exist
if not arcpy.Exists(sens_gdb):
    gdb_folder = os.path.dirname(sens_gdb)
    gdb_name = os.path.basename(sens_gdb)
    arcpy.management.CreateFileGDB(gdb_folder, gdb_name)
    print(f"[Created] {sens_gdb}")

# Copy the original grid to sensitivity.gdb (run once; overwrite if it already exists)
arcpy.management.CopyFeatures(src_grid, grid_10km)
print(f"[Copied] {src_grid} -> {grid_10km}")


def calculate_weighted_score(fc, grid_filter, index_fields, weights, score_field):
    """Calculate weighted composite score (0-100) and write to score_field."""
    assert len(index_fields) == len(weights), "index_fields 与 weights 数量不一致"
    assert abs(sum(weights) - 100) < 1e-6, f"weights 之和不是100: {sum(weights)}"

    existing_fields = [f.name for f in arcpy.ListFields(fc)]
    if score_field not in existing_fields:
        arcpy.AddField_management(fc, score_field, "DOUBLE")

    fields = index_fields + [score_field]
    with arcpy.da.UpdateCursor(fc, fields, where_clause=grid_filter) as cursor:
        for row in cursor:
            values = row[:len(index_fields)]
            if any(v is None for v in values):
                row[-1] = None
            else:
                row[-1] = sum(v * w for v, w in zip(values, weights)) / 100.0
            cursor.updateRow(row)

    print(f"[Done] {score_field}, filter: {grid_filter}")


# ==========================================================
# Scenario weight definitions
# ==========================================================
wind_onshore_filter = "Shengcode <> 100 AND Shengcode > 0"
wind_onshore_index = ['idx_terrain', 'wind_idx_install', 'idx_wind', 'idx_road']
wind_onshore_scenarios = {
    "baseline": [40, 10, 10, 40],
    "resource": [20, 10, 50, 20],
    "infra":    [20, 30, 10, 40],
    "terrain":  [55, 10, 10, 25],
    "equal":    [25, 25, 25, 25],
}

wind_offshore_filter = "Shengcode = 100"
wind_offshore_index = ['off_idx_shore', 'off_idx_install', 'off_idx_wind']
# Generate four scenarios using the specified offshore weights; do not generate an additional terrain scenario.
wind_offshore_scenarios = {
    "baseline": [40, 30, 30],
    "resource": [25, 25, 50],
    "infra":    [45, 40, 15],
    "equal":    [100/3, 100/3, 100/3],
}

pv_onshore_filter = "Shengcode <> 100 AND Shengcode > 0"
pv_onshore_index = ['idx_terrain', 'pv_idx_install', 'idx_ghi', 'idx_road']
pv_onshore_scenarios = {
    "baseline": [30, 20, 20, 30],
    "resource": [15, 20, 50, 15],
    "infra":    [20, 30, 10, 40],
    "terrain":  [50, 15, 15, 20],
    "equal":    [25, 25, 25, 25],
}


def run_all_scenarios(prefix, fc, grid_filter, index_fields, scenarios):
    for scen_name, weights in scenarios.items():
        score_field = f"score_{prefix}_{scen_name}"
        calculate_weighted_score(fc, grid_filter, index_fields, weights, score_field)


# ============ Execution ============
run_all_scenarios("wind_onshore",  grid_10km, wind_onshore_filter,  wind_onshore_index,  wind_onshore_scenarios)
run_all_scenarios("wind_offshore", grid_10km, wind_offshore_filter, wind_offshore_index, wind_offshore_scenarios)
run_all_scenarios("pv_onshore",    grid_10km, pv_onshore_filter,    pv_onshore_index,    pv_onshore_scenarios)

print("All scenarios done. Output:", grid_10km)
