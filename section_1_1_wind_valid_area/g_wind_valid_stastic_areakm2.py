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
merged_shp  = os.path.join(base_folder, r"processing\gisfiles\scratch\limitedAreasShp\wind_limited_PairwiseClip.shp")
vector_grid = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")
output_gdb  = os.path.join(base_folder, r"processing\arcprojects\MyProject1\limitedArea.gdb")
scratch_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb")

arcpy.env.overwriteOutput = True
arcpy.env.workspace = scratch_gdb

GRID_ID = "NID10"

# ---------------------------------------------------------------------------
# 0. Ensure output GDB exists
# ---------------------------------------------------------------------------
if not arcpy.Exists(output_gdb):
    arcpy.management.CreateFileGDB(os.path.dirname(output_gdb), os.path.basename(output_gdb))
    print(f"GDB created: {output_gdb}")

# Check input data
for label, path in [("Restrictive area", merged_shp), ("Grid", vector_grid)]:
    if not arcpy.Exists(path):
        raise FileNotFoundError(f"Input file does not exist [{label}]: {path}")

# ---------------------------------------------------------------------------
# 1. Intersect
# ---------------------------------------------------------------------------
intersect_out = rf"{scratch_gdb}\intersect_result"
print(f"[1/4] Intersecting...  {elapsed()}")
arcpy.analysis.Intersect([vector_grid, merged_shp], intersect_out, join_attributes="ALL")
count = int(arcpy.management.GetCount(intersect_out)[0])
print(f"[1/4] Intersect completed, total {count} intersecting features  {elapsed()}")

# ---------------------------------------------------------------------------
# 2. Calculate geodesic area
# ---------------------------------------------------------------------------
print(f"[2/4] Calculating geodesic area...  {elapsed()}")
arcpy.management.AddField(intersect_out, "area_km2", "DOUBLE")
arcpy.management.CalculateGeometryAttributes(
    intersect_out,
    [["area_km2", "AREA_GEODESIC"]],
    area_unit="SQUARE_KILOMETERS"
)

# ---------------------------------------------------------------------------
# 3. Summarize area by grid ID
# ---------------------------------------------------------------------------
summary_out = rf"{scratch_gdb}\summary_result"
print(f"[3/4] Summarizing area by grid ID...  {elapsed()}")
arcpy.analysis.Statistics(
    intersect_out,
    summary_out,
    statistics_fields=[["area_km2", "SUM"]],
    case_field=GRID_ID
)
sum_field = "SUM_area_km2"

# ---------------------------------------------------------------------------
# 4. Copy grid, join summary results, fill nulls with 0
# ---------------------------------------------------------------------------
output_fc = rf"{output_gdb}\grid_limited_area"
print(f"[4/4] Copying grid and joining summary results...  {elapsed()}")
arcpy.management.CopyFeatures(vector_grid, output_fc)
arcpy.management.JoinField(
    in_data=output_fc,
    in_field=GRID_ID,
    join_table=summary_out,
    join_field=GRID_ID,
    fields=[sum_field]
)

with arcpy.da.UpdateCursor(output_fc, [sum_field]) as cursor:
    for row in cursor:
        if row[0] is None:
            row[0] = 0
            cursor.updateRow(row)

# ---------------------------------------------------------------------------
# 5. Summary statistics
# ---------------------------------------------------------------------------
total_grid = int(arcpy.management.GetCount(output_fc)[0])

with arcpy.da.SearchCursor(output_fc, [sum_field]) as cursor:
    values = [row[0] for row in cursor if row[0] and row[0] > 0]

cnt_limited   = len(values)
total_limited = sum(values) if values else 0.0
avg_limited   = total_limited / cnt_limited if cnt_limited else 0.0
max_limited   = max(values) if values else 0.0

print(f"\n{'=' * 52}")
print(f"  Output path:           {output_fc}")
print(f"  Total grid count:           {total_grid}")
print(f"  Grid count with limitations:     {cnt_limited}")
print(f"{'─' * 52}")
print(f"  {'category':<14}  {'area':>12}")
print(f"{'─' * 52}")
print(f"  {'Total limited area':<14}  {total_limited:>10.2f} km2")
print(f"  {'Average limited grid':<14}  {avg_limited:>10.2f} km2")
print(f"  {'Maximum limited grid':<14}  {max_limited:>10.2f} km2")
print(f"{'=' * 52}")
print(f"  Total time: {elapsed()}")