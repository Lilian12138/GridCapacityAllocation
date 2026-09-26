from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]
import os, arcpy

road_network = os.path.join(base_folder, r"processing\gisfiles\limited_factors\road\road.shp")
grid_10km = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")
scratch_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb")
output_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb")

GRID_ID_FIELD = "NID10_INT"
GRID_FILTER = "Shengcode <> 100 AND Shengcode > 0"

arcpy.env.overwriteOutput = True
arcpy.CheckOutExtension("Spatial")
arcpy.env.workspace = scratch_gdb

# Materialize filtered land-area grid
grid_layer = "grid_layer_d"
arcpy.MakeFeatureLayer_management(grid_10km, grid_layer, GRID_FILTER)

grid_fc = os.path.join(scratch_gdb, "grid_filtered_d")
if arcpy.Exists(grid_fc):
    arcpy.management.Delete(grid_fc)
arcpy.management.CopyFeatures(grid_layer, grid_fc)

# Compute grid centroids
centroids = os.path.join(scratch_gdb, "grid_centroids_d")
if arcpy.Exists(centroids):
    arcpy.management.Delete(centroids)
arcpy.management.FeatureToPoint(grid_fc, centroids, "CENTROID")

# Nearest distance from each centroid to road network (geodesic → meters)
arcpy.analysis.Near(centroids, road_network, method="GEODESIC")

# Build distance dict (meters → km); NEAR_DIST is -1 when no near feature found
dist_dict = {}
with arcpy.da.SearchCursor(centroids, [GRID_ID_FIELD, "NEAR_DIST"]) as cur:
    for row in cur:
        fid, dist_m = row[0], row[1]
        if fid is not None and dist_m is not None and dist_m >= 0:
            dist_dict[fid] = dist_m / 1000.0

def score_distance(dist_km):
    if dist_km <= 30:
        return 1
    elif dist_km <= 40:
        return 0.8
    elif dist_km <= 50:
        return 0.6
    elif dist_km <= 100:
        return 0.4
    else:
        return 0.2

def add_field_safe(fc, field_name, field_type):
    existing = [f.name for f in arcpy.ListFields(fc)]
    if field_name not in existing:
        arcpy.management.AddField(fc, field_name, field_type)

add_field_safe(grid_10km, "idx_road", "DOUBLE")
with arcpy.da.UpdateCursor(grid_10km, [GRID_ID_FIELD, "idx_road"], GRID_FILTER) as cur:
    for row in cur:
        dist_km = dist_dict.get(row[0])
        row[1] = score_distance(dist_km) if dist_km is not None else 0
        cur.updateRow(row)

print("Done: idx_road")