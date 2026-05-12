# =============================================================================
# EMPIRICAL QUANTILE MAPPING (EQM) — DAILY BIAS CORRECTION
# Variables : Tmax, Tmin (°C) | Precipitation (mm/day)
# Model     : CMIP6 point data
# Reference : DHM in-situ observed point data
# =============================================================================

# -----------------------------------------------------------------------------
# SECTION 1 — IMPORTS
# -----------------------------------------------------------------------------
import numpy as np
import pandas as pd


# -----------------------------------------------------------------------------
# SECTION 2 — FILE PATHS
# -----------------------------------------------------------------------------

# -- Input: DHM observed files ------------------------------------------------
DHM_TEMP_FILE   = "DHM_temperature.csv"    # contains Tmax and Tmin columns
DHM_PRECIP_FILE = "DHM_precipitation.csv"  # contains Precip column

# -- Input: CMIP6 model files -------------------------------------------------
CMIP6_TEMP_FILE   = "CMIP6_temperature.csv"    # contains Tmax and Tmin columns
CMIP6_PRECIP_FILE = "CMIP6_precipitation.csv"  # contains Precip column

# -- Output: bias-corrected temperature files ---------------------------------
OUT_TEMP_CALIB = "EQM_temperature_calibration.csv"   # corrected 1980–2008
OUT_TEMP_VALID = "EQM_temperature_validation.csv"    # corrected 2009–2024

# -- Output: bias-corrected precipitation files -------------------------------
OUT_PRECIP_CALIB = "EQM_precipitation_calibration.csv"   # corrected 1980–2008
OUT_PRECIP_VALID = "EQM_precipitation_validation.csv"    # corrected 2009–2024


# -----------------------------------------------------------------------------
# SECTION 3 — COLUMN NAMES
# Change these to match the exact column headers in your CSV files
# -----------------------------------------------------------------------------

DATE_COL   = "Date"     # date column name  (must be the same in all 4 files)
TMAX_COL   = "Tmax"     # daily maximum temperature column name
TMIN_COL   = "Tmin"     # daily minimum temperature column name
PRECIP_COL = "Precip"   # daily precipitation column name


# -----------------------------------------------------------------------------
# SECTION 4 — CALIBRATION AND VALIDATION PERIODS
# -----------------------------------------------------------------------------

CALIB_START = "1980-01-01"
CALIB_END   = "2008-12-31"

VALID_START = "2009-01-01"
VALID_END   = "2024-12-31"


# -----------------------------------------------------------------------------
# SECTION 5 — EQM PARAMETERS
# -----------------------------------------------------------------------------

N_QUANTILES   = 100   # number of quantile levels (100 = percentiles 0–100)
WET_THRESHOLD = 0.1   # mm/day — minimum to count as a wet day in DHM obs

# Set True if CMIP6 precipitation is in kg m-2 s-1 (will be × 86400 → mm/day)
CONVERT_PRECIP_UNITS = False


# =============================================================================
# SECTION 6 — EQM CORE FUNCTIONS  (do not edit)
# =============================================================================

def _build_transfer(obs_vals, mod_vals, n_quantiles):
    """
    Sample both distributions at identical probability levels and return
    the paired quantile arrays (mod_q, obs_q) that define the transfer function.

    EQM equation:  x_corrected = F_obs^{-1}( F_mod(x) )
    Implemented by linear interpolation between sampled quantile pairs.
    """
    levels = np.linspace(0.0, 1.0, n_quantiles + 1)
    mod_q  = np.nanquantile(mod_vals, levels)
    obs_q  = np.nanquantile(obs_vals, levels)
    return mod_q, obs_q


def _apply_transfer(x, mod_q, obs_q):
    """
    Map values in x through the EQM transfer function using linear
    interpolation. Values outside the training range are clamped to
    the boundary quantiles (no extrapolation beyond the observed range).
    """
    return np.interp(x, mod_q, obs_q)


# -----------------------------------------------------------------------------

