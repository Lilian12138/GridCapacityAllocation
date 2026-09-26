from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]
import os
os.environ['GDAL_DATA'] = r'D:\installs\ArcGIS\Pro\Resources\pedata\gdaldata'
import arcpy

wind_installation = os.path.join(base_folder, r"processing\gisfiles\GridValidArea\grid10km_wind_valid_area_statistic.shp")
grid_10km = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")

scratch_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb")
output_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb")

GRID_ID_FIELD = "NID10_INT"
GRID_FILTER = "Shengcode = 100"

cap_kw = "cap_kw_new"

# Step 1: Read cap_kw for land-area cells from wind_installation shapefile
cap_dict = {}
with arcpy.da.SearchCursor(wind_installation, [GRID_ID_FIELD, cap_kw], GRID_FILTER) as cur:
    for row in cur:
        fid, val = row[0], row[1]
        if fid is not None and val is not None:
            cap_dict[fid] = val

# Step 2: Min-max normalize across land-area cells
valid_vals = list(cap_dict.values())
min_val = min(valid_vals)
max_val = max(valid_vals)
val_range = max_val - min_val

# Step 3: Multiply normalized value by 5 and write to grid_10km as off_idx_install
def add_field_safe(fc, field_name, field_type):
    existing = [f.name for f in arcpy.ListFields(fc)]
    if field_name not in existing:
        arcpy.management.AddField(fc, field_name, field_type)

add_field_safe(grid_10km, "off_idx_install", "DOUBLE")
with arcpy.da.UpdateCursor(grid_10km, [GRID_ID_FIELD, "off_idx_install"], GRID_FILTER) as cur:
    for row in cur:
        val = cap_dict.get(row[0])
        row[1] = (val - min_val) / val_range if val is not None and val_range > 0 else 0.0
        cur.updateRow(row)

print("Done: off_idx_install")
