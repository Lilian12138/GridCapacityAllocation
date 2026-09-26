"""
Grid-level installed-capacity allocation by province and year.
Logic: process 2030 -> 2035 -> 2040 -> 2050 -> 2060 in order, using the previous year's result as the baseline and greedily allocating increments by score ranking.
Output columns: NID50, NID10_INT, Shengcode, kw2025, kw2030, kw2035, kw2040, kw2050, kw2060
"""

from pathlib import Path
import os
import pandas as pd
import numpy as np

# ============================================================
# 1. Path configuration (consistent with the original code)
# ============================================================
base_folder = Path(__file__).resolve().parents[3]

# Score grid (feature class in GDB)
score_path = os.path.join(
    base_folder,
    r"processing\arcprojects\MyProject1\MyProject1.gdb\CL_WGS84"
)
onshore_wind_score = "score_wind_onshore"
offshore_wind_score = "score_wind_offshore"
onshore_solar_score = "score_pv_onshore"

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
LC_YEAR_COLS   = [f"lc_{y}" for y in YEARS]         # Low-carbon scenario
ALL_YEAR_COLS  = ["kw2025"] + PROV_YEAR_COLS + LC_YEAR_COLS

# Final output columns to retain
OUTPUT_COLS = ["NID50", NID10_INT, "Shengcode"] + ALL_YEAR_COLS


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
        # NID10_INT already exists; ensure it is an integer
        df[NID10_INT] = df[NID10_INT].astype(int)
    elif "NID10" in df.columns:
        # Only NID10 exists; convert it to an integer and rename it
        df[NID10_INT] = df["NID10"].astype(int)
        df = df.drop(columns=["NID10"])
    return df


def load_grid_data(potential_shp, potential_field, current_fc):
    """
    Read grid data and merge the potential and current-installation data sources.
    Return a DataFrame containing the following columns:
      - NID10_INT, NID50, Shengcode, KW2, kw2025
    """
    # Read potential data (including NID50), preferring NID10_INT and falling back to NID10
    import arcpy
    pot_all_fields = [f.name for f in arcpy.ListFields(potential_shp)]
    nid_field_pot = NID10_INT if NID10_INT in pot_all_fields else "NID10"
    pot_fields = [nid_field_pot, "NID50", "Shengcode", potential_field]
    df_pot = read_feature_to_df(potential_shp, pot_fields)
    df_pot = ensure_nid10_int(potential_shp, df_pot)
    df_pot = df_pot.rename(columns={potential_field: "KW2"})
    df_pot["KW2"] = df_pot["KW2"].fillna(0)

    # Read current installed-capacity data, preferring NID10_INT and falling back to NID10
    cur_all_fields = [f.name for f in arcpy.ListFields(current_fc)]
    nid_field_cur = NID10_INT if NID10_INT in cur_all_fields else "NID10"
    cur_fields = [nid_field_cur, current_cap_field]
    df_cur = read_feature_to_df(current_fc, cur_fields)
    df_cur = ensure_nid10_int(current_fc, df_cur)
    df_cur = df_cur.rename(columns={current_cap_field: "kw2025"})
    df_cur["kw2025"] = df_cur["kw2025"].fillna(0)

    # Check for duplicates: aggregate duplicate NID10_INT values by summation
    pot_dup = df_pot[NID10_INT].duplicated().sum()
    cur_dup = df_cur[NID10_INT].duplicated().sum()
    if pot_dup > 0:
        print(f"  ⚠ Potential data contains {pot_dup} duplicate NID10_INT records; aggregating by sum")
        df_pot = df_pot.groupby([NID10_INT, "NID50", "Shengcode"], as_index=False)["KW2"].sum()
    if cur_dup > 0:
        print(f"  ⚠ Current-installation data contains {cur_dup} duplicate NID10_INT records; aggregating by sum")
        df_cur = df_cur.groupby(NID10_INT, as_index=False)["kw2025"].sum()

    # Merge: use the potential table as the base and left-join current installations
    df = df_pot.merge(df_cur, on=NID10_INT, how="left")
    df["kw2025"] = df["kw2025"].fillna(0)

    print(f"  Potential grid cells: {len(df_pot)}, current-installation grid cells: {len(df_cur)}, after merge: {len(df)}")

    return df


