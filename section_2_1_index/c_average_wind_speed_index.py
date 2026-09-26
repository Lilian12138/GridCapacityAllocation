from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]
import os
os.environ['GDAL_DATA'] = r'D:\installs\ArcGIS\Pro\Resources\pedata\gdaldata'

import arcpy

wind_power_path = os.path.join(base_folder, r"processing\gisfiles\windspeed100m\merged.tif")
grid_10km = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")

scratch_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb")
output_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb")

GRID_ID_FIELD = "NID10_INT"
GRID_FILTER = "Shengcode <> 100 AND Shengcode > 0"

arcpy.env.overwriteOutput = True
arcpy.CheckOutExtension("Spatial")
arcpy.env.workspace = scratch_gdb

# Materialize filtered land-area grid to disk
grid_layer = "grid_layer_c"
arcpy.MakeFeatureLayer_management(grid_10km, grid_layer, GRID_FILTER)

grid_fc = os.path.join(scratch_gdb, "grid_filtered_c")
if arcpy.Exists(grid_fc):
    arcpy.management.Delete(grid_fc)
arcpy.management.CopyFeatures(grid_layer, grid_fc)

# Step 1: Zonal mean wind speed per grid cell
wind_table = os.path.join(scratch_gdb, "wind_zonal")
if arcpy.Exists(wind_table):
    arcpy.management.Delete(wind_table)
arcpy.sa.ZonalStatisticsAsTable(grid_fc, GRID_ID_FIELD, wind_power_path, wind_table, "DATA", "MEAN")

wind_zonal_dict = {r[0]: r[1] for r in arcpy.da.SearchCursor(wind_table, [GRID_ID_FIELD, "MEAN"])}

# Step 2: Centroid extraction as fallback for cells with no zonal data
centroids = os.path.join(scratch_gdb, "grid_centroids_c")
if arcpy.Exists(centroids):
    arcpy.management.Delete(centroids)
arcpy.management.FeatureToPoint(grid_fc, centroids, "CENTROID")
arcpy.sa.ExtractMultiValuesToPoints(centroids, [[wind_power_path, "wind_pt"]])

wind_pt_dict = {}
with arcpy.da.SearchCursor(centroids, [GRID_ID_FIELD, "wind_pt"]) as cur:
    for r in cur:
        if r[1] is not None:
            wind_pt_dict[r[0]] = r[1]

# Merge: zonal value first, centroid point as fallback
wind_values = {}
for fid, in arcpy.da.SearchCursor(grid_fc, [GRID_ID_FIELD]):
    val = wind_zonal_dict.get(fid)
    if val is None:
        val = wind_pt_dict.get(fid)
    if val is not None:
        wind_values[fid] = val

# Step 3: Classify wind speed into scored categories
def wind_score(speed):
    if speed is None:
        return 0.0
    if speed <= 4:
        return 0.2
    elif speed <= 5:
        return 0.4
    elif speed <= 6:
        return 0.6
    elif speed <= 7:
        return 0.8
    else:
        return 1.0

def add_field_safe(fc, field_name, field_type):
    existing = [f.name for f in arcpy.ListFields(fc)]
    if field_name not in existing:
        arcpy.management.AddField(fc, field_name, field_type)

add_field_safe(grid_fc, "idx_wind", "DOUBLE")
with arcpy.da.UpdateCursor(grid_fc, [GRID_ID_FIELD, "idx_wind"]) as cur:
    for row in cur:
        val = wind_values.get(row[0])
        row[1] = wind_score(val)
        cur.updateRow(row)

# write back to the original 10km grid
add_field_safe(grid_10km, "idx_wind", "DOUBLE")
join_dict = {r[0]: r[1] for r in arcpy.da.SearchCursor(grid_fc, [GRID_ID_FIELD, "idx_wind"])}
with arcpy.da.UpdateCursor(grid_10km, [GRID_ID_FIELD, "idx_wind"], GRID_FILTER) as cur:
    for row in cur:
        row[1] = join_dict.get(row[0], 0.0)
        cur.updateRow(row)

print("Done: idx_wind")