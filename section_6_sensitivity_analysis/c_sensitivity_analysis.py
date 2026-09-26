from pathlib import Path
import arcpy
import pandas as pd
import numpy as np
from scipy.stats import spearmanr
import os

# ============================================================
# Configuration
# ============================================================
base_folder = Path(__file__).resolve().parents[3]
sens_gdb = os.path.join(base_folder, r"processing\arcprojects\MyProject1\sensitivity.gdb")
arcpy.env.workspace = sens_gdb

# Configure according to the scenario fields actually written to sensitivity.gdb
SCENARIOS = {
    "wind_onshore": ["baseline", "resource", "infra", "terrain", "equal"],
    "wind_offshore": ["baseline", "resource", "infra", "equal"],
    "solar": ["baseline", "resource", "infra", "terrain", "equal"],
}

# Three evaluation systems (feature-class prefixes)
SYSTEMS = ["wind_onshore", "wind_offshore", "solar"]

OUT_FOLDER = os.path.join(base_folder, r"processing\tables")


# ============================================================
# Part 1: Inspect the field structure
# ============================================================
def inspect_fields():
    
    print("=== All Feature Classes ===")
    for fc in arcpy.ListFeatureClasses():
        print(" ", fc)

    # Use the first existing feature class as a sample for field inspection
    sample = None
    for sys in SYSTEMS:
        name = f"{sys}_baseline"
        if arcpy.Exists(name):
            sample = name
            break
    if sample:
        print(f"\n=== {sample} Fields ===")
        for f in arcpy.ListFields(sample):
            print(f"  {f.name} | {f.type}")
    return sample


# ============================================================
# Utility: read a feature class into a DataFrame (automatically select existing fields)
# ============================================================
def fc_to_df(fc_name, wanted_fields):
    all_fields = [f.name for f in arcpy.ListFields(fc_name)]
    use = [f for f in wanted_fields if f in all_fields]
    rows = [r for r in arcpy.da.SearchCursor(fc_name, use)]
    return pd.DataFrame(rows, columns=use)


# ============================================================
# Automatically identify yearly allocation columns (prov_2030 / lc_2030, etc.)
# ============================================================
def detect_year_cols(fc_name):
    all_fields = [f.name for f in arcpy.ListFields(fc_name)]
    prov = sorted([f for f in all_fields if f.lower().startswith("prov_")])
    lc   = sorted([f for f in all_fields if f.lower().startswith("lc_")])
    return prov, lc


# ============================================================
# Identify the grid ID column
# ============================================================
def detect_id_field(fc_name):
    
    all_fields = [f.name for f in arcpy.ListFields(fc_name)]
    for cand in ["NID10_INT", "NID10", "NID50", "OBJECTID"]:
        if cand in all_fields:
            return cand
    return "OBJECTID"


# ============================================================
# Compare baseline with a scenario (one province and one year)
# ============================================================
def compare_one(base, scen):
    df = pd.DataFrame({"base": base, "scen": scen}).dropna()
    if len(df) < 5:
        return np.nan, np.nan, np.nan

    if df["base"].nunique() < 2 or df["scen"].nunique() < 2:
        rho = np.nan
    else:
        rho, _ = spearmanr(df["base"], df["scen"])

    base_set = set(df.index[df["base"] > 0])
    scen_set = set(df.index[df["scen"] > 0])
    if len(base_set) == 0:
        return rho, np.nan, np.nan

    overlap = len(base_set & scen_set) / len(base_set)
    union = len(base_set | scen_set)
    jaccard = len(base_set & scen_set) / union if union > 0 else np.nan
    return rho, overlap, jaccard


# ============================================================
# Part 2: Main analysis
# ============================================================
def run_analysis():
    detail_rows = []

    for sys in SYSTEMS:
        base_fc = f"{sys}_baseline"
        if not arcpy.Exists(base_fc):
            print(f"Skipping (does not exist): {base_fc}")
            continue

        id_field = detect_id_field(base_fc)
        prov_cols, lc_cols = detect_year_cols(base_fc)
        plan_sets = {}
        if prov_cols: plan_sets["province"] = prov_cols
        if lc_cols:   plan_sets["low_carbon"] = lc_cols

        if not plan_sets:
            print(f"⚠ No prov_/lc_ year columns found in {base_fc}; skipping. Verify the allocation column names.")
            continue

        # Read the baseline
        base_wanted = [id_field, "Shengcode"] + prov_cols + lc_cols
        base_df = fc_to_df(base_fc, base_wanted).set_index(id_field)

        scenarios_for_sys = SCENARIOS.get(sys, ["baseline"])
        for scen in scenarios_for_sys:
            if scen == "baseline":
                continue
            scen_fc = f"{sys}_{scen}"
            if not arcpy.Exists(scen_fc):
                print(f"Skipping (does not exist): {scen_fc}")
                continue
            scen_df = fc_to_df(scen_fc, base_wanted).set_index(id_field)

            for plan_name, year_cols in plan_sets.items():
                for year_col in year_cols:
                    year = int(''.join(ch for ch in year_col if ch.isdigit()))

                    merged = pd.DataFrame({
                        "Shengcode": base_df["Shengcode"],
                        "base": base_df[year_col],
                        "scen": scen_df[year_col].reindex(base_df.index),
                    })

                    for sheng, g in merged.groupby("Shengcode"):
                        rho, overlap, jac = compare_one(g["base"], g["scen"])
                        if np.isnan(rho) and np.isnan(overlap):
                            continue
                        detail_rows.append({
                            "system": sys,
                            "plan": plan_name,
                            "scenario": scen,
                            "year": year,
                            "Shengcode": sheng,
                            "spearman_rho": rho,
                            "topN_overlap": overlap,
                            "jaccard": jac,
                        })
            print(f"[Complete] {sys} | {scen}")

    detail = pd.DataFrame(detail_rows)
    import os
    os.makedirs(OUT_FOLDER, exist_ok=True)
    detail.to_csv(os.path.join(OUT_FOLDER, "sensitivity_detail.csv"),
                  index=False, encoding="utf-8-sig")

    summary = detail.groupby(
        ["system", "plan", "scenario", "year"]
    ).agg(
        rho_mean=("spearman_rho", "mean"),
        rho_min=("spearman_rho", "min"),
        overlap_mean=("topN_overlap", "mean"),
        overlap_min=("topN_overlap", "min"),
        jaccard_mean=("jaccard", "mean"),
        n_provinces=("Shengcode", "nunique"),
        frac_robust=("spearman_rho", lambda s: (s > 0.9).mean()),
    ).round(4).reset_index()

    summary.to_csv(os.path.join(OUT_FOLDER, "sensitivity_summary.csv"),
                   index=False, encoding="utf-8-sig")

    print("\n===== Summary Results =====")
    print(summary.to_string(index=False))
    print(f"\nDetails: {OUT_FOLDER}\\sensitivity_detail.csv")
    print(f"Summary: {OUT_FOLDER}\\sensitivity_summary.csv")
    return detail, summary


# ============================================================
if __name__ == "__main__":
    sample = inspect_fields()      # Inspect the structure first
    print("\n" + "="*60)
    run_analysis()                 # Then calculate consistency