def load_score_data(score_fc, score_field):
    """Read scores from the score feature class for joining."""
    import arcpy
    all_fields = [f.name for f in arcpy.ListFields(score_fc)]
    nid_field = NID10_INT if NID10_INT in all_fields else "NID10"
    fields = [nid_field, score_field]
    df = read_feature_to_df(score_fc, fields)
    df = ensure_nid10_int(score_fc, df)
    df = df.rename(columns={score_field: "Score"})
    # Deduplicate by taking the mean of duplicate values
    if df[NID10_INT].duplicated().any():
        df = df.groupby(NID10_INT, as_index=False)["Score"].mean()
    return df


# ============================================================
# 3. Core allocation function (incremental across years)
# ============================================================
def plan_install_multiyear(df, shengcode, kw_targets, year_cols):
    """
    Allocate installed capacity to grid cells for one province in year order.

    Parameters:
        df         : DataFrame containing all grid cells for this energy type
        shengcode  : Province code
        kw_targets : List of provincial planning targets by year, in 10,000 kW
        year_cols  : List of corresponding output columns ['kw2030','kw2035','kw2040','kw2060']

    Returns:
        The allocated DataFrame for the province, including all year columns
    """
    df_prov = df.loc[df["Shengcode"] == shengcode].copy()

    if df_prov.empty:
        print(f"  ⚠ No grid cells found for province code {shengcode}; skipping")
        return df_prov

    # Sort by current installations, score, and maximum capacity in descending order (prioritize high-scoring grid cells)
    df_prov = df_prov.sort_values(
        by=["kw2025", "Score", "KW2"], ascending=False
    ).reset_index(drop=True)

    prev_col = "kw2025"  # Starting column: current installed capacity

    for year_col, kw_target_wan in zip(year_cols, kw_targets):
        kw_target = kw_target_wan * 10000  # 10,000 kW -> kW

        # Use the previous year's result as the baseline
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


# ============================================================
# 4. Batch processing: all provinces x all years
# ============================================================
def allocate_by_plan(df, plan_df, score_field, label):
    """Allocate by province and score field, returning a list of results."""
    print(f"Reading {label} score data: {score_field}...")
    score_df = load_score_data(score_path, score_field)
    df = df.merge(score_df, on=NID10_INT, how="left")
    df["Score"] = df["Score"].fillna(0)

    results = []
    for _, row in plan_df.iterrows():
        shengcode = row["Shengcode"]

        prov_targets = [row[col] for col in PROVINCE_PLAN_COLS]
        print(f"\nProvince: {shengcode} | {label} Province targets (10,000 kW): {prov_targets}")
        df_prov = plan_install_multiyear(df, shengcode, prov_targets, PROV_YEAR_COLS)

        lc_targets = [row[col] for col in LOWCARBON_PLAN_COLS]
        print(f"Province: {shengcode} | {label} LowCarbon targets (10,000 kW): {lc_targets}")
        df_lc = plan_install_multiyear(df, shengcode, lc_targets, LC_YEAR_COLS)

        if not df_prov.empty and not df_lc.empty:
            for col in LC_YEAR_COLS:
                df_prov[col] = df_lc[col].values
        results.append(df_prov)

    return results


