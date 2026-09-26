from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]

import arcpy
import os

wind_turbines_path = os.path.join(base_folder, r"processing\gisfiles\wind_solar_distribution_202605\windturbines.shp")
solar_panel_path = os.path.join(base_folder, r"processing\gisfiles\wind_solar_distribution_202605\solar_panel.shp")
grid_10km = os.path.join(base_folder, r"processing\gisfiles\limited_factors\RedlandGrid10km\CL_WGS84.shp")
scratch_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb")
installation_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\installation.gdb")

arcpy.env.overwriteOutput = True

# ---------- a. Count wind turbines in each grid cell ----------

wind_output = os.path.join(installation_gdb, "grid_wind_turbine_count")

arcpy.analysis.SpatialJoin(
    target_features=grid_10km,
    join_features=wind_turbines_path,
    out_feature_class=wind_output,
    join_operation="JOIN_ONE_TO_ONE",
    join_type="KEEP_ALL",
    match_option="CONTAINS"
)
# SpatialJoin creates the Join_Count field by default, representing the number of wind turbines in each grid cell
# Rename the field for clarity
arcpy.management.AlterField(wind_output, "Join_Count", "Wind_Turbine_Count", "Wind_Turbine_Count")

print("Wind turbine count statistics complete ->", wind_output)

# ---------- b. Calculate the solar panel area (m²) in each grid cell ----------

# First calculate an area field for solar_panel (project to an equal-area coordinate system to calculate m²)
# Add the area field
arcpy.management.AddField(solar_panel_path, "Area_m2", "DOUBLE")

# With WGS84 data, geometry area defaults to degrees, so the unit must be specified
# Use CalculateGeometryAttributes to calculate in m²
arcpy.management.CalculateGeometryAttributes(
    solar_panel_path,
    [["Area_m2", "AREA_GEODESIC"]],
    area_unit="SQUARE_METERS"
)

solar_output = os.path.join(installation_gdb, "grid_solar_panel_area")

# Spatial join and sum Area_m2
field_mappings = arcpy.FieldMappings()
field_mappings.addTable(grid_10km)
field_mappings.addTable(solar_panel_path)

# Find the Area_m2 field and set its merge rule to Sum
area_idx = field_mappings.findFieldMapIndex("Area_m2")
area_fm = field_mappings.getFieldMap(area_idx)
area_fm.mergeRule = "Sum"
field_mappings.replaceFieldMap(area_idx, area_fm)

arcpy.analysis.SpatialJoin(
    target_features=grid_10km,
    join_features=solar_panel_path,
    out_feature_class=solar_output,
    join_operation="JOIN_ONE_TO_ONE",
    join_type="KEEP_ALL",
    field_mapping=field_mappings,
    match_option="CONTAINS"
)

# Rename the field
arcpy.management.AlterField(solar_output, "Area_m2", "Solar_Area_m2", "Solar_Area_m2")

print("Solar panel area statistics complete ->", solar_output)
