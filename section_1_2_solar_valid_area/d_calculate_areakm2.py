from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]

import arcpy
import os
import time

t0 = time.time()
def elapsed():
    return f"{time.time() - t0:.1f}s"

# ---------------------------------------------------------------------------
# Path configuration
# ---------------------------------------------------------------------------
limited_shp     = os.path.join(base_folder, r"processing\gisfiles\scratch\limitedAreasShp\solar_limited_areas_dissolved_clip.shp")
residential_shp = os.path.join(base_folder, r"processing\gisfiles\limited_factors\residental_area\buildingupArea.shp")
vector_grid     = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")
output_gdb      = os.path.join(base_folder, r"processing\arcprojects\MyProject1\limitedArea.gdb")
scratch_gdb     = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb")

arcpy.env.overwriteOutput = True
arcpy.env.workspace = scratch_gdb

GRID_ID = "NID10"

# ---------------------------------------------------------------------------
# 0. Ensure the output GDB exists
# ---------------------------------------------------------------------------
if not arcpy.Exists(output_gdb):
    arcpy.management.CreateFileGDB(os.path.dirname(output_gdb), os.path.basename(output_gdb))
    print(f"GDB created: {output_gdb}")

# Check input data
for label, path in [("restricted area", limited_shp), ("residential area", residential_shp), ("grid", vector_grid)]:
    if not arcpy.Exists(path):
        raise FileNotFoundError(f"Input file not found [{label}]: {path}")

# ---------------------------------------------------------------------------
# Preparation: convert input shp files to GDB format
#   Reason: Merge/Append on shp files with differing schemas often raises
#           "Error in reading table"; GDB format reads more reliably and
#           Intersect runs faster on large datasets.
# ---------------------------------------------------------------------------
print(f"[Prep] Converting input shp files to GDB format...  {elapsed()}")
limited_fc  = rf"{scratch_gdb}\limited_fc"
resident_fc = rf"{scratch_gdb}\resident_fc"
arcpy.conversion.FeatureClassToFeatureClass(limited_shp,     scratch_gdb, "limited_fc")
arcpy.conversion.FeatureClassToFeatureClass(residential_shp, scratch_gdb, "resident_fc")
print(f"[Prep] Conversion complete  {elapsed()}")

# ---------------------------------------------------------------------------
# 1. Copy the grid and calculate the total area of each cell
# ---------------------------------------------------------------------------
output_fc = rf"{output_gdb}\solar_grid_area_stats"
print(f"[1/5] Copying grid and calculating cell total area...  {elapsed()}")
arcpy.management.CopyFeatures(vector_grid, output_fc)
arcpy.management.AddField(output_fc, "grid_km2", "DOUBLE")
arcpy.management.CalculateGeometryAttributes(
    output_fc, [["grid_km2", "AREA_GEODESIC"]], area_unit="SQUARE_KILOMETERS"
)

# ---------------------------------------------------------------------------
# Helper function: overlay -> geodesic area -> summarize by grid -> join to output_fc
# tag distinguishes the scratch intermediate tables; result_field is the
# final field name written to output_fc
# ---------------------------------------------------------------------------
def area_by_grid(overlay_fc, result_field, tag):
    isect  = rf"{scratch_gdb}\isect_{tag}"
    sumtbl = rf"{scratch_gdb}\sumtbl_{tag}"

    arcpy.analysis.Intersect([vector_grid, overlay_fc], isect, join_attributes="ALL")
    arcpy.management.AddField(isect, "atmp", "DOUBLE")
    arcpy.management.CalculateGeometryAttributes(
        isect, [["atmp", "AREA_GEODESIC"]], area_unit="SQUARE_KILOMETERS"
    )
    arcpy.analysis.Statistics(isect, sumtbl, [["atmp", "SUM"]], case_field=GRID_ID)

    arcpy.management.JoinField(output_fc, GRID_ID, sumtbl, GRID_ID, ["SUM_atmp"])
    arcpy.management.AlterField(output_fc, "SUM_atmp", result_field, result_field)

    with arcpy.da.UpdateCursor(output_fc, [result_field]) as cur:
        for row in cur:
            if row[0] is None:
                row[0] = 0.0
                cur.updateRow(row)

    arcpy.management.Delete(isect)
    arcpy.management.Delete(sumtbl)

# ---------------------------------------------------------------------------
# 2. Restricted (non-developable) area (merged/dissolved restriction factors)
# ---------------------------------------------------------------------------
print(f"[2/5] Calculating restricted area per grid cell...  {elapsed()}")
area_by_grid(limited_fc, "limited_km2", "lim")

# ---------------------------------------------------------------------------
# 3. Residential area
# ---------------------------------------------------------------------------
print(f"[3/5] Calculating residential area per grid cell...  {elapsed()}")
area_by_grid(resident_fc, "resident_km2", "res")

# ---------------------------------------------------------------------------
# 4. valid area calculation
# valid_km2 = grid_km2 - limited_km2 - resident_km2 × 75%
# ---------------------------------------------------------------------------
print(f"[4/5] valid area calcaulation...  {elapsed()}")
arcpy.management.AddField(output_fc, "valid_km2", "DOUBLE")
arcpy.management.CalculateField(
    output_fc, "valid_km2",
    "max(!grid_km2! - !limited_km2! - (!resident_km2! * 0.75), 0)",
    "PYTHON3"
)

# ---------------------------------------------------------------------------
# 5. Summary statistics
# ---------------------------------------------------------------------------
print(f"[5/5] Summarizing statistics...  {elapsed()}")

stat_fields = ["grid_km2", "limited_km2", "resident_km2", "valid_km2"]
totals = {f: 0.0 for f in stat_fields}
cnt_limited = cnt_resident = cnt_valid = 0
total_grid  = int(arcpy.management.GetCount(output_fc)[0])

with arcpy.da.SearchCursor(output_fc, stat_fields) as cur:
    for row in cur:
        for i, f in enumerate(stat_fields):
            if row[i]:
                totals[f] += row[i]
        if row[1] and row[1] > 0: cnt_limited  += 1
        if row[2] and row[2] > 0: cnt_resident += 1
        if row[3] and row[3] > 0: cnt_valid += 1

ratio = totals["valid_km2"] / totals["grid_km2"] * 100 if totals["grid_km2"] else 0

print(f"\n{'=' * 52}")
print(f"  Output path:              {output_fc}")
print(f"  Total grid cells:         {total_grid}")
print(f"  Cells with restricted area:   {cnt_limited}")
print(f"  Cells with residential area:  {cnt_resident}")
print(f"  Cells with developable area:  {cnt_valid}")
print(f"{'─' * 52}")
print(f"  {'Category':<14}  {'Area':>12}")
print(f"{'─' * 52}")
print(f"  {'Grid total':<14}  {totals['grid_km2']:>10.2f} km2")
print(f"  {'Restricted':<14}  {totals['limited_km2']:>10.2f} km2")
print(f"  {'Residential':<14}  {totals['resident_km2']:>10.2f} km2")
print(f"  {'Developable':<14}  {totals['valid_km2']:>10.2f} km2")
print(f"{'─' * 52}")
print(f"  Developable ratio:        {ratio:.1f}%")
print(f"{'=' * 52}")
print(f"  Total elapsed time: {elapsed()}")