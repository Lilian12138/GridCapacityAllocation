from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]
import os
import arcpy

wind_shore = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb\china_singleparts")
grid_10km = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")

scratch_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb")
output_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb")

GRID_ID_FIELD = "NID10_INT"
GRID_FILTER = "Shengcode = 100"

arcpy.env.overwriteOutput = True
arcpy.env.workspace = scratch_gdb

# ---------- Ensure the field exists ----------
def add_field_safe(fc, field_name, field_type):
    existing = [f.name for f in arcpy.ListFields(fc)]
    if field_name not in existing:
        arcpy.management.AddField(fc, field_name, field_type)

add_field_safe(grid_10km, "off_idx_shore", "DOUBLE")

# ---------- Filter offshore grid cells and generate centroids ----------
grid_layer = "grid_sea_layer"
arcpy.MakeFeatureLayer_management(grid_10km, grid_layer, GRID_FILTER)

sea_fc = os.path.join(scratch_gdb, "grid_sea_filtered")
if arcpy.Exists(sea_fc):
    arcpy.management.Delete(sea_fc)
arcpy.management.CopyFeatures(grid_layer, sea_fc)

centroids = os.path.join(scratch_gdb, "grid_sea_centroids")
if arcpy.Exists(centroids):
    arcpy.management.Delete(centroids)
arcpy.management.FeatureToPoint(sea_fc, centroids, "CENTROID")

# ---------- Calculate the nearest distance (meters) ----------
near_table = os.path.join(scratch_gdb, "shore_near")
if arcpy.Exists(near_table):
    arcpy.management.Delete(near_table)
arcpy.analysis.Near(centroids, wind_shore, method="GEODESIC")

# ---------- Build the distance lookup (convert to km) ----------
dist_dict = {}
with arcpy.da.SearchCursor(centroids, [GRID_ID_FIELD, "NEAR_DIST"]) as cur:
    for row in cur:
        dist_dict[row[0]] = row[1] / 1000.0  # m -> km

# ---------- Assign values ----------
with arcpy.da.UpdateCursor(grid_10km, [GRID_ID_FIELD, "off_idx_shore"], GRID_FILTER) as cur:
    for row in cur:
        d = dist_dict.get(row[0])
        if d is None or d < 10:
            row[1] = 0
        elif d <= 20:
            row[1] = 1.0
        elif d <= 30:
            row[1] = 0.8
        else:
            row[1] = 0.6
        cur.updateRow(row)

print("Done: off_idx_shore written back to CL_WGS84")