def eqm_temperature(obs_calib, mod_calib, mod_target, n_quantiles=N_QUANTILES):
    """
    Monthly EQM for one temperature variable (Tmax or Tmin).

    A separate transfer function is built for each of the 12 calendar months
    using the calibration data, then applied to every day of that month in
    mod_target.

    Parameters
    ----------
    obs_calib  : pd.Series  Daily observed temperature, calibration period
    mod_calib  : pd.Series  Daily CMIP6 temperature,   calibration period
    mod_target : pd.Series  Daily CMIP6 temperature,   period to correct

    Returns
    -------
    corrected : pd.Series  Bias-corrected daily temperature
    """
    corrected = mod_target.copy().astype(float)

    for month in range(1, 13):
        obs_m = obs_calib[obs_calib.index.month == month].dropna().values
        mod_m = mod_calib[mod_calib.index.month == month].dropna().values

        if len(obs_m) < 10 or len(mod_m) < 10:
            print(f"    Month {month:02d}: insufficient calibration data — skipped.")
            continue

        n_q = min(n_quantiles, len(obs_m) - 1, len(mod_m) - 1)
        mod_q, obs_q = _build_transfer(obs_m, mod_m, n_q)

        tgt_idx  = mod_target.index[mod_target.index.month == month]
        tgt_vals = mod_target.loc[tgt_idx].values.astype(float)

        valid  = ~np.isnan(tgt_vals)
        result = np.full(len(tgt_vals), np.nan)
        if np.any(valid):
            result[valid] = _apply_transfer(tgt_vals[valid], mod_q, obs_q)

        corrected.loc[tgt_idx] = result

    return corrected


# -----------------------------------------------------------------------------

def eqm_precipitation(obs_calib, mod_calib, mod_target,
                       n_quantiles=N_QUANTILES, wet_threshold=WET_THRESHOLD):
    """
    Monthly EQM for precipitation with wet-day frequency correction.

    Per calendar month:
      Step 1 — Wet-day frequency correction
               obs wet-day fraction: f = mean(obs_calib > wet_threshold)
               model wet-day threshold: mod_wet_thr = Q_mod_calib(1 - f)
               target days ≤ mod_wet_thr are classified as dry (set to 0).

      Step 2 — Build EQM transfer function on wet-day amounts only.

      Step 3 — Apply transfer function to wet days in mod_target.
               Corrected values are clipped to ≥ 0.

    Parameters
    ----------
    obs_calib     : pd.Series  Daily observed precipitation, calibration period
    mod_calib     : pd.Series  Daily CMIP6 precipitation,   calibration period
    mod_target    : pd.Series  Daily CMIP6 precipitation,   period to correct
    wet_threshold : float      mm/day threshold for a wet day in observed data

    Returns
    -------
    corrected : pd.Series  Bias-corrected daily precipitation (mm/day)
    """
    corrected = pd.Series(
        np.zeros(len(mod_target), dtype=float),
        index=mod_target.index,
        name=mod_target.name
    )

    for month in range(1, 13):
        obs_m = obs_calib[obs_calib.index.month == month].dropna().values
        mod_m = mod_calib[mod_calib.index.month == month].dropna().values

        tgt_idx  = mod_target.index[
            (mod_target.index.month == month) & (~mod_target.isna())
        ]
        tgt_vals = mod_target.loc[tgt_idx].values.astype(float)

        if len(obs_m) == 0 or len(mod_m) == 0 or len(tgt_vals) == 0:
            continue

        # Step 1 — wet-day frequency correction
        obs_wet_frac = np.mean(obs_m > wet_threshold)
        if obs_wet_frac == 0.0:
            corrected.loc[tgt_idx] = 0.0
            continue

        mod_wet_thr = float(np.quantile(mod_m, max(0.0, 1.0 - obs_wet_frac)))
        mod_wet_thr = max(mod_wet_thr, 0.0)

        # Step 2 — build transfer function on wet-day amounts only
        obs_wet = obs_m[obs_m > wet_threshold]
        mod_wet = mod_m[mod_m > mod_wet_thr]

        if len(obs_wet) < 2 or len(mod_wet) < 2:
            print(f"    Month {month:02d}: insufficient wet-day data — skipped.")
            continue

        n_q = min(n_quantiles, len(obs_wet) - 1, len(mod_wet) - 1)
        mod_q, obs_q = _build_transfer(obs_wet, mod_wet, n_q)

        # Step 3 — apply to target wet days
        result   = np.zeros(len(tgt_vals), dtype=float)
        wet_mask = tgt_vals > mod_wet_thr
        if np.any(wet_mask):
            result[wet_mask] = np.maximum(
                _apply_transfer(tgt_vals[wet_mask], mod_q, obs_q), 0.0
            )

        corrected.loc[tgt_idx] = result

    return corrected


# =============================================================================
# SECTION 7 — VALIDATION STATISTICS FUNCTION  (do not edit)
# =============================================================================

