
from pathlib import Path
base_folder  = Path(__file__).resolve().parents[3]

import arcpy
import os
arcpy.env.overwriteOutput = True
arcpy.management.ClearWorkspaceCache()

# buffer wind turbine points
windTurbine_points = os.path.join(base_folder, r"processing\gisfiles\wind_solar_distribution_202605\windturbines.shp")
windTurbine_points_buffer = os.path.join(base_folder, r"processing\arcprojects\MyProject1\limitedArea.gdb\windTurbine_points_buffer500m")

# 1. Buffer
arcpy.analysis.PairwiseBuffer(
    windTurbine_points,
    windTurbine_points_buffer,
    "500 Meters",
    dissolve_option="ALL",
    method="GEODESIC"
)

# 2. Multipart to singlepart
buffer_singlepart = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb\windTurbine_points_buffer500m_singparts")
arcpy.management.MultipartToSinglepart(
    in_features=windTurbine_points_buffer,
    out_feature_class=buffer_singlepart
)

# 3. Repair geometry
arcpy.management.RepairGeometry(
    in_features=buffer_singlepart,
    delete_null="DELETE_NULL",
    validation_method="OGC"
)

# 4. Add unique ID (creates field via field_type, no separate AddField needed)
arcpy.management.CalculateField(
    buffer_singlepart, "ID", "!OBJECTID!", "PYTHON3", field_type="LONG"
)