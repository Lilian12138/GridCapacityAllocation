## valid area of ghi less than 1000kwh/m2, output as polygon shapefile
from pathlib import Path
base_folder  = Path(__file__).resolve().parents[3]

import os
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

dem_path     = os.path.join(base_folder, r"processing\gisfiles\GHI\GHI_yr_365p25.tif")
mask_path    = os.path.join(base_folder, r"processing\gisfiles\scratch\GHI_yr_365p25_mask_1000kwhm2.tif")
polygon_path = os.path.join(base_folder, r"processing\gisfiles\scratch\limitedAreasShp\GHI_yr_365p25_mask_1000kwhm2.shp")

THRESHOLD = 1000

# ---------- 1. Threshold extraction, write out 0/1 mask raster ----------
src = gdal.Open(dem_path)
band = src.GetRasterBand(1)
xsize, ysize = src.RasterXSize, src.RasterYSize

driver = gdal.GetDriverByName("GTiff")
dst = driver.Create(
    mask_path, xsize, ysize, 1, gdal.GDT_Byte,
    options=["COMPRESS=LZW", "TILED=YES"]
)
dst.SetGeoTransform(src.GetGeoTransform())
dst.SetProjection(src.GetProjection())
dst_band = dst.GetRasterBand(1)
dst_band.SetNoDataValue(0)

# Read/write block by block to avoid loading 700 million pixels into memory at once
block_y = 512
import numpy as np
for y in range(0, ysize, block_y):
    rows = min(block_y, ysize - y)
    arr = band.ReadAsArray(0, y, xsize, rows)
    mask = (arr <= THRESHOLD).astype("uint8")  # <=1000 -> 1, others -> 0
    dst_band.WriteArray(mask, 0, y)

dst_band.FlushCache()
dst = None
src = None
print("Threshold raster written:", mask_path)

# ---------- 2. Vectorization (only vectorize areas with value 1) ----------
mask_ds = gdal.Open(mask_path)
mask_band = mask_ds.GetRasterBand(1)

srs = osr.SpatialReference()
srs.ImportFromWkt(mask_ds.GetProjection())

shp_driver = ogr.GetDriverByName("ESRI Shapefile")
if os.path.exists(polygon_path):
    shp_driver.DeleteDataSource(polygon_path)
out_ds = shp_driver.CreateDataSource(polygon_path)
layer = out_ds.CreateLayer("GHI_yr_365p25_mask_1000kwhm2", srs=srs, geom_type=ogr.wkbPolygon)
layer.CreateField(ogr.FieldDefn("value", ogr.OFTInteger))

# Use mask_band itself as the mask, so NoData(0) will not be vectorized
gdal.Polygonize(mask_band, mask_band, layer, 0, [], callback=None)

out_ds = None
mask_ds = None
print("Vectorization done:", polygon_path)