def validation_stats(obs, bc, raw, var_name):
    """
    Print a comparison table: DHM observed vs raw CMIP6 vs EQM-corrected CMIP6
    over the shared validation period.

    Metrics: Mean, Std Dev, RMSE, Bias, Pearson correlation (r).
    """
    common = obs.index.intersection(bc.index).intersection(raw.index)
    aligned = pd.concat(
        [obs.loc[common], bc.loc[common], raw.loc[common]], axis=1
    ).dropna()
    o = aligned.iloc[:, 0].values
    b = aligned.iloc[:, 1].values
    r = aligned.iloc[:, 2].values

    rmse = lambda p: np.sqrt(np.mean((p - o) ** 2))
    corr = lambda p: np.corrcoef(p, o)[0, 1]

    print(f"\n  {var_name}")
    print(f"  {'Metric':<26} {'Observed':>12} {'Raw CMIP6':>12} {'EQM corrected':>14}")
    print(f"  {'-' * 66}")
    print(f"  {'Mean':<26} {o.mean():>12.3f} {r.mean():>12.3f} {b.mean():>14.3f}")
    print(f"  {'Std Dev':<26} {o.std():>12.3f} {r.std():>12.3f} {b.std():>14.3f}")
    print(f"  {'RMSE vs Observed':<26} {'—':>12} {rmse(r):>12.3f} {rmse(b):>14.3f}")
    print(f"  {'Bias vs Observed':<26} {'—':>12} {r.mean()-o.mean():>12.3f} {b.mean()-o.mean():>14.3f}")
    print(f"  {'Correlation r':<26} {'—':>12} {corr(r):>12.3f} {corr(b):>14.3f}")


# =============================================================================
# SECTION 8 — LOAD DATA  (runs automatically — no edits needed)
# =============================================================================

print("=" * 60)
print("Loading data ...")
print("=" * 60)

dhm_temp_df    = pd.read_csv(DHM_TEMP_FILE,    parse_dates=[DATE_COL], index_col=DATE_COL)
dhm_precip_df  = pd.read_csv(DHM_PRECIP_FILE,  parse_dates=[DATE_COL], index_col=DATE_COL)
cmip6_temp_df  = pd.read_csv(CMIP6_TEMP_FILE,  parse_dates=[DATE_COL], index_col=DATE_COL)
cmip6_precip_df= pd.read_csv(CMIP6_PRECIP_FILE,parse_dates=[DATE_COL], index_col=DATE_COL)

if CONVERT_PRECIP_UNITS:
    cmip6_precip_df[PRECIP_COL] = cmip6_precip_df[PRECIP_COL] * 86400
    print("  Precipitation converted: kg m-2 s-1 → mm/day")

print(f"\n  DHM temperature   : {dhm_temp_df.index.min().date()} → {dhm_temp_df.index.max().date()}  ({len(dhm_temp_df):,} rows)")
print(f"  DHM precipitation : {dhm_precip_df.index.min().date()} → {dhm_precip_df.index.max().date()}  ({len(dhm_precip_df):,} rows)")
print(f"  CMIP6 temperature : {cmip6_temp_df.index.min().date()} → {cmip6_temp_df.index.max().date()}  ({len(cmip6_temp_df):,} rows)")
print(f"  CMIP6 precipitation: {cmip6_precip_df.index.min().date()} → {cmip6_precip_df.index.max().date()}  ({len(cmip6_precip_df):,} rows)")


# =============================================================================
# SECTION 9 — SLICE CALIBRATION AND VALIDATION PERIODS
# =============================================================================

# -- Temperature slices -------------------------------------------------------
dhm_temp_calib   = dhm_temp_df.loc[CALIB_START:CALIB_END]
dhm_temp_valid   = dhm_temp_df.loc[VALID_START:VALID_END]
cmip6_temp_calib = cmip6_temp_df.loc[CALIB_START:CALIB_END]
cmip6_temp_valid = cmip6_temp_df.loc[VALID_START:VALID_END]

# -- Precipitation slices -----------------------------------------------------
dhm_precip_calib   = dhm_precip_df.loc[CALIB_START:CALIB_END]
dhm_precip_valid   = dhm_precip_df.loc[VALID_START:VALID_END]
cmip6_precip_calib = cmip6_precip_df.loc[CALIB_START:CALIB_END]
cmip6_precip_valid = cmip6_precip_df.loc[VALID_START:VALID_END]

print(f"\n  Calibration period : {CALIB_START} → {CALIB_END}")
print(f"  Validation period  : {VALID_START} → {VALID_END}")


# =============================================================================
# SECTION 10 — TEMPERATURE BIAS CORRECTION
# =============================================================================

