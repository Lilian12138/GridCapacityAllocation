# -*- coding: utf-8 -*-
"""
Calculate the 100 m mean wind speed suitability index (off_idx_wind).
Workflow:
  0. Clean the wind speed raster (remove NoData fill values / invalid values)
  1. Zonal statistics: mean wind speed for each 10 km grid cell
  2. Centroid extraction: fallback for grid cells without zonal statistics
  3. Threshold filtering (>= 6 m/s) + percentile clipping and normalization to 0.2-1
  4. Write results back to the original CL_WGS84 feature class
"""

from pathlib import Path
import os

base_folder = Path(__file__).resolve().parents[3]
os.environ['GDAL_DATA'] = r'D:\installs\ArcGIS\Pro\Resources\pedata\gdaldata'

import arcpy
import numpy as np

# ----------------------------- Parameters -----------------------------
wind_power_path = os.path.join(base_folder, r"processing\gisfiles\windspeed100m\merged.tif")
grid_10km = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")

scratch_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb")

GRID_ID_FIELD = "NID10_INT"
GRID_FILTER = "Shengcode = 100"

WIND_THRESHOLD = 6.0        # Minimum qualifying value (m/s)
WIND_VALID_MIN = 0.0        # Lower bound of the physically valid range
WIND_VALID_MAX = 60.0       # Upper bound of the physically valid range (values beyond it are treated as fill values/anomalies)
PCT_LOW, PCT_HIGH = 2, 98   # Percentile clipping for normalization, preventing outliers from compressing the main distribution

OUT_FIELD = "off_idx_wind"

arcpy.env.overwriteOutput = True
arcpy.CheckOutExtension("Spatial")
arcpy.env.workspace = scratch_gdb


def add_field_safe(fc, field_name, field_type):
    existing = [f.name for f in arcpy.ListFields(fc)]
    if field_name not in existing:
        arcpy.management.AddField(fc, field_name, field_type)


def delete_if_exists(path):
    if arcpy.Exists(path):
        arcpy.management.Delete(path)


# ------------------- Step 0: Raster diagnostics and cleaning -------------------
ras = arcpy.Raster(wind_power_path)
print("=== Original Raster Diagnostics ===")
print(f"  noDataValue : {ras.noDataValue}")
print(f"  min / max   : {ras.minimum} / {ras.maximum}")

wind_clean = os.path.join(scratch_gdb, "wind_clean")

if ras.minimum is not None and ras.minimum >= WIND_VALID_MIN \
        and ras.maximum is not None and ras.maximum <= WIND_VALID_MAX:
    print("  Raster values are within the valid range; skipping cleaning")
    wind_raster = wind_power_path
else:
    print(f"  Invalid values detected; setting (<{WIND_VALID_MIN} or >{WIND_VALID_MAX}) to NoData ...")
    delete_if_exists(wind_clean)
    cleaned = arcpy.sa.SetNull((ras < WIND_VALID_MIN) | (ras > WIND_VALID_MAX), ras)
    cleaned.save(wind_clean)
    wind_raster = wind_clean
    ras2 = arcpy.Raster(wind_clean)
    print(f"  Cleaned min / max: {ras2.minimum} / {ras2.maximum}")

# ------------------- Save filtered grid cells -------------------
grid_layer = "grid_filtered_a"
arcpy.MakeFeatureLayer_management(grid_10km, grid_layer, GRID_FILTER)

grid_fc = os.path.join(scratch_gdb, "grid_filtered_a")
delete_if_exists(grid_fc)
arcpy.management.CopyFeatures(grid_layer, grid_fc)

total_cells = int(arcpy.management.GetCount(grid_fc)[0])
print(f"\nFiltered grid cell count: {total_cells}")

# ------------------- Step 1: Zonal statistics (MEAN) -------------------
wind_table = os.path.join(scratch_gdb, "wind_zonal")
delete_if_exists(wind_table)
arcpy.sa.ZonalStatisticsAsTable(grid_fc, GRID_ID_FIELD, wind_raster,
                                wind_table, "DATA", "MEAN")

wind_zonal_dict = {}
for fid, mean_v in arcpy.da.SearchCursor(wind_table, [GRID_ID_FIELD, "MEAN"]):
    # Secondary safeguard: discard any invalid mean after cleaning and use the fallback
    if mean_v is not None and WIND_VALID_MIN <= mean_v <= WIND_VALID_MAX:
        wind_zonal_dict[fid] = mean_v

print(f"Grid cells with valid zonal statistics: {len(wind_zonal_dict)}")

