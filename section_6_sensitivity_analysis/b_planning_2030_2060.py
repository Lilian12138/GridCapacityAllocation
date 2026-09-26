"""
Grid-level installed-capacity allocation by province and year.
Logic: process 2030 -> 2035 -> 2040 -> 2050 -> 2060 in order, using the previous year's result as the baseline and greedily allocating increments by score ranking.
Supports multiple score scenarios; wind is split into onshore/offshore, with offshore targets read from the Shengcode = 100 row in the planning table.
Output: write feature classes to sensitivity.gdb using scenario names.
"""

from pathlib import Path
import os
import pandas as pd

base_folder = Path(__file__).resolve().parents[3]

# Score grid (feature class in GDB)
score_path = os.path.join(
    base_folder,
    r"processing\arcprojects\MyProject1\sensitivity.gdb\CL_WGS84"
)
output_gdb = os.path.join(
    base_folder,
    r"processing\arcprojects\MyProject1\sensitivity.gdb"
)

wind_onshore_score_field = [
    'score_wind_onshore_baseline',
    'score_wind_onshore_resource',
    'score_wind_onshore_infra',
    'score_wind_onshore_terrain',
    'score_wind_onshore_equal'
]
# Offshore uses only the four configured scenario fields and excludes the unconfigured terrain score.
wind_offshore_score_field = [
    'score_wind_offshore_baseline',
    'score_wind_offshore_resource',
    'score_wind_offshore_infra',
    'score_wind_offshore_equal'
]
solar_score_field = [
    'score_solar_baseline',
    'score_solar_resource',
    'score_solar_infra',
    'score_solar_terrain',
    'score_solar_equal'
]

# Provincial planning table
planning_path = os.path.join(
    base_folder,
    r"processing\tables\Planned installed capacity.xlsx"
)
wind_sheetname = "Wind"
solar_sheetname = "Solar"

# Grid installation-potential shapefile (maximum installable capacity, KW2)
potential_wind_shp = os.path.join(
    base_folder,
    r"processing\gisfiles\GridValidArea\grid10km_wind_valid_area_statistic.shp"
)
potential_cap_wind = "cap_kw_new"  # Potential field -> renamed to KW2

potential_solar_shp = os.path.join(
    base_folder,
    r"processing\gisfiles\GridValidArea\grid10km_solar_valid_area_statistic.shp"
)
potential_cap_solar = "cap_kw"  # Potential field -> renamed to KW2

# Current grid installations (feature classes in GDB), both using the field name kw2025
current_wind_fc = os.path.join(
    base_folder,
    r"processing\arcprojects\MyProject1\installation.gdb\grid_wind_turbine_count"
)
current_solar_fc = os.path.join(
    base_folder,
    r"processing\arcprojects\MyProject1\installation.gdb\grid_solar_panel_area"
)
current_cap_field = "kw2025"  # Installed-capacity field name in both current feature classes

NID10_INT = "NID10_INT"

# Year configuration
YEARS = [2030, 2035, 2040, 2050, 2060]

# Planning-table column names for the two scenarios
PROVINCE_PLAN_COLS = [f"{y}_province" for y in YEARS]
LOWCARBON_PLAN_COLS = [f"{y}_low_carbon" for y in YEARS]

# Grid-level output column names for the two scenarios
PROV_YEAR_COLS = [f"prov_{y}" for y in YEARS]       # Province scenario
LC_YEAR_COLS = [f"lc_{y}" for y in YEARS]          # Low-carbon scenario
ALL_YEAR_COLS = ["kw2025"] + PROV_YEAR_COLS + LC_YEAR_COLS

# Fields retained in output feature classes (assembled dynamically by scenario)
BASE_OUTPUT_COLS = [NID10_INT, "Shengcode", "KW2", "kw2025"]


# ============================================================
# 2. Data loading (use arcpy to read shapefiles / feature classes)
# ============================================================
def read_feature_to_df(fc_path, fields):
    """Read a feature class / shapefile into a DataFrame using arcpy."""
    import arcpy
    all_fields = [f.name for f in arcpy.ListFields(fc_path)]
    use_fields = [f for f in fields if f in all_fields]
    data = [row for row in arcpy.da.SearchCursor(fc_path, use_fields)]
    return pd.DataFrame(data, columns=use_fields)