print("\n" + "=" * 60)
print("TEMPERATURE — EQM Bias Correction")
print("=" * 60)

# -- Calibration period -------------------------------------------------------
print("\n  Calibration (1980–2008):")
print("    Tmax ...")
bc_temp_calib_tmax = eqm_temperature(
    dhm_temp_calib[TMAX_COL],
    cmip6_temp_calib[TMAX_COL],
    cmip6_temp_calib[TMAX_COL]      # target = calibration period itself
)

print("    Tmin ...")
bc_temp_calib_tmin = eqm_temperature(
    dhm_temp_calib[TMIN_COL],
    cmip6_temp_calib[TMIN_COL],
    cmip6_temp_calib[TMIN_COL]
)

bc_temp_calib_df = pd.DataFrame({
    "Tmax_EQM": bc_temp_calib_tmax,
    "Tmin_EQM": bc_temp_calib_tmin
})

# -- Validation period --------------------------------------------------------
print("\n  Validation (2009–2024):")
print("    Tmax ...")
bc_temp_valid_tmax = eqm_temperature(
    dhm_temp_calib[TMAX_COL],       # transfer function built on calibration
    cmip6_temp_calib[TMAX_COL],
    cmip6_temp_valid[TMAX_COL]      # applied to validation period
)

print("    Tmin ...")
bc_temp_valid_tmin = eqm_temperature(
    dhm_temp_calib[TMIN_COL],
    cmip6_temp_calib[TMIN_COL],
    cmip6_temp_valid[TMIN_COL]
)

bc_temp_valid_df = pd.DataFrame({
    "Tmax_EQM": bc_temp_valid_tmax,
    "Tmin_EQM": bc_temp_valid_tmin
})


# =============================================================================
# SECTION 11 — PRECIPITATION BIAS CORRECTION
# =============================================================================

print("\n" + "=" * 60)
print("PRECIPITATION — EQM Bias Correction")
print("=" * 60)

# -- Calibration period -------------------------------------------------------
print("\n  Calibration (1980–2008):")
bc_precip_calib = eqm_precipitation(
    dhm_precip_calib[PRECIP_COL],
    cmip6_precip_calib[PRECIP_COL],
    cmip6_precip_calib[PRECIP_COL]  # target = calibration period itself
)

bc_precip_calib_df = pd.DataFrame({"Precip_EQM": bc_precip_calib})

# -- Validation period --------------------------------------------------------
print("\n  Validation (2009–2024):")
bc_precip_valid = eqm_precipitation(
    dhm_precip_calib[PRECIP_COL],   # transfer function built on calibration
    cmip6_precip_calib[PRECIP_COL],
    cmip6_precip_valid[PRECIP_COL]  # applied to validation period
)

bc_precip_valid_df = pd.DataFrame({"Precip_EQM": bc_precip_valid})


# =============================================================================
# SECTION 12 — VALIDATION STATISTICS
# =============================================================================

print("\n" + "=" * 60)
print("VALIDATION STATISTICS  (2009–2024)")
print("DHM observed  vs  raw CMIP6  vs  EQM-corrected CMIP6")
print("=" * 60)

validation_stats(
    dhm_temp_valid[TMAX_COL],
    bc_temp_valid_df["Tmax_EQM"],
    cmip6_temp_valid[TMAX_COL],
    "Tmax (°C)"
)

validation_stats(
    dhm_temp_valid[TMIN_COL],
    bc_temp_valid_df["Tmin_EQM"],
    cmip6_temp_valid[TMIN_COL],
    "Tmin (°C)"
)

validation_stats(
    dhm_precip_valid[PRECIP_COL],
    bc_precip_valid_df["Precip_EQM"],
    cmip6_precip_valid[PRECIP_COL],
    "Precipitation (mm/day)"
)


# =============================================================================
# SECTION 13 — SAVE OUTPUT FILES
# =============================================================================

bc_temp_calib_df.to_csv(OUT_TEMP_CALIB)
bc_temp_valid_df.to_csv(OUT_TEMP_VALID)
bc_precip_calib_df.to_csv(OUT_PRECIP_CALIB)
bc_precip_valid_df.to_csv(OUT_PRECIP_VALID)

print("\n" + "=" * 60)
print("Output files saved:")
print(f"  {OUT_TEMP_CALIB}")
print(f"  {OUT_TEMP_VALID}")
print(f"  {OUT_PRECIP_CALIB}")
print(f"  {OUT_PRECIP_VALID}")
print("=" * 60)
