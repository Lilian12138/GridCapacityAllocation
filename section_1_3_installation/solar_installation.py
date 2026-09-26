from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]

import arcpy
import os
import pandas as pd
import numpy as np

arcpy.env.overwriteOutput = True


def add_field_safe(fc, field_name, field_type):
    existing = [f.name for f in arcpy.ListFields(fc)]
    if field_name not in existing:
        arcpy.management.AddField(fc, field_name, field_type)


solar_valid_area = os.path.join(base_folder, r"processing\gisfiles\GridValidArea\grid10km_solar_valid_area_statistic.shp")
solar_density = os.path.join(base_folder, r"processing\tables\wind_solar_capacity_density.xlsx")

add_field_safe(solar_valid_area, "NID10_INT", "LONG")
arcpy.management.CalculateField(solar_valid_area, "NID10_INT", "int(!NID10!)", "PYTHON3")

# DEM and slope
dem = os.path.join(base_folder, r"processing\gisfiles\DEM\chinadem250.tif")
slope = os.path.join(base_folder, r"processing\gisfiles\slope\chinaslope250.tif")

scratch_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb")

# Mean slope
slope_stats = os.path.join(scratch_gdb, "solar_slope_stats")
arcpy.sa.ZonalStatisticsAsTable(solar_valid_area, "NID10_INT", slope, slope_stats, "DATA", "MEAN")
arcpy.management.JoinField(solar_valid_area, "NID10_INT", slope_stats, "NID10_INT", ["MEAN"])
add_field_safe(solar_valid_area, "slope_mean", "DOUBLE")
arcpy.management.CalculateField(solar_valid_area, "slope_mean", "!MEAN!", "PYTHON3")
arcpy.management.DeleteField(solar_valid_area, "MEAN")

# Relief (elevation range)
relief_stats = os.path.join(scratch_gdb, "solar_relief_stats")
arcpy.sa.ZonalStatisticsAsTable(solar_valid_area, "NID10_INT", dem, relief_stats, "DATA", "RANGE")
arcpy.management.JoinField(solar_valid_area, "NID10_INT", relief_stats, "NID10_INT", ["RANGE"])
add_field_safe(solar_valid_area, "relief", "DOUBLE")
arcpy.management.CalculateField(solar_valid_area, "relief", "!RANGE!", "PYTHON3")
arcpy.management.DeleteField(solar_valid_area, "RANGE")

# Terrain classification
add_field_safe(solar_valid_area, "terrain", "SHORT")

with arcpy.da.UpdateCursor(solar_valid_area, ["slope_mean", "relief", "terrain", "Shengcode"]) as cursor:
    for row in cursor:
        shengcode = row[3]
        if shengcode == 100:
            row[2] = 1
        else:
            s = row[0] if row[0] is not None else 0
            r = row[1] if row[1] is not None else 0
            if s <= 3:
                row[2] = 1
            elif s <= 20:
                if r < 200:
                    row[2] = 2
                else:
                    row[2] = 3
            elif s < 30:
                row[2] = 3
            else:
                row[2] = 0  # Exclude only areas with slopes of 30 degrees or more
        cursor.updateRow(row)

# Read the density table and build interpolation lookup tables by terrain type
solar_density_df = pd.read_excel(solar_density, sheet_name="solar_sel")
density_lookup = {}
for t in [1, 2, 3]:
    sub = solar_density_df[solar_density_df["terrain type"] == t].sort_values("latitude")
    density_lookup[t] = {
        "lat": sub["latitude"].values,
        "density": sub["110KV(kw/km2)"].values
    }

# Capacity density interpolation
add_field_safe(solar_valid_area, "cap_dens", "DOUBLE")

with arcpy.da.UpdateCursor(solar_valid_area, ["terrain", "SHAPE@", "cap_dens"]) as cursor:
    for row in cursor:
        terrain = row[0]
        lat = abs(row[1].centroid.Y)

        if terrain == 0 or terrain not in density_lookup:
            row[2] = 0
        else:
            lk = density_lookup[terrain]
            density = np.interp(lat, lk["lat"], lk["density"])
            row[2] = density
        cursor.updateRow(row)

# Calculate installed capacity (kW) = capacity density (kW/km²) × valid area (km²)
add_field_safe(solar_valid_area, "cap_kw", "DOUBLE")
with arcpy.da.UpdateCursor(solar_valid_area, ["cap_dens", "validArea", "cap_kw"]) as cursor:
    for row in cursor:
        density = row[0] if row[0] else 0
        area = row[1] if row[1] else 0
        row[2] = density * area
        cursor.updateRow(row)
