# ===== step_a_terrain.py =====
from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]
import arcpy, os

grid_10km = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")
k3_classes = os.path.join(base_folder, r"processing\gisfiles\limited_factors\k3classes\k3classes_fill_clip.tif")
elevation = os.path.join(base_folder, r"processing\gisfiles\DEM\chinadem250.tif")

scratch_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb")
output_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb")

GRID_ID_FIELD = "NID10_INT"
def add_field_safe(fc, field_name, field_type):
    existing = [f.name for f in arcpy.ListFields(fc)]
    if field_name not in existing:
        arcpy.management.AddField(fc, field_name, field_type)

add_field_safe(grid_10km, GRID_ID_FIELD, "LONG")
arcpy.management.CalculateField(grid_10km, GRID_ID_FIELD, "int(!NID10!)", "PYTHON3")

GRID_FILTER = "Shengcode <> 100 AND Shengcode > 0"
with arcpy.da.SearchCursor(grid_10km, ["NID10"], GRID_FILTER) as cur:
    sample = [r[0] for r in cur][:5]
print(sample)


arcpy.env.overwriteOutput = True
arcpy.CheckOutExtension("Spatial")
arcpy.env.workspace = scratch_gdb

grid_layer = "grid_layer"
arcpy.MakeFeatureLayer_management(grid_10km, grid_layer, GRID_FILTER)

# Materialize the filtered layer to disk — ZonalStatisticsAsTable fails on
# in-memory feature layers when running standalone outside ArcGIS Pro.
grid_fc = os.path.join(scratch_gdb, "grid_filtered")
if arcpy.Exists(grid_fc):
    arcpy.management.Delete(grid_fc)
arcpy.management.CopyFeatures(grid_layer, grid_fc)

# Zonal majority k3
k3_table = os.path.join(scratch_gdb, "k3_zonal")
# if arcpy.Exists(k3_table):
#     arcpy.management.Delete(k3_table)
# arcpy.sa.ZonalStatisticsAsTable(grid_fc, GRID_ID_FIELD, k3_classes, k3_table, "DATA", "MAJORITY")

# # Zonal mean elevation
elev_table = os.path.join(scratch_gdb, "elev_zonal")
# if arcpy.Exists(elev_table):
#     arcpy.management.Delete(elev_table)
# arcpy.sa.ZonalStatisticsAsTable(grid_fc, GRID_ID_FIELD, elevation, elev_table, "DATA", "MEAN")

# Centroids + point extraction as fallback
centroids = os.path.join(scratch_gdb, "grid_centroids")
arcpy.FeatureToPoint_management(grid_fc, centroids, "CENTROID")
arcpy.sa.ExtractMultiValuesToPoints(centroids, [[k3_classes, "k3_pt"], [elevation, "elev_pt"]])

# Build dicts
k3_pt_dict = {}
elev_pt_dict = {}
with arcpy.da.SearchCursor(centroids, [GRID_ID_FIELD, "k3_pt", "elev_pt"]) as cur:
    for r in cur:
        k3_pt_dict[r[0]] = r[1]
        elev_pt_dict[r[0]] = r[2]

k3_zonal_dict = {r[0]: r[1] for r in arcpy.da.SearchCursor(k3_table, [GRID_ID_FIELD, "MAJORITY"])}
elev_zonal_dict = {r[0]: r[1] for r in arcpy.da.SearchCursor(elev_table, [GRID_ID_FIELD, "MEAN"])}

# Score
add_field_safe(grid_fc, "idx_terrain", "DOUBLE")
with arcpy.da.UpdateCursor(grid_fc, [GRID_ID_FIELD, "idx_terrain"]) as cur:
    for row in cur:
        fid = row[0]
        majority = k3_zonal_dict.get(fid)
        if majority is None:
            majority = k3_pt_dict.get(fid)
        elev_mean = elev_zonal_dict.get(fid)
        if elev_mean is None:
            elev_mean = elev_pt_dict.get(fid)

        if elev_mean is None and majority is None:
            row[1] = 0
        elif elev_mean is None or elev_mean > 4000:
            row[1] = 0
        elif majority in (31, 32):
            row[1] = 0
        elif majority == 0:
            row[1] = 1
        elif majority == 26:
            row[1] = 0.8
        elif majority == 27:
            row[1] = 0.6
        else:
            row[1] = 0.6
        cur.updateRow(row)

add_field_safe(grid_10km, "idx_terrain", "DOUBLE")
join_dict = {r[0]: r[1] for r in arcpy.da.SearchCursor(grid_fc, [GRID_ID_FIELD, "idx_terrain"])}
with arcpy.da.UpdateCursor(grid_10km, [GRID_ID_FIELD, "idx_terrain"], GRID_FILTER) as cur:
    for row in cur:
        row[1] = join_dict.get(row[0], 0.0)
        cur.updateRow(row)

print("Done: idx_terrain written back to CL_WGS84")