def run_allocation(energy_type="wind"):
    """
    energy_type: 'wind' or 'solar'
    """
    print(f"\n{'='*60}")
    print(f"  Starting allocation: {energy_type.upper()}")
    print(f"{'='*60}")

    # ---- Read the planning table ----
    sheet = wind_sheetname if energy_type == "wind" else solar_sheetname
    print("Reading the planning table...")
    plan_df = pd.read_excel(planning_path, sheet_name=sheet)

    # ---- Read grid potential + current-installation data ----
    if energy_type == "wind":
        pot_shp = potential_wind_shp
        pot_field = potential_cap_wind
        cur_fc = current_wind_fc
    else:
        pot_shp = potential_solar_shp
        pot_field = potential_cap_solar
        cur_fc = current_solar_fc

    print("Reading grid potential + current-installation data...")
    grid_df = load_grid_data(pot_shp, pot_field, cur_fc)

    results = []
    if energy_type == "wind":
        # Separate onshore/offshore grid cells and use their respective score fields
        onshore_grid = grid_df.loc[grid_df["Shengcode"] != 100].copy()
        offshore_grid = grid_df.loc[grid_df["Shengcode"] == 100].copy()

        onshore_plan = plan_df.loc[plan_df["Shengcode"] != 100].copy()
        offshore_plan = plan_df.loc[plan_df["Shengcode"] == 100].copy()

        if not onshore_plan.empty:
            results.extend(allocate_by_plan(onshore_grid, onshore_plan, onshore_wind_score, "Onshore"))
        else:
            print("  ⚠ No onshore province rows found in the Wind planning table; skipping onshore allocation")

        if not offshore_plan.empty:
            results.extend(allocate_by_plan(offshore_grid, offshore_plan, offshore_wind_score, "Offshore"))
        else:
            print("  ⚠ No offshore row with Shengcode=100 found in the Wind planning table; skipping offshore allocation")
    else:
        results.extend(allocate_by_plan(grid_df, plan_df, onshore_solar_score, "Solar"))

    if not results:
        raise ValueError("没有生成任何分配结果，请检查规划表和网格数据")

    final_df = pd.concat(results, ignore_index=True)

    # ---- Retain only the specified output columns ----
    keep_cols = [c for c in OUTPUT_COLS if c in final_df.columns]
    final_df = final_df[keep_cols]

    # ---- Summary check ----
    print(f"\n{'='*60}")
    print("Allocation result summary (10,000 kW):")
    print(f"{'='*60}")
    summary = final_df.groupby("Shengcode")[ALL_YEAR_COLS].sum() / 10000
    print(summary.to_string())

    total = final_df[ALL_YEAR_COLS].sum() / 10000
    print(f"\nNational total (10,000 kW):")
    for col in ALL_YEAR_COLS:
        print(f"  {col}: {total[col]:.1f}")

    summary_path = os.path.join(
        base_folder,
        rf"processing\tables\{energy_type}_allocation_summary.csv"
    )
    summary.to_csv(summary_path, encoding="utf-8-sig")
    print(f"Provincial summary exported: {summary_path}")

    return final_df


# ============================================================
# 5. Write results back to a shapefile (optional)
# ============================================================
def write_results_to_shp(final_df, output_shp, grid_shp):
    """Join allocation results back to a shapefile and output kw2025 through kw2060."""
    import arcpy
    arcpy.env.overwriteOutput = True

    # Export to CSV first, then join through arcpy
    csv_path = output_shp.replace(".shp", "_result.csv")
    final_df.to_csv(csv_path, index=False)

    # Copy the original shapefile
    arcpy.management.CopyFeatures(grid_shp, output_shp)

    # Delete unnecessary fields, retaining only NID50, NID10_INT, and Shengcode
    keep_fields = {"NID50", NID10_INT, "Shengcode", "cap_kw", "cap_kw_new",
                   "FID", "Shape", "OBJECTID", "OID"}
    all_fields = arcpy.ListFields(output_shp)
    drop_fields = [f.name for f in all_fields
                   if f.name not in keep_fields and f.type not in ("OID", "Geometry")]
    if drop_fields:
        arcpy.management.DeleteField(output_shp, drop_fields)

    # Add year fields and assign values
    for col in ALL_YEAR_COLS:
        arcpy.management.AddField(output_shp, col, "DOUBLE")

    # Write using UpdateCursor (handling potentially duplicate NID10_INT values)
    # Aggregate by NID10_INT (sum duplicate values)
    agg_df = final_df.groupby(NID10_INT)[ALL_YEAR_COLS].sum()
    lookup = agg_df.to_dict("index")

    update_fields = [NID10_INT] + ALL_YEAR_COLS

    with arcpy.da.UpdateCursor(output_shp, update_fields) as cursor:
        for row in cursor:
            nid = row[0]
            if nid in lookup:
                for i, col in enumerate(ALL_YEAR_COLS, start=1):
                    row[i] = lookup[nid][col]
                cursor.updateRow(row)

    print(f"Results written to: {output_shp}")


# ============================================================
# 6. Main entry point
# ============================================================
if __name__ == "__main__":
    # ---- Wind allocation ----
    wind_result = run_allocation("wind")

    # ---- Solar allocation ----
    solar_result = run_allocation("solar")

    # ---- Optional: export results ----
    output_folder = os.path.join(base_folder, r"processing\gisfiles\GridValidArea")

    wind_output = os.path.join(output_folder, "grid10km_wind_planned.shp")
    write_results_to_shp(wind_result, wind_output, potential_wind_shp)

    solar_output = os.path.join(output_folder, "grid10km_solar_planned.shp")
    write_results_to_shp(solar_result, solar_output, potential_solar_shp)

    print("\n✅ All allocations complete!")