def ensure_nid10_int(fc_path, df):
    """
    Ensure that the DataFrame contains a long-integer NID10_INT column.
    If the source data contains only the text NID10 column, convert and rename it.
    """
    import arcpy
    all_fields = [f.name for f in arcpy.ListFields(fc_path)]

    if NID10_INT in df.columns:
        df[NID10_INT] = df[NID10_INT].astype(int)
    elif "NID10" in df.columns:
        df[NID10_INT] = df["NID10"].astype(int)
        df = df.drop(columns=["NID10"])
    return df


def load_grid_data(potential_shp, potential_field, current_fc, province_filter=None):
    """
    Read grid data and merge the potential and current-installation data sources.
    Return a DataFrame containing the following columns:
      - NID10_INT, NID50, Shengcode, KW2, kw2025
    """
    import arcpy

    pot_all_fields = [f.name for f in arcpy.ListFields(potential_shp)]
    nid_field_pot = NID10_INT if NID10_INT in pot_all_fields else "NID10"
    pot_fields = [nid_field_pot, "NID50", "Shengcode", potential_field]
    df_pot = read_feature_to_df(potential_shp, pot_fields)
    df_pot = ensure_nid10_int(potential_shp, df_pot)
    df_pot = df_pot.rename(columns={potential_field: "KW2"})
    df_pot["KW2"] = df_pot["KW2"].fillna(0)

    cur_all_fields = [f.name for f in arcpy.ListFields(current_fc)]
    nid_field_cur = NID10_INT if NID10_INT in cur_all_fields else "NID10"
    cur_fields = [nid_field_cur, current_cap_field]
    df_cur = read_feature_to_df(current_fc, cur_fields)
    df_cur = ensure_nid10_int(current_fc, df_cur)
    df_cur = df_cur.rename(columns={current_cap_field: "kw2025"})
    df_cur["kw2025"] = df_cur["kw2025"].fillna(0)

    pot_dup = df_pot[NID10_INT].duplicated().sum()
    cur_dup = df_cur[NID10_INT].duplicated().sum()
    if pot_dup > 0:
        print(f"  ⚠ Potential data contains {pot_dup} duplicate NID10_INT records; aggregating by sum")
        df_pot = df_pot.groupby([NID10_INT, "NID50", "Shengcode"], as_index=False)["KW2"].sum()
    if cur_dup > 0:
        print(f"  ⚠ Current-installation data contains {cur_dup} duplicate NID10_INT records; aggregating by sum")
        df_cur = df_cur.groupby(NID10_INT, as_index=False)["kw2025"].sum()

    df = df_pot.merge(df_cur, on=NID10_INT, how="left")
    df["kw2025"] = df["kw2025"].fillna(0)

    if province_filter is not None:
        df = df.loc[province_filter(df["Shengcode"])].copy()

    print(f"  Potential grid cells: {len(df_pot)}, current-installation grid cells: {len(df_cur)}, after merge: {len(df)}")
    return df


def load_score_data(score_fc, score_field):
    """Read scores from the score feature class for joining; use 0 if the field does not exist."""
    import arcpy
    all_fields = [f.name for f in arcpy.ListFields(score_fc)]
    nid_field = NID10_INT if NID10_INT in all_fields else "NID10"

    if score_field not in all_fields:
        print(f"  ⚠ Score field {score_field} does not exist; using 0")
        df = read_feature_to_df(score_fc, [nid_field])
        df = ensure_nid10_int(score_fc, df)
        df["Score"] = 0.0
        return df

    fields = [nid_field, score_field]
    df = read_feature_to_df(score_fc, fields)
    df = ensure_nid10_int(score_fc, df)
    df = df.rename(columns={score_field: "Score"})
    if df[NID10_INT].duplicated().any():
        df = df.groupby(NID10_INT, as_index=False)["Score"].mean()
    return df


