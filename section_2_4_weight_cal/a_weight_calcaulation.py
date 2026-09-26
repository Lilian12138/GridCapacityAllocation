from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]

import arcpy
import os

grid_10km = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")

def calculate_weighted_score(fc, grid_filter, index_fields, weights, score_field):
    """Calculate weighted composite score (0-100) and write to score_field."""
    # Add score field if it doesn't exist
    existing_fields = [f.name for f in arcpy.ListFields(fc)]
    if score_field not in existing_fields:
        arcpy.AddField_management(fc, score_field, "DOUBLE")

    # Calculate weighted score row by row (weights should sum to 100)
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


# ============ Wind Onshore ============
wind_onshore_filter = "Shengcode <> 100 AND Shengcode > 0"
wind_onshore_index = ['idx_terrain', 'wind_idx_install', 'idx_wind', 'idx_road']
wind_onshore_weight = [40, 10, 10, 40]
calculate_weighted_score(grid_10km, wind_onshore_filter,
                         wind_onshore_index, wind_onshore_weight,
                         "score_wind_onshore")

# ============ Wind Offshore ============
wind_offshore_filter = "Shengcode = 100"
wind_offshore_index = ['off_idx_shore', 'off_idx_install', 'off_idx_wind']
wind_offshore_weight = [40, 30, 30]
calculate_weighted_score(grid_10km, wind_offshore_filter,
                         wind_offshore_index, wind_offshore_weight,
                         "score_wind_offshore")

# ============ PV Onshore ============
pv_onshore_filter = "Shengcode <> 100 AND Shengcode > 0"
pv_onshore_index = ['idx_terrain', 'pv_idx_install', 'idx_ghi', 'idx_road']
pv_onshore_weight = [30, 20, 20, 30]
calculate_weighted_score(grid_10km, pv_onshore_filter,
                         pv_onshore_index, pv_onshore_weight,
                         "score_pv_onshore")