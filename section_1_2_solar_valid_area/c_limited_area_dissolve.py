from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]

import os
import time
import arcpy

t0 = time.time()
def elapsed():
    return f"{time.time() - t0:.1f}s"

# ---------------------------------------------------------------------------
# Input files
# ---------------------------------------------------------------------------
path_list = [
    r"processing\gisfiles\scratch\limitedAreasShp\slope_above_30.shp",
    r"pprocessing\gisfiles\limited_factors\water\water.shp",
    r"processing\gisfiles\limited_factors\nature_area\natureArea.shp",
    r"processing\gisfiles\scratch\limitedAreasShp\windTurbine_points_buffer500m_singparts.shp",
    r"processing\gisfiles\wind_solar_distribution_202605\solar_panel.shp",
    r"processing\gisfiles\scratch\limitedAreasShp\dem_above_4500m.shp",
    r"processing\gisfiles\scratch\limitedAreasShp\dissolve_roads_railways_buffer1000m.shp",
    r"processing\gisfiles\scratch\limitedAreasShp\GHI_yr_365p25_mask_1000kwhm2.shp",
]

# ---------------------------------------------------------------------------
# Output files
# ---------------------------------------------------------------------------
output_folder = os.path.join(base_folder, r"processing\gisfiles\scratch\limitedAreasShp")
output_path = os.path.join(output_folder, "solar_limited_areas_dissolved.shp")
os.makedirs(output_folder, exist_ok=True)

arcpy.env.overwriteOutput = True

# ---------------------------------------------------------------------------
# Check input files, use the first valid file's coordinate system as reference
# ---------------------------------------------------------------------------
valid_inputs = []
for p in path_list:
    full_path = os.path.join(base_folder, p)
    if arcpy.Exists(full_path):
        valid_inputs.append(full_path)
        print(f"[Found] {os.path.basename(full_path)}")
    else:
        print(f"[Skipped] File not found: {full_path}")

if not valid_inputs:
    print("No input files found. Exiting.")
else:
    arcpy.env.outputCoordinateSystem = arcpy.Describe(valid_inputs[0]).spatialReference

    # Step 1: Merge all layers into memory (avoid writing temporary disk files)
    merged = r"in_memory\temp_merged"
    print(f"\nMerging {len(valid_inputs)} layers...  {elapsed()}")
    arcpy.management.Merge(valid_inputs, merged)
    print(f"Merge complete  {elapsed()}")

    # Step 2: Dissolve into a single MultiPolygon feature
    print(f"Starting dissolve...  {elapsed()}")
    arcpy.management.Dissolve(merged, output_path, multi_part="MULTI_PART")
    print(f"Dissolve complete  {elapsed()}")

    arcpy.management.Delete(merged)
    print(f"\nOutput file: {output_path}  Total elapsed time: {elapsed()}")