# ------------------- Step 2: Centroid extraction fallback -------------------
centroids = os.path.join(scratch_gdb, "grid_centroids_a")
delete_if_exists(centroids)
arcpy.management.FeatureToPoint(grid_fc, centroids, "CENTROID")
arcpy.sa.ExtractMultiValuesToPoints(centroids, [[wind_raster, "wind_pt"]])

wind_pt_dict = {}
with arcpy.da.SearchCursor(centroids, [GRID_ID_FIELD, "wind_pt"]) as cur:
    for fid, v in cur:
        if v is not None and WIND_VALID_MIN <= v <= WIND_VALID_MAX:
            wind_pt_dict[fid] = v

# ------------------- Merge results + threshold filtering -------------------
wind_values = {}        # Qualifying grid cells: fid -> wind speed
below_threshold = 0     # Has data but falls below the threshold
no_data_cells = 0       # No data available

with arcpy.da.SearchCursor(grid_fc, [GRID_ID_FIELD]) as cur:
    for (fid,) in cur:
        val = wind_zonal_dict.get(fid)
        if val is None:
            val = wind_pt_dict.get(fid)
        if val is None:
            no_data_cells += 1
        elif val >= WIND_THRESHOLD:
            wind_values[fid] = val
        else:
            below_threshold += 1

print(f"\n=== Threshold Filtering Results (>= {WIND_THRESHOLD} m/s) ===")
print(f"  Qualifying grid cells     : {len(wind_values)}")
print(f"  Below-threshold grid cells: {below_threshold}")
print(f"  Grid cells without data   : {no_data_cells}")

if not wind_values:
    raise RuntimeError("没有任何格网达到风速阈值, 请检查栅格单位/阈值设置!")

# ------------------- Step 3: Percentile clipping and normalization (0.2-1) -------------------
valid_arr = np.array(list(wind_values.values()), dtype=float)
print(f"\n=== Wind Speed Distribution of Qualifying Grid Cells (m/s) ===")
print(f"  min={valid_arr.min():.2f}  max={valid_arr.max():.2f}")
print(f"  P5={np.percentile(valid_arr, 5):.2f}  "
      f"P50={np.percentile(valid_arr, 50):.2f}  "
      f"P95={np.percentile(valid_arr, 95):.2f}")

low = float(np.percentile(valid_arr, PCT_LOW))
high = float(np.percentile(valid_arr, PCT_HIGH))
val_range = high - low
print(f"  Normalization range (P{PCT_LOW}-P{PCT_HIGH}): [{low:.2f}, {high:.2f}]")

add_field_safe(grid_fc, OUT_FIELD, "DOUBLE")
with arcpy.da.UpdateCursor(grid_fc, [GRID_ID_FIELD, OUT_FIELD]) as cur:
    for row in cur:
        val = wind_values.get(row[0])
        if val is None:
            row[1] = 0.0                    # Below threshold or no data
        elif val_range > 0:
            v = min(max(val, low), high)    # Clip to the percentile range
            row[1] = 0.2 + (v - low) / val_range * 0.8
        else:
            row[1] = 1.0                    # All qualifying grid cells have the same wind speed
        cur.updateRow(row)

# ------------------- Step 4: Write back to the original feature class -------------------
add_field_safe(grid_10km, OUT_FIELD, "DOUBLE")
join_dict = {r[0]: r[1] for r in
             arcpy.da.SearchCursor(grid_fc, [GRID_ID_FIELD, OUT_FIELD])}

with arcpy.da.UpdateCursor(grid_10km, [GRID_ID_FIELD, OUT_FIELD], GRID_FILTER) as cur:
    for row in cur:
        row[1] = join_dict.get(row[0], 0.0)
        cur.updateRow(row)

# ------------------- Result distribution check -------------------
idx_arr = np.array([v for v in join_dict.values()], dtype=float)
nonzero = idx_arr[idx_arr > 0]
print(f"\n=== off_idx_wind Result Distribution ===")
print(f"  Zero (below threshold/no data): {int((idx_arr == 0).sum())}")
if nonzero.size:
    print(f"  Nonzero values: min={nonzero.min():.3f}  "
          f"P50={np.percentile(nonzero, 50):.3f}  max={nonzero.max():.3f}")

print(f"\nDone: {OUT_FIELD} (0.2-1, wind speed >= {WIND_THRESHOLD} m/s, "
      f"P{PCT_LOW}-P{PCT_HIGH} clipped normalization) written back to CL_WGS84")
