from pathlib import Path
base_folder = Path(__file__).resolve().parents[3]

import arcpy
import os

grid_10km = os.path.join(base_folder, r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84")


# export score to shapefile
score_fields = ["score_wind_onshore", "score_wind_offshore", "score_pv_onshore"]
folder = os.path.join(base_folder, r"processing\gisfiles\score")


def build_field_mappings(input_fc, score_field):
    """Keep grid identifiers and export the selected score as a short field name."""
    existing_fields = {field.name for field in arcpy.ListFields(input_fc)}
    keep_fields = [
        field_name
        for field_name in ["NID10", "NID10_INT", "Shengcode", score_field]
        if field_name in existing_fields
    ]

    field_mappings = arcpy.FieldMappings()
    for field_name in keep_fields:
        field_map = arcpy.FieldMap()
        field_map.addInputField(input_fc, field_name)

        # A Shapefile field name can contain at most 10 characters. The output
        # file name identifies the score type, so use a common short field name.
        if field_name == score_field:
            output_field = field_map.outputField
            output_field.name = "score"
            output_field.aliasName = score_field
            field_map.outputField = output_field

        field_mappings.addFieldMap(field_map)

    return field_mappings


def export_scores(input_fc, output_folder, fields):
    """Export every non-null score field to an individual Shapefile."""
    if not arcpy.Exists(input_fc):
        raise FileNotFoundError(f"Input feature class does not exist: {input_fc}")

    existing_fields = {field.name for field in arcpy.ListFields(input_fc)}
    missing_fields = [field for field in fields if field not in existing_fields]
    if missing_fields:
        raise ValueError(
            "Score fields do not exist in the input feature class: "
            + ", ".join(missing_fields)
        )

    os.makedirs(output_folder, exist_ok=True)
    arcpy.env.overwriteOutput = True

    for score_field in fields:
        output_shp = os.path.join(output_folder, f"{score_field}.shp")
        delimited_field = arcpy.AddFieldDelimiters(input_fc, score_field)
        where_clause = f"{delimited_field} IS NOT NULL"

        arcpy.conversion.ExportFeatures(
            in_features=input_fc,
            out_features=output_shp,
            where_clause=where_clause,
            field_mapping=build_field_mappings(input_fc, score_field),
        )

        feature_count = int(arcpy.management.GetCount(output_shp)[0])
        print(f"[Done] {score_field}: {feature_count} features -> {output_shp}")


if __name__ == "__main__":
    try:
        export_scores(grid_10km, folder, score_fields)
    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))
        raise