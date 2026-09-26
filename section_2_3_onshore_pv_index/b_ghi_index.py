from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]
import os
os.environ['GDAL_DATA'] = r'D:\installs\ArcGIS\Pro\Resources\pedata\gdaldata'

import arcpy

ghi_path = os.path.join(base_folder, r"processing\gisfiles\GHI\GHI_yr_365p25.tif")
grid_10km = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")

scratch_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb")
output_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb")

GRID_ID_FIELD = "NID10_INT"
GRID_FILTER = "Shengcode <> 100 AND Shengcode > 0"

arcpy.env.overwriteOutput = True
arcpy.CheckOutExtension("Spatial")
arcpy.env.workspace = scratch_gdb

def add_field_safe(fc, field_name, field_type):
    existing = [f.name for f in arcpy.ListFields(fc)]
    if field_name not in existing:
        arcpy.management.AddField(fc, field_name, field_type)

# ---------- Filter onshore grid cells ----------
grid_layer = "grid_ghi_layer"
arcpy.MakeFeatureLayer_management(grid_10km, grid_layer, GRID_FILTER)

grid_fc = os.path.join(scratch_gdb, "grid_filtered_ghi")
if arcpy.Exists(grid_fc):
    arcpy.management.Delete(grid_fc)
arcpy.management.CopyFeatures(grid_layer, grid_fc)

# ---------- Zonal Mean ----------
ghi_table = os.path.join(scratch_gdb, "ghi_zonal")
if arcpy.Exists(ghi_table):
    arcpy.management.Delete(ghi_table)
arcpy.sa.ZonalStatisticsAsTable(grid_fc, GRID_ID_FIELD, ghi_path, ghi_table, "DATA", "MEAN")

ghi_zonal_dict = {r[0]: r[1] for r in arcpy.da.SearchCursor(ghi_table, [GRID_ID_FIELD, "MEAN"])}

# ---------- Extract centroids as a fallback ----------
centroids = os.path.join(scratch_gdb, "grid_centroids_ghi")
if arcpy.Exists(centroids):
    arcpy.management.Delete(centroids)
arcpy.management.FeatureToPoint(grid_fc, centroids, "CENTROID")
arcpy.sa.ExtractMultiValuesToPoints(centroids, [[ghi_path, "ghi_pt"]])

ghi_pt_dict = {}
with arcpy.da.SearchCursor(centroids, [GRID_ID_FIELD, "ghi_pt"]) as cur:
    for r in cur:
        if r[1] is not None:
            ghi_pt_dict[r[0]] = r[1]

# ---------- Merge: prioritize zonal results, use centroids as fallback ----------
ghi_values = {}
for fid, in arcpy.da.SearchCursor(grid_fc, [GRID_ID_FIELD]):
    val = ghi_zonal_dict.get(fid)
    if val is None:
        val = ghi_pt_dict.get(fid)
    if val is not None:
        ghi_values[fid] = val

# ---------- Normalize to 0-1 ----------
valid_vals = list(ghi_values.values())
min_val = min(valid_vals)
max_val = max(valid_vals)
val_range = max_val - min_val

add_field_safe(grid_fc, "idx_ghi", "DOUBLE")
with arcpy.da.UpdateCursor(grid_fc, [GRID_ID_FIELD, "idx_ghi"]) as cur:
    for row in cur:
        val = ghi_values.get(row[0])
        if val is not None and val_range > 0:
            row[1] = (val - min_val) / val_range
        elif val is not None:
            row[1] = 1.0
        else:
            row[1] = 0.0
        cur.updateRow(row)

# ---------- Write back to the original feature class ----------
add_field_safe(grid_10km, "idx_ghi", "DOUBLE")
join_dict = {r[0]: r[1] for r in arcpy.da.SearchCursor(grid_fc, [GRID_ID_FIELD, "idx_ghi"])}
with arcpy.da.UpdateCursor(grid_10km, [GRID_ID_FIELD, "idx_ghi"], GRID_FILTER) as cur:
    for row in cur:
        row[1] = join_dict.get(row[0], 0.0)
        cur.updateRow(row)

print("Done: idx_ghi (0-1 normalized) written back to CL_WGS84")
