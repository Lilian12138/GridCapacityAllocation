import arcpy
import os
from pathlib import Path
base_folder  = Path(__file__).resolve().parents[3]

# buffer road and railways
road_path = os.path.join(base_folder, r"processing\gisfiles\limited_factors\road\road.shp")
railways =  os.path.join(base_folder, r"processing\gisfiles\limited_factors\railway\railway.shp")

# intermediate temp file
roads_railways_merged = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb\roads_railways_merged")
dissolve_roads_railways = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb\dissolve_roads_railways_buffer100m")

# step 1: merge road and railways into one layer
arcpy.management.Merge(
    inputs=[road_path, railways],
    output=roads_railways_merged
)

# step 2: buffer 1000m and dissolve to single feature
arcpy.analysis.PairwiseBuffer(
    in_features=roads_railways_merged,
    out_feature_class=dissolve_roads_railways,
    buffer_distance_or_field="1000 Meters",
    dissolve_option="ALL",
    method="GEODESIC"
)

# step 3: fix geometry
arcpy.management.RepairGeometry(
    in_features=dissolve_roads_railways,
    delete_null="DELETE_NULL",
    validation_method="OGC"
)