# ============================================================
# 3. Core allocation function (incremental across years)
# ============================================================
def plan_install_multiyear(df, shengcode, kw_targets, year_cols):
    """
    Allocate installed capacity to grid cells for one province in year order.
    """
    df_prov = df.loc[df["Shengcode"] == shengcode].copy()

    if df_prov.empty:
        print(f"  ⚠ No grid cells found for province code {shengcode}; skipping")
        return df_prov

    df_prov = df_prov.sort_values(
        by=["kw2025", "Score", "KW2"], ascending=False
    ).reset_index(drop=True)

    prev_col = "kw2025"

    for year_col, kw_target_wan in zip(year_cols, kw_targets):
        kw_target = kw_target_wan * 10000
        df_prov[year_col] = df_prov[prev_col].copy()

        already = df_prov[year_col].sum()
        remain = kw_target - already

        if remain <= 0:
            print(f"  {year_col}: target {kw_target_wan:.1f} x 10,000 kW is already met by the previous year; no addition needed")
            prev_col = year_col
            continue

        allocated = 0
        for idx in df_prov.index:
            if remain <= 0:
                break
            cell_room = max(df_prov.at[idx, "KW2"] - df_prov.at[idx, year_col], 0)
            alloc = min(remain, cell_room)
            df_prov.at[idx, year_col] += alloc
            remain -= alloc
            allocated += alloc

        print(
            f"  {year_col}: target {kw_target_wan:.1f} x 10,000 kW, "
            f"added {allocated/10000:.1f} x 10,000 kW, "
            f"unallocated {max(remain,0)/10000:.1f} x 10,000 kW"
        )
        prev_col = year_col

    return df_prov


def ensure_output_gdb():
    import arcpy
    if not arcpy.Exists(output_gdb):
        arcpy.management.CreateFileGDB(os.path.dirname(output_gdb), os.path.basename(output_gdb))
        print(f"[Created] {output_gdb}")


def prepare_output_feature_class(base_fc, output_fc):
    import arcpy
    arcpy.env.overwriteOutput = True
    if arcpy.Exists(output_fc):
        arcpy.management.Delete(output_fc)
    arcpy.management.CopyFeatures(base_fc, output_fc)
    print(f"[Prepared] {output_fc}")
    return output_fc


def write_results_to_fc(final_df, output_fc, field_cols):
    import arcpy
    arcpy.env.overwriteOutput = True

    if not arcpy.Exists(output_fc):
        raise FileNotFoundError(f"输出要素类不存在: {output_fc}")

    existing_fields = [f.name for f in arcpy.ListFields(output_fc)]
    for col in field_cols:
        if col not in existing_fields:
            if col in [NID10_INT, "Shengcode"]:
                arcpy.management.AddField(output_fc, col, "LONG")
            else:
                arcpy.management.AddField(output_fc, col, "DOUBLE")

    protected_fields = {"OBJECTID", "OID", "FID", "Shape", "SHAPE", "Shape_Length", "Shape_Area"}
    keep_fields = protected_fields | {NID10_INT, "Shengcode", "KW2", "kw2025"} | set(field_cols)

    for field in arcpy.ListFields(output_fc):
        if field.name in keep_fields or field.required:
            continue
        try:
            arcpy.management.DeleteField(output_fc, field.name)
        except Exception as ex:
            print(f"  Skipping field {field.name}: {ex}")

    lookup = final_df.groupby(NID10_INT)[field_cols].first().to_dict("index")
    update_fields = [NID10_INT] + field_cols

    with arcpy.da.UpdateCursor(output_fc, update_fields) as cursor:
        for row in cursor:
            nid = row[0]
            if nid in lookup:
                values = lookup[nid]
                for i, col in enumerate(field_cols, start=1):
                    row[i] = values.get(col, 0.0)
                cursor.updateRow(row)

    print(f"[Wrote] {output_fc}")


