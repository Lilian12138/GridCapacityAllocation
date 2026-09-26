from pathlib import Path

import arcpy
import os

base_folder = Path(__file__).resolve().parents[3]
arcpy.env.overwriteOutput = True

# ---------- paths ----------
wind_valid_area = os.path.join(base_folder, r"processing\gisfiles\GridValidArea\grid10km_wind_valid_area_statistic.shp")
slope_path = os.path.join(base_folder, r"processing\gisfiles\slope\chinaslope250.tif")
slope_stats = os.path.join(base_folder, r"processing\arcprojects\MyProject1\scratch.gdb\slope_zonal_stats")

# ---------- helpers ----------
def add_field_safe(fc, field_name, field_type):
    existing = {f.name for f in arcpy.ListFields(fc)}
    if field_name not in existing:
        arcpy.management.AddField(fc, field_name, field_type)


def get_joined_field_name(fc, base_name):
    """JoinField 可能将字段重命名为 MEAN_1 等，返回实际存在的字段名。"""
    fields = [f.name for f in arcpy.ListFields(fc)]
    if base_name in fields:
        return base_name
    for f in fields:
        if f.startswith(base_name):
            return f
    raise RuntimeError(f"字段 '{base_name}' 在 {fc} 中未找到")


# ---------- 1. 创建整型 zone 字段 ----------
add_field_safe(wind_valid_area, "NID10_INT", "LONG")
arcpy.management.CalculateField(wind_valid_area, "NID10_INT", "int(!NID10!)", "PYTHON3")

# ---------- 2. 坡度分区统计 ----------
arcpy.sa.ZonalStatisticsAsTable(
    wind_valid_area, "NID10_INT", slope_path, slope_stats, "DATA", "MEAN"
)

# ---------- 3. 连接 MEAN 字段 ----------
# 先检查目标 shapefile 是否已有 MEAN 字段，若有则删除，避免重命名
if "MEAN" in {f.name for f in arcpy.ListFields(wind_valid_area)}:
    arcpy.management.DeleteField(wind_valid_area, "MEAN")

arcpy.management.JoinField(wind_valid_area, "NID10_INT", slope_stats, "NID10_INT", ["MEAN"])
mean_field = get_joined_field_name(wind_valid_area, "MEAN")

# ---------- 4. 根据坡度赋装机密度 ----------
DENSITY_TABLE = [
    (0,    1.7,  6.27),
    (1.7,  3.4,  4.94),
    (3.4,  16.7, 3.89),
    (16.7, 30,   2.69),
    (30,   600,  0),
]

add_field_safe(wind_valid_area, "dens_new", "DOUBLE")

with arcpy.da.UpdateCursor(wind_valid_area, [mean_field, "dens_new"]) as cursor:
    for row in cursor:
        slope_val = row[0]
        if slope_val is None or slope_val < 0:
            row[1] = 0
        else:
            row[1] = 0  # 默认值，防止漏赋
            for low, high, d in DENSITY_TABLE:
                if low <= slope_val < high:
                    row[1] = d
                    break
        cursor.updateRow(row)

# ---------- 5. 计算装机容量 ----------
CAP_FIELD = "cap_kw_new"
add_field_safe(wind_valid_area, CAP_FIELD, "DOUBLE")

with arcpy.da.UpdateCursor(wind_valid_area, ["validareak", "dens_new", "Shengcode", CAP_FIELD]) as cursor:
    for row in cursor:
        area = row[0] if row[0] else 0
        dens = row[1] if row[1] else 0
        sheng = row[2] if row[2] is not None else -1

        if sheng == 100:
            row[3] = area * 8 * 1000
        else:
            row[3] = area * dens * 1000
        cursor.updateRow(row)

print("完成。")