def run_scenario(energy_type, scenario_name, score_field, pot_shp, pot_field, cur_fc, sheet_name, province_filter):
    """Run one allocation for a score scenario and output it to sensitivity.gdb."""
    print(f"\n{'=' * 60}")
    print(f"Starting allocation: {energy_type} | scenario: {scenario_name}")
    print(f"Score field: {score_field}")
    print(f"{'=' * 60}")

    print("Reading grid potential + current-installation data...")
    grid_df = load_grid_data(pot_shp, pot_field, cur_fc, province_filter=province_filter)

    print("Reading score data...")
    score_df = load_score_data(score_path, score_field)
    if "Score" in score_df.columns:
        score_df = score_df.rename(columns={"Score": score_field})
    grid_df = grid_df.merge(score_df, on=NID10_INT, how="left")
    if score_field not in grid_df.columns:
        grid_df[score_field] = 0.0
    else:
        grid_df[score_field] = grid_df[score_field].fillna(0)
    grid_df["Score"] = grid_df[score_field]

    print("Reading the planning table...")
    plan_df = pd.read_excel(planning_path, sheet_name=sheet_name)
    if province_filter is not None:
        plan_df = plan_df.loc[plan_df["Shengcode"].apply(province_filter)].copy()

    if plan_df.empty:
        print("  ⚠ No provinces meeting the conditions were found in the planning table; skipping")
        return None

    results = []
    for _, row in plan_df.iterrows():
        shengcode = row["Shengcode"]

        prov_targets = [row[col] for col in PROVINCE_PLAN_COLS]
        print(f"\nProvince: {shengcode} | Province targets (10,000 kW): {prov_targets}")
        df_prov = plan_install_multiyear(grid_df, shengcode, prov_targets, PROV_YEAR_COLS)

        lc_targets = [row[col] for col in LOWCARBON_PLAN_COLS]
        print(f"Province: {shengcode} | LowCarbon targets (10,000 kW): {lc_targets}")
        df_lc = plan_install_multiyear(grid_df, shengcode, lc_targets, LC_YEAR_COLS)

        if not df_prov.empty and not df_lc.empty:
            for col in LC_YEAR_COLS:
                df_prov[col] = df_lc[col].values
        results.append(df_prov)

    if not results:
        print("  ⚠ No results were generated; skipping")
        return None

    final_df = pd.concat(results, ignore_index=True)
    keep_cols = [c for c in BASE_OUTPUT_COLS + [score_field] + PROV_YEAR_COLS + LC_YEAR_COLS if c in final_df.columns]
    final_df = final_df[keep_cols]

    print(f"\n{'=' * 60}")
    print("Allocation result summary (10,000 kW):")
    print(f"{'=' * 60}")
    summary = final_df.groupby("Shengcode")[ALL_YEAR_COLS].sum() / 10000
    print(summary.to_string())

    total = final_df[ALL_YEAR_COLS].sum() / 10000
    print("\nNational total (10,000 kW):")
    for col in ALL_YEAR_COLS:
        print(f"  {col}: {total[col]:.1f}")

    output_name = f"{energy_type}_{scenario_name}"
    output_fc = os.path.join(output_gdb, output_name)
    prepare_output_feature_class(score_path, output_fc)
    write_results_to_fc(final_df, output_fc, keep_cols)

    summary_path = os.path.join(
        base_folder,
        rf"processing\tables\{output_name}_allocation_summary.csv"
    )
    summary.to_csv(summary_path, encoding="utf-8-sig")
    print(f"Provincial summary exported: {summary_path}")
    return final_df


# ============================================================
# 4. Batch processing: generate output feature classes by scenario
# ============================================================
def main():
    import arcpy
    ensure_output_gdb()
    arcpy.env.overwriteOutput = True

    scenario_configs = [
        ("wind_onshore", wind_onshore_score_field, potential_wind_shp, potential_cap_wind, current_wind_fc, wind_sheetname, lambda x: x != 100),
        ("wind_offshore", wind_offshore_score_field, potential_wind_shp, potential_cap_wind, current_wind_fc, wind_sheetname, lambda x: x == 100),
        ("solar", solar_score_field, potential_solar_shp, potential_cap_solar, current_solar_fc, solar_sheetname, None),
    ]

    for energy_type, score_fields, pot_shp, pot_field, cur_fc, sheet_name, province_filter in scenario_configs:
        for score_field in score_fields:
            scenario_name = score_field.rsplit("_", 1)[-1]
            run_scenario(
                energy_type=energy_type,
                scenario_name=scenario_name,
                score_field=score_field,
                pot_shp=pot_shp,
                pot_field=pot_field,
                cur_fc=cur_fc,
                sheet_name=sheet_name,
                province_filter=province_filter,
            )


if __name__ == "__main__":
    main()
    print("\n✅ All allocations complete!")
